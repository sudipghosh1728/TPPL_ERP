import base64, http.cookiejar, json, pathlib, tempfile, threading, unittest, urllib.request, urllib.error
import server
from mongo_test_support import test_store,clean

class DepartmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();server.STORE=test_store();cls.store=server.STORE;server.initialize(migrate_local=False,demo=True)
        class QuietHandler(server.Handler):
            def log_message(self,*args):pass
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.clients={r:urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) for r in ('Admin','Design','Machining','Fabrication','Store','Accounts','Anonymous')}
        cls.password='Department-test-password-123'
        cls.call('Admin','auth/setup',dict(username='admin',name='Admin',password=cls.password))
        for role in ('Design','Machining','Fabrication','Store','Accounts'):
            cls.call('Admin','users',dict(username=role.lower(),name=role+' User',role=role,password=cls.password))
            cls.call(role,'auth/login',dict(username=role.lower(),password=cls.password))
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.temp.cleanup();clean(cls.store)
    @classmethod
    def call(cls,role,path,data=None,headers=None):
        req=urllib.request.Request(cls.url+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with cls.clients[role].open(req) as r:
                payload=r.read()
                return r.status,json.loads(payload) if 'json' in r.headers.get('Content-Type','') else payload
        except urllib.error.HTTPError as e:
            with e:return e.code,json.load(e)
    def state(self,role='Admin'):return self.call(role,'state')[1]
    def job(self,jid):return next(j for j in self.state()['work_jobs'] if j['id']==jid)
    def file(self,name='customer-po.pdf'):return dict(name=name,content=base64.b64encode(b'%PDF-1.4\nTest document only').decode())
    def create(self,title):
        data=dict(title=title,customer='Workflow Customer',po_number='PO-'+title,due='2026-12-31',file=self.file())
        self.assertEqual(self.call('Admin','work/create',data)[0],200)
        return self.state()['work_jobs'][0]['id']
    def change(self,role,jid,action,**kw):
        return self.call(role,'work/transition',dict(job_id=jid,version=self.job(jid)['version'],action=action,notes='Reviewed by '+role,**kw))
    def add_req(self,role,jid,qty=3,tc=False):
        self.assertEqual(self.call(role,'work/requirement',dict(job_id=jid,version=self.job(jid)['version'],product_id=1,quantity=qty,tc_required=tc,tc_notes='Material heat certificate',notes='Plate for base frame'))[0],200)
        return self.state()['requirements'][-1]['id']
    def attach(self,role,jid,kind):
        self.assertEqual(self.call(role,'work/attach',dict(job_id=jid,version=self.job(jid)['version'],kind=kind,file=self.file(kind+'.pdf')))[0],200)
        return self.state()['job_documents'][-1]['id']

    def test_complete_machining_route_and_tc_issue(self):
        jid=self.create('Machining route')
        self.assertEqual(self.state('Machining')['work_jobs'],[])
        self.assertEqual(self.change('Fabrication',jid,'design_approve',machining_required=True)[0],403)
        self.assertEqual(self.change('Design',jid,'design_approve',machining_required=True)[0],400)
        self.attach('Design',jid,'Drawing')
        design_req=self.add_req('Design',jid,1)
        self.assertEqual(self.change('Design',jid,'design_approve',machining_required=True)[0],200)
        self.assertTrue(any(j['id']==jid for j in self.state('Machining')['work_jobs']))
        req=self.add_req('Machining',jid,3,True)
        self.assertEqual(self.change('Machining',jid,'machining_submit')[0],200)
        fabrication_req=self.add_req('Fabrication',jid,2)
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=req,quantity=1,version=self.job(jid)['version']))[0],400)
        self.assertEqual(self.change('Fabrication',jid,'request_changes')[0],200)
        self.assertEqual(self.change('Machining',jid,'machining_submit')[0],200)
        self.assertEqual(self.change('Fabrication',jid,'fabrication_approve')[0],200)
        self.assertEqual(self.job(jid)['stage'],'Machining execution')
        self.assertEqual(self.change('Machining',jid,'machining_complete')[0],400)
        before=next(p['stock'] for p in self.state()['products'] if p['id']==1)
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=req,quantity=1,version=self.job(jid)['version']))[0],400)
        tc=self.attach('Store',jid,'TC')
        payload=dict(requirement_id=req,quantity=1,version=self.job(jid)['version'],tc_document_id=tc,tc_reference='HEAT-001',request_id='issue-once')
        self.assertEqual(self.call('Store','work/issue',payload)[0],200)
        self.assertEqual(self.call('Store','work/issue',payload)[0],200)
        self.assertEqual(next(p['stock'] for p in self.state()['products'] if p['id']==1),before-1)
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=req,quantity=3,version=self.job(jid)['version'],tc_document_id=tc,tc_reference='HEAT-001'))[0],400)
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=req,quantity=2,version=self.job(jid)['version'],tc_document_id=tc,tc_reference='HEAT-001'))[0],200)
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=design_req,quantity=1,version=self.job(jid)['version']))[0],200)
        self.assertEqual(self.change('Machining',jid,'machining_complete')[0],200)
        self.assertEqual(self.change('Fabrication',jid,'fabrication_complete')[0],400)
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=fabrication_req,quantity=2,version=self.job(jid)['version']))[0],200)
        self.assertEqual(self.change('Fabrication',jid,'fabrication_complete')[0],200)
        self.assertEqual(self.job(jid)['stage'],'Completed')
        self.assertEqual(next(p['stock'] for p in self.state()['products'] if p['id']==1),before-6)
        self.assertTrue(any('Fabrication review → Machining execution'==h['action'] for h in self.state()['work_history']))

    def test_nonmachining_is_hidden_and_accounts_are_separate(self):
        jid=self.create('No machining')
        doc=next(d['id'] for d in self.state()['job_documents'] if d['job_id']==jid)
        self.assertEqual(self.change('Design',jid,'design_approve',machining_required=False)[0],200)
        self.assertEqual(self.job(jid)['stage'],'Fabrication review')
        self.assertFalse(any(j['id']==jid for j in self.state('Machining')['work_jobs']))
        self.assertEqual(self.call('Machining',f'documents/{doc}')[0],404)
        self.assertEqual(self.call('Accounts',f'documents/{doc}')[0],404)
        self.assertEqual(self.call('Store',f'documents/{doc}')[0],200)
        self.assertEqual(self.call('Anonymous','state')[0],401)
        for role in ('Design','Machining','Fabrication','Store'):
            state=self.state(role)
            for key in ('accounts','journals','orders','settlements'):self.assertEqual(state[key],[])
            self.assertNotIn('price',state['products'][0])
            self.assertEqual(self.call(role,'journals',{})[0],403)
            self.assertEqual(self.call(role,'users',{})[0],403)
            self.assertEqual(self.call(role,'export/tally')[0],403)
        self.assertEqual(self.state('Accounts')['work_jobs'],[])
        self.assertEqual(self.call('Accounts','work/create',{})[0],403)
        req=self.add_req('Fabrication',jid,1)
        self.assertEqual(self.change('Fabrication',jid,'fabrication_approve')[0],200)
        self.assertEqual(self.job(jid)['stage'],'Fabrication execution')
        self.assertEqual(self.call('Store','work/issue',dict(requirement_id=req,quantity=1,version=self.job(jid)['version']))[0],200)
        self.assertEqual(self.change('Fabrication',jid,'fabrication_complete')[0],200)

    def test_revisions_stale_edits_invalid_files_and_access(self):
        before=len(self.state()['work_jobs'])
        self.assertEqual(self.call('Admin','work/create',dict(title='Invalid',customer='Test',po_number='Test',due='2026-12-31',file=self.file('bad.html')))[0],400)
        self.assertEqual(len(self.state()['work_jobs']),before)
        jid=self.create('Revision test');stale=self.job(jid)['version']
        self.assertEqual(self.change('Design',jid,'return_admin')[0],200)
        self.attach('Admin',jid,'PO')
        self.assertEqual(self.change('Admin',jid,'resubmit')[0],200)
        self.assertEqual(self.call('Design','work/transition',dict(job_id=jid,version=stale,action='design_approve',machining_required=False,notes='Stale review'))[0],400)
        self.assertEqual(self.call('Admin','auth/setup',{})[0],403)
        self.assertEqual(self.call('Admin','accounts',dict(name='Cross site',type='Cash'),{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.call('Admin','users',dict(username='disabledtest',name='Disabled',role='Store',password=self.password))[0],200)
        u=next(u for u in self.state()['users'] if u['username']=='disabledtest')
        self.clients['Disabled']=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.assertEqual(self.call('Disabled','auth/login',dict(username='disabledtest',password=self.password))[0],200)
        self.assertEqual(self.call('Admin','users',dict(id=u['id'],active=0))[0],200)
        self.assertEqual(self.call('Disabled','state')[0],401)
        admin=self.state()['user']
        self.assertEqual(self.call('Admin','users',dict(id=admin['id'],active=0))[0],400)

if __name__=='__main__':unittest.main()
