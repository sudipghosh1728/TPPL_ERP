import unittest, tempfile, pathlib, threading, json, urllib.request, urllib.error
import server
from mongo_test_support import test_store,clean

class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        server.STORE=test_store();cls.store=server.STORE
        server.initialize(migrate_local=False)
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        import http.cookiejar
        cls.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        req=urllib.request.Request(cls.url+'/api/auth/setup',data=json.dumps(dict(username='testadmin',name='Test Admin',password='Test-only-password-123')).encode(),headers={'Content-Type':'application/json'})
        with cls.opener.open(req) as r:json.load(r)
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.temp.cleanup();clean(cls.store)
    def request(self,path,data=None):
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:
            with e:return e.code,json.load(e)
    def state(self):return self.request('state')[1]
    def stock(self):return next(p['stock'] for p in self.state()['products'] if p['id']==1)
    def test_manufacturing_workflow(self):
        before=self.stock()
        self.assertEqual(self.request('purchases',dict(supplier='Test steel vendor',product_id=1,quantity=10,unit_cost=100))[0],200)
        po=self.state()['purchases'][0]['id']
        self.assertEqual(self.request('receive',dict(id=po))[0],200)
        self.assertEqual(self.stock(),before+10)
        self.assertEqual(self.request('receive',dict(id=po))[0],400)
        self.assertEqual(self.stock(),before+10)
        self.assertEqual(self.request('jobs',dict(name='Test frame',customer='Test',product_id=1,quantity=3,due='2026-12-01'))[0],200)
        job=self.state()['jobs'][0]['id']
        self.assertEqual(self.request('job-action',dict(id=job))[0],200)
        self.assertEqual(self.stock(),before+7)
        self.assertEqual(self.request('job-action',dict(id=job))[0],200)
        self.assertEqual(self.stock(),before+7)
        self.assertEqual(self.request('job-action',dict(id=job))[0],400)
        self.assertEqual(self.request('orders',dict(customer='Test',product_id=1,quantity=2))[0],200)
        self.assertEqual(self.stock(),before+5)
        count=len(self.state()['orders'])
        self.assertEqual(self.request('orders',dict(customer='Test',product_id=1,quantity=999999))[0],400)
        self.assertEqual(len(self.state()['orders']),count)
        self.assertEqual(self.stock(),before+5)
        self.assertEqual(self.request('orders',dict(customer='Test',product_id=1,quantity=-1))[0],400)
        server.initialize()
        self.assertEqual(self.stock(),before+5)
    def test_xml_is_well_formed(self):
        import xml.etree.ElementTree as ET
        with self.opener.open(self.url+'/api/export/tally') as r:
            root=ET.fromstring(r.read())
        self.assertEqual(root.tag,'ENVELOPE')
        self.assertGreater(len(root.findall('.//VOUCHER')),0)

    def test_accounting_and_partial_receipts(self):
        self.assertEqual(self.request('accounts',dict(name='Precision Test Customer',type='Customer',opening='123.45',opening_side='Debit',date='2026-01-01'))[0],200)
        a=next(a for a in self.state()['accounts'] if a['name']=='Precision Test Customer')
        self.assertEqual(a['balance'],12345)
        bank=next(a['id'] for a in self.state()['accounts'] if a['type']=='Bank')
        before=self.stock()
        body=dict(account_id=a['id'],date='2026-09-01',due='2026-10-01',items=[dict(product_id=1,quantity=2,unit_price='10.15'),dict(product_id=4,quantity=3,unit_price='0.10')],request_id='test-idempotent-invoice')
        self.assertEqual(self.request('invoices',body)[0],200)
        o=self.state()['orders'][0]
        self.assertEqual(o['total_paise'],2060)
        self.assertEqual(self.stock(),before-2)
        self.assertEqual(self.request('invoices',body)[0],200)
        self.assertEqual(self.stock(),before-2)
        self.assertEqual(self.state()['orders'][0]['id'],o['id'])
        receipt=dict(account_id=a['id'],money_account_id=bank,order_id=o['id'],date='2026-09-02',reference='TEST-RECEIPT',amount='10.10',request_id='test-idempotent-payment')
        self.assertEqual(self.request('settlements',receipt)[0],200)
        self.assertEqual(self.request('settlements',receipt)[0],200)
        order=next(x for x in self.state()['orders'] if x['id']==o['id'])
        self.assertEqual((order['status'],order['paid_paise'],order['outstanding_paise']),('Part paid',1010,1050))
        receipt.pop('request_id');receipt['amount']='10.51'
        count=len(self.state()['journals'])
        self.assertEqual(self.request('settlements',receipt)[0],400)
        self.assertEqual(len(self.state()['journals']),count)
        receipt['amount']='10.50'
        self.assertEqual(self.request('settlements',receipt)[0],200)
        self.assertEqual(next(x for x in self.state()['orders'] if x['id']==o['id'])['status'],'Paid')
        receipt.pop('order_id');receipt['amount']='123.45'
        self.assertEqual(self.request('settlements',receipt)[0],200)
        self.assertEqual(next(x for x in self.state()['accounts'] if x['id']==a['id'])['balance'],0)
        data=self.state();self.assertEqual(sum(a['debit'] for a in data['accounts']),sum(a['credit'] for a in data['accounts']))
        count=len(data['journals']);server.initialize();self.assertEqual(len(self.state()['journals']),count)

    def test_supplier_and_expense_postings(self):
        self.assertEqual(self.request('purchases',dict(supplier='Accounts Test Supplier',product_id=1,quantity=2,unit_cost='25.25'))[0],200)
        p=self.state()['purchases'][0]
        self.assertEqual(next(a for a in self.state()['accounts'] if a['id']==p['account_id'])['balance'],0)
        self.assertEqual(self.request('receive',dict(id=p['id']))[0],200)
        self.assertEqual(next(a for a in self.state()['accounts'] if a['id']==p['account_id'])['balance'],-5050)
        bank=next(a['id'] for a in self.state()['accounts'] if a['type']=='Bank')
        self.assertEqual(self.request('settlements',dict(account_id=p['account_id'],money_account_id=bank,purchase_id=p['id'],amount='20.25',reference='Supplier part payment'))[0],200)
        self.assertEqual(next(a for a in self.state()['accounts'] if a['id']==p['account_id'])['balance'],-3025)
        self.assertEqual(self.request('accounts',dict(name='Power expenses',type='Expense'))[0],200)
        expense=next(a['id'] for a in self.state()['accounts'] if a['name']=='Power expenses')
        voucher=dict(debit_account_id=expense,credit_account_id=bank,amount='100.75',reference='Power-1',description='Electricity expense')
        self.assertEqual(self.request('journals',voucher)[0],200)
        self.assertEqual(next(a for a in self.state()['accounts'] if a['id']==expense)['balance'],10075)
        voucher['credit_account_id']=expense
        self.assertEqual(self.request('journals',voucher)[0],400)
        voucher['credit_account_id']=p['account_id']
        self.assertEqual(self.request('journals',voucher)[0],400)

    def test_invoice_atomic_validation(self):
        before=self.stock();count=len(self.state()['journals'])
        data=dict(customer='Rollback Customer',items=[dict(product_id=1,quantity=before,unit_price=1),dict(product_id=1,quantity=1,unit_price=1)])
        self.assertEqual(self.request('invoices',data)[0],400)
        self.assertEqual(self.stock(),before)
        self.assertEqual(len(self.state()['journals']),count)
        self.assertFalse(any(a['name']=='Rollback Customer' for a in self.state()['accounts']))
        data['items']=[dict(product_id=1,quantity='1.5',unit_price=1)]
        self.assertEqual(self.request('invoices',data)[0],400)
        data['items']=[dict(product_id=1,quantity=1,unit_price='NaN')]
        self.assertEqual(self.request('invoices',data)[0],400)
        data['items']=['invalid']
        self.assertEqual(self.request('invoices',data)[0],400)

if __name__=='__main__':unittest.main()
