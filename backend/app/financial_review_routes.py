"""Public source-bound history/exports; operator-token guarded review writes."""
import os
import secrets
from threading import Lock
from time import monotonic
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from app.financial_reviews import review_state, submit_review, ReviewConflict, ReviewUnavailable
from app.research_export import export_research
from app.verified_financials import company_comparisons, DEFAULT_ARTIFACT_ROOT

class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metric: str = Field(pattern=r'^(revenue|receivables|operating_cash_flow)$')
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_review_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')
    idempotency_key: str = Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')
    decision: str = Field(pattern=r'^(confirmed|rejected|needs_evidence)$')
    reason: str = Field(min_length=3,max_length=1000)
    reviewer: str | None = Field(default=None,min_length=1,max_length=40)
    @field_validator('reason')
    @classmethod
    def reason_length(cls,value):
        if len(value.strip()) < 3: raise ValueError('reason must contain at least 3 characters')
        return value
    @field_validator('reason','reviewer')
    @classmethod
    def not_blank(cls,value):
        if value is None: return value
        if not value.strip() or any(ord(c)<32 and c not in '\n\t\r' for c in value): raise ValueError('nonempty printable text required')
        return value.strip()


def build_review_router(store):
    router = APIRouter(prefix='/api/v1/companies/{company_code}')
    lock = Lock(); writes = []
    def authorize(request: Request, authorization: str | None = Header(default=None)):
        if request.app.state.auth_enabled:
            if request.state.session['user']['role'] not in ('reviewer','admin'): raise HTTPException(403,'reviewer_required')
            return
        expected = os.getenv('FINANCIAL_REVIEW_TOKEN','')
        if len(expected)<32: raise HTTPException(503,'financial_review_writes_disabled')
        if not authorization or not secrets.compare_digest(authorization.encode(), ('Bearer '+expected).encode()):
            raise HTTPException(401,'financial_review_unauthorized')
        with lock:
            now=monotonic();writes[:]=[t for t in writes if now-t<60]
            if len(writes)>=10: raise HTTPException(429,'financial_review_rate_limit')
            writes.append(now)
    def comparison(company_code, period, statement_scope):
        if company_code not in ('002555','002230') or period!='2024FY' or statement_scope!='consolidated':
            raise HTTPException(422,'unsupported_financial_review_scope')
        try:
            return company_comparisons(store.engine,company_code,period,statement_scope,
                os.getenv('INGESTION_ARTIFACT_ROOT', DEFAULT_ARTIFACT_ROOT))
        except Exception as exc: raise HTTPException(503,'financial_source_verification_unavailable') from exc
    def unavailable(exc):
        raise HTTPException(503,'financial_review_store_unavailable') from exc
    @router.get('/financial-reviews')
    def history(company_code: str, period: str='2024FY', statement_scope: str='consolidated'):
        source=comparison(company_code,period,statement_scope)
        try:return review_state(store.engine,source)
        except SQLAlchemyError as exc:unavailable(exc)
    @router.post('/financial-reviews',status_code=201,dependencies=[Depends(authorize)])
    def write(company_code: str, body: ReviewRequest, request: Request, period: str='2024FY', statement_scope: str='consolidated'):
        source=comparison(company_code,period,statement_scope)
        payload=body.model_dump()
        if request.app.state.auth_enabled:
            if 'reviewer' in body.model_fields_set: raise HTTPException(422,'reviewer_must_be_server_bound')
            user=request.state.session['user']
            payload.update(reviewer=user['nickname'],user_id=user['id'],username=user['username'])
        elif not payload['reviewer']: raise HTTPException(422,'reviewer_required')
        try:
            token=request.cookies.get('__Host-finsentinel_session' if os.getenv('AUTH_COOKIE_SECURE','true').lower()=='true' else 'finsentinel_session','') if request.app.state.auth_enabled else None
            return submit_review(store.engine,source,payload,session_token=token)
        except ReviewConflict as exc:raise HTTPException(409,str(exc)) from exc
        except ReviewUnavailable as exc:raise HTTPException(422,str(exc)) from exc
        except SQLAlchemyError as exc:unavailable(exc)
        except ValueError as exc:
            if str(exc) in ('authentication_required','reviewer_required'):raise HTTPException(401 if str(exc)=='authentication_required' else 403,str(exc)) from exc
            raise
    @router.get('/research-report')
    def export(company_code: str, period: str='2024FY', statement_scope: str='consolidated', format: str=Query(default='json',pattern='^(json|markdown)$')):
        source=comparison(company_code,period,statement_scope)
        try:body=export_research(store.engine,source,format)
        except SQLAlchemyError as exc:unavailable(exc)
        extension='json' if format=='json' else 'md'
        return Response(body,media_type='application/json' if format=='json' else 'text/markdown',
            headers={'Content-Disposition':f'attachment; filename="finsentinel-{company_code}-{period}-{statement_scope}.{extension}"',
                     'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    return router
