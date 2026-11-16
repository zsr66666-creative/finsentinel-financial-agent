import base64
import hashlib
import hmac
import io
import re
import secrets
import time
from contextlib import contextmanager
from uuid import uuid4
from sqlalchemy import MetaData, Table, Column, String, Boolean, Float, Text, ForeignKey, select, text, inspect, func

metadata = MetaData()
users = Table('account_users', metadata, Column('id',String(36),primary_key=True), Column('username',String(32),unique=True,nullable=False), Column('nickname',String(24),nullable=False), Column('avatar',Text), Column('role',String(10),nullable=False), Column('enabled',Boolean,nullable=False), Column('must_change_password',Boolean,nullable=False), Column('password_hash',Text,nullable=False))
sessions = Table('account_sessions',metadata,Column('token_hash',String(64),primary_key=True),Column('user_id',String(36),ForeignKey('account_users.id'),nullable=False),Column('csrf_token',String(100),nullable=False),Column('issued_at',Float,nullable=False),Column('expires_at',Float,nullable=False))
audit = Table('account_audit',metadata,Column('id',String(36),primary_key=True),Column('actor_id',String(36)),Column('target_id',String(36),nullable=False),Column('action',String(80),nullable=False),Column('created_at',Float,nullable=False))

def hash_password(password):
    if not isinstance(password,str) or not 12 <= len(password) <= 128: raise ValueError('password_length')
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return 'scrypt$v1$16384$8$1$'+salt.hex()+'$'+digest.hex()

def verify_password(password, encoded):
    try:
        if not isinstance(password,str) or len(password)>128: return False
        algorithm,version,n,r,p,salt,digest=encoded.split('$')
        if (algorithm,version,n,r,p)!=('scrypt','v1','16384','8','1'): return False
        result=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=int(n),r=int(r),p=int(p),dklen=32)
        return hmac.compare_digest(result,bytes.fromhex(digest))
    except (ValueError,TypeError): return False

DUMMY_HASH=hash_password('dummy unknown account password')

def migrate_accounts(engine):
    from app.migrations import _ensure_version_table
    with engine.begin() as c:
        if engine.dialect.name=='postgresql': c.execute(text('SELECT pg_advisory_xact_lock(572016)'))
        _ensure_version_table(c)
        exists=c.execute(text("SELECT 1 FROM schema_migrations WHERE name='006_accounts'")).first()
        names=set(inspect(c).get_table_names())
        required=set(metadata.tables)
        if exists:
            if not required.issubset(names): raise ValueError('accounts_schema_mismatch')
            return []
        if required & names: raise ValueError('unversioned_accounts_tables')
        metadata.create_all(c)
        c.execute(text('INSERT INTO schema_migrations(name,applied_at) VALUES (:n,:t)'),{'n':'006_accounts','t':str(time.time())})
    return ['006_accounts']

def public_user(row): return {k:row[k] for k in ('id','username','nickname','avatar','role','enabled','must_change_password')}

def safe_avatar(value):
    if value is None: return None
    if not isinstance(value,str) or len(value)>1400000: raise ValueError('invalid_avatar')
    try:
        from PIL import Image
        header,data=value.split(',',1)
        if header not in ('data:image/png;base64','data:image/jpeg;base64','data:image/webp;base64'): raise ValueError()
        raw=base64.b64decode(data,validate=True)
        if len(raw)>1000000: raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>4000000: raise ValueError()
            image.load(); image.thumbnail((256,256)); converted=image.convert('RGBA')
            out=io.BytesIO();converted.save(out,format='PNG')
            return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
    except Exception as exc: raise ValueError('invalid_avatar') from exc

class Accounts:
    def __init__(self,engine): self.engine=engine
    @contextmanager
    def transaction(self):
        with self.engine.connect() as c:
            try:
                if self.engine.dialect.name=='sqlite': c.exec_driver_sql('BEGIN IMMEDIATE')
                elif self.engine.dialect.name=='postgresql': c.execute(text('SELECT pg_advisory_xact_lock(572016)'))
                else: raise ValueError('unsupported_database')
                yield c
                c.commit()
            except Exception:
                c.rollback(); raise
    def authorize_actor(self,c,actor_id,token,admin=False):
        # None is reserved for trusted CLI/direct-service callers; HTTP always supplies its cookie.
        if token is None:return
        row=c.execute(select(users).join(sessions,sessions.c.user_id==users.c.id).where(users.c.id==actor_id,users.c.enabled==True,sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest(),sessions.c.expires_at>time.time())).mappings().first()
        if not row:raise ValueError('authentication_required')
        if admin and (row['role']!='admin' or row['must_change_password']):raise ValueError('admin_required')
        return row
    def log(self,c,actor,target,action): c.execute(audit.insert().values(id=str(uuid4()),actor_id=actor,target_id=target,action=action,created_at=time.time()))
    def create_user(self,username,password,role,nickname,actor_id=None,bootstrap_only=False,session_token=None):
        if not re.fullmatch('[a-z0-9_]{3,32}',username): raise ValueError('invalid_username')
        if role not in ('viewer','reviewer','admin'): raise ValueError('invalid_role')
        if not isinstance(nickname,str) or not 1<=len(nickname.strip())<=24: raise ValueError('invalid_nickname')
        row=dict(id=str(uuid4()),username=username,nickname=nickname.strip(),avatar=None,role=role,enabled=True,must_change_password=True,password_hash=hash_password(password))
        with self.transaction() as c:
            self.authorize_actor(c,actor_id,session_token,admin=True)
            if bootstrap_only and c.execute(select(users.c.id).where(users.c.enabled==True,users.c.role=='admin')).first(): return None
            if c.execute(select(users.c.id).where(users.c.username==username)).first(): raise ValueError('username_exists')
            c.execute(users.insert().values(**row));self.log(c,actor_id,row['id'],'create')
        return public_user(row)
    def update_user(self,user_id,changes,actor_id,session_token=None):
        changes=dict(changes)
        if 'role' in changes and changes['role'] not in ('viewer','reviewer','admin'): raise ValueError('invalid_role')
        if 'password' in changes: changes['password_hash']=hash_password(changes.pop('password'));changes['must_change_password']=True
        with self.transaction() as c:
            self.authorize_actor(c,actor_id,session_token,admin=True)
            row=c.execute(select(users).where(users.c.id==user_id)).mappings().first()
            if not row: raise ValueError('user_not_found')
            result=dict(row,**changes)
            if row['enabled'] and row['role']=='admin' and (not result['enabled'] or result['role']!='admin'):
                count=c.execute(select(func.count()).select_from(users).where(users.c.enabled==True,users.c.role=='admin')).scalar()
                if count<=1: raise ValueError('last_admin')
            c.execute(users.update().where(users.c.id==user_id).values(**changes)); c.execute(sessions.delete().where(sessions.c.user_id==user_id))
            self.log(c,actor_id,user_id,'update:'+','.join(sorted(k for k in changes if k!='password_hash')))
        return public_user(result)
    def login(self,username,password):
        with self.transaction() as c:
            row=c.execute(select(users).where(users.c.username==username)).mappings().first()
            valid=verify_password(password,row['password_hash'] if row else DUMMY_HASH)
            if not valid or not row or not row['enabled']: return None
            token=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32);now=time.time()
            c.execute(sessions.delete().where(sessions.c.expires_at<=now))
            c.execute(sessions.insert().values(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=row['id'],csrf_token=csrf,issued_at=now,expires_at=now+28800))
            return token,{'user':public_user(row),'csrf_token':csrf}
    def session(self,token):
        if not token or len(token)>200: return None
        with self.engine.connect() as c:
            row=c.execute(select(users,sessions.c.csrf_token).join(sessions,sessions.c.user_id==users.c.id).where(sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest(),sessions.c.expires_at>time.time(),users.c.enabled==True)).mappings().first()
            return {'user':public_user(row),'csrf_token':row['csrf_token']} if row else None
    def logout(self,token):
        with self.engine.begin() as c: c.execute(sessions.delete().where(sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    def password(self,user_id,current,new,session_token=None):
        encoded=hash_password(new)
        with self.transaction() as c:
            self.authorize_actor(c,user_id,session_token)
            row=c.execute(select(users).where(users.c.id==user_id)).mappings().one()
            if not verify_password(current,row['password_hash']): raise ValueError('current_password_invalid')
            if verify_password(new,row['password_hash']): raise ValueError('password_unchanged')
            c.execute(users.update().where(users.c.id==user_id).values(password_hash=encoded,must_change_password=False))
            c.execute(sessions.delete().where(sessions.c.user_id==user_id));self.log(c,user_id,user_id,'password_change')
    def profile(self,user_id,nickname,avatar,session_token=None):
        if not 1<=len(nickname.strip())<=24: raise ValueError('invalid_nickname')
        image=safe_avatar(avatar)
        with self.transaction() as c:
            self.authorize_actor(c,user_id,session_token)
            c.execute(users.update().where(users.c.id==user_id).values(nickname=nickname.strip(),avatar=image))
            row=c.execute(select(users).where(users.c.id==user_id)).mappings().one()
        return public_user(row)
    def list_users(self):
        with self.engine.connect() as c:return [public_user(r) for r in c.execute(select(users).order_by(users.c.username)).mappings()]
