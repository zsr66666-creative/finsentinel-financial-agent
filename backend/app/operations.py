"""Read-only, fail-closed public operations summary. Never execute maintenance."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

LABELS = {key: key.replace('_', ' ').title() for key in ('nginx','backend','frontend','ingestion_worker','query_encoder','renewal_timer','backup_timer','restore_timer','renewal','database','https_health','https_login','https_static','encoder_health','disk','certificate','backup','restore')}
REASONS = frozenset(('check_passed','check_failed','check_timeout','not_configured','never_completed','backup_aging','backup_expired','restore_aging','certificate_expiring','certificate_urgent','disk_low','disk_critical','task_failed','status_missing','status_invalid','status_stale'))
STATUSES = frozenset(('ok','warning','critical','unknown'))

def stamp(): return datetime.now(timezone.utc).isoformat()
def parsed_time(value):
    value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None: raise ValueError('timezone required')
    return value

def summary(reason, status='unknown'):
    return dict(schema_version=1, checked_at=stamp(), status=status, checks=[dict(id='status', label='Operations status', status=status, reason=reason, checked_at=stamp(), duration_ms=0)], history=[])

def read_status(path=None, *, enforce_fresh=True):
    path=Path(path or os.getenv('OPERATIONS_STATUS_FILE','/var/lib/finsentinel/operations/status.json'))
    try:
        if any(parent.is_symlink() for parent in (path,*path.parents)): return summary('status_invalid')
        if not path.exists(): return summary('status_missing')
        if path.stat().st_size > 262144: return summary('status_invalid')
        data=json.loads(path.read_text(encoding='utf-8'))
        if type(data.get('schema_version')) is not int or data['schema_version']!=1 or data['status'] not in STATUSES: raise ValueError()
        checked=parsed_time(data['checked_at'])
        age=(datetime.now(timezone.utc)-checked).total_seconds()
        if age < -60: raise ValueError()
        if age>900 and enforce_fresh: return summary('status_stale','critical')
        if not isinstance(data['checks'],list) or len(data['checks'])>len(LABELS) or not isinstance(data['history'],list) or len(data['history'])>200: raise ValueError()
        checks=[]; history=[]; seen=set()
        for row in data['checks']:
            key=row['id']
            if key not in LABELS or key in seen or row['status'] not in STATUSES or row['reason'] not in REASONS: raise ValueError()
            seen.add(key); check_age=(datetime.now(timezone.utc)-parsed_time(row['checked_at'])).total_seconds()
            if check_age < -60: raise ValueError()
            if check_age>900 and enforce_fresh: return summary('status_stale','critical')
            duration=row['duration_ms']
            if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<=duration<=120000: raise ValueError()
            checks.append(dict(id=key,label=LABELS[key],status=row['status'],reason=row['reason'],checked_at=row['checked_at'],duration_ms=duration))
            clean=checks[-1]
            if key in ('backup','restore') and 'last_success_at' in row:
                when=parsed_time(row['last_success_at'])
                if (when-datetime.now(timezone.utc)).total_seconds()>60: raise ValueError()
                clean['last_success_at']=when.astimezone(timezone.utc).isoformat()
            if key=='certificate' and 'expires_at' in row:
                clean['expires_at']=parsed_time(row['expires_at']).astimezone(timezone.utc).isoformat()
            if key=='disk' and ('free_bytes' in row or 'total_bytes' in row):
                free,total=row['free_bytes'],row['total_bytes']
                if type(free) is not int or type(total) is not int or not 0<=free<=total or total<=0: raise ValueError()
                clean.update(free_bytes=free,total_bytes=total)
        for row in data['history'][-200:]:
            if row['check_id'] not in LABELS or row['status'] not in STATUSES or row['reason'] not in REASONS: raise ValueError()
            parsed_time(row['at'])
            history.append({k:row[k] for k in ('at','check_id','status','reason')})
        if seen!=set(LABELS): return summary('status_invalid')
        status=aggregate(checks)
        return dict(schema_version=1,checked_at=data['checked_at'],status=status,checks=checks,history=history)
    except (OSError,ValueError,TypeError,KeyError,AttributeError): return summary('status_invalid')

def aggregate(checks):
    statuses={row['status'] for row in checks}
    return next((s for s in ('critical','unknown','warning') if s in statuses),'ok')

def build_router():
    router=APIRouter()
    @router.get('/api/v1/admin/operations')
    def operations(request:Request):
        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
        if not getattr(request.app.state,'auth_enabled',False): return JSONResponse({'detail':'authentication_required'},status_code=401,headers=headers)
        session=getattr(request.state,'session',None)
        if not session: return JSONResponse({'detail':'authentication_required'},status_code=401,headers=headers)
        if session.get('user',{}).get('role')!='admin': return JSONResponse({'detail':'admin_required'},status_code=403,headers=headers)
        return JSONResponse(read_status(),headers=headers)
    return router
