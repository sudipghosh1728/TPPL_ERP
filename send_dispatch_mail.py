"""Explicitly enabled email worker. Never run during the isolated preview.
Queued archives are immutable. Interrupted/uncertain sends are not automatically retried.
"""
import os, pathlib, smtplib, ssl, datetime,hashlib
from email.message import EmailMessage
from pymongo import ReturnDocument
from storage import MongoStore

def configuration():
 values={}
 path=pathlib.Path(__file__).with_name('.env')
 if path.exists():
  for line in path.read_text(encoding='utf-8').splitlines():
   if line.strip() and not line.lstrip().startswith('#') and '=' in line:
    k,v=line.split('=',1);values[k.strip()]=v.strip().strip('"').strip("'")
 values.update(os.environ)
 return values

def send_next(store,settings,transport=None,outbox_id=None):
 if settings.get('ARCHIVE_MAIL_ENABLED')!='true':return 'Disabled'
 for key in ('SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM'):
  if not settings.get(key):raise ValueError('Missing email configuration: '+key)
 query={'status':'Queued'}
 if outbox_id is not None:query.update(id=outbox_id,kind='Project deletion')
 row=store.db.dispatch_outbox.find_one_and_update(query,{'$set':{'status':'Sending','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}},sort=[('id',1)],return_document=ReturnDocument.AFTER)
 if not row:return 'Empty'
 try:
  chunks=store.run(lambda c:c.all('dispatch_archives',{'outbox_id':row['id']},sort=[('chunk',1)]))
  if not chunks:raise ValueError('Archive snapshot missing')
  packet=b''.join(bytes(x['content']) for x in chunks)
  if row.get('archive_sha256') and hashlib.sha256(packet).hexdigest()!=row['archive_sha256']:raise ValueError('Archive integrity check failed')
  deletion=row.get('kind')=='Project deletion'
  msg=EmailMessage();msg['From']=settings['SMTP_FROM'];msg['To']=row['recipient'];msg['Subject']=('Project deleted' if deletion else 'PO completed')+f' · Project JOB-{row["job_id"]:04}'
  msg['Message-ID']=f'<grey-dispatch-{row["id"]}@{settings["SMTP_FROM"].split("@")[-1]}>'
  msg.set_content(('Project '+row.get('project_title','')+' was deleted by '+row.get('deleted_by','Admin')+'. All project documents, reports, approvals and history are in the attached ZIP.') if deletion else 'Packing and dispatch are complete. The project archive is attached.')
  msg.add_attachment(packet,maintype='application',subtype='zip',filename=f'JOB-{row["job_id"]:04}-archive.zip')
  if transport:transport(msg)
  else:
   port=int(settings.get('SMTP_PORT','587'));implicit=port==465
   options={'context':ssl.create_default_context()} if implicit else {}
   with (smtplib.SMTP_SSL if implicit else smtplib.SMTP)(settings['SMTP_HOST'],port,timeout=10,**options) as smtp:
    if not implicit:smtp.starttls(context=ssl.create_default_context())
    smtp.login(settings['SMTP_USER'],settings['SMTP_PASSWORD'])
    if smtp.send_message(msg):raise ValueError('Recipient refused')
 except Exception as exc:
  # A server can accept mail and lose the acknowledgement. Do not blindly resend.
  store.db.dispatch_outbox.update_one({'id':row['id']},{'$set':{'status':'Needs review','error_category':type(exc).__name__}})
  return 'Needs review'
 def accepted(c):
  c.update('dispatch_outbox',{'id':row['id']},{'status':'Sent','sent_at':datetime.datetime.now().isoformat()})
  if row.get('kind')=='Project deletion':c.delete('dispatch_archives',{'outbox_id':row['id']})
 store.run(accepted)
 return 'Sent'

def deliver_after_commit(store,result):
 """No SMTP inside a retryable database transaction, and no failed-mail rollback claim."""
 oid=result.pop('_mail_outbox_id',None)
 if oid is None:return result
 result['deletion_mail_id']=oid
 try:
  status=send_next(store,configuration(),outbox_id=oid)
  if status in ('Disabled','Empty'):
   row=store.db.dispatch_outbox.find_one({'id':oid},{'status':1})
   status=row.get('status','Queued') if row else 'Queued'
  result['deletion_mail_status']=status
 except Exception:
  try:
   row=store.db.dispatch_outbox.find_one({'id':oid},{'status':1})
   result['deletion_mail_status']=row.get('status','Queued') if row else 'Queued'
  except Exception:result['deletion_mail_status']='Needs review'
 return result

if __name__=='__main__':
 settings=configuration()
 if settings.get('ARCHIVE_MAIL_ENABLED')!='true':print('Email worker disabled. No messages sent.')
 else:
  store=MongoStore()
  try:
   import sys,time
   while True:
    print('Archive email:',send_next(store,settings),flush=True)
    if '--watch' not in sys.argv:break
    time.sleep(15)
  finally:store.close()
