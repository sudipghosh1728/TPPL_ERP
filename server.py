import json, sqlite3, pathlib, datetime, csv, io, html
import accounting
import access, manufacturing, hashlib
from contextlib import contextmanager
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).parent
DB = ROOT / 'data' / 'erp.db'

@contextmanager
def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:
            yield c
    finally:
        c.close()

def initialize():
    DB.parent.mkdir(exist_ok=True)
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT UNIQUE NOT NULL, category TEXT, warehouse TEXT, stock INTEGER CHECK(stock>=0), minimum INTEGER, price REAL CHECK(price>=0));
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, customer TEXT, product_id INTEGER REFERENCES products(id), quantity INTEGER CHECK(quantity>0), total REAL, status TEXT, date TEXT);
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), quantity INTEGER, reason TEXT, date TEXT);
        CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, message TEXT, date TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY, supplier TEXT, product_id INTEGER REFERENCES products(id), quantity INTEGER CHECK(quantity>0), unit_cost REAL CHECK(unit_cost>=0), status TEXT, date TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, name TEXT, customer TEXT, product_id INTEGER REFERENCES products(id), quantity INTEGER CHECK(quantity>0), due TEXT, status TEXT);
        ''')
        if not c.execute('SELECT 1 FROM settings').fetchone():
            c.executemany('INSERT INTO settings VALUES(?,?)',[('company','TPPL Industries'),('tally_company','TPPL Industries'),('tally_url','http://localhost:9000')])
            c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?,?,?)',[(1,'Industrial steel coils','STL-001','Raw materials','Main warehouse',124,30,18500),(2,'Precision bearing kit','BRG-002','Components','Main warehouse',18,25,2450),(3,'Hydraulic pump assembly','HYD-003','Finished goods','East warehouse',46,15,12800),(4,'Copper wire · 100m','CPR-004','Raw materials','Main warehouse',85,20,6200),(5,'Safety equipment set','SAF-005','Consumables','East warehouse',12,20,1850),(6,'Control panel unit','CTL-006','Finished goods','Main warehouse',32,10,9600)])
            today=datetime.date.today()
            for i in range(18):
                pid=i%6+1; qty=i%4+1; price=c.execute('SELECT price FROM products WHERE id=?',(pid,)).fetchone()[0]
                c.execute('INSERT INTO orders(customer,product_id,quantity,total,status,date) VALUES(?,?,?,?,?,?)',(['Eastern Engineering','Apex Manufacturing','Horizon Projects','Bengal Industrial Co.'][i%4],pid,qty,price*qty,'Paid' if i%3 else 'Pending',(today-datetime.timedelta(days=i*4)).isoformat()))
            log(c,'Demo workspace created. Welcome to TPPL One.')
        if not c.execute("SELECT 1 FROM settings WHERE key='manufacturing_v1'").fetchone():
            c.execute("INSERT INTO settings VALUES('manufacturing_v1','1')")
            c.execute("UPDATE settings SET value='TPPL Fabrication' WHERE key='company'")
            materials=[('MS plate · 20mm','PLT-020','Fabrication raw materials','Raw material yard',124,30,18500,1),('Machining insert · CNMG','MCH-002','Machining supplies','Tool crib',18,25,2450,2),('Structural steel beam','STL-003','Fabrication raw materials','Raw material yard',46,15,12800,3),('Grinding wheel · 7 inch','GRD-004','Grinding supplies','Tool crib',85,20,620,4),('Epoxy primer · 20L','PNT-005','Painting supplies','Paint store',12,20,4850,5),('Welding wire · 15kg','WLD-006','Welding supplies','Consumables store',32,10,3600,6)]
            c.executemany('UPDATE products SET name=?,sku=?,category=?,warehouse=?,stock=?,minimum=?,price=? WHERE id=?',materials)
            c.execute("INSERT INTO purchases(supplier,product_id,quantity,unit_cost,status,date) VALUES('Eastern Steel Traders',1,20,17200,'Ordered',?)",(datetime.date.today().isoformat(),))
            c.execute("INSERT INTO jobs(name,customer,product_id,quantity,due,status) VALUES('Heavy base frame · BF-104','Apex Manufacturing',1,8,?,'Planned')",((datetime.date.today()+datetime.timedelta(days=10)).isoformat(),))
        accounting.initialize(c)
        access.initialize(c)
        manufacturing.initialize(c)

def log(c,message):
    c.execute('INSERT INTO activity(message,date) VALUES(?,?)',(message,datetime.datetime.now().isoformat(timespec='seconds')))

def required(d,key):
    v=str(d.get(key,'')).strip()
    if not v: raise ValueError(f'{key.replace("_"," ").title()} is required')
    return v

def number(d,key,minimum=0,integer=False):
    v=float(required(d,key))
    if not __import__('math').isfinite(v) or v<minimum or (integer and v!=int(v)): raise ValueError(f'Invalid {key}')
    return int(v) if integer else v

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'public'),**kwargs)
    def reply(self,data,status=200,content_type='application/json'):
        payload=json.dumps(data).encode() if content_type=='application/json' else data.encode()
        self.send_response(status); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store')
        if getattr(self,'session_cookie',None):self.send_header('Set-Cookie',self.session_cookie)
        self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        path=urlparse(self.path).path
        if path.startswith('/api/'):
            with connect() as c:
                user=access.current(c,self.headers.get('Cookie'))
                if path=='/api/auth/session':return self.reply({'user':user,'setup_required':not bool(c.execute('SELECT 1 FROM users').fetchone())})
                if not user:return self.reply({'error':'Please sign in to continue'},401)
                if path=='/api/export/tally' and user['role'] not in ('Admin','Accounts'):return self.reply({'error':'Accounts access required'},403)
                if path.startswith('/api/documents/'):
                    try:
                        doc=c.execute('SELECT * FROM job_documents WHERE id=?',(path.rsplit('/',1)[-1],)).fetchone()
                        if not doc:raise access.AccessError('Document not found',404)
                        manufacturing.get_job(c,doc['job_id'],user)
                        from urllib.parse import quote
                        self.send_response(200);self.send_header('Content-Type','application/octet-stream')
                        self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(doc['name']))
                        self.send_header('Content-Length',str(len(doc['content'])));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
                        self.end_headers();self.wfile.write(doc['content']);return
                    except access.AccessError as e:return self.reply({'error':str(e)},e.status)
        if path=='/api/state':
            with connect() as c:
                data={t:[dict(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY id DESC')] for t in ['products','orders','movements','activity','purchases','jobs']}
                data['settings']=dict(c.execute('SELECT key,value FROM settings').fetchall())
                accounting.state(c,data)
                manufacturing.state(c,data,user)
                access.filter_state(c,data,user)
            return self.reply(data)
        if path=='/api/export/tally':
            with connect() as c:
                company=c.execute("SELECT value FROM settings WHERE key='tally_company'").fetchone()[0]
                vouchers=[]
                for r in c.execute('SELECT * FROM orders ORDER BY id'):
                    customer=html.escape(r['customer']); amount=f"{r['total']:.2f}"
                    vouchers.append(f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Accounting Voucher View"><DATE>{r["date"].replace("-","")}</DATE><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME><VOUCHERNUMBER>TPPL-{r["id"]:04}</VOUCHERNUMBER><PARTYLEDGERNAME>{customer}</PARTYLEDGERNAME><PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><ALLLEDGERENTRIES.LIST><LEDGERNAME>{customer}</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-{amount}</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Sales</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{amount}</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER></TALLYMESSAGE>')
            return self.reply('<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>'+html.escape(company)+'</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA>'+''.join(vouchers)+'</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>',content_type='application/xml')
        return super().do_GET()
    def do_POST(self):
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON requests are required')
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise access.AccessError('Cross-site requests are not allowed')
            if int(self.headers.get('Content-Length',0))>8*1024*1024: raise ValueError('Request too large (maximum document size is 5 MB)')
            d=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
            if not isinstance(d,dict): raise ValueError('Expected a JSON object')
            path=urlparse(self.path).path
            with connect() as c:
                c.execute('BEGIN IMMEDIATE')
                user=access.current(c,self.headers.get('Cookie'))
                if path in ('/api/auth/setup','/api/auth/login'):
                    if path=='/api/auth/setup':
                        if c.execute('SELECT 1 FROM users').fetchone():raise access.AccessError('Initial setup is already complete')
                        access.create_user(c,{**d,'role':'Admin'})
                    signed,token,error=access.login(c,d,self.client_address[0])
                    if error:return self.reply({'error':error},401)
                    self.session_cookie='tppl_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'
                    return self.reply({'user':signed})
                if not user:raise access.AccessError('Please sign in to continue',401)
                if path=='/api/auth/logout':
                    from http.cookies import SimpleCookie
                    cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                    if 'tppl_session' in cookie:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(cookie['tppl_session'].value.encode()).hexdigest(),))
                    self.session_cookie='tppl_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                    return self.reply({'ok':True})
                if path=='/api/auth/password':
                    u=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
                    if not access.verify(d.get('current_password'),u['password_hash']):raise ValueError('Current password is incorrect')
                    c.execute('UPDATE users SET password_hash=? WHERE id=?',(access.password_hash(d.get('password')),user['id']))
                    c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
                    return self.reply({'ok':True})
                if path=='/api/users':access.require(user)
                elif path.startswith('/api/work/'):
                    access.require(user,('Design','Machining','Fabrication','Store'))
                else:access.require(user,access.PERMISSIONS.get(path.removeprefix('/api/'),()))
                if d.get('request_id'):
                    token=str(user['id'])+':'+required(d,'request_id')
                    if c.execute('SELECT 1 FROM requests WHERE token=?',(token,)).fetchone():
                        return self.reply({'ok':True,'duplicate':True})
                    c.execute('INSERT INTO requests VALUES(?)',(token,))
                if path=='/api/users':
                    access.manage_user(c,d,user);log(c,'User access updated by '+user['name'])
                elif path=='/api/work/create':manufacturing.create(c,d,user)
                elif path=='/api/work/attach':manufacturing.attach(c,d,user)
                elif path=='/api/work/requirement':manufacturing.requirement(c,d,user)
                elif path=='/api/work/transition':manufacturing.transition(c,d,user)
                elif path=='/api/work/issue':manufacturing.issue(c,d,user)
                elif path=='/api/accounts':
                    accounting.create_account(c,d); log(c,'Account created: '+d['name'])
                elif path=='/api/settlements':
                    accounting.settle(c,d); log(c,'Payment voucher recorded: '+d['reference'])
                elif path=='/api/journals':
                    accounting.manual_journal(c,d); log(c,'Journal voucher recorded: '+d['reference'])
                elif path=='/api/invoices':
                    oid=accounting.create_invoice(c,d); log(c,f'Sales invoice INV-{oid:04} posted to ledger')
                elif path=='/api/purchases':
                    supplier=required(d,'supplier'); aid=accounting.party(c,supplier,'Supplier')
                    c.execute('INSERT INTO purchases(supplier,product_id,quantity,unit_cost,status,date,account_id) VALUES(?,?,?,?,?,?,?)',(supplier,number(d,'product_id',1,True),number(d,'quantity',1,True),accounting.cents(number(d,'unit_cost'))/100,'Ordered',datetime.date.today().isoformat(),aid))
                    log(c,'Purchase order raised for '+d['supplier'])
                elif path=='/api/receive':
                    p=c.execute("SELECT * FROM purchases WHERE id=? AND status='Ordered'",(number(d,'id',1,True),)).fetchone()
                    if not p: raise ValueError('Open purchase order not found')
                    c.execute("UPDATE purchases SET status='Received' WHERE id=?",(p['id'],))
                    c.execute('UPDATE products SET stock=stock+? WHERE id=?',(p['quantity'],p['product_id']))
                    c.execute('INSERT INTO movements(product_id,quantity,reason,date) VALUES(?,?,?,?)',(p['product_id'],p['quantity'],'Goods receipt PO-'+str(p['id']),datetime.date.today().isoformat()))
                    accounting.post_purchase(c,p['id'])
                    log(c,'Goods received against PO-'+str(p['id']))
                elif path=='/api/jobs':
                    due=datetime.date.fromisoformat(required(d,'due')).isoformat()
                    c.execute("INSERT INTO jobs(name,customer,product_id,quantity,due,status) VALUES(?,?,?,?,?,'Planned')",(required(d,'name'),required(d,'customer'),number(d,'product_id',1,True),number(d,'quantity',1,True),due)); log(c,'Fabrication job planned: '+d['name'])
                elif path=='/api/job-action':
                    j=c.execute('SELECT * FROM jobs WHERE id=?',(number(d,'id',1,True),)).fetchone()
                    if not j: raise ValueError('Job not found')
                    if j['status']=='Planned':
                        if not c.execute('UPDATE products SET stock=stock-? WHERE id=? AND stock>=?',(j['quantity'],j['product_id'],j['quantity'])).rowcount: raise ValueError('Insufficient material to start this job')
                        c.execute('INSERT INTO movements(product_id,quantity,reason,date) VALUES(?,?,?,?)',(j['product_id'],-j['quantity'],'Material issued to job '+j['name'],datetime.date.today().isoformat()))
                        status='In progress'
                    elif j['status']=='In progress': status='Completed'
                    else: raise ValueError('Job already completed')
                    c.execute('UPDATE jobs SET status=? WHERE id=?',(status,j['id'])); log(c,j['name']+': '+status)
                elif path=='/api/products':
                    c.execute('INSERT INTO products(name,sku,category,warehouse,stock,minimum,price) VALUES(?,?,?,?,?,?,?)',(required(d,'name'),required(d,'sku'),required(d,'category'),required(d,'warehouse'),number(d,'stock',integer=True),number(d,'minimum',integer=True),number(d,'price')))
                    log(c,'Added inventory item: '+d['name'])
                elif path=='/api/stock':
                    pid=number(d,'product_id',1,True); qty=number(d,'quantity',1,True)
                    if not c.execute('UPDATE products SET stock=stock+? WHERE id=?',(qty,pid)).rowcount: raise ValueError('Product not found')
                    c.execute('INSERT INTO movements(product_id,quantity,reason,date) VALUES(?,?,?,?)',(pid,qty,required(d,'reason'),datetime.date.today().isoformat())); log(c,f'Received {qty} units into inventory')
                elif path=='/api/orders':
                    oid=accounting.create_invoice(c,d); log(c,f'Sales invoice INV-{oid:04} posted to ledger')
                elif path=='/api/pay':
                    o=c.execute('SELECT * FROM orders WHERE id=?',(number(d,'id',1,True),)).fetchone()
                    if not o: raise ValueError('Invoice not found')
                    paid=c.execute('SELECT COALESCE(SUM(amount),0) FROM settlements WHERE order_id=?',(o['id'],)).fetchone()[0]
                    accounting.settle(c,{'account_id':o['account_id'],'money_account_id':accounting.system(c,'Main bank'),'order_id':o['id'],'amount':(accounting.cents(o['total'])-paid)/100,'reference':'Receipt INV-'+str(o['id'])})
                    log(c,'Payment recorded for order TPPL-'+str(d['id']))
                elif path=='/api/settings':
                    for key in ['company','tally_company','tally_url']: c.execute('UPDATE settings SET value=? WHERE key=?',(required(d,key),key))
                    log(c,'Company and integration settings updated')
                else: return self.reply({'error':'Endpoint not found'},404)
            self.reply({'ok':True})
        except access.AccessError as e:self.reply({'error':str(e)},e.status)
        except sqlite3.IntegrityError as e:
            message='That name or SKU already exists. Please use a unique value.' if 'UNIQUE' in str(e) else 'The selected record or value is not valid. Check your entries.'
            self.reply({'error':message},400)
        except (ValueError,TypeError) as e: self.reply({'error':str(e)},400)
        except Exception: self.reply({'error':'Unexpected server error'},500)

if __name__=='__main__':
    initialize()
    print('TPPL One running at http://localhost:8000',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
