"""Single-attempt official PDF download; task queue owns retry budgets.

Deadline is checked around blocking operations, not a process-level hard kill.
"""
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
import urllib3

HOSTS=frozenset({'static.cninfo.com.cn','www.cninfo.com.cn','www.sse.com.cn','static.sse.com.cn','disc.static.szse.cn'})

class DownloadError(ValueError):
    def __init__(self,code,retryable=False):
        super().__init__(code); self.code=code; self.retryable=retryable

def check_url(url):
    try:
        p=urlsplit(url)
        if (p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or
            p.port not in (None,443) or p.fragment or '\\' in url or any(ord(c)<33 for c in url)):
            raise ValueError()
    except (ValueError,TypeError):raise DownloadError('invalid_source') from None
    return p

def resolve_source(url):
    p=check_url(url)
    try:answers=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    except OSError:raise DownloadError('dns_failed',True) from None
    addresses=[a[4][0] for a in answers]
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise DownloadError('non_public_address')
    return p.hostname,addresses[0]

class PinnedResponse:
    def __init__(self,pool,response):
        self.pool=pool; self.response=response
        self.status=response.status; self.headers=response.headers
    def read1(self,n):return self.response.read1(n,decode_content=False)
    def close(self):
        self.response.close(); self.pool.close()

def open_pinned(url,remaining):
    host,ip=resolve_source(url)
    # TCP destination is the validated literal IP. SNI, certificate verification
    # and HTTP Host remain the official DNS hostname; no proxy environment used.
    pool=urllib3.HTTPSConnectionPool(ip,port=443,server_hostname=host,
        assert_hostname=host,ssl_context=ssl.create_default_context(),maxsize=1)
    p=urlsplit(url)
    try:
        response=pool.urlopen('GET',p.path+('?' + p.query if p.query else ''),
            headers={'Host':host,'User-Agent':'FinSentinel-research/1.0','Accept-Encoding':'identity'},
            redirect=False,retries=False,preload_content=False,
            timeout=urllib3.Timeout(connect=min(8,remaining),read=min(45,remaining),total=remaining))
        return PinnedResponse(pool,response)
    except Exception:
        pool.close(); raise

def download_pdf(url,destination,*,deadline_seconds=120,max_bytes=32*1024*1024,
                 transport=None,clock=time.monotonic):
    if not 0<deadline_seconds<=120 or not 0<max_bytes<=32*1024*1024:
        raise ValueError('invalid resource limits')
    destination=Path(destination)
    if destination.exists():raise DownloadError('destination_exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    started=clock(); current=url; temp=None
    def remaining():
        value=deadline_seconds-(clock()-started)
        if value<=0:raise DownloadError('download_deadline',True)
        return value
    try:
        for hop in range(4):
            check_url(current)
            response=(transport or open_pinned)(current,remaining())
            try:
                remaining()
                if response.status in (301,302,303,307,308):
                    location=response.headers.get('Location')
                    if not location or hop==3:raise DownloadError('invalid_redirect')
                    current=urljoin(current,location); check_url(current)
                    continue
                if response.status!=200:
                    raise DownloadError('http_error',response.status==429 or 500<=response.status<=599)
                if response.headers.get('Content-Encoding','identity').lower()!='identity':
                    raise DownloadError('encoded_response')
                length=response.headers.get('Content-Length')
                if length is not None and (not length.isdigit() or int(length)>max_bytes):
                    raise DownloadError('invalid_content_length')
                fd,temp=tempfile.mkstemp(prefix='.download-',dir=destination.parent)
                size=0; digest=hashlib.sha256(); prefix=b''
                with os.fdopen(fd,'wb') as output:
                    while True:
                        remaining()
                        chunk=response.read1(64*1024)
                        remaining()
                        if not chunk:break
                        size+=len(chunk)
                        if size>max_bytes:raise DownloadError('pdf_too_large')
                        prefix=(prefix+chunk)[:5]; digest.update(chunk); output.write(chunk)
                if prefix!=b'%PDF-':raise DownloadError('not_pdf')
                if length is not None and size!=int(length):raise DownloadError('truncated_response',True)
                # Full parse validity belongs to the bounded parser worker.
                os.link(temp,destination)  # exclusive publication; never overwrite
                return dict(requested_url=url,final_url=current,acquired_at=datetime.now(timezone.utc).isoformat(),
                    sha256=digest.hexdigest(),bytes=size,path=str(destination))
            finally:response.close()
        raise DownloadError('invalid_redirect')
    except DownloadError:raise
    except (ssl.SSLError,urllib3.exceptions.SSLError):raise DownloadError('tls_failed') from None
    except (OSError,urllib3.exceptions.HTTPError):raise DownloadError('network_failed',True) from None
    finally:
        if temp is not None:Path(temp).unlink(missing_ok=True)
