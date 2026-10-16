"""Private in-application reminders; sender identity comes only from the session."""
import access, manufacturing as m
from storage import identifier

def tone(sender_role, recipient_role):
 return 'red' if sender_role=='Admin' else ('neutral' if sender_role==recipient_role else 'yellow')

def inbox(c,user):
 rows=c.all('reminders',{'recipient_id':user['id']},sort=[('id',-1)])[:200]
 return [{**r,'tone':tone(r['sender_role'],user['role'])} for r in rows]

def state(c,data,user):
 data['reminders']=inbox(c,user)
 data['reminder_directory']=c.all('users',{'active':1},projection={'id':1,'name':1,'role':1},sort=[('name',1)])

def send(c,d,user):
 message=m.text(d,'message')
 if d.get('recipient_id'):
  recipients=c.all('users',{'id':identifier(d['recipient_id']),'active':1},projection={'id':1,'role':1})
 else:
  department=d.get('department')
  if department not in access.ROLES:raise ValueError('Choose a person or department')
  recipients=c.all('users',{'role':department,'active':1},projection={'id':1,'role':1})
 recipients=[r for r in recipients if r['id']!=user['id']]
 if not recipients:raise ValueError('No other active users in this destination')
 job_id=identifier(d['job_id']) if d.get('job_id') else None
 if job_id:m.get_job(c,job_id,user)
 for recipient in recipients:
  if job_id:m.get_job(c,job_id,recipient)
  c.insert('reminders',recipient_id=recipient['id'],sender_id=user['id'],sender_name=user['name'],sender_role=user['role'],message=message,job_id=job_id,created_at=m.now(),read_at='')

def read(c,d,user):
 row=c.one('reminders',{'id':identifier(d.get('id')),'recipient_id':user['id']})
 if not row:raise ValueError('Reminder not found')
 c.update('reminders',{'id':row['id']},{'read_at':m.now()})

HANDLERS={'send':send,'read':read}
