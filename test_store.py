import unittest,concurrent.futures
import access,seed,store_ops,server
from mongo_test_support import test_store,clean

class StoreTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(seed.initialize)
  self.actor=dict(id=1,name='Store User',role='Store')
  self.pid=self.store.run(lambda c:c.insert('products',name='Steel plate',sku='PLATE',unit='pcs',stock=10,minimum=1,price=100,category='Raw',warehouse='Main'))
 def tearDown(self):clean(self.store)
 def payload(self,kind='Issue',qty=3,**extra):return dict(kind=kind,party='Job work supplier',date=store_ops.accounting.date(),items=[dict(product_id=self.pid,quantity=qty,rate='12.50',hsn='7208')],**extra)
 def save(self,data,actor=None):return self.store.run(lambda c:store_ops.save(c,data,actor or self.actor))
 def doc(self):return self.store.run(lambda c:c.all('store_documents',sort=[('id',-1)])[0])
 def stock(self):return self.store.run(lambda c:c.one('products',{'id':self.pid})['stock'])
 def test_job_material_can_be_issued_before_department_approval(self):
  import manufacturing
  jid=self.store.run(lambda c:c.insert('work_jobs',title='Unapproved job',stage='Design review',version=1))
  rid=self.store.run(lambda c:c.insert('requirements',job_id=jid,product_id=self.pid,department='Design',quantity=2,issued=0,approved=0,tc_required=0))
  self.store.run(lambda c:manufacturing.issue(c,dict(requirement_id=rid,quantity=2,version=1),self.actor))
  self.assertEqual(self.stock(),8)
  self.assertEqual(self.store.run(lambda c:c.one('work_jobs',{'id':jid}))['stage'],'Design review')
 def test_draft_post_reverse_and_tax_snapshot(self):
  self.save(self.payload(cgst=9,sgst=9));self.assertEqual(self.stock(),10)
  d=self.doc();self.save(dict(id=d['id'],version=d['version'],action='post'))
  self.assertEqual(self.stock(),7);d=self.doc();self.assertEqual(d['total'],4426)
  self.store.run(lambda c:c.update('products',{'id':self.pid},{'name':'Renamed'}))
  self.assertEqual(self.doc()['items'][0]['description'],'Steel plate')
  with self.assertRaises(ValueError):self.save(dict(id=d['id'],version=d['version'],action='post'))
  self.save(dict(id=d['id'],version=d['version'],action='cancel',reason='Wrong recipient'))
  self.assertEqual(self.stock(),10)
 def test_receipt_then_issue_without_job_and_cannot_reverse_spent_stock(self):
  self.save(self.payload('Inbound',5,action='save_post'));receipt=self.doc();self.assertEqual(self.stock(),15)
  self.save(self.payload(qty=14,action='save_post'));self.assertEqual(self.stock(),1)
  with self.assertRaises(ValueError):self.save(dict(id=receipt['id'],version=receipt['version'],action='cancel',reason='Mistake'))
  self.assertEqual(self.stock(),1)
 def test_oversell_is_atomic_and_concurrent_safe(self):
  def attempt(_):
   try:self.save(self.payload(qty=7,action='save_post'));return True
   except ValueError:return False
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
  self.assertEqual(sum(results),1);self.assertEqual(self.stock(),3)
  with self.assertRaises(ValueError):self.save(self.payload(qty=4,action='save_post'))
  self.assertEqual(self.store.run(lambda c:len(c.all('store_documents'))),1)
 def test_validation_permissions_and_eway_metadata(self):
  with self.assertRaises(access.AccessError):self.save(self.payload(),dict(id=2,name='Accounts',role='Accounts'))
  with self.assertRaises(ValueError):self.save(self.payload(cgst=9,igst=18))
  data=self.payload();data['items']*=2
  with self.assertRaises(ValueError):self.save(data)
  self.save(self.payload(action='save_post'));d=self.doc()
  self.save(dict(action='eway',id=d['id'],version=d['version'],eway_number='123456789012'))
  self.assertEqual(self.stock(),7);self.assertEqual(self.doc()['eway_number'],'123456789012')
 def test_api_idempotency_and_role_visibility(self):
  previous=server.STORE;server.STORE=self.store
  try:
   def login(c,role):
    access.create_user(c,dict(username=role.lower(),name=role,role=role,password='Store-test-password-123'))
    _,token,_=access.login(c,dict(username=role.lower(),password='Store-test-password-123'),'test')
    return 'tppl_session='+token
   cookie=self.store.run(lambda c:login(c,'Store'));other=self.store.run(lambda c:login(c,'Accounts'))
   data=self.payload(action='save_post',request_id='same-issue')
   for _ in range(2):self.store.run(lambda c:server.write_api(c,'/api/store-documents',data,cookie,'test'))
   self.assertEqual(self.stock(),7)
   self.assertEqual(self.store.run(lambda c:server.read_api(c,'/api/state',other))['store_documents'],[])
   self.assertEqual(len(self.store.run(lambda c:server.read_api(c,'/api/state',cookie))['store_documents']),1)
  finally:server.STORE=previous

if __name__=='__main__':unittest.main()
