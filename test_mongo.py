"""Integration tests against a real MongoDB replica set, including rollback/races."""
import concurrent.futures,pathlib,sqlite3,tempfile,unittest
from contextlib import closing
import accounting,seed,access
from migrate_to_mongo import migrate
from mongo_test_support import test_store,clean
from pymongo.errors import DuplicateKeyError

class MongoIntegrationTests(unittest.TestCase):
    def setUp(self):self.store=test_store();self.store.prepare()
    def tearDown(self):clean(self.store)

    def test_failed_transaction_leaves_no_partial_posting(self):
        self.store.run(lambda c:seed.initialize(c,demo=True))
        before=self.store.db.products.find_one({'id':1})['stock']
        def fail(c):
            c.update('products',{'id':1},inc={'stock':-1})
            c.insert('movements',product_id=1,quantity=-1,reason='Should roll back',date='2026-09-29')
            raise ValueError('Simulated failure before journal commit')
        with self.assertRaises(ValueError):self.store.run(fail)
        self.assertEqual(self.store.db.products.find_one({'id':1})['stock'],before)
        self.assertEqual(self.store.db.movements.count_documents({'reason':'Should roll back'}),0)

    def test_concurrent_sales_cannot_oversell(self):
        self.store.run(lambda c:seed.initialize(c,demo=True))
        self.store.run(lambda c:c.update('products',{'id':1},{'stock':1}))
        def sale(index):
            try:
                self.store.run(lambda c:accounting.create_invoice(c,dict(customer='Race customer',product_id=1,quantity=1)))
                return 'sold'
            except ValueError:return 'out of stock'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(sale,range(2)))
        self.assertCountEqual(results,['sold','out of stock'])
        self.assertEqual(self.store.db.products.find_one({'id':1})['stock'],0)
        self.assertEqual(self.store.db.orders.count_documents({'customer':'Race customer'}),1)

    def test_concurrent_receipts_cannot_overpay(self):
        self.store.run(lambda c:seed.initialize(c,demo=True))
        oid=self.store.run(lambda c:accounting.create_invoice(c,dict(customer='Receipt race',product_id=1,quantity=1,items=[dict(product_id=1,quantity=1,unit_price='10.00')])))
        o=self.store.db.orders.find_one({'id':oid});bank=self.store.run(lambda c:accounting.system(c,'Main bank'))
        def receipt(index):
            try:
                self.store.run(lambda c:accounting.settle(c,dict(account_id=o['account_id'],money_account_id=bank,order_id=oid,amount='10.00',reference='RACE-'+str(index))))
                return 'paid'
            except ValueError:return 'rejected'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(receipt,range(2)))
        self.assertCountEqual(results,['paid','rejected'])
        self.assertEqual(self.store.db.settlements.count_documents({'order_id':oid}),1)

    def test_sqlite_migration_preserves_ids_passwords_binary_and_counters(self):
        with tempfile.TemporaryDirectory() as temp:
            source=pathlib.Path(temp)/'source.db';password=access.password_hash('Migration-test-password')
            with closing(sqlite3.connect(source)) as c, c:
                c.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,name TEXT,role TEXT,password_hash TEXT,active INTEGER); CREATE TABLE job_documents(id INTEGER PRIMARY KEY,job_id INTEGER,kind TEXT,name TEXT,mime TEXT,content BLOB,uploaded_by INTEGER,created_at TEXT);')
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',(17,'original','Original Admin','Admin',password,1))
                c.execute('INSERT INTO job_documents VALUES(?,?,?,?,?,?,?,?)',(41,10,'PO','original.pdf','application/octet-stream',b'%PDF\x00\xff\x12',17,'2026-09-29'))
            result=migrate(source,self.store)
            self.assertEqual(result['counts']['users'],1)
            self.assertTrue(pathlib.Path(result['snapshot']).is_file())
            user=self.store.db.users.find_one({'id':17});self.assertTrue(access.verify('Migration-test-password',user['password_hash']))
            self.assertEqual(self.store.db.job_documents.find_one({'id':41})['content'],b'%PDF\x00\xff\x12')
            self.assertTrue(migrate(source,self.store)['already_migrated'])
            uid=self.store.run(lambda c:access.create_user(c,dict(username='second',name='Second',role='Store',password='Second-test-password')))
            self.assertEqual(uid,18)
            with closing(sqlite3.connect(source)) as c, c:c.execute("UPDATE users SET name='Changed source' WHERE id=17")
            with self.assertRaises(ValueError):migrate(source,self.store)
            self.assertEqual(self.store.db.users.find_one({'id':17})['name'],'Original Admin')

    def test_unique_accounts_and_migration_refuses_nonempty_target(self):
        self.store.run(lambda c:seed.initialize(c,demo=True))
        with self.assertRaises(DuplicateKeyError):self.store.run(lambda c:c.insert('accounts',name='MAIN BANK',type='Bank'))
        with tempfile.TemporaryDirectory() as temp:
            source=pathlib.Path(temp)/'empty.db'
            with closing(sqlite3.connect(source)) as c, c:c.execute('CREATE TABLE settings(key TEXT,value TEXT)')
            with self.assertRaises(ValueError):migrate(source,self.store)
        self.assertEqual(self.store.db.products.count_documents({}),6)

if __name__=='__main__':unittest.main()
