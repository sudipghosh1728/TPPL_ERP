import base64, io, json, unittest, zipfile
from unittest.mock import patch
import server, seed, project_flow as pf, access
from mongo_test_support import test_store, clean
from send_dispatch_mail import send_next

class PlantProjectsTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(lambda c:seed.initialize(c,demo=True));self.old=server.STORE;server.STORE=self.store
  self.users={r:dict(id=i+1,name=r+' Tester',role=r,username=r.lower(),active=1) for i,r in enumerate(access.ROLES)}
 def tearDown(self):server.STORE=self.old;clean(self.store)
 def file(self,name='po.pdf'):return dict(name=name,content=base64.b64encode(b'Test attachment').decode())
 def job(self,jid):return self.store.run(lambda c:c.one('work_jobs',{'id':jid}))
 def rows(self,name,jid):return self.store.run(lambda c:c.all(name,{'job_id':jid},sort=[('id',1)]))
 def call(self,role,path,**d):
  if d.get('job_id') and 'version' not in d:d['version']=self.job(d['job_id'])['version']
  with patch('server.access.current',return_value=self.users[role]):return self.store.run(lambda c:server.write_response(c,'/api/'+path,d,None,'local'))
 def create(self,plant='talawade',route='Fabrication + machining'):
  self.call('Design','projects/create',plant_id=plant,title='Test project',customer='Test',po_number='PO-1',quantity=3,due='2026-12-31',route=route,file=self.file())
  return self.store.run(lambda c:c.all('work_jobs',sort=[('id',-1)])[0]['id'])
 def approve(self,jid):
  r=next(r for r in self.rows('project_requests',jid) if r['status']=='Pending')
  self.call('QC','projects/decide',job_id=jid,request=r['id'],decision='Approved',notes='Verified')
 def test_routes_all_plants_and_archive_email_queue(self):
  for plant in pf.PLANTS:
   for route in pf.ROUTES:
    jid=self.create(plant['id'],route)
    self.call('Design','projects/requirement',job_id=jid,product_id=1,quantity=1,material_group='Raw material')
    self.call('Design','projects/submit',job_id=jid,notes='Drawing and materials verified')
    req=self.rows('requirements',jid)[0]
    with self.assertRaises(ValueError):self.call('Store','projects/issue',job_id=jid,requirement_id=req['id'],quantity=1)
    with self.assertRaises(ValueError):self.call('Store','work/issue',job_id=jid,requirement_id=req['id'],quantity=1)
    self.approve(jid)
    self.call('Store','projects/issue',job_id=jid,requirement_id=req['id'],quantity=1,request_id='issue-'+str(jid),return_state=True)
    self.call('Store','projects/issue',job_id=jid,requirement_id=req['id'],quantity=1,request_id='issue-'+str(jid))
    if route!='Machining only':
     self.assertEqual(self.job(jid)['stage'],'Fabrication execution')
     self.call('Fabrication','projects/action',job_id=jid,action='fabrication_done',notes='Fabrication completed');self.approve(jid)
    if route!='Fabrication only':
     self.assertEqual(self.job(jid)['stage'],'Machining execution')
     self.call('Machining','projects/action',job_id=jid,action='machining_done',notes='Machining completed');self.approve(jid)
    self.assertEqual(self.job(jid)['stage'],'QC inspection')
    self.call('QC','projects/chat',job_id=jid,message='Final measurements checked')
    self.call('QC','projects/action',job_id=jid,action='final_inspection',notes='Accepted')
    with self.assertRaises(ValueError):self.call('Fabrication','projects/action',job_id=jid,action='dispatch',notes='Packed')
    self.call('Accounts','projects/attach',job_id=jid,kind='EWAY challan',file=self.file('eway.pdf'))
    self.call('Fabrication','projects/action',job_id=jid,action='dispatch',notes='Packed and dispatched',request_id='dispatch-'+str(jid))
    self.call('Fabrication','projects/action',job_id=jid,action='dispatch',notes='Packed and dispatched',request_id='dispatch-'+str(jid))
    self.assertEqual(self.job(jid)['stage'],'Completed');self.assertEqual(len(self.rows('dispatch_outbox',jid)),1)
    result=self.store.run(lambda c:pf.archive(c,jid,self.users['Admin']))
    z=zipfile.ZipFile(io.BytesIO(result['_download']['content']))
    self.assertIn('project_messages.json',z.namelist());self.assertEqual(json.loads(z.read('project.json'))['plant_id'],plant['id'])
    self.assertTrue(any('eway.pdf' in n for n in z.namelist()))
  self.assertEqual(send_next(self.store,{}),'Disabled')
  sent=[];settings=dict(ARCHIVE_MAIL_ENABLED='true',SMTP_HOST='example.invalid',SMTP_USER='test',SMTP_PASSWORD='test',SMTP_FROM='test@example.invalid')
  self.assertEqual(send_next(self.store,settings,lambda msg:sent.append(msg)),'Sent');self.assertEqual(len(sent),1)
  self.assertEqual(str(sent[0]['To']),'sudipghosh1728@gmail.com')
 def test_inspection_approval_rework_revision_and_chat_scope(self):
  jid=self.create();other=self.create('solu')
  self.call('QC','projects/inspection',job_id=jid,action='call',notes='Customer inspection on site')
  call=self.rows('inspection_calls',jid)[0]
  with self.assertRaises(access.AccessError):self.call('QC','projects/inspection',job_id=jid,action='approve',call_id=call['id'],notes='Approve')
  with self.assertRaises(ValueError):self.call('QC','projects/inspection',job_id=jid,action='report',call_id=call['id'],result='OK')
  self.call('Admin','projects/inspection',job_id=jid,action='approve',call_id=call['id'],notes='Confirmed')
  with self.assertRaises(ValueError):self.call('QC','projects/inspection',job_id=jid,action='report',call_id=call['id'],result='Rework',notes='')
  self.call('QC','projects/inspection',job_id=jid,action='report',call_id=call['id'],result='Rework',notes='Repair weld')
  with self.assertRaises(ValueError):self.call('Admin','projects/action',job_id=jid,action='final_inspection',notes='Pending report')
  self.call('QC','projects/inspection',job_id=jid,action='report',call_id=call['id'],result='OK',notes='')
  self.call('Design','projects/chat',job_id=jid,message='Only this project')
  self.call('Design','projects/chat',job_id=other,message='Other project')
  with patch('server.access.current',return_value=self.users['QC']):
   messages=self.store.run(lambda c:server.read_api(c,'/api/projects/chat/'+str(jid),None))['messages']
   self.assertEqual([m['body'] for m in messages],['Only this project'])
  self.call('Admin','projects/action',job_id=jid,action='override',stage='Fabrication execution',notes='Authorized exception')
  self.call('Design','projects/attach',job_id=jid,kind='TC',file=self.file('tc.pdf'))
  self.assertEqual(self.job(jid)['stage'],'Fabrication execution')
  self.call('Design','projects/attach',job_id=jid,kind='Revised PO',file=self.file('rev.pdf'))
  self.assertEqual(self.job(jid)['stage'],'Design review')
  po=self.rows('job_documents',jid)[0]
  self.call('Design','projects/delete-document',job_id=jid,document=po['id'],notes='Replaced by revised PO')
  self.call('Design','projects/submit',job_id=jid,notes='Revised PO is the current order')
  with self.assertRaises(access.AccessError):self.call('Fabrication','projects/create',plant_id='solu')
  with self.assertRaises(ValueError):self.call('Design','projects/requirement',job_id=jid,product_id=1,quantity=1,material_group='Tool')
 def test_direct_handoff_cannot_skip_store_and_dispatch_snapshot_is_immutable(self):
  jid=self.create(route='Fabrication only')
  self.call('Design','projects/requirement',job_id=jid,product_id=1,quantity=2,material_group='Paint')
  self.call('Design','projects/request',job_id=jid,target='Fabrication',notes='Request fabrication')
  self.approve(jid);self.assertEqual(self.job(jid)['stage'],'Store issue')
  self.call('Admin','projects/action',job_id=jid,action='override',stage='QC inspection',notes='Inspect before release')
  with self.assertRaises(ValueError):self.call('QC','projects/action',job_id=jid,action='final_inspection',notes='Not issued')
  self.call('Admin','projects/action',job_id=jid,action='final_inspection',notes='Authorized Admin exception')
  self.call('Store','projects/attach',job_id=jid,kind='EWAY challan',file=self.file('dispatch.pdf'))
  self.call('Fabrication','projects/action',job_id=jid,action='dispatch',notes='Done')
  before=self.store.run(lambda c:pf.archive(c,jid,self.users['Admin']))['_download']['content']
  self.call('Design','projects/attach',job_id=jid,kind='TC',file=self.file('late-tc.pdf'))
  after=self.store.run(lambda c:pf.archive(c,jid,self.users['Admin']))['_download']['content']
  self.assertEqual(before,after)
  z=zipfile.ZipFile(io.BytesIO(after));self.assertNotIn('price',json.loads(z.read('materials.json'))[0])

 def test_design_support_department_request_returns_through_qc(self):
  jid=self.create(route='Machining only')
  self.call('Design','projects/request',job_id=jid,target='Accounts',notes='Confirm customer terms')
  self.approve(jid);self.assertEqual(self.job(jid)['stage'],'Accounts review')
  with self.assertRaises(access.AccessError):self.call('Store','projects/action',job_id=jid,action='request_done',notes='Wrong department')
  self.call('Accounts','projects/action',job_id=jid,action='request_done',notes='Terms confirmed')
  self.assertEqual(self.job(jid)['stage'],'QC approval');self.approve(jid)
  self.assertEqual(self.job(jid)['stage'],'Design review')
  self.call('Design','projects/request',job_id=jid,target='Store',notes='Verify availability; no issue required')
  self.approve(jid);self.call('Store','projects/action',job_id=jid,action='store_ready',notes='No outstanding requirements')
  self.assertEqual(self.job(jid)['stage'],'Machining execution')

 def test_maintenance_permissions_and_stale_writes(self):
  self.call('Accounts','projects/maintenance',plant_id='chakan',category='Internet',equipment='Office router',description='No connection')
  t=self.store.run(lambda c:c.all('maintenance_tickets')[0])
  with self.assertRaises(access.AccessError):self.call('Maintenance','projects/maintenance',id=t['id'],version=1,status='Open',notes='Approve')
  self.call('QC','projects/maintenance',id=t['id'],version=1,status='Open',notes='Approved')
  with self.assertRaises(ValueError):self.call('Maintenance','projects/maintenance',id=t['id'],version=1,status='Resolved',notes='Fixed')
  self.call('Maintenance','projects/maintenance',id=t['id'],version=2,status='In progress',notes='Checking switch')
  self.call('Maintenance','projects/maintenance',id=t['id'],version=3,status='Resolved',notes='Replaced cable')
  t=self.store.run(lambda c:c.all('maintenance_tickets')[0]);self.assertEqual(t['status'],'Resolved');self.assertEqual(len(t['updates']),3)

if __name__=='__main__':unittest.main()
