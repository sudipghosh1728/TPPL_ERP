"""Shared report drafts with unrestricted layouts and explicit QC review."""
import copy,re
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
 if edit and row['version']!=version:raise ValueError('Another user changed this report. Reopen it before saving; your unsaved cells are still on screen.')
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
 row=get(c,rid,user);images,notes=sheet.view_images(row['source'],row['model'])
 return dict(report={**metadata(row),'model':row['model']},images=images,warnings=notes,calculated=sheet.calculate(row['model']),history=c.all('report_workbook_audit',{'report_id':row['id']},projection={'previous_model':0},sort=[('id',-1)]))

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
 if not any(cell['v'].strip() for s in row['model']['sheets'] for cell in s['cells'].values()):raise ValueError('Add report content before approval')
 if any(isinstance(v,str) and v.startswith('#') for s in sheet.calculate(row['model']).values() for v in s.values()):raise ValueError('Resolve unsupported or invalid formulas before approval')
 c.update('report_workbooks',{'id':row['id']},{'status':'Approved','approved_by':user['name'],'approved_at':m.now(),'review_notes':notes,'updated_at':m.now()},inc={'version':1})
 audit(c,{**row,'version':row['version']+1},user,'Approved report',notes)
 return {'id':row['id']}

def duplicate(c,d,user):
 row=get(c,d.get('id'),user,True,d.get('version'))
 new={k:copy.deepcopy(v) for k,v in row.items() if k not in ('id','_revision','approved_by','approved_at','review_notes')}
 new.update(name=(row['name']+' · revised draft')[:160],status='Draft',version=1,revision_of=row['id'],created_at=m.now(),updated_at=m.now(),created_by=user['name'],created_by_id=user['id'])
 rid=c.insert('report_workbooks',**new);audit(c,{**new,'id':rid},user,'Copied content into revised draft')
 return {'id':rid}

def export(c,rid,user):
 row=get(c,rid,user);name=re.sub(r'[^\w .-]','_',row['name'])[:120]
 return {'_download':{'name':f'{name}-{row["status"]}-v{row["version"]}.xlsx','content':sheet.export(row['source'],row['model'])}}

def archive(z,c,jid):
 import json
 rows=c.all('report_workbooks',{'job_id':jid})
 z.writestr('report-workshop/records.json',json.dumps([{**metadata(r),'model':r['model']} for r in rows],indent=2,default=str))
 z.writestr('report-workshop/history.json',json.dumps(c.all('report_workbook_audit',{'job_id':jid}),indent=2,default=str))
 for row in rows:
  z.writestr(f'report-workshop/{row["id"]}-original.xlsx',row['source'])
  z.writestr(f'report-workshop/{row["id"]}-{row["status"]}.xlsx',sheet.export(row['source'],row['model']))

HANDLERS={'create':create,'save':save,'approve':approve,'duplicate':duplicate}
