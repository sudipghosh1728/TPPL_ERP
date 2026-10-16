import base64,datetime as dt,hashlib,io,json,os,unittest,zipfile
from unittest.mock import patch
import access,project_deletion as deletion,project_flow,seed,server
from mongo_test_support import test_store,clean

class ProjectDeletionTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(seed.initialize);self.old_store=server.STORE;server.STORE=self.store
  self.admin=dict(id=1,name='Admin',role='Admin');self.other=dict(id=2,name='Other Admin',role='Admin')
  def create(c):
   for title in ('Delete me','Keep me'):
    project_flow.create(c,dict(plant_id='solu',title=title,customer='Customer',po_number='PO',quantity=1,due='2026-12-01',route='Fabrication only',file=dict(name='po.pdf',content=base64.b64encode(b'Original PO').decode())),self.admin)
   pid=c.insert('products',name='Steel',sku='TEST',stock=8,unit='kg',price=20)
   for jid in (1,2):
    rid=c.insert('requirements',job_id=jid,product_id=pid,quantity=2,issued=2)
    c.insert('material_issues',requirement_id=rid,quantity=2,issued_by=1)
    c.insert('project_requests',job_id=jid,status='Approved',review_notes='QC approved')
    c.insert('inspection_calls',job_id=jid,status='OK',report='Accepted')
    c.insert('project_messages',job_id=jid,body='Verified drawing',author='QC')
    c.insert('project_notifications',job_id=jid,message='Approved')
    c.insert('reminders',job_id=jid,recipient_id=1,sender_role='Admin',sender_name='Admin',created_at='2026-10-16T09:00:00',message='Project reminder',read_at='')
    c.insert('alert_reads',user_id=1,key=f'2026-10-14:{jid}:2026-10-15:QC approval')
    c.insert('movements',product_id=pid,quantity=-2,reason=f'Job JOB-{jid:04} / requirement {rid}',date='2026-10-14')
   c.insert('accounts',name='Shared customer',type='Customer')
  self.store.run(create)
 def tearDown(self):server.STORE=self.old_store;clean(self.store)
 def call(self,path,data,user=None):
  with patch('server.access.current',return_value=user or self.admin):return self.store.run(lambda c:server.write_response(c,'/api/projects/'+path,data,None,'local'))
 def prepare(self,jid=1):return self.call('delete-export',dict(job_id=jid))
 def part(self,meta,n,user=None):
  with patch('server.access.current',return_value=user or self.admin):return self.store.run(lambda c:server.read_api(c,f'/api/projects/delete-export/{meta["token"]}/{n}',None))['_download']['content']
 def download(self,meta):
  packet=b''.join(self.part(meta,n) for n in range(meta['parts']));self.assertEqual(len(packet),meta['bytes']);self.assertEqual(hashlib.sha256(packet).hexdigest(),meta['sha256']);return packet
 def delete(self,meta,**extra):return self.call('delete',dict(job_id=1,export_token=meta['token'],download_confirmed=True,confirmation='JOB-0001',**extra))
 def rows(self,t):return self.store.run(lambda c:c.all(t,sort=[('id',1)]))
 def test_archive_all_records_chunked_and_cascade_preserves_other_project_and_books(self):
  payload=os.urandom(700000)
  self.store.run(lambda c:c.insert('job_documents',job_id=1,kind='TC',name='../unsafe/TC.pdf',content=payload))
  def queue(c):
   oid=c.insert('dispatch_outbox',job_id=1,status='Queued',recipient='test@example.invalid')
   c.insert('dispatch_archives',outbox_id=oid,chunk=0,content=b'previous dispatch archive')
  self.store.run(queue);before={t:self.rows(t) for t in ('products','movements','accounts')}
  meta=self.prepare();self.assertGreater(meta['parts'],1)
  with self.assertRaises(ValueError):self.delete(meta)
  self.part(meta,0)
  with self.assertRaises(ValueError):self.delete(meta)
  archive=zipfile.ZipFile(io.BytesIO(self.download(meta)))
  self.assertEqual(archive.read('documents/3-TC.pdf'),payload)
  for path in ('project.json','work_history.json','project_requests.json','project_messages.json','inspection_calls.json','material_issues.json','reports/project-report.html','reports/work_history.csv','dispatch-archives/1.zip'):self.assertIn(path,archive.namelist())
  self.assertEqual(json.loads(archive.read('project_requests.json'))[0]['review_notes'],'QC approved')
  self.assertFalse(any('..' in name for name in archive.namelist()))
  result=self.delete(meta,request_id='delete-once',return_state=True);self.assertTrue(result['ok']);self.assertNotIn(1,[j['id'] for j in result['state']['work_jobs']])
  self.assertTrue(self.delete(meta,request_id='delete-once')['duplicate'])
  for t in deletion.OWNED:
   if t!='dispatch_outbox':self.assertEqual(len(self.rows(t)),1,t)
  self.assertEqual([j['id'] for j in self.rows('work_jobs')],[2]);self.assertEqual(len(self.rows('material_issues')),1);self.assertEqual(len(self.rows('alert_reads')),1)
  for t in ('dispatch_archives','dispatch_outbox','project_delete_exports','project_delete_parts'):self.assertEqual(self.rows(t),[])
  for t,rows in before.items():self.assertEqual(self.rows(t),rows)
 def test_permissions_user_bound_token_expiry_and_confirmation(self):
  meta=self.prepare()
  for role in access.ROLES:
   if role=='Admin':continue
   user=dict(id=3,name=role,role=role)
   for fn in (lambda:self.call('delete-export',dict(job_id=1),user),lambda:self.part(meta,0,user),lambda:self.call('delete',dict(job_id=1,export_token=meta['token']),user)):
    with self.assertRaises(access.AccessError):fn()
  with self.assertRaises(ValueError):self.part(meta,0,self.other)
  self.download(meta)
  for changes in ({'download_confirmed':False},{'confirmation':'wrong'},{'job_id':2}):
   with self.assertRaises(ValueError):self.call('delete',dict(job_id=1,export_token=meta['token'],download_confirmed=True,confirmation='JOB-0001')|changes)
  self.store.run(lambda c:c.update('project_delete_exports',{},dict(expires_at=dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1))))
  with self.assertRaises(ValueError):self.delete(meta)
  self.assertEqual(len(self.rows('work_jobs')),2)
 def test_chat_and_document_changes_invalidate_snapshot_even_without_version_change(self):
  for collection,values in [('project_messages',dict(body='New message')),('job_documents',dict(name='new.pdf',kind='Drawing',content=b'new drawing'))]:
   meta=self.prepare();self.download(meta);self.store.run(lambda c:c.insert(collection,job_id=1,**values))
   with self.assertRaisesRegex(ValueError,'changed'):self.delete(meta)
  fresh=self.prepare();self.download(fresh);self.delete(fresh);self.assertEqual(len(self.rows('work_jobs')),1)
 def test_legacy_project_and_transaction_rollback(self):
  self.store.run(lambda c:c.update('work_jobs',{'id':1},{'flow_version':1}))
  meta=self.prepare();self.download(meta)
  from storage import UnitOfWork
  original=UnitOfWork.delete
  def failing(c,name,query):
   if name=='project_messages':raise ValueError('Simulated failure')
   return original(c,name,query)
  with patch.object(UnitOfWork,'delete',failing):
   with self.assertRaisesRegex(ValueError,'Simulated'):self.delete(meta)
  self.assertEqual(len(self.rows('requirements')),2);self.assertEqual(len(self.rows('work_jobs')),2)
  self.delete(meta);self.assertEqual(len(self.rows('work_jobs')),1)
 def test_inflight_email_blocks_deletion(self):
  meta=self.prepare();self.download(meta)
  self.store.run(lambda c:c.insert('dispatch_outbox',job_id=1,status='Sending'))
  with self.assertRaisesRegex(ValueError,'in progress'):self.delete(meta)
  with self.assertRaisesRegex(ValueError,'in progress'):self.prepare()

if __name__=='__main__':unittest.main()
