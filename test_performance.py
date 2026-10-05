"""Performance-path regressions: freshness, permissions and retry correctness."""
import unittest
import server,seed,access
from mongo_test_support import test_store,clean

class PerformanceTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(seed.initialize)
  self.previous=server.STORE;server.STORE=self.store
 def tearDown(self):server.STORE=self.previous;clean(self.store)
 def test_transaction_read_reuse_is_copy_safe_and_invalidated_by_writes(self):
  def check(c):
   pid=c.insert('products',name='Performance test',sku='PERF',stock=10)
   a=c.one('products',{'id':pid});a['stock']=999
   self.assertEqual(c.one('products',{'id':pid})['stock'],10)
   rows=c.all('products');rows.clear();self.assertEqual(len(c.all('products')),1)
   c.update('products',{'id':pid},inc={'stock':-1});self.assertEqual(c.one('products',{'id':pid})['stock'],9)
   c.delete('products',{'id':pid});self.assertIsNone(c.one('products',{'id':pid}));self.assertEqual(c.all('products'),[])
  self.store.run(check)
 def test_bootstrap_and_save_return_current_authorized_state_and_retry_once(self):
  def setup(c):
   access.create_user(c,dict(username='perf-store',name='Store',role='Store',password='Performance-test-password'))
   _,token,_=access.login(c,dict(username='perf-store',password='Performance-test-password'),'test')
   pid=c.insert('products',name='Plate',sku='PL',stock=10,minimum=0,price=1,category='Raw',warehouse='Main',unit='pcs')
   return 'tppl_session='+token,pid
  cookie,pid=self.store.run(setup)
  boot=self.store.run(lambda c:server.read_api(c,'/api/bootstrap',cookie))
  self.assertEqual(boot['state']['products'][0]['stock'],10);self.assertEqual(boot['state']['accounts'],[])
  body=dict(kind='Issue',party='Test recipient',action='save_post',items=[dict(product_id=pid,quantity=2)],request_id='retry-token',return_state=True)
  for _ in range(2):
   saved=self.store.run(lambda c:server.write_response(c,'/api/store-documents',body,cookie,'test'))
   self.assertEqual(saved['state']['products'][0]['stock'],8);self.assertEqual(saved['state']['journal_lines'],[])
  self.assertEqual(len(saved['state']['store_documents']),1)
  self.store.run(lambda c:c.update('users',{'username':'perf-store'},{'active':0}))
  with self.assertRaises(access.AccessError):self.store.run(lambda c:server.read_api(c,'/api/state',cookie))
  boot=self.store.run(lambda c:server.read_api(c,'/api/bootstrap',cookie));self.assertIsNone(boot['user']);self.assertNotIn('state',boot)

if __name__=='__main__':unittest.main()
