import json,unittest
from unittest.mock import patch
import access,server,seed
from mongo_test_support import test_store,clean

class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.store=test_store();self.store.prepare();self.store.run(lambda c:seed.initialize(c,demo=True))
        self.password='Original-test-password-123';self.new='Replacement-test-password-456';self.users={}
        for role in ('Admin','Purchase','QC'):
            uid=self.store.run(lambda c,r=role:access.create_user(c,dict(username=r.lower(),name=r,role=r,password=self.password)))
            self.users[role]=self.store.run(lambda c,i=uid:access.public(c.one('users',{'id':i})))
        uid=self.store.run(lambda c:access.create_user(c,dict(username='other-admin',name='Other admin',role='Admin',password=self.password)))
        self.target=self.store.run(lambda c:access.public(c.one('users',{'id':uid})))
    def tearDown(self):clean(self.store)
    def reset(self,actor=None,target=None,**overrides):
        payload=dict(id=(target or self.target)['id'],password=self.new,confirm_password=self.new);payload.update(overrides)
        with patch('server.access.current',return_value=actor or self.users['Admin']):return self.store.run(lambda c:server.write_api(c,'/api/users/reset-password',payload,None,'fixture'))
    def test_admin_resets_other_admin_revokes_sessions_and_audits_without_secrets(self):
        def login(c):return access.login(c,dict(username=self.target['username'],password=self.password),'fixture')
        tokens=[self.store.run(login)[1] for _ in range(2)]
        self.reset()
        for token in tokens:self.assertIsNone(self.store.run(lambda c:access.current(c,'tppl_session='+token)))
        self.assertIsNotNone(self.store.run(login)[2])
        user,_,error=self.store.run(lambda c:access.login(c,dict(username=self.target['username'],password=self.new),'fixture'))
        self.assertIsNone(error);self.assertEqual(user,self.target)
        audit=json.dumps(self.store.run(lambda c:c.all('activity')))
        self.assertIn('Password reset for other-admin (Admin) by Admin',audit)
        self.assertNotIn(self.password,audit);self.assertNotIn(self.new,audit)
        self.assertNotEqual(self.store.run(lambda c:c.one('users',{'id':user['id']}))['password_hash'],self.new)
    def test_permissions_confirmation_strength_self_reset_and_disabled_status(self):
        with self.assertRaises(access.AccessError):self.reset(self.users['QC'])
        for values in ({'confirm_password':'mismatch'},{'password':'short','confirm_password':'short'},{'id':99999}):
            with self.assertRaises(ValueError):self.reset(**values)
        with self.assertRaisesRegex(ValueError,'My password'):self.reset(target=self.users['Admin'])
        self.assertTrue(access.verify(self.password,self.store.run(lambda c:c.one('users',{'id':self.target['id']}))['password_hash']))
        self.store.run(lambda c:c.update('users',{'id':self.target['id']},{'active':0}))
        self.reset();self.assertEqual(self.store.run(lambda c:c.one('users',{'id':self.target['id']}))['active'],0)
    def test_purchase_retains_full_admin_access_and_can_reset_department_user(self):
        self.reset(self.users['Purchase'],self.users['QC'])
        row=self.store.run(lambda c:c.one('users',{'id':self.users['QC']['id']}))
        self.assertTrue(access.verify(self.new,row['password_hash']));self.assertEqual(row['role'],'QC')
