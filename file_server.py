"""Company laptop file service. No MongoDB credentials or public file links."""
import argparse,hmac,json,os,ssl
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from file_storage import DiskStore,StorageError,MAX_BYTES,valid_key,digest

def make_server(address,store,token):
    if len(token)<32:raise ValueError('FILE_STORAGE_TOKEN must contain at least 32 characters')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(15)
        def log_message(self,*args):pass # Do not log credentials or customer document identifiers.
        def reply(self,status,data):
            raw=data if isinstance(data,bytes) else json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type','application/octet-stream' if isinstance(data,bytes) else 'application/json')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        def allowed(self):
            if not hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+token).encode()):self.reply(401,{'error':'Unauthorized'});return False
            if self.headers.get('X-Store-ID')!=store.store_id:self.reply(409,{'error':'Wrong storage identity'});return False
            return True
        def do_GET(self):
            if not self.allowed():return
            try:
                if self.path=='/health':return self.reply(200,store.health())
                if not self.path.startswith('/files/'):return self.reply(404,{'error':'Not found'})
                key=valid_key(self.path.removeprefix('/files/'));path=store.path(key)
                with path.open('rb') as f:data=f.read(MAX_BYTES+1)
                if len(data)>MAX_BYTES or digest(data)!=key:raise StorageError('File integrity check failed')
                self.reply(200,data)
            except (ValueError,OSError):self.reply(503,{'error':'File drive unavailable or file invalid'})
        def do_PUT(self):
            if not self.allowed():return
            try:
                if not self.path.startswith('/files/'):return self.reply(404,{'error':'Not found'})
                key=valid_key(self.path.removeprefix('/files/'));size=int(self.headers.get('Content-Length','0'))
                if self.headers.get('Transfer-Encoding') or not 0<size<=MAX_BYTES:raise ValueError('Invalid size')
                data=self.rfile.read(size)
                if len(data)!=size or digest(data)!=key:raise ValueError('Invalid content')
                self.reply(200,store.put(data))
            except (ValueError,OSError):self.reply(503,{'error':'File not saved; check drive and request'})
    return ThreadingHTTPServer(address,Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['init','serve']);parser.add_argument('--root',required=True);parser.add_argument('--config',default='.env.file-server');parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8090)
    args=parser.parse_args()
    if args.action=='init':print('FILE_STORAGE_ID='+DiskStore.initialize(args.root));return
    values={};path=Path(args.config)
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                k,v=line.split('=',1);values[k.strip()]=v.strip().strip('"').strip("'")
    values.update(os.environ);cert=values.get('FILE_SERVER_CERT');key=values.get('FILE_SERVER_KEY')
    if args.host not in ('127.0.0.1','localhost','::1') and not (cert and key):parser.error('LAN listeners require a TLS certificate and key; otherwise use a reverse proxy to the loopback listener')
    store=DiskStore(args.root,values.get('FILE_STORAGE_ID',''));server=make_server((args.host,args.port),store,values.get('FILE_STORAGE_TOKEN',''))
    if cert and key:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
    print('Company file server started. Keep this device powered on. Press Ctrl+C to stop.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
