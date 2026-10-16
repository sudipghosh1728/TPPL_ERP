"""Plant projects, QC gates, inspection calls, maintenance and project archives."""
import datetime, io, json, zipfile
import access, manufacturing as m, store_catalog, hr_ops
from storage import identifier

PLANTS=[dict(id='talawade',name='Unit I · Talawade, Pune',area='40,000 sq. ft.',capabilities='Profile cutting, bending and machining',cranes='Up to 20 tonnes'),dict(id='solu',name='Unit II · Solu, Alandi',area='160,000 sq. ft.',capabilities='Machining, welding, painting and shot blasting',cranes='Up to 40 tonnes'),dict(id='chakan',name='Unit III · Chakan, Wasuli',area='46,000 sq. ft.',capabilities='Machining and fabrication',cranes='10 tonnes'),dict(id='khandala',name='Unit IV · Khandala, Satara',area='70,000 sq. ft.',capabilities='Heavy machining, bending and laser cutting',cranes='Up to 32 tonnes')]
STAGES=['Design review','Admin review','Accounts review','Maintenance review','HR review','QC approval','Store issue','Fabrication execution','Machining execution','QC inspection','Packing & dispatch','Completed']
ROUTES={'Fabrication only':False,'Fabrication + machining':True,'Machining only':True}
TARGETS={'Design':'Design review','Store':'Store issue','Fabrication':'Fabrication execution','Machining':'Machining execution','QC':'QC inspection','Admin':'Admin review','Accounts':'Accounts review','Maintenance':'Maintenance review','HR':'HR review'}
REQUEST_TARGETS={role:tuple(access.ROLES) for role in access.ROLES}

def plant(value):
 if value not in {p['id'] for p in PLANTS}:raise ValueError('Choose a plant')
 return value

def date(value):return datetime.date.fromisoformat(str(value)).isoformat()
def project(c,d,user):
 j=m.get_job(c,d.get('job_id'),user)
 if j.get('flow_version')!=2:raise ValueError('Use the earlier workflow for this legacy job')
 return j

def notify(c,j,user,message,roles):
 c.insert('project_notifications',job_id=j['id'],plant_id=j['plant_id'],message=message,roles=list(roles),actor=user['name'],created_at=m.now())

def record(c,j,user,message,notes=''):
 m.bump(c,j['id']);m.history(c,j['id'],user,message,notes)

def open_job(j):
 if j['stage']=='Completed':raise ValueError('This project is completed')

def create(c,d,user):
 access.require(user,('Design',))
 route=d.get('route')
 if route not in ROUTES:raise ValueError('Choose the production route')
 jid=c.insert('work_jobs',flow_version=2,plant_id=plant(d.get('plant_id')),title=m.text(d,'title'),customer=m.text(d,'customer'),po_number=m.text(d,'po_number'),quantity=m.whole(d.get('quantity')),due=date(d.get('due')),revised_due=date(d['revised_due']) if d.get('revised_due') else '',route=route,machining_required=int(ROUTES[route]),machining_completed=False,final_inspection=False,created_by=user['id'],created_at=m.now(),instructions=str(d.get('instructions',''))[:4000])
 m.upload(c,jid,user,'PO',d.get('file'));m.history(c,jid,user,'Project created → Design review')

def pending(c,j):return c.one('project_requests',{'job_id':j['id'],'status':'Pending'})

def request(c,d,user):
 j=project(c,d,user);m.version(j,d);open_job(j)
 access.require(user,('Design','Machining','Fabrication','QC','Store','Accounts','Maintenance','HR'))
 target=d.get('target')
 if target not in (access.ROLES if user['role']=='Admin' else REQUEST_TARGETS.get(user['role'],())):raise ValueError('Choose an allowed destination department')
 if pending(c,j):raise ValueError('QC must decide the current request first')
 kind=d.get('kind','Handoff')
 if kind not in ('Handoff','Rework'):raise ValueError('Choose a handoff or rework request')
 c.insert('project_requests',job_id=j['id'],target=target,kind=kind,notes=m.text(d,'notes'),status='Pending',from_stage=j['stage'],created_by=user['id'],actor=user['name'],department=user['role'],created_at=m.now())
 c.update('work_jobs',{'id':j['id']},{'stage':'QC approval','final_inspection':False})
 record(c,j,user,kind+' requested from '+target+' · awaiting QC',d['notes']);notify(c,j,user,kind+' approval requested for '+target,('QC','Admin'))

def submit(c,d,user):
 access.require(user,('Design',));j=project(c,d,user);m.version(j,d);open_job(j)
 if j['stage']!='Design review':raise ValueError('Return the project to Design review first')
 if not c.one('job_documents',{'job_id':j['id'],'kind':{'$in':['PO','Revised PO']}}):raise ValueError('Upload the customer PO before release')
 req=c.one('requirements',{'job_id':j['id'],'$expr':{'$lt':['$issued','$quantity']}})
 target='Store' if req else ('Machining' if j['route']=='Machining only' else 'Fabrication')
 request(c,{**d,'target':target},user)

def decide(c,d,user):
 access.require(user,('QC',));j=project(c,d,user);m.version(j,d)
 hr_ops.assigned(c,j,user)
 r=c.one('project_requests',{'id':identifier(d.get('request')),'job_id':j['id'],'status':'Pending'})
 if not r:raise ValueError('This request has already been decided')
 decision=d.get('decision')
 if decision not in ('Approved','Rejected'):raise ValueError('Choose approve or reject')
 notes=m.text(d,'notes')
 stage=TARGETS[r['target']] if decision=='Approved' else r['from_stage']
 c.update('project_requests',{'id':r['id']},{'status':decision,'reviewer':user['name'],'review_notes':notes,'decided_at':m.now()})
 values={'stage':stage}
 if decision=='Approved' and r['target'] in ('Store','Fabrication','Machining'):
  next_stage=stage if r['target']!='Store' else ('Machining execution' if j['route']=='Machining only' else 'Fabrication execution')
  if c.one('requirements',{'job_id':j['id'],'$expr':{'$lt':['$issued','$quantity']}}):values={'stage':'Store issue','store_next_stage':next_stage}
 if decision=='Approved' and r['target']=='Machining':
  values.update(machining_required=True,machining_completed=False)
  if j['route']=='Fabrication only':values['route']='Fabrication + machining'
 c.update('work_jobs',{'id':j['id']},values)
 if decision=='Approved':c.update('requirements',{'job_id':j['id']},{'approved':1})
 record(c,j,user,decision+' request to '+r['target']+' → '+values['stage'],notes);notify(c,j,user,decision+': '+r['target']+' · '+values['stage'],(r['target'],r['department'],'Admin','Store') if values['stage']=='Store issue' else (r['target'],r['department'],'Admin'))

def revise(c,j,user,reason):
 # Revisions remain possible at every stage; active work must be reverified.
 if j['stage'] not in ('Design review','QC approval','Completed'):
  c.update('work_jobs',{'id':j['id']},{'stage':'Design review','final_inspection':False})
 if j['stage']=='QC approval':
  c.update('project_requests',{'job_id':j['id'],'status':'Pending'},{'status':'Superseded','review_notes':reason})
  c.update('work_jobs',{'id':j['id']},{'stage':'Design review','final_inspection':False})
 notify(c,j,user,reason+' · Design resubmission required for active work',('QC','Admin','Design'))

def edit(c,d,user):
 access.require(user,('Design',));j=project(c,d,user);m.version(j,d)
 route=d.get('route',j['route'])
 if route not in ROUTES:raise ValueError('Choose a production route')
 values=dict(title=m.text(d,'title'),po_number=m.text(d,'po_number'),quantity=m.whole(d.get('quantity')),due=date(d.get('due')),revised_due=date(d['revised_due']) if d.get('revised_due') else '',route=route,machining_required=int(ROUTES[route]))
 if route!=j['route']:values['machining_completed']=False
 c.update('work_jobs',{'id':j['id']},values);revise(c,j,user,'Project details revised');record(c,j,user,'Project details revised',d.get('notes',''))

def attach(c,d,user):
 j=project(c,d,user);m.version(j,d);kind=d.get('kind')
 if kind in ('PO','Revised PO','Drawing','Material requirement'):access.require(user,('Design',))
 elif kind=='TC':access.require(user,('Design','Store'))
 elif kind=='EWAY challan':access.require(user,access.ROLES)
 elif kind=='Supporting':access.require(user,('Design','Store','Fabrication','Machining','QC'))
 else:raise ValueError('Choose a document type')
 m.upload(c,j['id'],user,kind,d.get('file'))
 if kind in ('PO','Revised PO','Drawing','Material requirement'):revise(c,j,user,kind+' uploaded')
 record(c,j,user,kind+' uploaded')

def delete_document(c,d,user):
 access.require(user,('Design',));j=project(c,d,user);m.version(j,d)
 doc=c.one('job_documents',{'id':identifier(d.get('document')),'job_id':j['id']})
 if not doc or doc['kind'] not in ('PO','Revised PO'):raise ValueError('Only PO documents may be deleted here')
 reason=m.text(d,'notes');c.delete('job_documents',{'id':doc['id']});revise(c,j,user,'PO deleted')
 record(c,j,user,'Deleted '+doc['kind']+': '+doc['name'],reason)

def requirement(c,d,user):
 access.require(user,('Design',));j=project(c,d,user);m.version(j,d)
 p=c.one('products',{'id':identifier(d.get('product_id'))})
 if not p:raise ValueError('Choose a Store material')
 group=d.get('material_group')
 if group not in ('Raw material','Paint'):raise ValueError('Project Store release is for raw materials and paints only')
 qty=m.whole(d.get('quantity'))
 c.insert('requirements',job_id=j['id'],product_id=p['id'],quantity=qty,department='Design',material_group=group,tc_required=0,tc_notes='',notes=str(d.get('notes',''))[:4000],created_by=user['id'])
 revise(c,j,user,'Material requirement changed');record(c,j,user,'Added '+group+' requirement',p['name']+': '+str(qty))

def issue(c,d,user):
 access.require(user,('Store',));j=project(c,d,user);m.version(j,d)
 hr_ops.assigned(c,j,user)
 if j['stage']!='Store issue':raise ValueError('QC must release this project to Store first')
 r=c.one('requirements',{'id':identifier(d.get('requirement_id')),'job_id':j['id']})
 if not r or not r.get('approved') or r.get('material_group') not in ('Raw material','Paint'):raise ValueError('Choose a QC-approved raw material or paint requirement')
 store_catalog.require_ready(c.one('products',{'id':r['product_id']}))
 m.issue(c,{**d,'requirement_id':r['id']},user)
 if not c.one('requirements',{'job_id':j['id'],'$expr':{'$lt':['$issued','$quantity']}}):
  target=j.get('store_next_stage') or ('Machining execution' if j['route']=='Machining only' else 'Fabrication execution')
  c.update('work_jobs',{'id':j['id']},{'stage':target});m.history(c,j['id'],user,'Materials issued → '+target);notify(c,j,user,'Materials ready · '+target,('Machining' if j['route']=='Machining only' else 'Fabrication','QC','Design'))

def action(c,d,user):
 j=project(c,d,user);m.version(j,d);open_job(j);a=d.get('action');notes=m.text(d,'notes')
 hr_ops.assigned(c,j,user)
 if a=='store_ready':
  access.require(user,('Store',))
  if j['stage']!='Store issue':raise ValueError('QC must release this project to Store first')
  if c.one('requirements',{'job_id':j['id'],'$expr':{'$lt':['$issued','$quantity']}}):raise ValueError('Issue all outstanding raw material and paint requirements first')
  target=j.get('store_next_stage') or ('Machining execution' if j['route']=='Machining only' else 'Fabrication execution')
  c.update('work_jobs',{'id':j['id']},{'stage':target});record(c,j,user,'Store verification complete → '+target,notes);notify(c,j,user,'Store verification complete',('Design','QC','Fabrication','Machining'));return
 if a=='request_done':
  owner={'Admin review':'Admin','Accounts review':'Accounts','Maintenance review':'Maintenance','HR review':'HR'}.get(j['stage'])
  if not owner:raise ValueError('This project has no active support department request')
  access.require(user,(owner,));request(c,{**d,'target':'Design'},user);return
 if a=='progress':
  access.require(user,('Fabrication','Machining'))
  if user['role']!='Admin' and j['stage']!=user['role']+' execution':raise ValueError('Your department has not been released to start this process')
  record(c,j,user,user['role']+' progress update',notes);return
 if a in ('fabrication_done','machining_done'):
  role='Fabrication' if a=='fabrication_done' else 'Machining';access.require(user,(role,))
  if j['stage']!=role+' execution':raise ValueError('This process is not active')
  if a=='machining_done':c.update('work_jobs',{'id':j['id']},{'machining_completed':True})
  target='Machining' if a=='fabrication_done' and j['machining_required'] else 'QC'
  request(c,{**d,'target':target},user);return
 if a=='final_inspection':
  access.require(user,('QC',))
  if j['stage']!='QC inspection' and user['role']!='Admin':raise ValueError('Project is not at final inspection')
  if j['machining_required'] and not j.get('machining_completed') and user['role']!='Admin':raise ValueError('Complete machining before final inspection')
  if user['role']!='Admin' and c.one('requirements',{'job_id':j['id'],'$expr':{'$lt':['$issued','$quantity']}}):raise ValueError('Store must issue all approved project materials before final inspection')
  if c.one('inspection_calls',{'job_id':j['id'],'status':{'$in':['Pending Admin','Approved','Rework']}}):raise ValueError('Resolve the outstanding inspection call and record an OK report first')
  if pending(c,j) and user['role']!='Admin':raise ValueError('Decide the pending request first')
  c.update('project_requests',{'job_id':j['id'],'status':'Pending'},{'status':'Superseded','review_notes':'Admin final inspection override: '+notes})
  c.update('work_jobs',{'id':j['id']},{'stage':'Packing & dispatch','final_inspection':True});record(c,j,user,'Final inspection done → Packing & dispatch',notes);notify(c,j,user,'Final inspection done',('Admin','Design','Fabrication'));return
 if a=='dispatch':
  access.require(user,('Fabrication',))
  if j['stage']!='Packing & dispatch' or not j.get('final_inspection'):raise ValueError('Final QC inspection must be completed before dispatch')
  if not c.one('job_documents',{'job_id':j['id'],'kind':'EWAY challan'}):raise ValueError('Upload the EWAY challan before dispatch')
  if pending(c,j):raise ValueError('Resolve pending QC requests before dispatch')
  c.update('work_jobs',{'id':j['id']},{'stage':'Completed','dispatch_at':m.now()});record(c,j,user,'Dispatch done · PO completed',notes)
  row=c.one('settings',{'key':'archive_recipient'});recipient=row['value'] if row else 'sudipghosh1728@gmail.com'
  oid=c.insert('dispatch_outbox',job_id=j['id'],recipient=recipient,status='Queued',created_at=m.now(),version=j['version']+1)
  packet=build_archive(c,j['id'],user)['_download']['content']
  for offset in range(0,len(packet),512*1024):c.insert('dispatch_archives',outbox_id=oid,chunk=offset//(512*1024),content=packet[offset:offset+512*1024])
  notify(c,j,user,'Dispatched · project archive queued for email',('Admin','Design'));return
 if a=='override':
  access.require(user);target=d.get('stage')
  if target not in STAGES[:-1]:raise ValueError('Use dispatch completion to close a project')
  c.update('project_requests',{'job_id':j['id'],'status':'Pending'},{'status':'Superseded','review_notes':'Admin override: '+notes})
  c.update('requirements',{'job_id':j['id']},{'approved':1})
  c.update('work_jobs',{'id':j['id']},{'stage':target,'final_inspection':target=='Packing & dispatch'})
  record(c,j,user,'Admin override → '+target,notes);notify(c,j,user,'Admin override → '+target,('Design','QC','Fabrication','Machining','Store'));return
 raise ValueError('Unknown project action')

def inspection(c,d,user):
 access.require(user,('QC',));j=project(c,d,user);m.version(j,d);open_job(j);a=d.get('action')
 hr_ops.assigned(c,j,user)
 if a=='call':
  if c.one('inspection_calls',{'job_id':j['id'],'status':{'$in':['Pending Admin','Approved','Rework']}}):raise ValueError('Finish the existing inspection call first')
  c.insert('inspection_calls',job_id=j['id'],status='Pending Admin',notes=m.text(d,'notes'),created_by=user['name'],created_at=m.now())
  notify(c,j,user,'Customer inspection call · Admin approval required',('Admin','Design'));record(c,j,user,'Customer inspection call raised',d['notes']);return
 call=c.one('inspection_calls',{'id':identifier(d.get('call_id')),'job_id':j['id']})
 if not call:raise ValueError('Inspection call not found')
 if a=='approve':
  access.require(user)
  if call['status']!='Pending Admin':raise ValueError('This call is not pending Admin approval')
  status='Approved';notes=m.text(d,'notes')
 elif a=='report':
  if call['status'] not in ('Approved','Rework'):raise ValueError('Admin must approve the call first')
  status=d.get('result')
  if status not in ('OK','Rework'):raise ValueError('Select OK or Rework')
  notes=m.text(d,'notes') if status=='Rework' else str(d.get('notes',''))[:4000]
  if status=='Rework':c.update('work_jobs',{'id':j['id']},{'stage':'QC inspection','final_inspection':False})
 else:raise ValueError('Unknown inspection action')
 c.update('inspection_calls',{'id':call['id']},{'status':status,'report':notes,'updated_by':user['name'],'updated_at':m.now()})
 record(c,j,user,'Inspection call '+status,notes);notify(c,j,user,'Inspection call '+status,('Admin','Design','QC'))

def chat(c,d,user):
 j=project(c,d,user)
 c.insert('project_messages',job_id=j['id'],author_id=user['id'],author=user['name'],department=user['role'],body=m.text(d,'message'),created_at=m.now())

def maintenance(c,d,user):
 if not d.get('id'):
  c.insert('maintenance_tickets',plant_id=plant(d.get('plant_id')),category=m.text(d,'category'),equipment=m.text(d,'equipment'),description=m.text(d,'description'),status='QC approval',version=1,created_by=user['id'],requester=user['name'],department=user['role'],created_at=m.now(),updates=[]);return
 t=c.one('maintenance_tickets',{'id':identifier(d['id'])})
 if not t:raise ValueError('Maintenance ticket not found')
 if d.get('version')!=t['version']:raise ValueError('Ticket changed. Refresh before saving.')
 status=d.get('status');notes=m.text(d,'notes')
 if t['status']=='QC approval' and status in ('Open','Rejected'):access.require(user,('QC',))
 elif t['status'] in ('Open','In progress') and status in ('In progress','Resolved'):access.require(user,('Maintenance',))
 elif t['status'] in ('Resolved','Rejected') and status=='QC approval':
  if user['id']!=t['created_by']:access.require(user)
 else:raise ValueError('Invalid ticket transition')
 updates=t['updates']+[dict(status=status,notes=notes,by=user['name'],at=m.now())]
 c.update('maintenance_tickets',{'id':t['id']},{'status':status,'updates':updates},inc={'version':1})

def archive_settings(c,d,user):
 access.require(user);address=m.text(d,'recipient')
 import re
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',address) or len(address)>254:raise ValueError('Enter a valid email address')
 c.update('settings',{'key':'archive_recipient'},{'key':'archive_recipient','value':address},upsert=True)

def build_archive(c,jid,user):
 j=project(c,{'job_id':jid},user)
 if j['stage']!='Completed':raise ValueError('Project archive is available after dispatch')
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('project.json',json.dumps(j,indent=2,default=str))
  for collection in ('requirements','work_history','project_messages','project_requests','inspection_calls'):
   z.writestr(collection+'.json',json.dumps(c.all(collection,{'job_id':j['id']}),indent=2,default=str))
  project_requirements=c.all('requirements',{'job_id':j['id']})
  reqs=[r['id'] for r in project_requirements]
  material_ids=list({r['product_id'] for r in project_requirements})
  z.writestr('materials.json',json.dumps(c.all('products',{'id':{'$in':material_ids}},projection={'price':0}),indent=2,default=str))
  z.writestr('material_issues.json',json.dumps(c.all('material_issues',{'requirement_id':{'$in':reqs}}),indent=2,default=str))
  for doc in c.all('job_documents',{'job_id':j['id']}):z.writestr('documents/'+str(doc['id'])+'-'+doc['name'],doc['content'])
 return {'_download':{'name':f'JOB-{j["id"]:04}-archive.zip','content':output.getvalue()}}

def archive(c,jid,user):
 j=project(c,{'job_id':jid},user)
 rows=c.all('dispatch_outbox',{'job_id':j['id']},sort=[('id',-1)])
 if not rows:raise ValueError('The archive is available after dispatch')
 chunks=c.all('dispatch_archives',{'outbox_id':rows[0]['id']},sort=[('chunk',1)])
 return {'_download':{'name':f'JOB-{j["id"]:04}-archive.zip','content':b''.join(x['content'] for x in chunks)}}

def state(c,data,user):
 data['plants']=PLANTS
 ids=[j['id'] for j in data['work_jobs'] if j.get('flow_version')==2]
 for name in ('project_requests','inspection_calls','dispatch_outbox'):
  data[name]=c.all(name,{'job_id':{'$in':ids}},sort=[('id',-1)])
 data['project_notifications']=c.all('project_notifications',{} if user['role']=='Admin' else {'roles':user['role']},sort=[('id',-1)])[:200] if user else []
 data['maintenance_tickets']=c.all('maintenance_tickets',{} if user['role'] in ('Admin','QC','Maintenance') else {'created_by':user['id']},sort=[('id',-1)])
 data['archive_recipient']=(c.one('settings',{'key':'archive_recipient'}) or {}).get('value','sudipghosh1728@gmail.com') if user['role']=='Admin' else ''

HANDLERS={'create':create,'edit':edit,'attach':attach,'delete-document':delete_document,'requirement':requirement,'issue':issue,'submit':submit,'request':request,'decide':decide,'action':action,'inspection':inspection,'chat':chat,'maintenance':maintenance,'archive-settings':archive_settings}
