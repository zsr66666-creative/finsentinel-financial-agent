import socket
import pytest
from app.ingestion.source_policy import resolve_source, DownloadError, download_pdf

URL='https://static.cninfo.com.cn/a.pdf'

def test_resolved_address_is_pinned_and_private_answers_rejected(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])
    assert resolve_source(URL)==('static.cninfo.com.cn','8.8.8.8')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    with pytest.raises(DownloadError):resolve_source(URL)

class Response:
    def __init__(self,status=200,headers=None,chunks=None):
        self.status=status; self.headers=headers or {}; self.chunks=iter(chunks or [b'%PDF-1.7\n'])
    def read1(self,n):return next(self.chunks,b'')
    def close(self):pass

def test_redirect_escape_and_missing_location_leave_no_file(tmp_path):
    for headers in ({},{'Location':'https://evil.test/a.pdf'}):
        with pytest.raises(DownloadError):
            download_pdf(URL,tmp_path/'x.pdf',transport=lambda *a:Response(302,headers))
        assert not (tmp_path/'x.pdf').exists()

def test_success_metadata_size_and_magic(tmp_path):
    result=download_pdf(URL,tmp_path/'x.pdf',transport=lambda *a:Response())
    assert result['bytes']==9 and len(result['sha256'])==64
    for chunks in ([b'html'],[b'%PDF-'+b'x'*20]):
        with pytest.raises(DownloadError):
            download_pdf(URL,tmp_path/'bad.pdf',max_bytes=10,transport=lambda *a:Response(chunks=chunks))
        assert not (tmp_path/'bad.pdf').exists()

def test_deadline_and_error_classification(tmp_path):
    ticks=iter([0,0,121])
    with pytest.raises(DownloadError) as error:
        download_pdf(URL,tmp_path/'x',clock=lambda:next(ticks),transport=lambda *a:Response())
    assert error.value.retryable
    for status,retryable in [(404,False),(429,True),(503,True)]:
        with pytest.raises(DownloadError) as error:
            download_pdf(URL,tmp_path/'x',transport=lambda *a:Response(status))
        assert error.value.retryable is retryable

def test_transport_pins_ip_preserving_sni_host_and_tls(monkeypatch):
    from app.ingestion.source_policy import open_pinned
    import ssl
    captured={}
    monkeypatch.setattr('app.ingestion.source_policy.resolve_source',lambda u:('static.cninfo.com.cn','8.8.8.8'))
    class Pool:
        def __init__(self,ip,**kwargs):captured.update(ip=ip,**kwargs)
        def urlopen(self,method,path,**kwargs):
            captured.update(request=kwargs,path=path); return Response()
        def close(self):pass
    monkeypatch.setattr('app.ingestion.source_policy.urllib3.HTTPSConnectionPool',Pool)
    response=open_pinned(URL,100); response.close()
    assert captured['ip']=='8.8.8.8'
    assert captured['server_hostname']==captured['assert_hostname']=='static.cninfo.com.cn'
    assert captured['ssl_context'].verify_mode==ssl.CERT_REQUIRED
    assert captured['request']['headers']['Host']=='static.cninfo.com.cn'
    assert captured['request']['retries'] is False and captured['request']['redirect'] is False

def test_safe_redirect_revalidates_and_closes(tmp_path):
    calls=[]
    def transport(url,remaining):
        calls.append(url)
        return Response(302,{'Location':'/b.pdf'}) if len(calls)==1 else Response()
    result=download_pdf(URL,tmp_path/'x',transport=transport)
    assert result['final_url']=='https://static.cninfo.com.cn/b.pdf'
    assert len(calls)==2

@pytest.mark.parametrize('headers',[{'Content-Length':'999999999'}, {'Content-Length':'bad'},
    {'Content-Encoding':'gzip'}, {'Content-Length':'100'}])
def test_bad_headers_or_truncated_payload_not_published(tmp_path,headers):
    with pytest.raises(DownloadError):
        download_pdf(URL,tmp_path/'x',transport=lambda *a:Response(headers=headers))
    assert not (tmp_path/'x').exists()
    assert not list(tmp_path.glob('.download-*'))

def test_tls_failure_not_retryable(tmp_path):
    import ssl
    def transport(*args):raise ssl.SSLError('private diagnostic')
    with pytest.raises(DownloadError) as error:download_pdf(URL,tmp_path/'x',transport=transport)
    assert error.value.code=='tls_failed' and not error.value.retryable
    assert 'diagnostic' not in str(error.value)
