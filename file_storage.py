"""Optional immutable document storage on a company-owned drive or HTTPS server.

MongoDB stores a small reference in place of each binary field. Database rollback
may leave an unreferenced file, but never removes a previously committed file.
"""
import hashlib,json,os,re,ssl,tempfile,uuid
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler,HTTPSHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError

FIELDS={'job_documents':'content','report_workbooks':'source','dispatch_archives':'content','project_delete_parts':'content'}
MAX_BYTES=3*1024*1024

class StorageError(ValueError):pass

def digest(data):return hashlib.sha256(data).hexdigest()
def valid_key(key):
    if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key):raise StorageError('Invalid file reference')
    return key
def reference(store_id,data):return {'_grey_file':1,'store_id':store_id,'key':digest(data),'size':len(data)}
def is_reference(value):return isinstance(value,dict) and value.get('_grey_file')==1
def checked(ref,data,store_id):
    if ref.get('store_id')!=store_id or len(data)!=ref.get('size') or digest(data)!=ref.get('key'):raise StorageError('Stored file integrity check failed; no database data was removed')
    return data

class DiskStore:
    def __init__(self,root,store_id):
        self.root=Path(root).resolve();self.store_id=store_id
    @staticmethod
    def initialize(root):
        path=Path(root).resolve();path.mkdir(parents=True,exist_ok=True)
        marker=path/'.grey-store.json'
        if marker.exists():return json.loads(marker.read_text(encoding='utf-8'))['store_id']
        if any(path.iterdir()):raise StorageError('Initialize a new empty folder on the external drive')
        sid=uuid.uuid4().hex
        with marker.open('x',encoding='utf-8') as f:json.dump({'store_id':sid},f);f.flush();os.fsync(f.fileno())
        return sid
    def health(self):
        try:actual=json.loads((self.root/'.grey-store.json').read_text(encoding='utf-8'))['store_id']
        except (OSError,ValueError,KeyError):raise StorageError('Company file drive is unavailable or not initialized') from None
        if actual!=self.store_id:raise StorageError('Wrong company file drive; check the configured storage identity')
        return {'store_id':actual}
    def path(self,key):
        self.health();key=valid_key(key);path=self.root/key[:2]/key
        if not path.resolve().is_relative_to(self.root):raise StorageError('Invalid storage path')
        return path
    def get(self,ref):
        try:
            with self.path(ref['key']).open('rb') as f:return checked(ref,f.read(MAX_BYTES+1),self.store_id)
        except OSError:raise StorageError('Company file unavailable; reconnect the file server or restore its backup') from None
    def put(self,data):
        if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:raise StorageError('Invalid stored file size')
        ref=reference(self.store_id,data);path=self.path(ref['key'])
        try:
            if path.exists():self.get(ref);return ref
            path.parent.mkdir(exist_ok=True)
            fd,name=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
            try:
                with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
                os.replace(name,path)
            finally:
                if os.path.exists(name):os.unlink(name)
            self.get(ref)
            return ref
        except OSError:raise StorageError('Could not write to company file drive; original data is unchanged') from None

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):raise StorageError('File server redirects are not allowed')

class RemoteStore:
    def __init__(self,url,token,store_id,ca_file=None):
        parts=urlsplit(url)
        if parts.scheme!='https' and not (parts.scheme=='http' and parts.hostname in ('127.0.0.1','localhost','::1')):raise StorageError('Use HTTPS for the company file server')
        if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('','/'):raise StorageError('Use only the file server origin URL')
        if len(token)<32 or not store_id:raise StorageError('Configure the private file server key and storage identity')
        self.url=url.rstrip('/');self.token=token;self.store_id=store_id
        self.opener=build_opener(NoRedirect,HTTPSHandler(context=ssl.create_default_context(cafile=ca_file or None)))
    def request(self,path,data=None):
        try:
            req=Request(self.url+path,data=data,method='PUT' if data is not None else 'GET',headers={'Authorization':'Bearer '+self.token,'X-Store-ID':self.store_id,'Content-Type':'application/octet-stream'})
            with self.opener.open(req,timeout=8) as r:
                result=r.read(MAX_BYTES+1)
                if len(result)>MAX_BYTES:raise StorageError('Invalid file server response')
                return result
        except StorageError:raise
        except HTTPError as error:
            error.close()
            raise StorageError('Company file server rejected the request. Check the private key, drive and connection.') from None
        except Exception:raise StorageError('Company file server unavailable. Check power, connection and private server settings.') from None
    def health(self):
        result=json.loads(self.request('/health'))
        if result.get('store_id')!=self.store_id:raise StorageError('Wrong company file server')
        return result
    def get(self,ref):
        if ref.get('store_id')!=self.store_id:raise StorageError('File belongs to a different storage drive')
        return checked(ref,self.request('/files/'+valid_key(ref['key'])),self.store_id)
    def put(self,data):
        if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:raise StorageError('Invalid stored file size')
        ref=reference(self.store_id,data)
        result=json.loads(self.request('/files/'+ref['key'],data))
        if result!=ref:raise StorageError('File server did not confirm the saved file')
        self.get(ref) # Verify original bytes before replacing MongoDB's copy.
        return ref

def configuration():
    values={};path=Path(__file__).with_name('.env')
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                k,v=line.split('=',1);values[k.strip()]=v.strip().strip('"').strip("'")
    values.update(os.environ);return values

def configured(values=None):
    v=configuration() if values is None else values;mode=v.get('FILE_STORAGE_MODE','mongo')
    if mode=='mongo':return None
    if mode=='disk':
        if v.get('VERCEL'):raise StorageError('Vercel cannot use a local disk. Configure the HTTPS file server.')
        if not v.get('FILE_STORAGE_ROOT') or not v.get('FILE_STORAGE_ID'):raise StorageError('Configure company file drive and storage identity')
        return DiskStore(v['FILE_STORAGE_ROOT'],v['FILE_STORAGE_ID'])
    if mode=='remote':return RemoteStore(v.get('FILE_STORAGE_URL',''),v.get('FILE_STORAGE_TOKEN',''),v.get('FILE_STORAGE_ID',''),v.get('FILE_STORAGE_CA_FILE'))
    raise StorageError('Invalid file storage mode')

def pack(collection,values,store):
    result=dict(values);field=FIELDS.get(collection)
    if store and field and isinstance(result.get(field),bytes):result[field]=store.put(bytes(result[field]))
    return result

def unpack(collection,doc,store):
    if doc is None:return None
    result=dict(doc);field=FIELDS.get(collection);ref=result.get(field)
    if field and is_reference(ref):
        if store is None:raise StorageError('Reconnect the configured company file server to open this file')
        result[field]=store.get(ref)
    return result
