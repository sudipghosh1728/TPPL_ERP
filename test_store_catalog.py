import unittest
import store_catalog,store_ops,accounting,access,seed,server
from mongo_test_support import test_store,clean

class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(seed.initialize)
  self.actor=dict(id=1,name='Store operator',role='Store')
 def tearDown(self):clean(self.store)
 def test_import_preserves_existing_and_is_repeatable(self):
  existing=self.store.run(lambda c:c.insert('products',name='Test steel',sku='OLD',stock=12,unit='kg',price=1,minimum=0,category='Raw materials',warehouse='Main store'))
  rows=[dict(row=1,name='TEST STEEL'),dict(row=2,name='Test wheel',source_values=['10','15','2'])]
  preview=self.store.run(lambda c:store_catalog.import_names(c,rows,'testsource'))
  self.assertEqual(preview[1]['action'],'New material');self.assertEqual(self.store.db.products.count_documents({}),1)
  for _ in range(2):self.store.run(lambda c:store_catalog.import_names(c,rows,'testsource',True))
  self.assertEqual(self.store.db.products.count_documents({}),2)
  old=self.store.run(lambda c:c.one('products',{'id':existing}));self.assertEqual((old['stock'],old['unit']),(12,'kg'))
  new=self.store.run(lambda c:c.one('products',{'name':'Test wheel'}));self.assertTrue(new['catalog_pending']);self.assertEqual(new['stock'],0);self.assertEqual(new['unit'],'')
 def test_pending_material_requires_unit_and_opening_confirmation(self):
  self.store.run(lambda c:store_catalog.import_names(c,[dict(row=1,name='Test wheel')],'testsource',True))
  p=self.store.run(lambda c:c.one('products'));pid=p['id']
  with self.assertRaises(ValueError):self.store.run(lambda c:store_ops.save(c,dict(kind='Inbound',party='Test',items=[dict(product_id=pid,quantity=1)],action='save_post'),self.actor))
  with self.assertRaises(ValueError):self.store.run(lambda c:accounting.create_invoice(c,dict(customer='Test',items=[dict(product_id=pid,quantity=1)])))
  data=dict(id=pid,unit='kg',quantity=20,date=accounting.date())
  with self.assertRaises(access.AccessError):self.store.run(lambda c:store_catalog.confirm(c,data,dict(role='Accounts')))
  self.store.run(lambda c:store_catalog.confirm(c,data,self.actor))
  with self.assertRaises(ValueError):self.store.run(lambda c:store_catalog.confirm(c,data,self.actor))
  p=self.store.run(lambda c:c.one('products',{'id':pid}));self.assertEqual((p['stock'],p['unit'],p['catalog_pending']),(20,'kg',False))
  moves=self.store.run(lambda c:c.all('movements'));self.assertEqual(len(moves),1);self.assertEqual(moves[0]['kind'],'catalog_opening')
 def test_store_invoice_projection_does_not_expose_financial_books(self):
  def setup(c):
   pid=c.insert('products',name='Test plate',sku='PL',stock=20,price=100,minimum=0,category='Raw materials',warehouse='Main store',unit='pcs')
   accounting.create_invoice(c,dict(customer='Test customer',items=[dict(product_id=pid,quantity=2)]))
   access.create_user(c,dict(username='storetest',name='Store',role='Store',password='Store-test-password-123'))
   _,token,_=access.login(c,dict(username='storetest',password='Store-test-password-123'),'test');return token
  token=self.store.run(setup);previous=server.STORE;server.STORE=self.store
  try:data=self.store.run(lambda c:server.read_api(c,'/api/state','tppl_session='+token))
  finally:server.STORE=previous
  self.assertEqual(len(data['store_invoices']),1);self.assertEqual(data['store_invoices'][0]['items'][0]['quantity'],2)
  for key in ('orders','accounts','settlements','journal_lines','journals'):self.assertEqual(data[key],[])
  self.assertNotIn('paid_paise',data['store_invoices'][0]);self.assertNotIn('account_id',data['store_invoices'][0])

if __name__=='__main__':unittest.main()
