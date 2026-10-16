import unittest
from unittest.mock import patch
import access, reminders, seed, server
from mongo_test_support import test_store, clean

class ReminderTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.store.run(lambda c:seed.initialize(c,demo=True));self.old=server.STORE;server.STORE=self.store
  self.users=[]
  for i,role in enumerate(['Admin','Machining','Fabrication','Machining','QC','Design']):
   u=dict(id=i+1,name=role+' '+str(i),username='reminder'+str(i),role=role,active=1,password_hash='private-test-hash')
   self.store.run(lambda c,u=u:c.insert('users',**u));self.users.append(u)
 def tearDown(self):server.STORE=self.old;clean(self.store)
 def call(self,index,path,**data):
  with patch('server.access.current',return_value=self.users[index]):return self.store.run(lambda c:server.write_response(c,'/api/'+path,data,None,'local'))
 def inbox(self,index):return self.store.run(lambda c:reminders.inbox(c,self.users[index]))
 def test_recipient_scope_server_authority_and_acknowledgement(self):
  self.call(0,'reminders/send',recipient_id=2,message='Admin instruction',sender_role='Fabrication',request_id='once')
  self.call(0,'reminders/send',recipient_id=2,message='Admin instruction',request_id='once')
  rows=self.inbox(1);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['tone'],'red');self.assertEqual(self.inbox(2),[])
  with self.assertRaises(ValueError):self.call(2,'reminders/read',id=rows[0]['id'])
  self.call(1,'reminders/read',id=rows[0]['id']);self.assertTrue(self.inbox(1)[0]['read_at'])
  self.call(1,'reminders/send',department='Machining',message='Same team',sender_role='Admin')
  self.assertEqual(self.inbox(3)[0]['tone'],'neutral');self.assertEqual(self.inbox(3)[0]['sender_role'],'Machining')
  self.call(1,'reminders/send',department='Fabrication',message='Please review rework')
  self.assertEqual(self.inbox(2)[0]['tone'],'yellow')
  with self.assertRaises(ValueError):self.call(1,'reminders/send',recipient_id=999,message='Invalid recipient')
  with patch('server.access.current',return_value=self.users[1]):
   state=self.store.run(lambda c:server.read_api(c,'/api/state',None))
  self.assertTrue(state['reminder_directory']);self.assertTrue(all(set(u)<=set(('id','name','role')) for u in state['reminder_directory']))
  self.assertEqual(len(state['reminders']),1)

 def test_urgency_role_and_stale_version_guards(self):
  self.call(0,'projects/create',plant_id='solu',title='Urgent job',customer='Test',po_number='PO',quantity=1,due='2026-12-31',route='Fabrication only',file={'name':'po.pdf','content':'UE8='})
  j=self.store.run(lambda c:c.all('work_jobs',sort=[('id',-1)])[0])
  with self.assertRaises(access.AccessError):self.call(1,'projects/urgency',job_id=j['id'],version=j['version'],urgent=True)
  self.call(5,'projects/urgency',job_id=j['id'],version=j['version'],urgent=True,urgent_role='Admin')
  latest=self.store.run(lambda c:c.one('work_jobs',{'id':j['id']}));self.assertEqual(latest['urgent_role'],'Design')
  self.assertEqual(reminders.tone(latest['urgent_role'],'Design'),'neutral');self.assertEqual(reminders.tone(latest['urgent_role'],'QC'),'yellow')
  with self.assertRaises(ValueError):self.call(0,'projects/urgency',job_id=j['id'],version=j['version'],urgent=False)
  self.call(0,'projects/urgency',job_id=j['id'],version=latest['version'],urgent=False)
  self.assertFalse(self.store.run(lambda c:c.one('work_jobs',{'id':j['id']}))['urgent'])

if __name__=='__main__' :unittest.main()
