"""Session-only private report boundary; existing auth middleware enforces CSRF."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from app.saved_reports import SavedReports, SourceUnavailable

class CreateReport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_code:Literal['002555','002230']
    period:Literal['2024FY']='2024FY'
    statement_scope:Literal['consolidated']='consolidated'
    title:str=Field(min_length=1,max_length=120)
    question:str|None=Field(default=None,max_length=1000)
    @field_validator('title','question')
    @classmethod
    def printable(cls,value):
        if value is not None and any(ord(c)<32 and c not in '\n\r\t' for c in value):raise ValueError('printable_text_required')
        return value
    @field_validator('title')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('title_required')
        return value.strip()


def wire_saved_reports(app,store):
    service=SavedReports(store);router=APIRouter(prefix='/api/v1/me/research/reports')
    def owner(request):
        session=getattr(request.state,'session',None)
        if not app.state.auth_enabled or not session:raise HTTPException(401,'authentication_required')
        return session['user']['id']
    def run(operation):
        if service.engine is None:raise HTTPException(503,'saved_report_store_unavailable')
        try:return operation()
        except SourceUnavailable as exc:raise HTTPException(503,'saved_report_source_unavailable') from exc
        except ValueError as exc:
            code=str(exc)
            if code not in ('not_found','authentication_required','saved_reports_limit','saved_report_snapshot_too_large','unsupported_saved_report_scope','invalid_saved_report_text','invalid_pagination'):code='invalid_saved_report'
            raise HTTPException(404 if code=='not_found' else 401 if code=='authentication_required' else 409 if code=='saved_reports_limit' else 422,code) from exc
        except SQLAlchemyError as exc:raise HTTPException(503,'saved_report_store_unavailable') from exc
    @router.get('')
    def listing(request:Request,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100)):
        user=owner(request);return run(lambda:service.listing(user,offset,limit))
    @router.post('',status_code=201)
    def create(body:CreateReport,request:Request):
        user=owner(request);return run(lambda:service.create(user,**body.model_dump()))
    @router.get('/{ident}')
    def detail(ident:UUID,request:Request):
        user=owner(request);return run(lambda:service.detail(user,str(ident)))
    @router.delete('/{ident}',status_code=204)
    def remove(ident:UUID,request:Request):
        user=owner(request);run(lambda:service.remove(user,str(ident)));return Response(status_code=204)
    @router.get('/{ident}/export')
    def export(ident:UUID,request:Request,format:Literal['json','markdown']='json'):
        user=owner(request);body=run(lambda:service.export(user,str(ident),format))
        extension='json' if format=='json' else 'md'
        return Response(body,media_type='application/json' if format=='json' else 'text/markdown',headers={'Content-Disposition':f'attachment; filename="finsentinel-saved-{ident}.{extension}"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    app.include_router(router)
