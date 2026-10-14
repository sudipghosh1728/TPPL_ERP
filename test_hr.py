import datetime as dt, unittest
from unittest.mock import patch
import access,hr_ops as h,project_flow as pf
from mongo_test_support import test_store,clean

PHOTO='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/aEAAAAASUVORK5CYII='
class HRTests(unittest.TestCase):
 def setUp(self):
  self.store=test_store();self.store.prepare();self.users={}
  for name,role in [('Admin','Admin'),('HR','HR'),('Design','Design'),('QC1','QC'),('QC2','QC'),('Store','Store')]:
   uid=self.store.run(lambda c,n=name,r=role:c.insert('users',username=n.lower(),name=n,role=r,password_hash='unused'))
   self.users[name]={'id':uid,'name':name,'role':role,'username':name.lower(),'active':1}
  self.time=dt.datetime(2026,10,13,9,0,tzinfo=h.IST);self.clock=patch('hr_ops.now',side_effect=lambda:self.time);self.clock.start()
 def tearDown(self):self.clock.stop();clean(self.store)
 def call(self,who,endpoint,**d):return self.store.run(lambda c:h.HANDLERS[endpoint](c,d,self.users[who]))
 def rows(self,name):return self.store.run(lambda c:c.all(name))
 def profile(self,who):self.call(who,'profile',name=who,phone='9999999999',email=who.lower()+'@example.invalid',blood_group='O+',dob='1990-01-01',photo=PHOTO,department=self.users[who]['role'])
 def test_profile_validation_privacy_and_role_control(self):
  with self.assertRaises(ValueError):self.call('QC1','profile',name='QC1')
  self.profile('QC1');self.profile('QC2')
  with self.assertRaises(access.AccessError):self.call('QC1','profile',user_id=self.users['QC2']['id'])
  with self.assertRaises(ValueError):self.call('QC1','profile',name='QC1',phone='9999999999',email='ok@example.invalid',blood_group='O+',dob='1990-01-01',photo=PHOTO,department='Admin')
  def view(c,who):
   data={'work_jobs':[]};h.state(c,data,self.users[who]);return data
  own=self.store.run(lambda c:view(c,'QC1'));design=self.store.run(lambda c:view(c,'Design'));admin=self.store.run(lambda c:view(c,'Admin'))
  self.assertEqual(own['employee_profile']['name'],'QC1');self.assertEqual(own['hr_profiles'],[])
  self.assertEqual(design['hr_profiles'],[]);self.assertNotIn('email',design['employee_directory'][0]);self.assertEqual(len(admin['hr_profiles']),2)
 def test_leave_assignment_coverage_and_return(self):
  uid=self.users['QC1']['id'];self.call('QC1','leave',start='2026-10-13',end='2026-10-19',reason='Personal')
  rid=self.rows('employee_leave')[0]['id'];self.call('HR','leave',id=rid,action='Approved',paid=True,notes='Approved')
  j={'assignments':{'QC':uid}}
  self.store.run(lambda c:h.assigned(c,j,self.users['QC2']))
  self.call('QC1','leave',id=rid,action='resume')
  with self.assertRaises(access.AccessError):self.store.run(lambda c:h.assigned(c,j,self.users['QC2']))
  self.store.run(lambda c:h.assigned(c,j,self.users['QC1']))
  self.call('QC2','leave',start='2026-10-13',end='2026-10-17',reason='Five days')
  short=self.rows('employee_leave')[-1]['id'];self.call('HR','leave',id=short,action='Approved',notes='Approved')
  with self.assertRaises(access.AccessError):self.store.run(lambda c:h.assigned(c,{'assignments':{'QC':self.users['QC2']['id']}},self.users['QC1']))
  with self.assertRaises(access.AccessError):self.call('QC2','leave',id=rid,action='Approved',notes='No')
  jid=self.store.run(lambda c:c.insert('work_jobs',flow_version=2,plant_id='solu',title='Test',due='2026-10-15',po_number='PO1',route='Fabrication only',quantity=1,assignments={'QC':uid}))
  self.call('Design','assign',job_id=jid,version=1,department='QC',user_id=uid)
  self.store.run(lambda c:c.insert('project_requests',job_id=jid,target='Fabrication',status='Pending',from_stage='Design review',department='Design'))
  r=self.rows('project_requests')[0]
  with self.assertRaises(access.AccessError):self.store.run(lambda c:pf.decide(c,{'job_id':jid,'version':2,'request':r['id'],'decision':'Approved','notes':'No'},self.users['QC2']))
  self.assertEqual(self.rows('project_requests')[0]['status'],'Pending')
 def test_attendance_elapsed_accuracy_cutoff_and_regularization(self):
  self.call('HR','pin',plant_id='solu',latitude=18.6,longitude=73.8)
  payload=dict(plant_id='solu',latitude=18.6,longitude=73.8,accuracy=5)
  with self.assertRaises(ValueError):self.call('QC1','attendance',action='start',**{**payload,'accuracy':80})
  self.call('QC1','attendance',action='start',**payload)
  for minute in range(1,32):
   row=self.rows('employee_attendance')[0];self.time+=dt.timedelta(seconds=60)
   self.call('QC1','attendance',action='heartbeat',nonce=row['nonce'],**payload)
  row=self.rows('employee_attendance')[0];self.assertEqual(row['status'],'Present');self.assertGreater(row['seconds'],1800)
  self.time+=dt.timedelta(days=1)
  self.call('QC1','attendance',action='out');self.assertTrue(self.rows('employee_attendance')[0]['out_at'])
  with self.assertRaises(ValueError):self.call('QC2','attendance',action='start',**payload)
  self.call('QC2','regularize',date='2026-10-13',in_time='09:00',out_time='17:00',reason='GPS inaccurate')
  rid=self.rows('attendance_requests')[0]['id']
  with self.assertRaises(access.AccessError):self.call('QC2','regularize',id=rid,status='Approved',notes='Self approve')
  self.call('HR','regularize',id=rid,status='Approved',notes='Verified gate register')
  self.assertTrue(next(r for r in self.rows('employee_attendance') if r['user_id']==self.users['QC2']['id'])['regularized'])
 def test_interrupted_attendance_and_payroll_lifecycle(self):
  self.call('HR','pin',plant_id='solu',latitude=18.6,longitude=73.8)
  payload=dict(plant_id='solu',latitude=18.6,longitude=73.8,accuracy=5)
  self.call('QC1','attendance',action='start',**payload);r=self.rows('employee_attendance')[0]
  self.time+=dt.timedelta(seconds=121);self.call('QC1','attendance',action='heartbeat',nonce=r['nonce'],**payload)
  self.assertEqual(self.rows('employee_attendance')[0]['status'],'Interrupted')
  uid=self.users['QC1']['id']
  with self.assertRaises(access.AccessError):self.call('QC1','salary',user_id=uid)
  self.call('HR','salary',user_id=uid,mode='Monthly',rate=26000,allowance=1000,deduction=500,overtime_rate=100,effective_from='2026-10-01')
  self.call('HR','payroll',user_id=uid,month='2026-10',working_days=26,payable_days=25,overtime_hours=2,additional_deduction=0,notes='Attendance reviewed')
  r=self.rows('payroll_runs')[0];self.assertEqual(r['net_paise'],2570000)
  with self.assertRaises(ValueError):self.call('HR','payroll',user_id=uid,month='2026-10')
  self.call('HR','payroll',id=r['id'],action='Approve',notes='Checked');self.call('Admin','payroll',id=r['id'],action='Paid',notes='Transfer complete',reference='BANK-TEST')
  self.assertEqual(self.rows('payroll_runs')[0]['status'],'Paid')
  with self.assertRaises(ValueError):self.call('HR','payroll',id=r['id'],action='Void',notes='No')
  self.call('HR','salary',user_id=uid,mode='Daily',rate=1000,allowance=0,deduction=0,overtime_rate=100,effective_from='2026-10-01')
  self.call('HR','payroll',user_id=uid,month='2026-11',working_days=26,payable_days=20.5,overtime_hours=1.5,notes='Daily wages reviewed')
  self.assertEqual(self.rows('payroll_runs')[-1]['net_paise'],2065000)
 def test_in_app_reminders_owner_read_receipts_and_completion(self):
  jid=self.store.run(lambda c:c.insert('work_jobs',flow_version=2,title='Test',po_number='TEST',due='2026-10-15',stage='QC approval',assignments={'QC':self.users['QC1']['id'],'Design':self.users['Design']['id']}))
  def reminders(who):return self.store.run(lambda c:h.alerts(c,c.all('work_jobs'),self.users[who]))
  self.assertEqual(len(reminders('QC1')),1);self.assertEqual(reminders('QC2'),[]);self.assertEqual(len(reminders('Admin')),1)
  alert=reminders('QC1')[0];self.assertFalse(alert['read'])
  self.call('QC1','read-alert',key=alert['key']);self.call('QC1','read-alert',key=alert['key'])
  self.assertTrue(reminders('QC1')[0]['read']);self.assertEqual(len(self.rows('alert_reads')),1)
  with self.assertRaises(access.AccessError):self.call('QC2','read-alert',key=alert['key'])
  self.time+=dt.timedelta(days=1);self.assertFalse(reminders('QC1')[0]['read'])
  self.store.run(lambda c:c.update('work_jobs',{'id':jid},{'due':'2026-12-01'}));self.assertEqual(reminders('QC1'),[])
  self.store.run(lambda c:c.update('work_jobs',{'id':jid},{'due':'2026-10-14','stage':'Completed'}));self.assertEqual(reminders('Admin'),[])

if __name__=='__main__':unittest.main()
