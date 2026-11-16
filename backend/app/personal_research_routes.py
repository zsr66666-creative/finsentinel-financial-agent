"""HTTP boundary: owner identity comes exclusively from authenticated session."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from app.personal_research import ResearchLibrary

class Payload(BaseModel):model_config=ConfigDict(extra='forbid')
class Favorite(Payload):
    kind:Literal['company','evidence']
    company_code:str=Field(min_length=1,max_length=100)
    period:str|None=Field(default=None,max_length=40)
    chunk_id:str|None=Field(default=None,max_length=200)
    note:str|None=Field(default=None,max_length=1000)
class Note(Payload):note:str=Field(max_length=1000)
class History(Payload):
    kind:Literal['search','compare']
    company_code:str|None=Field(default=None,min_length=1,max_length=100)
    period:str|None=Field(default=None,max_length=40)
    query:str=Field(min_length=1,max_length=1000)

def wire_personal_research(app,store):
    service=ResearchLibrary(store);router=APIRouter(prefix='/api/v1/me/research')
    def owner(request):
        session=getattr(request.state,'session',None)
        if not app.state.auth_enabled or not session:raise HTTPException(401,'authentication_required')
        return session['user']['id']
    def run(operation):
        try:return operation()
        except ValueError as exc:raise HTTPException(404 if str(exc)=='not_found' else 409 if str(exc)=='favorites_limit' else 422,str(exc)) from exc
        except SQLAlchemyError as exc:raise HTTPException(503,'research_store_unavailable') from exc
    @router.get('/favorites')
    def listing(request:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),kind:Literal['company','evidence']|None=None,company_code:str|None=Query(None,max_length=100),period:str|None=Query(None,max_length=40),chunk_id:str|None=Query(None,max_length=200)):
        user=owner(request);return run(lambda:service.listing(user,offset=offset,limit=limit,kind=kind,company_code=company_code,period=period,chunk_id=chunk_id))
    @router.post('/favorites')
    def favorite(body:Favorite,request:Request):
        user=owner(request);return run(lambda:service.favorite(user,**body.model_dump()))
    @router.post('/favorites/{ident}/note')
    def note(ident:str,body:Note,request:Request):
        user=owner(request);return run(lambda:service.note(user,ident,body.note))
    @router.delete('/favorites/{ident}',status_code=204)
    def remove(ident:str,request:Request):
        user=owner(request);run(lambda:service.remove(user,ident));return Response(status_code=204)
    @router.get('/history')
    def listing_history(request:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100)):
        user=owner(request);return run(lambda:service.listing(user,history=True,offset=offset,limit=limit))
    @router.post('/history')
    def record(body:History,request:Request):
        user=owner(request);return run(lambda:service.record(user,**body.model_dump()))
    @router.delete('/history',status_code=204)
    def clear(request:Request):
        user=owner(request);run(lambda:service.clear(user));return Response(status_code=204)
    @router.delete('/history/{ident}',status_code=204)
    def remove_history(ident:str,request:Request):
        user=owner(request);run(lambda:service.remove(user,ident,history_record=True));return Response(status_code=204)
    app.include_router(router)
