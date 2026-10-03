"""VECTORone HTTP application using native MongoDB transactions."""

import datetime,hashlib,html,json,pathlib

from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler

from http.cookies import SimpleCookie

from urllib.parse import urlparse,quote

from pymongo.errors import DuplicateKeyError,PyMongoError

import access,accounting,manufacturing,seed
import company as company_config
import store_ops

from storage import MongoStore,identifier



ROOT=pathlib.Path(__file__).parent

STORE=None



def initialize(migrate_local=True, demo=False):

    global STORE

    if STORE is None:STORE=MongoStore()

    STORE.prepare()

    local=ROOT/'data'/'erp.db'

    if migrate_local and local.exists() and not STORE.run(lambda c:c.one('settings')):

        from migrate_to_mongo import migrate

        migrate(local,STORE)

    STORE.run(lambda c:seed.initialize(c,demo=demo))



def log(c,message):c.insert('activity',message=message,date=datetime.datetime.now().isoformat(timespec='seconds'))

def required(d,key):

    v=str(d.get(key,'')).strip()

    if not v:raise ValueError(f'{key.replace("_"," ").title()} is required')

    return v

def number(d,key,minimum=0,integer=False):

    v=float(required(d,key))

    if not __import__('math').isfinite(v) or v<minimum or (integer and v!=int(v)):raise ValueError(f'Invalid {key}')

    return int(v) if integer else v

def product(c,d):

    pid=identifier(d.get('product_id'))

    if not c.one('products',{'id':pid}):raise ValueError('Product not found')

    return pid



def read_api(c,path,cookie):

    user=access.current(c,cookie)

    if path=='/api/auth/session':return {'user':user,'setup_required':False if user else not bool(c.one('users'))}

    if not user:raise access.AccessError('Please sign in to continue',401)

    company_config.guard(c,path)

    if path.startswith('/api/documents/'):

        doc=c.one('job_documents',{'id':identifier(path.rsplit('/',1)[-1])})

        if not doc:raise access.AccessError('Document not found',404)

        manufacturing.get_job(c,doc['job_id'],user)

        return {'_download':doc}

    if path=='/api/state':

        role=user['role']
        tables=['products']
        if role in ('Admin','Accounts'):tables+=['orders','activity']
        if role in ('Admin','Store'):tables+=['movements']
        if role in ('Admin','Store','Accounts'):tables+=['purchases']
        if role=='Admin':tables+=['jobs']
        data={t:[] for t in ('products','orders','movements','activity','purchases','jobs','accounts','journals','journal_lines','invoice_items','settlements')}
        for t in tables:data[t]=c.all(t,sort=[('id',-1)])

        data['settings']={r['key']:r['value'] for r in c.all('settings')}

        if role in ('Admin','Accounts'):accounting.state(c,data)
        manufacturing.state(c,data,user)
        workspace=data['settings'].get('workspace')
        access.filter_state(c,data,user)

        data['workspace']=workspace or company_config.get(c)

        data['templates']=company_config.TEMPLATES if user['role']=='Admin' else {}

        data['store_documents']=c.all('store_documents',sort=[('id',-1)]) if role in ('Admin','Store') else []
        data['database']={'engine':'MongoDB','name':STORE.database}

        return data

    if path=='/api/export/tally':

        access.require(user,('Accounts',))

        company=c.one('settings',{'key':'tally_company'})['value'];vouchers=[]

        for r in c.all('orders',sort=[('id',1)]):

            customer=html.escape(r['customer']);amount=f"{r['total']:.2f}"

            vouchers.append(f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Accounting Voucher View"><DATE>{r["date"].replace("-","")}</DATE><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME><VOUCHERNUMBER>TPPL-{r["id"]:04}</VOUCHERNUMBER><PARTYLEDGERNAME>{customer}</PARTYLEDGERNAME><PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><ALLLEDGERENTRIES.LIST><LEDGERNAME>{customer}</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-{amount}</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Sales</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{amount}</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER></TALLYMESSAGE>')

        return {'_xml':'<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>'+html.escape(company)+'</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA>'+''.join(vouchers)+'</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>'}

    raise access.AccessError('Endpoint not found',404)



def write_api(c,path,d,cookie,ip):

    user=access.current(c,cookie)

    if path in ('/api/auth/setup','/api/auth/login'):

        if path=='/api/auth/setup':

            if c.one('users'):raise access.AccessError('Initial setup is already complete')

            access.create_user(c,{**d,'role':'Admin'})

        signed,token,error=access.login(c,d,ip)

        if error:return {'error':error,'_status':401}
        portal=d.get('portal')
        if (portal=='admin' and signed['role']!='Admin') or (portal=='user' and signed['role']=='Admin'):
            c.delete('sessions',{'token_hash':hashlib.sha256(token.encode()).hexdigest()})
            return {'error':'Use the Admin panel for Admin accounts and the User portal for department accounts.','_status':403}

        return {'user':signed,'_cookie':'tppl_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'}

    if not user:raise access.AccessError('Please sign in to continue',401)

    if path=='/api/auth/logout':

        cookies=SimpleCookie();cookies.load(cookie or '')

        if 'tppl_session' in cookies:c.delete('sessions',{'token_hash':hashlib.sha256(cookies['tppl_session'].value.encode()).hexdigest()})

        return {'ok':True,'_cookie':'tppl_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'}

    if path=='/api/auth/password':

        u=c.one('users',{'id':user['id']})

        if not access.verify(d.get('current_password'),u['password_hash']):raise ValueError('Current password is incorrect')

        c.update('users',{'id':user['id']},{'password_hash':access.password_hash(d.get('password'))});c.delete('sessions',{'user_id':user['id']})

        return {'ok':True}

    if path=='/api/users':access.require(user)

    elif path=='/api/store-documents':access.require(user,('Store',))
    elif path.startswith('/api/work/'):access.require(user,('Design','Machining','Fabrication','Store'))

    else:access.require(user,access.PERMISSIONS.get(path.removeprefix('/api/'),()))

    c.update('settings',{'key':'company'},inc={'_revision':1})

    company_config.guard(c,path)

    if d.get('request_id'):

        token=str(user['id'])+':'+required(d,'request_id')

        if c.one('requests',{'token':token}):return {'ok':True,'duplicate':True}

        c.insert('requests',token=token)

    work={'create':manufacturing.create,'attach':manufacturing.attach,'requirement':manufacturing.requirement,'transition':manufacturing.transition,'issue':manufacturing.issue}

    if path=='/api/users':access.manage_user(c,d,user);log(c,'User access updated by '+user['name'])

    elif path.startswith('/api/work/') and path.split('/')[-1] in work:work[path.split('/')[-1]](c,d,user)

    elif path=='/api/store-documents':store_ops.save(c,d,user)
    elif path=='/api/accounts':accounting.create_account(c,d);log(c,'Account created: '+d['name'])

    elif path=='/api/settlements':accounting.settle(c,d);log(c,'Payment voucher recorded: '+d['reference'])

    elif path=='/api/journals':accounting.manual_journal(c,d);log(c,'Journal voucher recorded: '+d['reference'])

    elif path in ('/api/invoices','/api/orders'):

        oid=accounting.create_invoice(c,d);log(c,f'Sales invoice INV-{oid:04} posted to ledger')

    elif path=='/api/purchases':

        supplier=required(d,'supplier');aid=accounting.party(c,supplier,'Supplier')

        c.insert('purchases',supplier=supplier,product_id=product(c,d),quantity=number(d,'quantity',1,True),unit_cost=accounting.cents(number(d,'unit_cost'))/100,status='Ordered',date=datetime.date.today().isoformat(),account_id=aid)

        log(c,'Purchase order raised for '+supplier)

    elif path=='/api/receive':

        p=c.one('purchases',{'id':identifier(d.get('id')),'status':'Ordered'})

        if not p:raise ValueError('Open purchase order not found')

        c.update('purchases',{'id':p['id']},{'status':'Received'});c.update('products',{'id':p['product_id']},inc={'stock':p['quantity']})

        c.insert('movements',product_id=p['product_id'],quantity=p['quantity'],reason='Goods receipt PO-'+str(p['id']),date=datetime.date.today().isoformat())

        accounting.post_purchase(c,p['id']);log(c,'Goods received against PO-'+str(p['id']))

    elif path=='/api/jobs':

        c.insert('jobs',name=required(d,'name'),customer=required(d,'customer'),product_id=product(c,d),quantity=number(d,'quantity',1,True),due=datetime.date.fromisoformat(required(d,'due')).isoformat(),status='Planned');log(c,'Fabrication job planned: '+d['name'])

    elif path=='/api/job-action':

        j=c.one('jobs',{'id':identifier(d.get('id'))})

        if not j:raise ValueError('Job not found')

        if j['status']=='Planned':

            if not c.update('products',{'id':j['product_id'],'stock':{'$gte':j['quantity']}},inc={'stock':-j['quantity']}):raise ValueError('Insufficient material to start this job')

            c.insert('movements',product_id=j['product_id'],quantity=-j['quantity'],reason='Material issued to job '+j['name'],date=datetime.date.today().isoformat());status='In progress'

        elif j['status']=='In progress':status='Completed'

        else:raise ValueError('Job already completed')

        c.update('jobs',{'id':j['id']},{'status':status});log(c,j['name']+': '+status)

    elif path=='/api/company':

        company_config.save(c,d);log(c,'Company configuration updated by '+user['name'])

    elif path=='/api/products':

        details=company_config.product_details(c,d)

        c.insert('products',name=required(d,'name'),sku=required(d,'sku'),category=required(d,'category'),warehouse=required(d,'warehouse'),stock=number(d,'stock',integer=True),minimum=number(d,'minimum',integer=True),price=number(d,'price'),**details);log(c,'Added inventory item: '+d['name'])

    elif path=='/api/stock':

        pid=product(c,d);qty=number(d,'quantity',1,True);c.update('products',{'id':pid},inc={'stock':qty})

        c.insert('movements',product_id=pid,quantity=qty,reason=required(d,'reason'),date=datetime.date.today().isoformat());log(c,f'Received {qty} units into inventory')

    elif path=='/api/pay':

        o=c.one('orders',{'id':identifier(d.get('id'))})

        if not o:raise ValueError('Invoice not found')

        paid=sum(s['amount'] for s in c.all('settlements',{'order_id':o['id']}))

        accounting.settle(c,{'account_id':o['account_id'],'money_account_id':accounting.system(c,'Main bank'),'order_id':o['id'],'amount':(accounting.cents(o['total'])-paid)/100,'reference':'Receipt INV-'+str(o['id'])});log(c,'Payment recorded for order TPPL-'+str(d['id']))

    elif path=='/api/settings':

        for key in ('company','tally_company','tally_url'):c.update('settings',{'key':key},{'value':required(d,key)})

        log(c,'Company and integration settings updated')

    else:raise access.AccessError('Endpoint not found',404)

    return {'ok':True}



class Handler(SimpleHTTPRequestHandler):

    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'public'),**kwargs)

    def reply(self,data,status=200,content_type='application/json',cookie=None):

        payload=json.dumps(data).encode() if content_type=='application/json' else data.encode()

        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')

        if cookie:self.send_header('Set-Cookie',cookie)

        self.end_headers();self.wfile.write(payload)

    def failure(self,error):

        if isinstance(error,access.AccessError):return self.reply({'error':str(error)},error.status)

        if isinstance(error,DuplicateKeyError):return self.reply({'error':'That name, SKU, or reference already exists.'},400)

        if isinstance(error,(ValueError,TypeError)):return self.reply({'error':str(error)},400)

        if isinstance(error,PyMongoError):return self.reply({'error':'Database connection unavailable. No success has been confirmed; retry the same request after reconnecting.'},503)

        self.log_error('Request failed (%s)',type(error).__name__)

        return self.reply({'error':'Unexpected server error'},500)

    def do_GET(self):

        path=urlparse(self.path).path

        if path.rstrip('/') in ('/admin','/user'):
            self.path='/index.html'
            return super().do_GET()
        if not path.startswith('/api/'):return super().do_GET()

        try:

            result=STORE.run(lambda c:read_api(c,path,self.headers.get('Cookie')))

            if '_download' in result:

                doc=result['_download'];self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(doc['name']));self.send_header('Content-Length',str(len(doc['content'])));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(doc['content']);return

            if '_xml' in result:return self.reply(result['_xml'],content_type='application/xml')

            return self.reply(result)

        except Exception as e:return self.failure(e)

    def do_POST(self):

        try:

            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON requests are required')

            origin=self.headers.get('Origin')

            if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise access.AccessError('Cross-site requests are not allowed')

            length=int(self.headers.get('Content-Length',0))

            if not 0<length<=8*1024*1024:raise ValueError('Invalid request size (maximum document size is 3 MB)')

            d=json.loads(self.rfile.read(length))

            if not isinstance(d,dict):raise ValueError('Expected a JSON object')

            result=STORE.run(lambda c:write_api(c,urlparse(self.path).path,d,self.headers.get('Cookie'),self.client_address[0]))

            cookie=result.pop('_cookie',None);status=result.pop('_status',200)

            return self.reply(result,status,cookie=cookie)

        except Exception as e:return self.failure(e)



if __name__=='__main__':

    # Reserve the port first: do not migrate while the previous local server runs.

    try:http=ThreadingHTTPServer(('127.0.0.1',8000),Handler)

    except OSError:

        print('Port 8000 is in use. Stop the previous VECTORone server before switching databases.',flush=True)

        raise SystemExit(1)

    try:initialize()

    except (PyMongoError,ValueError) as e:

        http.server_close()

        print('Database startup failed ('+type(e).__name__+'). Check private MongoDB configuration and Atlas network access. Credentials were not logged.',flush=True)

        raise SystemExit(1)

    print('VECTORone running at http://localhost:8000 — MongoDB database '+STORE.database,flush=True)

    http.serve_forever()
