import unittest
import accounting as a,access,seed,store_ops,stock_corrections as sc,finance_ops,store_catalog
from mongo_test_support import test_store,clean

class OperationTests(unittest.TestCase):
 def setUp(self):
  self.db=test_store();self.db.prepare();self.db.run(seed.initialize)
  self.actor=dict(id=1,name='Store',role='Store')
  self.pid=self.db.run(lambda c:c.insert('products',name='Steel',sku='TEST',unit='kg',stock=10,price=100,warehouse='Main',minimum=0))
 def tearDown(self):clean(self.db)
 def rows(self,t):return self.db.run(lambda c:c.all(t))
 def stock(self):return self.rows('products')[0]['stock']
 def correction(self,inside,outside,**extra):
  def go(c):
   p=c.one('products',{'id':self.pid});t=sc.totals(c,p)
   sc.save(c,dict(product_id=self.pid,inbound=inside,outbound=outside,expected_stock=p['stock'],expected_inbound=t['inbound'],expected_outbound=t['outbound'],reason='Count reconciled',date=a.date(),**extra),self.actor)
  self.db.run(go)
 def invoice(self,**extra):return dict(document_mode='gst_dispatch',customer='Customer',supplier_gstin='27ABCDE1234F1Z5',customer_gstin='',place_of_supply='27',company_address='Pune',customer_address='Pune',delivery_address='Pune',items=[dict(product_id=self.pid,quantity=2,unit_price='100.00',hsn='7208',gst_rate='18')],**extra)
 def test_corrections_preserve_opening_and_history(self):
  self.correction(5,3);self.assertEqual(self.stock(),12)
  self.correction(2,1);self.assertEqual(self.stock(),11)
  totals=self.db.run(lambda c:sc.totals(c,c.one('products',{'id':self.pid})))
  self.assertEqual(totals,dict(opening=10,inbound=2,outbound=1,adjustments=0));self.assertEqual(len(self.rows('stock_corrections')),2);self.assertEqual(len(self.rows('movements')),4)
  with self.assertRaises(ValueError):self.correction(0,11)
  with self.assertRaises(ValueError):self.correction(-1,1)
  payload=dict(product_id=self.pid,inbound=3,outbound=1,expected_stock=10,expected_inbound=2,expected_outbound=1,reason='Stale',date=a.date())
  with self.assertRaises(ValueError):self.db.run(lambda c:sc.save(c,payload,self.actor))
  self.actor['role']='Design'
  with self.assertRaises(access.AccessError):self.correction(3,1)
  self.assertEqual(self.stock(),11)
 def test_intrastate_gst_and_credit_note_reverse_tax(self):
  oid=self.db.run(lambda c:a.create_invoice(c,self.invoice()));o=self.rows('orders')[0]
  self.assertEqual((o['taxable_paise'],o['cgst_paise'],o['sgst_paise'],o['igst_paise']),(20000,1800,1800,0));self.assertEqual(a.cents(o['total']),23600);self.assertEqual(self.stock(),8)
  for amount in ['0.01','117.99','118.00']:
   self.db.run(lambda c:finance_ops.note(c,dict(kind='Credit note',document_id=oid,amount=amount,reference='CN',description='Allowance')))
  for label in ['Sales revenue','Output CGST','Output SGST']:
   self.assertEqual(self.db.run(lambda c:a.balance(c,a.system(c,label))),0)
  self.assertEqual(self.db.run(lambda c:a.balance(c,o['account_id'])),0)
  for j in self.rows('journals'):
   lines=[l for l in self.rows('journal_lines') if l['journal_id']==j['id']];self.assertEqual(sum(l['debit'] for l in lines),sum(l['credit'] for l in lines))
  projection=self.db.run(lambda c:store_catalog.invoice_register(c))[0];self.assertEqual(projection['supplier_gstin'],o['supplier_gstin']);self.assertEqual(projection['items'][0]['unit'],'kg')
 def test_interstate_validation_and_rollback(self):
  data=self.invoice();data['place_of_supply']='29';oid=self.db.run(lambda c:a.create_invoice(c,data));o=self.rows('orders')[0]
  self.assertEqual((o['cgst_paise'],o['sgst_paise'],o['igst_paise']),(0,0,3600))
  for mutate in [lambda d:d.update(supplier_gstin=''),lambda d:d['items'][0].update(hsn=''),lambda d:d['items'][0].update(gst_rate='NaN')]:
   data=self.invoice();mutate(data)
   with self.assertRaises(ValueError):self.db.run(lambda c:a.create_invoice(c,data))
  self.assertEqual(len(self.rows('orders')),1);self.assertEqual(self.stock(),8)
 def test_inhouse_no_sale_no_tax_and_accounts_permission(self):
  data=dict(kind='Issue',operation='Inhouse',same_registration=True,party='Fabrication',action='save_post',items=[dict(product_id=self.pid,quantity=2,rate=100)])
  actor=dict(id=2,name='Accounts',role='Accounts');self.db.run(lambda c:store_ops.save(c,data,actor))
  self.assertEqual(self.stock(),8);self.assertEqual(self.rows('orders'),[]);self.assertEqual(self.rows('journals'),[]);self.assertEqual(self.rows('store_documents')[0]['cgst'],0)
  for extra in [dict(same_registration=False),dict(cgst=9),dict(company_gstin='27ABCDE1234F1Z5',party_gstin='29ABCDE1234F1Z5')]:
   with self.assertRaises(ValueError):self.db.run(lambda c:store_ops.save(c,{**data,**extra},actor))
  self.assertEqual(self.stock(),8)

if __name__=='__main__':unittest.main()
