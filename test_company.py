import unittest
import access,company,seed,server
from mongo_test_support import test_store,clean

class CompanyTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(seed.initialize)
 def tearDown(self):clean(self.store)
 def config(self,industry='Supermarket'):
  return dict(company='Example Stores',industry=industry,address='10 Market Road',financial_year='2026-04-01',**company.TEMPLATES[industry])
 def test_clean_setup_and_product_validation(self):
  self.assertEqual(self.store.run(lambda c:len(c.all('orders'))),0)
  self.store.run(lambda c:company.save(c,self.config()))
  cfg=self.store.run(company.get);self.assertFalse(cfg['manufacturing'])
  self.assertEqual(self.store.run(lambda c:c.one('settings',{'key':'company'}))['value'],'Example Stores')
  data=dict(category='Grocery',warehouse='Shop floor',unit='pack',barcode='1234',attributes={'Brand':'Example'})
  self.assertEqual(self.store.run(lambda c:company.product_details(c,data))['unit'],'pack')
  with self.assertRaises(ValueError):self.store.run(lambda c:company.product_details(c,{**data,'category':'Steel'}))
  with self.assertRaises(ValueError):self.store.run(lambda c:company.product_details(c,{**data,'attributes':{'$set':'bad'}}))
  with self.assertRaises(access.AccessError):self.store.run(lambda c:company.guard(c,'/api/work/create'))
 def test_active_jobs_prevent_disable(self):
  self.store.run(lambda c:c.insert('work_jobs',title='Live job',stage='Design review'))
  with self.assertRaises(ValueError):self.store.run(lambda c:company.save(c,self.config()))
  self.assertTrue(self.store.run(company.get)['manufacturing'])
 def test_configuration_admin_only(self):
  def attempt(c):
   access.create_user(c,dict(name='Store',username='store',password='Test-password-123',role='Store'))
   _,token,_=access.login(c,dict(username='store',password='Test-password-123'),'local')
   return server.write_api(c,'/api/company',self.config(),'tppl_session='+token,'local')
  with self.assertRaises(access.AccessError):self.store.run(attempt)
 def test_duplicate_barcode_rejected(self):
  self.store.run(lambda c:c.insert('products',sku='A',barcode='123'))
  from pymongo.errors import DuplicateKeyError
  with self.assertRaises(DuplicateKeyError):self.store.run(lambda c:c.insert('products',sku='B',barcode='123'))

if __name__=='__main__':unittest.main()
