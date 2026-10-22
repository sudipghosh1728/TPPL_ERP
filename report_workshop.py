"""Shared report drafts with unrestricted layouts and explicit QC review."""
import base64,binascii,copy,pathlib,re
import access,hr_ops,manufacturing as m,report_sheet as sheet
from storage import identifier

COLLECTIONS=('report_workbooks','report_workbook_audit')

def project(c,jid,user,edit=False):
 if not jid:return None
 job=m.get_job(c,jid,user)
 if edit and job['stage']=='Completed':raise ValueError('Completed project reports are read-only')
 return job

def get(c,rid,user,edit=False,version=None):
 row=c.one('report_workbooks',{'id':identifier(rid)})
 if not row:raise ValueError('Report workbook not found')
 project(c,row.get('job_id'),user,edit)
 if edit and row['version']!=version:raise ValueError('Another user changed this report. Reopen it before uploading or approving.')
 return row

def audit(c,row,user,action,notes='',previous_model=None):
 c.insert('report_workbook_audit',report_id=row['id'],job_id=row.get('job_id'),actor_id=user['id'],actor=user['name'],action=action,notes=str(notes)[:4000],created_at=m.now(),version=row['version'],**({'previous_model':previous_model} if previous_model else {}))
 if row.get('job_id'):
  m.history(c,row['job_id'],user,'Report workshop: '+action,row['name']);m.bump(c,row['job_id'])

def metadata(row):return {k:v for k,v in row.items() if k not in ('source','model','_revision')}

def listing(c,user):
 jobs={j['id']:j for j in c.all('work_jobs')}
 return [r for r in c.all('report_workbooks',projection={'source':0,'model':0},sort=[('id',-1)]) if not r.get('job_id') or (r['job_id'] in jobs and m.visible(jobs[r['job_id']],user))]

def detail(c,rid,user):
 row=get(c,rid,user)
 batch=c.one('qc_batches',{'id':row['batch_id'],'job_id':row.get('job_id')}) if row.get('batch_id') else None
 return dict(report=metadata(row),batch=batch,history=c.all('report_workbook_audit',{'report_id':row['id']},projection={'previous_model':0},sort=[('id',-1)]))

def upload(c,d,user):
 import qc_ops as q
 prior=get(c,d['id'],user,True,d.get('version')) if d.get('id') else None
 if prior and prior.get('mode')!='uploaded':raise ValueError('Upload this as a new report; the earlier workbook remains available to download')
 name=str(d.get('name','')).strip();category=str(d.get('category','Other')).strip()
 if not name or len(name)>160:raise ValueError('Enter a report name (up to 160 characters)')
 if not category or len(category)>80:raise ValueError('Enter a report type (up to 80 characters)')
 notes=str(d.get('notes','')).strip()
 if len(notes)>4000:raise ValueError('Notes must be under 4000 characters')
 file=d.get('file')
 if not isinstance(file,dict):raise ValueError('Choose a report file to upload')
 filename=re.sub(r'[\x00-\x1f<>:"|?*]','_',str(file.get('name','')).replace('\\','/').split('/')[-1])[:180]
 if pathlib.Path(filename).suffix.lower() not in {'.pdf','.xlsx','.xls','.docx','.doc','.csv','.txt','.png','.jpg','.jpeg','.webp','.ods','.odt'}:raise ValueError('Choose a PDF, Excel, Word, CSV, text or image report')
 try:raw=base64.b64decode(file.get('content',''),validate=True)
 except (ValueError,TypeError,binascii.Error):raise ValueError('Invalid report file data')
 if not 0<len(raw)<=3*1024*1024:raise ValueError('Report must be between 1 byte and 3 MB')
 jid=prior.get('job_id') if prior else d.get('job_id');bid=prior.get('batch_id') if prior else d.get('batch_id');b=None
 job=project(c,jid,user,True)
 if bid:
  b,job=q.batch(c,{'batch_id':bid,'version':d.get('batch_version')},user,True,author=True)
  if not jid or job['id']!=identifier(jid):raise ValueError('Choose a batch belonging to the selected project')
  if prior and b.get('current_upload')!=prior['id']:raise ValueError('A newer report exists for this batch. Open the latest report before revising it.')
 rid=c.insert('report_workbooks',name=name,category=category,notes=notes,mode='uploaded',source=raw,source_name=filename,size=len(raw),job_id=job['id'] if job else None,batch_id=b['id'] if b else None,status='Draft',version=1,revision_of=prior['id'] if prior else None,created_at=m.now(),updated_at=m.now(),created_by=user['name'],created_by_id=user['id'])
 row=c.one('report_workbooks',{'id':rid});audit(c,row,user,'Uploaded revised report' if prior else 'Uploaded report',notes)
 if b:
  c.update('qc_batches',{'id':b['id']},{'current_upload':rid});q.invalidate(c,b,job);q.log(c,b,user,'Report uploaded for QC review',name)
 return {'id':rid}

def create(c,d,user):
 name=str(d.get('name','')).strip()
 if not name or len(name)>160:raise ValueError('Enter a report name (up to 160 characters)')
 job=project(c,d.get('job_id'),user,True);raw=sheet.file_bytes(d['file']) if d.get('file') else sheet.blank()
 model=sheet.read(raw);model=sheet.validate(model,model)
 rid=c.insert('report_workbooks',name=name,job_id=job['id'] if job else None,source=raw,source_name=str((d.get('file') or {}).get('name','Blank workbook.xlsx'))[:180],model=model,status='Draft',version=1,created_at=m.now(),updated_at=m.now(),created_by=user['name'],created_by_id=user['id'])
 row=c.one('report_workbooks',{'id':rid});audit(c,row,user,'Created draft')
 return {'id':rid}

def save(c,d,user):
 row=get(c,d.get('id'),user,True,d.get('version'))
 if row.get('mode')=='uploaded':raise ValueError('Use Upload revised report to replace this file')
 if row['status']!='Draft':raise ValueError('Approved reports are locked. Make a revised draft first.')
 model=sheet.validate(d.get('model'),sheet.read(row['source']))
 # Sheet renaming must not silently break existing cross-sheet formulas.
 old_names={s['id']:s['name'] for s in row['model']['sheets']}
 renamed={old_names[s['id']]:s['name'] for s in model['sheets'] if s['id'] in old_names and old_names[s['id']]!=s['name']}
 for s in model['sheets']:
  for cell in s['cells'].values():
   if cell['t']=='f':
    for old,new in renamed.items():
     pattern=r"(?<![A-Za-z0-9_'])"+re.escape("'"+old.replace("'","''")+"'")+r'!|(?<![A-Za-z0-9_\x27])'+re.escape(old)+r'!'
     cell['v']=re.sub(pattern,lambda _:"'"+new.replace("'","''")+"'!",cell['v'])
 c.update('report_workbooks',{'id':row['id']},{'model':model,'updated_at':m.now(),'updated_by':user['name']},inc={'version':1})
 audit(c,{**row,'version':row['version']+1},user,'Saved draft',previous_model=row['model'])
 return {'id':row['id']}

def approve(c,d,user):
 access.require(user,('QC',));row=get(c,d.get('id'),user,True,d.get('version'))
 if row['status']!='Draft':raise ValueError('This report is already approved')
 job=project(c,row.get('job_id'),user,True)
 if job:hr_ops.assigned(c,job,user)
 notes=str(d.get('notes','')).strip()
 if not notes or len(notes)>4000:raise ValueError('Enter review notes confirming the report contents were checked (up to 4000 characters)')
 snapshot={}
 if row.get('mode')=='uploaded':
  if row.get('batch_id'):
   import qc_ops as q
   b,job=q.batch(c,{'batch_id':row['batch_id'],'version':d.get('batch_version')},user,True)
   if b.get('current_upload')!=row['id']:raise ValueError('Approve the latest uploaded report for this batch')
   errors=[e for e in q.release_errors(c,b,check_steps=False) if e!='Approve the current inspection report']
   if errors:raise ValueError('; '.join(errors))
   snapshot={'snapshot_batch':b,'snapshot_trace':q.traces(c,b)}
   q.log(c,b,user,'Uploaded report approved',row['name']+' · '+notes)
 else:
  if not any(cell['v'].strip() for s in row['model']['sheets'] for cell in s['cells'].values()):raise ValueError('Add report content before approval')
  if any(isinstance(v,str) and v.startswith('#') for s in sheet.calculate(row['model']).values() for v in s.values()):raise ValueError('Resolve unsupported or invalid formulas before approval')
 c.update('report_workbooks',{'id':row['id']},{'status':'Approved','approved_by':user['name'],'approved_at':m.now(),'review_notes':notes,'updated_at':m.now(),**snapshot},inc={'version':1})
 audit(c,{**row,'version':row['version']+1},user,'Approved report',notes)
 return {'id':row['id']}

def duplicate(c,d,user):
 row=get(c,d.get('id'),user,True,d.get('version'))
 if row.get('mode')=='uploaded':raise ValueError('Choose the revised file using Upload revised report')
 new={k:copy.deepcopy(v) for k,v in row.items() if k not in ('id','_revision','approved_by','approved_at','review_notes')}
 new.update(name=(row['name']+' · revised draft')[:160],status='Draft',version=1,revision_of=row['id'],created_at=m.now(),updated_at=m.now(),created_by=user['name'],created_by_id=user['id'])
 rid=c.insert('report_workbooks',**new);audit(c,{**new,'id':rid},user,'Copied content into revised draft')
 return {'id':rid}

def export(c,rid,user):
 row=get(c,rid,user);name=re.sub(r'[^\w .-]','_',row['name'])[:120]
 if row.get('mode')=='uploaded':return {'_download':{'name':row['source_name'],'content':row['source']}}
 return {'_download':{'name':f'{name}-{row["status"]}-v{row["version"]}.xlsx','content':sheet.export(row['source'],row['model'])}}

def archive(z,c,jid,batch_id=None):
 import json
 rows=c.all('report_workbooks',{'job_id':jid,**({'batch_id':batch_id} if batch_id else {})})
 z.writestr('report-workshop/records.json',json.dumps([{**metadata(r),**({'model':r['model']} if 'model' in r else {})} for r in rows],indent=2,default=str))
 z.writestr('report-workshop/history.json',json.dumps(c.all('report_workbook_audit',{'report_id':{'$in':[r['id'] for r in rows]}}),indent=2,default=str))
 for row in rows:
  if row.get('mode')=='uploaded':
   z.writestr(f'uploaded-reports/{row["id"]}-{row["status"]}-{row["source_name"]}',row['source']);continue
  z.writestr(f'report-workshop/{row["id"]}-original.xlsx',row['source'])
  z.writestr(f'report-workshop/{row["id"]}-{row["status"]}.xlsx',sheet.export(row['source'],row['model']))

HANDLERS={'upload':upload,'create':create,'save':save,'approve':approve,'duplicate':duplicate}
