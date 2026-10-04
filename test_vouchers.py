import unittest,concurrent.futures
import seed,store_ops,accounting,finance_ops,access,server
from mongo_test_support import test_store,clean


class VoucherTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(seed.initialize)
  self.actor={'id':1,'role':'Store','name':'Store'}
  self.pid=self.store.run(lambda c:c.insert('products',name='Raw steel',sku='RAW',stock=10,price=100,unit='pcs',warehouse='Main',minimum=2))
  self.finished=self.store.run(lambda c:c.insert('products',name='Frame',sku='FRAME',stock=0,price=300,unit='pcs',warehouse='Main',minimum=1))
 def tearDown(self):clean(self.store)
 def run_db(self,fn):return self.store.run(fn)
 def stock(self,pid=None):return self.run_db(lambda c:c.one('products',{'id':pid or self.pid})['stock'])
 def save(self,kind,qty=1,**values):
  d=dict(kind=kind,party='Vendor',items=[dict(product_id=self.pid,quantity=qty)],action='save_post',**values)
  self.run_db(lambda c:store_ops.save(c,d,self.actor));return self.run_db(lambda c:c.all('store_documents',sort=[('id',-1)])[0])
 def cancel(self,doc):return self.run_db(lambda c:store_ops.save(c,dict(id=doc['id'],version=doc['version'],action='cancel',reason='Correction'),self.actor))
 def test_linked_returns_limit_and_cancel_order(self):
  issue=self.save('Issue',6);ret=self.save('Return in',2,source_id=issue['id']);self.assertEqual(self.stock(),6)
  with self.assertRaises(ValueError):self.save('Return in',5,source_id=issue['id'])
  with self.assertRaises(ValueError):self.cancel(issue)
  self.cancel(ret);self.assertEqual(self.stock(),4);self.cancel(issue);self.assertEqual(self.stock(),10)
  receipt=self.save('Inbound',4);ret=self.save('Return out',3,source_id=receipt['id']);self.assertEqual(self.stock(),11)
  self.cancel(ret);self.assertEqual(self.stock(),14)
 def test_concurrent_returns_do_not_exceed_original(self):
  issue=self.save('Issue',4)
  def attempt(_):
   try:self.save('Return in',3,source_id=issue['id']);return True
   except ValueError:return False
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
  self.assertEqual(sum(results),1);self.assertEqual(self.stock(),9)
 def test_physical_count_stale_draft_zero_and_reversal(self):
  d=dict(kind='Physical stock',remarks='Cycle count',items=[dict(product_id=self.pid,quantity=7,book_quantity=10)])
  self.run_db(lambda c:store_ops.save(c,d,self.actor));doc=self.run_db(lambda c:c.all('store_documents')[0])
  self.save('Issue',1)
  with self.assertRaises(ValueError):self.run_db(lambda c:store_ops.save(c,dict(id=doc['id'],version=doc['version'],action='post'),self.actor))
  self.assertEqual(self.stock(),9)
  d['action']='save_post';d['items'][0].update(book_quantity=9,quantity=0)
  self.run_db(lambda c:store_ops.save(c,d,self.actor));self.assertEqual(self.stock(),0)
  last=self.run_db(lambda c:c.all('store_documents',sort=[('id',-1)])[0]);self.cancel(last);self.assertEqual(self.stock(),9)
 def test_stock_journal_atomic_and_reversible(self):
  d=dict(kind='Stock journal',remarks='Frame production',action='save_post',items=[dict(product_id=self.pid,quantity=4,direction='Consume'),dict(product_id=self.finished,quantity=1,direction='Produce')])
  self.run_db(lambda c:store_ops.save(c,d,self.actor));self.assertEqual((self.stock(),self.stock(self.finished)),(6,1))
  doc=self.run_db(lambda c:c.all('store_documents')[0]);self.cancel(doc);self.assertEqual((self.stock(),self.stock(self.finished)),(10,0))
  d['items'][0]['quantity']=11
  with self.assertRaises(ValueError):self.run_db(lambda c:store_ops.save(c,d,self.actor))
  self.assertEqual(self.stock(self.finished),0)
 def test_financial_notes_payment_cap_and_balanced_books(self):
  oid=self.run_db(lambda c:accounting.create_invoice(c,dict(customer='Customer',items=[dict(product_id=self.pid,quantity=2,unit_price=100)])))
  invoice=self.run_db(lambda c:c.one('orders',{'id':oid}));bank=self.run_db(lambda c:accounting.system(c,'Main bank'))
  note=dict(kind='Credit note',document_id=oid,amount=50,reference='CN-1',description='Price allowance')
  self.run_db(lambda c:finance_ops.note(c,note));self.assertEqual(self.stock(),8)
  pay=dict(account_id=invoice['account_id'],money_account_id=bank,order_id=oid,amount=151,reference='PAY')
  with self.assertRaises(ValueError):self.run_db(lambda c:accounting.settle(c,pay))
  pay['amount']=150;self.run_db(lambda c:accounting.settle(c,pay))
  with self.assertRaises(ValueError):self.run_db(lambda c:finance_ops.note(c,note))
  def snapshot(c):
   data={'orders':c.all('orders'),'purchases':[]};accounting.state(c,data);return data
  data=self.run_db(snapshot);self.assertEqual(data['orders'][0]['outstanding_paise'],0);self.assertEqual(data['orders'][0]['credited_paise'],5000)
  self.assertEqual(sum(a['balance'] for a in data['accounts']),0)
  supplier=self.run_db(lambda c:accounting.party(c,'Supplier','Supplier'))
  pid=self.run_db(lambda c:c.insert('purchases',supplier='Supplier',account_id=supplier,product_id=self.pid,quantity=1,unit_cost=100,status='Received',date=accounting.date()))
  self.run_db(lambda c:accounting.post_purchase(c,pid));self.run_db(lambda c:finance_ops.note(c,dict(kind='Debit note',document_id=pid,amount=30,reference='DN-1',description='Allowance')))
  self.assertEqual(self.run_db(lambda c:accounting.balance(c,supplier)),-7000)
 def test_contra_reconcile_and_accounts_permission(self):
  cash=self.run_db(lambda c:accounting.system(c,'Cash in hand'));bank=self.run_db(lambda c:accounting.system(c,'Main bank'))
  d=dict(from_account_id=cash,to_account_id=bank,amount='15.25',reference='CTR-1',description='Deposit')
  self.run_db(lambda c:finance_ops.contra(c,d));self.assertEqual(self.run_db(lambda c:accounting.balance(c,bank)),1525)
  with self.assertRaises(ValueError):self.run_db(lambda c:finance_ops.contra(c,{**d,'to_account_id':cash}))
  line=self.run_db(lambda c:c.one('journal_lines',{'account_id':bank}))
  self.run_db(lambda c:finance_ops.reconcile(c,dict(line_id=line['id'],cleared_date=accounting.date())))
  with self.assertRaises(ValueError):self.run_db(lambda c:finance_ops.reconcile(c,dict(line_id=line['id'],cleared_date='')))
  self.run_db(lambda c:finance_ops.reconcile(c,dict(line_id=line['id'],cleared_date='',previous_date=accounting.date())))
  def cookie(c,role):
   access.create_user(c,dict(username=role,name=role,role=role,password='Voucher-test-password-123'))
   _,token,_=access.login(c,dict(username=role,password='Voucher-test-password-123'),role)
   return 'tppl_session='+token
  store_cookie=self.run_db(lambda c:cookie(c,'Store'));accounts_cookie=self.run_db(lambda c:cookie(c,'Accounts'))
  with self.assertRaises(access.AccessError):self.run_db(lambda c:server.write_api(c,'/api/contra',d,store_cookie,'test'))
  d['request_id']='same-transfer';self.run_db(lambda c:server.write_api(c,'/api/contra',d,accounts_cookie,'test'));self.run_db(lambda c:server.write_api(c,'/api/contra',d,accounts_cookie,'test'))
  self.assertEqual(self.run_db(lambda c:accounting.balance(c,bank)),3050)


if __name__=='__main__':unittest.main()
