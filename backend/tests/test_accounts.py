import pytest
from sqlalchemy import create_engine
from app.auth.service import Accounts, migrate_accounts, hash_password, verify_password

def test_password_and_migration(tmp_path):
    encoded = hash_password('long secure password')
    assert verify_password('long secure password', encoded)
    assert not verify_password('wrong password', encoded)
    with pytest.raises(ValueError): hash_password('short')
    engine = create_engine('sqlite:///' + str(tmp_path / 'accounts.db'))
    assert migrate_accounts(engine) == ['006_accounts']
    assert migrate_accounts(engine) == []
    service = Accounts(engine)
    admin = service.create_user('root_admin', 'long secure password', 'admin', 'Root')
    with pytest.raises(ValueError, match='last_admin'): service.update_user(admin['id'], {'enabled': False}, admin['id'])
from concurrent.futures import ThreadPoolExecutor
import base64
import io
import time
from sqlalchemy import select
from app.auth.service import sessions,users,audit,safe_avatar

def test_sessions_revocation_and_identity(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'sessions.db'));migrate_accounts(engine);a=Accounts(engine)
    root=a.create_user('root','temporary password','admin','Root')
    token,envelope=a.login('root','temporary password')
    with engine.connect() as c:
        stored=c.execute(select(sessions)).mappings().one()
        assert stored['token_hash']!=token and stored['expires_at']-stored['issued_at']==28800
        assert token not in str(c.execute(select(audit)).all())
    assert a.session(token)['user']['id']==root['id']
    a.password(root['id'],'temporary password','permanent password')
    assert a.session(token) is None
    token,_=a.login('root','permanent password')
    with engine.begin() as c:c.execute(sessions.update().values(expires_at=time.time()-1))
    assert a.session(token) is None
    viewer=a.create_user('viewer','temporary password','viewer','Viewer')
    token,_=a.login('viewer','temporary password')
    a.update_user(viewer['id'],{'enabled':False},root['id'])
    assert a.session(token) is None and a.login('viewer','temporary password') is None
    assert a.login('missing','temporary password') is None

def test_last_admin_serializes_concurrent_updates(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'concurrent.db'));migrate_accounts(engine);a=Accounts(engine)
    first=a.create_user('first','temporary password','admin','First');second=a.create_user('second','temporary password','admin','Second')
    def disable(user):
        try:a.update_user(user['id'],{'enabled':False},first['id']);return 'ok'
        except ValueError as e:return str(e)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(disable,[first,second]))
    assert sorted(results)==['last_admin','ok']
    assert sum(u['enabled'] and u['role']=='admin' for u in a.list_users())==1

def test_avatar_decode_reencode_and_reject():
    from PIL import Image
    image=Image.new('RGB',(512,512),'red');stream=io.BytesIO();image.save(stream,format='JPEG')
    result=safe_avatar('data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode())
    assert result.startswith('data:image/png;base64,')
    with Image.open(io.BytesIO(base64.b64decode(result.split(',')[1]))) as output:assert output.size==(256,256)
    for value in ('https://example.com/image.png','data:image/svg+xml;base64,PHN2Zz4=','data:image/png;base64,bm90IGltYWdl'):
        with pytest.raises(ValueError,match='invalid_avatar'):safe_avatar(value)

def test_authenticated_review_identity_and_nickname_idempotency(tmp_path):
    from app.financial_reviews import migrate_reviews,submit_review
    from test_task12_reviews import comparison,request
    engine=create_engine('sqlite:///'+str(tmp_path/'identity.db'));migrate_reviews(engine)
    body={**request(),'user_id':'immutable-id','username':'reviewer'}
    record=submit_review(engine,comparison(),body)
    assert record['identity_assurance']=='authenticated_user' and record['user_id']=='immutable-id'
    assert submit_review(engine,comparison(),dict(body,reviewer='Changed nickname'))==record
    from app.financial_reviews import ReviewConflict
    with pytest.raises(ReviewConflict):submit_review(engine,comparison(),dict(body,user_id='different-id'))

def test_stale_admin_snapshot_cannot_mutate_after_revocation(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'stale.db'));migrate_accounts(engine);a=Accounts(engine)
    first=a.create_user('first','temporary password','admin','First');second=a.create_user('second','temporary password','admin','Second')
    token,_=a.login('first','temporary password')
    a.update_user(first['id'],{'role':'viewer'},second['id'])
    with pytest.raises(ValueError,match='authentication_required'):
        a.create_user('forged','temporary password','admin','Forged',actor_id=first['id'],session_token=token)
    with pytest.raises(ValueError,match='authentication_required'):
        a.update_user(second['id'],{'role':'viewer'},first['id'],session_token=token)

def test_review_revalidates_revoked_actor_without_committing(tmp_path):
    from app.financial_reviews import migrate_reviews,submit_review,review_table
    from test_task12_reviews import comparison,request
    engine=create_engine('sqlite:///'+str(tmp_path/'review-revoked.db'));migrate_accounts(engine);migrate_reviews(engine);a=Accounts(engine)
    admin=a.create_user('admin','temporary password','admin','Admin');actor=a.create_user('reviewer','temporary password','reviewer','Reviewer')
    a.password(actor['id'],'temporary password','permanent password');token,_=a.login('reviewer','permanent password')
    a.update_user(actor['id'],{'enabled':False},admin['id'])
    with pytest.raises(ValueError,match='authentication_required'):
        submit_review(engine,comparison(),{**request(),'user_id':actor['id'],'username':'reviewer'},session_token=token)
    with engine.connect() as c:assert c.execute(select(review_table)).first() is None
