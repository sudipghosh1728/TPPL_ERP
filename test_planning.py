import unittest,base64,copy
import access,seed,project_flow as pf,qc_ops as q,production_planning as plan,report_workshop as reports,po_entities,server,dispatch_structure as ds,hr_ops
from mongo_test_support import test_store,clean
from unittest.mock import patch

def file(name='po.txt',text='Paint: epoxy RAL 7035 DFT 120 microns\nMaterial: IS 2062 E250 BR; EN 10204 3.1'):
 return dict(name=name,content=base64.b64encode(text.encode()).decode())
class PlanningTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(lambda c:seed.initialize(c,demo=True))
  self.users={r:dict(id=i+1,name=r+' test',role=r,username=r.lower(),active=1) for i,r in enumerate(access.ROLES)}
  self.store.run(lambda c:pf.create(c,dict(plant_id='solu',title='560 plates',customer='Test',po_number='PLAN-560',quantity=560,due='2026-12-01',route='Fabrication + machining',drawing_file=dict(name='drawing.txt',content='RFJBV0lORw=='),file=file()),self.users['Design']))
  self.jid=self.store.run(lambda c:c.all('work_jobs')[0]['id'])
 def tearDown(self):clean(self.store)
 def job(self):return self.store.run(lambda c:c.one('work_jobs',{'id':self.jid}))
 def batch(self,bid):return self.store.run(lambda c:c.one('qc_batches',{'id':bid}))
 def call(self,fn,role='Design',**d):return self.store.run(lambda c:fn(c,d,self.users[role]))
 def lot(self,name='First 60',qty=60):
  self.call(plan.dispatch_lot,job_id=self.jid,version=self.job()['version'],name=name,quantity=qty,date='2026-12-01');return self.job()['dispatch_lots'][-1]['id']
 def drawing(self,lot=None,qty=60):return self.call(q.create_batch,job_id=self.jid,lot_id=lot,drawing='DR-01',thickness='20',quantity=qty,planned_date='2026-12-01')
 def assembly_lot(self,qty=80):
  self.call(plan.dispatch_lot,job_id=self.jid,version=self.job()['version'],name='Assembly dispatch',quantity=qty,date=hr_ops.today(),quantity_basis='assemblies');return self.job()['dispatch_lots'][-1]['id']
 def item(self,lid,name,qty,parent=None):return self.call(plan.work_item,job_id=self.jid,version=self.job()['version'],lot_id=lid,name=name,quantity=qty,parent_id=parent)
 def parts(self,lid,iid,rows):return self.call(q.create_many,job_id=self.jid,version=self.job()['version'],lot_id=lid,work_item_id=iid,drawings=[dict(drawing=name,pieces_per_item=qty,thickness='20',tc_required=True) for name,qty in rows])['ids']
 def test_assemblies_multiple_jobs_subjobs_and_drawing_totals(self):
  lid=self.assembly_lot();root=self.item(lid,'Frame',60);other=self.item(lid,'Housing',20);child=self.item(lid,'Support',2,root)
  first,second=self.parts(lid,root,[('Plate',2),('Bracket',1)]);sub=self.parts(lid,child,[('Pin',3)])[0];last=self.parts(lid,other,[('Shell',2)])[0]
  self.assertEqual([self.batch(b)['quantity'] for b in (first,second,sub,last)],[120,60,360,40])
  self.assertEqual(self.batch(sub)['job_path'],'Frame / Support')
  lot=self.job()['dispatch_lots'][0];rows=self.store.run(lambda c:c.all('qc_batches',{'job_id':self.jid}))
  self.assertEqual(ds.planning_errors(lot,rows),[])
  with self.assertRaisesRegex(ValueError,'exceed'):self.item(lid,'Too many',1)
  with self.assertRaises(ValueError):self.parts(lid,root,[('Plate',1)])
  before=len(rows)
  with self.assertRaises(ValueError):self.parts(lid,root,[('Valid',1),('Invalid',0)])
  self.assertEqual(len(self.store.run(lambda c:c.all('qc_batches',{'job_id':self.jid}))),before)
  with self.assertRaises(access.AccessError):self.call(plan.work_item,'QC',job_id=self.jid,version=self.job()['version'],lot_id=lid,name='Wrong',quantity=1)
  with self.assertRaises(ValueError):self.call(q.create_many,job_id=self.jid,version=1,lot_id=lid,work_item_id=root,drawings=[dict(drawing='Stale',thickness='20',pieces_per_item=1)])
 def test_dispatch_reminder_counts_complete_assemblies_not_component_pieces(self):
  lid=self.assembly_lot();root=self.item(lid,'Frame',80);a,b=self.parts(lid,root,[('Plate',2),('Bracket',1)])
  self.store.run(lambda c:c.update('qc_batches',{'id':a},{'actual_date':q.today()}))
  rows=self.store.run(lambda c:c.all('qc_batches',{'job_id':self.jid}));lot=self.job()['dispatch_lots'][0]
  self.assertFalse(ds.dispatched(lot,rows))
  alerts=self.store.run(lambda c:hr_ops.alerts(c,[self.job()],self.users['Design']));self.assertEqual(alerts[0]['due'],hr_ops.today())
  with self.assertRaisesRegex(ValueError,'dispatched'):self.parts(lid,root,[('Late part',1)])
  self.store.run(lambda c:c.update('qc_batches',{'id':b},{'actual_date':q.today()}))
  self.assertTrue(ds.dispatched(lot,self.store.run(lambda c:c.all('qc_batches',{'job_id':self.jid}))))
 def test_tc_scopes_and_process_progress_before_documents(self):
  lid=self.assembly_lot();root=self.item(lid,'Frame',60);child=self.item(lid,'Support',2,root);other=self.item(lid,'Housing',20)
  a=self.parts(lid,root,[('Plate',1)])[0];b=self.parts(lid,child,[('Pin',1)])[0];z=self.parts(lid,other,[('Shell',1)])[0]
  steps={s:dict(status='Done',quantity=60,notes='Complete') if s not in ('Final QC','Packing') else dict(status='Pending',quantity=0,notes='Awaiting final inspection') for s in q.x.STEPS}
  self.call(q.save_steps,'Admin',batch_id=a,version=self.batch(a)['version'],steps=steps,notes='No documents yet')
  self.assertEqual(self.batch(a)['steps']['Final Paint']['status'],'Done')
  errors=self.store.run(lambda c:q.release_errors(c,self.batch(a),check_steps=False));self.assertIn('Attach Drawing',errors);self.assertIn('Attach TC',errors)
  self.call(pf.attach,'Store',job_id=self.jid,version=self.job()['version'],kind='TC',file=file('frame-tc.txt'),tc_scope='job',tc_lot_id=lid,tc_item_id=root)
  self.assertTrue(self.batch(a)['document_ids']);self.assertEqual(self.batch(a)['document_ids'],self.batch(b)['document_ids']);self.assertFalse(self.batch(z)['document_ids'])
  late=self.parts(lid,child,[('Washer',2)])[0];self.assertEqual(self.batch(late)['document_ids'],self.batch(b)['document_ids'])
  self.call(pf.attach,'QC',job_id=self.jid,version=self.job()['version'],kind='TC',file=file('shell-tc.txt'),tc_scope='drawing',tc_batch_id=z)
  self.assertEqual(len(self.batch(z)['document_ids']),1)
  self.assertEqual(self.batch(a)['steps']['Final Paint']['status'],'Done')
  steps['Final QC']=dict(status='Done',quantity=60,notes='Missing evidence')
  with self.assertRaises(ValueError):self.call(q.save_steps,'Admin',batch_id=a,version=self.batch(a)['version'],steps=steps,notes='Too early')
 def test_new_projects_require_po_and_drawing_atomically(self):
  payload=dict(plant_id='solu',title='Requires drawing',customer='Test',po_number='Required',quantity=1,due='2026-12-01',route='Fabrication only')
  before=len(self.store.run(lambda c:c.all('work_jobs')))
  for extra in ({},{'file':file()},{'drawing_file':file('drawing.txt')}):
   with self.assertRaisesRegex(ValueError,'both'):self.call(pf.create,**payload,**extra)
  self.assertEqual(len(self.store.run(lambda c:c.all('work_jobs'))),before)
  self.call(pf.create,**payload,file=file(),drawing_file=file('drawing.txt'))
  project=self.store.run(lambda c:c.all('work_jobs',sort=[('id',-1)])[0]);docs=self.store.run(lambda c:c.all('job_documents',{'job_id':project['id']}))
  self.assertEqual({d['kind'] for d in docs},{'PO','Drawing'})
 def test_lots_dimensions_consumption_and_stale_edits(self):
  lid=self.lot();bid=self.drawing(lid)
  with self.assertRaises(ValueError):self.drawing(lid,1)
  for i in range(4):self.lot(str(i),125)
  self.assertEqual(sum(l['quantity'] for l in self.job()['dispatch_lots']),560)
  with self.assertRaises(ValueError):self.lot('Excess',1)
  payload=dict(batch_id=bid,version=self.batch(bid)['version'],job_version=self.job()['version'],product_id=1,pieces_per_job=2,shape='Plate',length_mm=500,width_mm=250,thickness_mm=20,blank_length_mm=520,blank_width_mm=270,notes='E250; tolerance +/- 1 mm')
  rid=self.call(plan.requirement,**payload)
  r=self.store.run(lambda c:c.one('requirements',{'id':rid}));self.assertEqual(r['quantity'],120);self.assertEqual(r['lot_id'],lid)
  with self.assertRaises(ValueError):self.call(plan.requirement,**payload)
  self.call(plan.cut,job_id=self.jid,version=self.job()['version'],requirement_id=rid,cut_quantity=60,scrap_kg=4.2,notes='First cutting complete')
  with self.assertRaises(ValueError):self.call(plan.cut,job_id=self.jid,version=self.job()['version'],requirement_id=rid,cut_quantity=121,notes='Overrun')
  with self.assertRaises(access.AccessError):self.call(plan.cut,'QC',job_id=self.jid,version=self.job()['version'],requirement_id=rid,cut_quantity=10,notes='Wrong owner')
  self.assertEqual(self.store.run(lambda c:c.one('products',{'id':1}))['stock'],124)
 def test_department_process_ownership(self):
  bid=self.drawing(qty=160)
  for step,owner in q.PROCESS_OWNERS.items():
   b=self.batch(bid);steps=copy.deepcopy(b['steps']);steps[step]=dict(status='In progress',quantity=1,notes='Started')
   wrong='QC' if owner!='QC' else 'Design'
   with self.assertRaises(access.AccessError):self.call(q.save_steps,wrong,batch_id=bid,version=b['version'],steps=steps,notes='Forbidden')
   self.call(q.save_steps,owner,batch_id=bid,version=b['version'],steps=steps,notes='Department update')
   self.assertEqual(self.batch(bid)['step_updates'][step]['department'],owner)
  with self.assertRaises(access.AccessError):self.call(q.create_batch,'QC',job_id=self.jid,drawing='Wrong',quantity=1,thickness='20',planned_date='2026-12-01')
 def test_po_extraction_and_any_user_review(self):
  bid=self.drawing(qty=1)
  specs=self.job()['po_specs'];self.assertIn('RAL 7035',specs['painting']);self.assertIn('IS 2062',specs['material']);self.assertEqual(specs['status'],'Review required')
  self.call(plan.specifications,'Store',job_id=self.jid,version=self.job()['version'],painting='RAL 9005',material='E350',notes='Checked original')
  self.assertEqual(self.batch(bid)['evidence_version'],1)
  self.call(pf.attach,'Design',job_id=self.jid,version=self.job()['version'],kind='Revised PO',file=file(text='Epoxy RAL 7032'))
  self.assertEqual(self.job()['po_specs']['painting'],'RAL 9005');self.assertIn('7032',self.job()['po_spec_suggestions']['painting'])
  self.assertEqual(po_entities.suggestions(b'scan','scan.png')['status'],'Manual review required')
 def test_chat_routes_and_report_saved_atomically(self):
  for role in ('Design','Store','Purchase','QC','Fabrication'):
   u=self.users[role];self.store.run(lambda c,u=u:c.insert('users',**u,password_hash='test'))
  self.call(pf.chat,'Machining',job_id=self.jid,message='Need plate 500 x 250 x 20 mm; drawing dimension changed',file=file('check.pdf','%PDF-1.4 test'))
  rows=self.store.run(lambda c:c.all('report_workbooks'));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['job_id'],self.jid)
  recipients=self.store.run(lambda c:c.all('reminders'));self.assertEqual({r['recipient_id'] for r in recipients},{self.users[r]['id'] for r in ('Design','Store','Purchase','QC','Fabrication')})
  messages=self.store.run(lambda c:c.all('project_messages'));self.assertEqual(messages[0]['report_id'],rows[0]['id']);self.assertEqual(messages[1]['author'],'Project assistant')
 def test_delete_approved_report_invalidates_batch(self):
  bid=self.drawing(qty=1)
  rid=self.call(reports.upload,'Store',name='Final report',file=file('inspection.pdf','report'),job_id=self.jid,batch_id=bid,batch_version=self.batch(bid)['version'])['id']
  self.store.run(lambda c:c.update('report_workbooks',{'id':rid},{'status':'Approved'}))
  with self.assertRaises(access.AccessError):self.call(reports.delete,'Design',id=rid,version=1,batch_version=self.batch(bid)['version'],notes='Replace')
  self.call(reports.delete,'QC',id=rid,version=1,batch_version=self.batch(bid)['version'],notes='Wrong signed report')
  self.assertIsNone(self.store.run(lambda c:c.one('report_workbooks',{'id':rid})));self.assertIsNone(self.batch(bid)['current_upload']);self.assertIn('Approve the current inspection report',self.store.run(lambda c:q.release_errors(c,self.batch(bid))))
 def test_first_lot_dispatch_does_not_wait_for_later_lots(self):
  first=self.lot();second=self.lot('Later 500',500);bid=self.drawing(first);self.drawing(second,500)
  b=self.batch(bid)
  self.call(q.trace,'QC',batch_id=bid,version=b['version'],new_lot=dict(heat_no='H1',plate_no='P1',quantity=60))
  lot=self.store.run(lambda c:c.all('qc_trace_lots')[0])
  self.call(q.trace,'QC',batch_id=bid,version=self.batch(bid)['version'],allocations=[dict(lot_id=lot['id'],quantity=60)])
  self.call(q.document,'QC',batch_id=bid,version=self.batch(bid)['version'],kind='Drawing',file=file('drawing.pdf','drawing'))
  rid=self.call(reports.upload,'Design',name='Approved first lot',file=file('report.pdf','report'),job_id=self.jid,batch_id=bid,batch_version=self.batch(bid)['version'])['id']
  self.call(reports.approve,'QC',id=rid,version=1,batch_version=self.batch(bid)['version'],notes='Checked all evidence')
  steps={s:dict(status='Done',quantity=60,notes='Complete') for s in q.x.STEPS};steps['Packing']=dict(status='Pending',quantity=0,notes='Pack next')
  self.call(q.save_steps,'Admin',batch_id=bid,version=self.batch(bid)['version'],steps=steps,notes='Department records verified')
  steps['Packing']=dict(status='Done',quantity=60,notes='Packed')
  self.call(q.save_steps,'Fabrication',batch_id=bid,version=self.batch(bid)['version'],steps=steps,notes='First lot packed')
  self.call(q.document,'QC',batch_id=bid,version=self.batch(bid)['version'],kind='EWAY challan',file=file('eway.pdf','eway'))
  rid=self.store.run(lambda c:c.insert('requirements',job_id=self.jid,batch_id=bid,product_id=1,quantity=1,department='Design'))
  with self.assertRaisesRegex(ValueError,'Issue all materials'):self.call(q.dispatch,'Fabrication',batch_id=bid,version=self.batch(bid)['version'],actual_date=q.today(),notes='Not issued')
  self.store.run(lambda c:c.update('requirements',{'id':rid},{'issued':1}))
  self.call(q.dispatch,'Fabrication',batch_id=bid,version=self.batch(bid)['version'],actual_date=q.today(),notes='First 60 dispatched')
  self.assertTrue(self.batch(bid)['actual_date']);self.assertNotEqual(self.job()['stage'],'Completed')
  with self.assertRaises(ValueError):self.store.run(lambda c:q.gate(c,self.job(),dispatching=True))
 def test_pdf_entity_extraction(self):
  import io
  from reportlab.pdfgen.canvas import Canvas
  out=io.BytesIO();pdf=Canvas(out);pdf.drawString(30,700,'Epoxy RAL 7035 DFT 120 microns; material ASTM A36');pdf.save()
  result=po_entities.suggestions(out.getvalue(),'purchase.pdf');self.assertIn('7035',result['painting']);self.assertIn('A36',result['material'])
 def test_purchase_full_admin_backend(self):
  u=self.users['Purchase'];access.require(u);access.require(u,('HR',));access.require(u,('QC',))
  self.store.run(lambda c:access.manage_user(c,dict(name='New HR',username='newhr',password='Testing-only-123',role='HR'),u))
  with patch('server.access.current',return_value=u),patch('server.STORE',self.store):data=self.store.run(lambda c:server.read_api(c,'/api/state',None))
  self.assertTrue(data['users']);self.assertTrue(data['orders']);self.assertTrue(data['settings']);self.assertIn('hr_profiles',data)
if __name__=='__main__':unittest.main()
