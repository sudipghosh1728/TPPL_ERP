"""Explicitly enabled email worker. Never run during the isolated preview.
Queued archives are immutable. Interrupted/uncertain sends are not automatically retried.
"""
import os, pathlib, smtplib, ssl, datetime
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

def send_next(store,settings,transport=None):
 if settings.get('ARCHIVE_MAIL_ENABLED')!='true':return 'Disabled'
 for key in ('SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM'):
  if not settings.get(key):raise ValueError('Missing email configuration: '+key)
 row=store.db.dispatch_outbox.find_one_and_update({'status':'Queued'},{'$set':{'status':'Sending','started_at':datetime.datetime.now().isoformat()}},sort=[('id',1)],return_document=ReturnDocument.AFTER)
 if not row:return 'Empty'
 try:
  chunks=list(store.db.dispatch_archives.find({'outbox_id':row['id']}).sort('chunk',1))
  if not chunks:raise ValueError('Archive snapshot missing')
  msg=EmailMessage();msg['From']=settings['SMTP_FROM'];msg['To']=row['recipient'];msg['Subject']=f'PO completed · Project JOB-{row["job_id"]:04}'
  msg['Message-ID']=f'<grey-dispatch-{row["id"]}@{settings["SMTP_FROM"].split("@")[-1]}>'
  msg.set_content('Packing and dispatch are complete. The project archive is attached.')
  msg.add_attachment(b''.join(bytes(x['content']) for x in chunks),maintype='application',subtype='zip',filename=f'JOB-{row["job_id"]:04}-archive.zip')
  if transport:transport(msg)
  else:
   with smtplib.SMTP(settings['SMTP_HOST'],int(settings.get('SMTP_PORT','587')),timeout=30) as smtp:
    smtp.starttls(context=ssl.create_default_context());smtp.login(settings['SMTP_USER'],settings['SMTP_PASSWORD']);smtp.send_message(msg)
 except Exception as exc:
  # A server can accept mail and lose the acknowledgement. Do not blindly resend.
  store.db.dispatch_outbox.update_one({'id':row['id']},{'$set':{'status':'Needs review','error_category':type(exc).__name__}})
  return 'Needs review'
 store.db.dispatch_outbox.update_one({'id':row['id']},{'$set':{'status':'Sent','sent_at':datetime.datetime.now().isoformat()}})
 return 'Sent'

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
