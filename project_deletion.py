"""Admin-only, archived-snapshot deletion of project-owned records."""
import csv,datetime as dt,hashlib,html,io,json,re,secrets,zipfile
import access,manufacturing as m
from storage import identifier

CHUNK_SIZE=512*1024
OWNED=('qc_batches','qc_reports','qc_trace_lots','qc_imports','qc_audit','reminders','requirements','work_history','project_messages','project_requests','inspection_calls','project_notifications','dispatch_outbox','job_documents')
OWNED+=('report_workbooks','report_workbook_audit')
def now():return dt.datetime.now(dt.timezone.utc)
def encoded(value):
 if isinstance(value,bytes):return {'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()}
 if isinstance(value,dt.datetime):return value.isoformat()
 raise TypeError('Unsupported archive value')
def dump(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,default=encoded,indent=2)
def reference(jid):return f'JOB-{jid:04}'

def snapshot(c,jid,user):
 access.require(user)
 j=m.get_job(c,jid,user);jid=j['id']
 queries={name:{'job_id':jid} for name in OWNED}
 reqs=c.all('requirements',{'job_id':jid});rids=[r['id'] for r in reqs]
 outbox=c.all('dispatch_outbox',{'job_id':jid})
 if any(r['status']=='Sending' for r in outbox):raise ValueError('An archive delivery is in progress. Wait for it to finish before deleting this project.')
 queries.update(material_issues={'$or':[{'job_id':jid},{'requirement_id':{'$in':rids}}]},dispatch_archives={'outbox_id':{'$in':[r['id'] for r in outbox]}},alert_reads={'$or':[{'job_id':jid},{'key':{'$regex':r'^\d{4}-\d{2}-\d{2}:'+str(jid)+':'}}]})
 records={name:c.all(name,q,sort=[('id',1)]) for name,q in queries.items()}
 movements=c.all('movements',{'$or':[{'job_id':jid},{'requirement_id':{'$in':rids}},{'reason':{'$regex':'^Job '+reference(jid)+r' / requirement \d+$'}}]},sort=[('id',1)])
 data={'project':j,**records,'stock_movements':movements}
 digest=hashlib.sha256(dump(data).encode()).hexdigest()
 return data,queries,digest

def safe_name(value):
 name=str(value).replace('\\','/').split('/')[-1]
 return re.sub(r'[\x00-\x1f<>:"|?*]','_',name)[:180] or 'document'

def make_zip(c,data,digest,user):
 output=io.BytesIO();jid=data['project']['id'];documents=data['job_documents']
 materials=c.all('products',{'id':{'$in':list({r['product_id'] for r in data['requirements']})}},projection={'price':0},sort=[('id',1)])
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  import report_workshop
  report_workshop.archive(z,c,jid)
  z.writestr('README.txt','Project deletion backup: '+reference(jid)+'\nOpen reports/project-report.html for the readable report. JSON files contain complete structured records. Documents retain their original bytes. Previously queued dispatch ZIPs are in dispatch-archives/.\nShared product, stock movement and accounting records remain in the ERP; deleting a project does not return issued stock or reverse posted accounts.\n')
  z.writestr('manifest.json',dump(dict(project_id=jid,snapshot_sha256=digest,exported_at=now(),exported_by=user['id'],counts={k:len(v) for k,v in data.items() if isinstance(v,list)})))
  for name,records in data.items():z.writestr(name+'.json',dump(records))
  z.writestr('materials.json',dump(materials))
  assignments=data['project'].get('assignments',{})
  z.writestr('assigned_people.json',dump(c.all('users',{'id':{'$in':list(assignments.values())}},projection={'id':1,'name':1,'role':1},sort=[('id',1)])))
  for doc in documents:z.writestr('documents/'+str(doc['id'])+'-'+safe_name(doc['name']),doc['content'])
  for outbox in data['dispatch_outbox']:
   chunks=sorted((r for r in data['dispatch_archives'] if r['outbox_id']==outbox['id']),key=lambda r:r['chunk'])
   if chunks:z.writestr(f'dispatch-archives/{outbox["id"]}.zip',b''.join(r['content'] for r in chunks))
  for name in ('work_history','project_requests','inspection_calls','project_messages','material_issues','stock_movements'):
   rows=data[name];keys=list(dict.fromkeys(k for row in rows for k in row));stream=io.StringIO(newline='');writer=csv.writer(stream)
   writer.writerow(keys)
   # Neutralise spreadsheet formula prefixes in user-entered notes.
   for row in rows:
    values=[str(row.get(k,'')) for k in keys];writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in values])
   z.writestr('reports/'+name+'.csv',stream.getvalue().encode('utf-8-sig'))
  sections=''.join('<h2>'+html.escape(name.replace('_',' ').title())+'</h2><pre>'+html.escape(dump(records))+'</pre>' for name,records in data.items())
  z.writestr('reports/project-report.html','<!doctype html><meta charset="utf-8"><title>Project archive</title><style>body{font:15px system-ui;max-width:1100px;margin:40px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f4;padding:20px}h2{border-bottom:1px solid #ddd}</style><h1>'+reference(jid)+' · '+html.escape(data['project']['title'])+'</h1>'+sections)
 return output.getvalue()

def remove_exports(c,query):
 ids=[r['id'] for r in c.all('project_delete_exports',query)]
 c.delete('project_delete_parts',{'export_id':{'$in':ids}});c.delete('project_delete_exports',query)

def prepare(c,d,user):
 data,queries,digest=snapshot(c,d.get('job_id'),user);jid=data['project']['id']
 packet=make_zip(c,data,digest,user);token=secrets.token_urlsafe(32);expires=now()+dt.timedelta(hours=1)
 remove_exports(c,{'job_id':jid,'user_id':user['id']})
 count=(len(packet)+CHUNK_SIZE-1)//CHUNK_SIZE
 eid=c.insert('project_delete_exports',job_id=jid,user_id=user['id'],token_hash=hashlib.sha256(token.encode()).hexdigest(),snapshot=digest,expires_at=expires,parts=count,downloaded=[])
 for part in range(count):c.insert('project_delete_parts',export_id=eid,part=part,content=packet[part*CHUNK_SIZE:(part+1)*CHUNK_SIZE],expires_at=expires)
 return dict(token=token,parts=count,bytes=len(packet),sha256=hashlib.sha256(packet).hexdigest(),filename=reference(jid)+'-complete-project.zip')

def grant(c,token,user):
 access.require(user)
 if not isinstance(token,str) or len(token)>100:raise ValueError('Download a new project ZIP first')
 row=c.one('project_delete_exports',{'token_hash':hashlib.sha256(token.encode()).hexdigest(),'user_id':user['id']})
 if not row or row['expires_at'].replace(tzinfo=dt.timezone.utc)<=now():raise ValueError('Download a new project ZIP first; this download has expired')
 return row

def download_part(c,token,part,user):
 row=grant(c,token,user)
 if not re.fullmatch(r'\d{1,6}',str(part)) or int(part)>=row['parts']:raise ValueError('Invalid archive part')
 part=int(part);chunk=c.one('project_delete_parts',{'export_id':row['id'],'part':part})
 if not chunk:raise ValueError('Archive part expired. Download a new ZIP.')
 c.update('project_delete_exports',{'id':row['id']},{'downloaded':sorted(set(row['downloaded']+[part]))})
 return {'_download':{'name':'project-archive.part','content':chunk['content']}}

def delete(c,d,user):
 access.require(user);jid=identifier(d.get('job_id'));row=grant(c,d.get('export_token'),user)
 if row['job_id']!=jid or len(row['downloaded'])!=row['parts']:raise ValueError('Download every part of this project ZIP before deleting')
 if d.get('download_confirmed') is not True or d.get('confirmation')!=reference(jid):raise ValueError('Confirm you saved the ZIP and type '+reference(jid))
 data,queries,digest=snapshot(c,jid,user)
 if digest!=row['snapshot']:raise ValueError('Project changed after the ZIP was prepared. Download a fresh ZIP before deleting.')
 c.touch('work_jobs',jid)
 for name,query in queries.items():c.delete(name,query)
 remove_exports(c,{'job_id':jid});c.delete('work_jobs',{'id':jid})
 # A minimal company-wide deletion receipt; no project documents or project payload remains.
 c.insert('activity',message=reference(jid)+' deleted by Admin after archive download',actor_id=user['id'],date=m.now(),archive_sha256=digest)
 return {'ok':True}
