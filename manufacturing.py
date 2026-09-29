"""Department workflow, controlled documents, and material requirements."""
import base64, binascii, datetime, pathlib
from access import require, AccessError
from storage import identifier

STAGES=('Design review','Admin revision','Machining requirements','Fabrication review','Machining execution','Fabrication execution','Completed')
EDIT_STAGES={'Design':('Design review',),'Machining':('Machining requirements',),'Fabrication':('Fabrication review',)}

def initialize(c):
    pass  # Collections and indexes are prepared centrally by MongoStore.

def now():return datetime.datetime.now().isoformat(timespec='seconds')
def text(d,key):
    v=str(d.get(key,'')).strip()
    if not v or len(v)>4000:raise ValueError('Enter '+key.replace('_',' '))
    return v
def whole(v):
    try:
        n=int(v)
        if float(v)!=n or not 0<n<=10000000:raise ValueError()
        return n
    except (ValueError,TypeError,OverflowError):raise ValueError('Quantity must be a positive whole number')
def history(c,jid,user,action,notes=''):
    c.insert('work_history',job_id=jid,actor_id=user['id'],actor_name=user['name'],department=user['role'],action=action,notes=str(notes)[:4000],created_at=now())
def visible(job,user):
    role=user['role']
    if role in ('Admin','Design','Fabrication','Store'):return True
    if role=='Machining':return job['machining_required']==1 and job['stage'] not in ('Design review','Admin revision')
    return False
def get_job(c,jid,user):
    job=c.one('work_jobs',{'id':identifier(jid)})
    if not job or not visible(job,user):raise AccessError('Job not available to your department',404)
    return dict(job)
def version(job,d):
    if d.get('version')!=job['version']:raise ValueError('This job has changed. Refresh it before saving.')
def bump(c,jid):c.update('work_jobs',{'id':jid},inc={'version':1})

def upload(c,jid,user,kind,file):
    if kind not in ('PO','Drawing','TC','Supporting'):raise ValueError('Invalid document type')
    if not isinstance(file,dict):raise ValueError('Choose a document to upload')
    name=str(file.get('name','')).replace('\\','/').split('/')[-1][:180]
    extensions={'.pdf','.png','.jpg','.jpeg','.txt','.dwg','.dxf','.step','.stp','.xlsx','.docx','.csv'}
    if pathlib.Path(name).suffix.lower() not in extensions:raise ValueError('Use PDF, image, text, CAD, Word, or Excel documents')
    try:content=base64.b64decode(file.get('content',''),validate=True)
    except (ValueError,binascii.Error):raise ValueError('Invalid document data')
    if not 0<len(content)<=3*1024*1024:raise ValueError('Document must be between 1 byte and 3 MB')
    return c.insert('job_documents',job_id=jid,kind=kind,name=name,mime='application/octet-stream',content=content,size=len(content),uploaded_by=user['id'],created_at=now())

def create(c,d,user):
    require(user)
    due=datetime.date.fromisoformat(text(d,'due')).isoformat()
    jid=c.insert('work_jobs',title=text(d,'title'),customer=text(d,'customer'),po_number=text(d,'po_number'),due=due,instructions=str(d.get('instructions',''))[:4000],created_by=user['id'],created_at=now())
    upload(c,jid,user,'PO',d.get('file'))
    history(c,jid,user,'PO uploaded → Design review',d.get('instructions',''))

def attach(c,d,user):
    job=get_job(c,d.get('job_id'),user);version(job,d);kind=d.get('kind')
    if kind=='PO':
        require(user)
        if job['stage'] not in ('Admin revision','Design review'):raise ValueError('PO revisions require a return to Admin first')
    elif kind=='Drawing':
        require(user,('Design',))
        if job['stage']!='Design review':raise ValueError('Drawings are uploaded during Design review')
    elif kind=='TC':
        require(user,('Store',))
        if job['stage']=='Completed':raise ValueError('Completed jobs cannot receive new certificates')
    else:
        require(user,('Design','Machining','Fabrication'))
        if job['stage']=='Completed':raise ValueError('Completed jobs are read-only')
    upload(c,job['id'],user,kind,d.get('file'));bump(c,job['id']);history(c,job['id'],user,kind+' document uploaded')

def requirement(c,d,user):
    require(user,('Design','Machining','Fabrication'))
    job=get_job(c,d.get('job_id'),user);version(job,d)
    dept=user['role'] if user['role']!='Admin' else d.get('department')
    if job['stage'] not in EDIT_STAGES.get(dept,()):raise ValueError('Requirements can only be changed by the department currently reviewing this job')
    product=c.one('products',{'id':identifier(d.get('product_id'))})
    if not product:raise ValueError('Choose a material from the Store catalogue')
    qty=whole(d.get('quantity'));tc=d.get('tc_required',False)
    if type(tc) is not bool:raise ValueError('Select whether a test certificate is required')
    notes=str(d.get('notes',''))[:4000];tc_notes=str(d.get('tc_notes',''))[:4000]
    if d.get('id'):
        r=c.one('requirements',{'id':identifier(d['id']),'job_id':job['id']})
        if not r or r['department']!=dept or r['issued']:raise ValueError('You can only update your department’s unissued requirement')
        c.update('requirements',{'id':r['id']},{'product_id':product['id'],'quantity':qty,'tc_required':int(tc),'tc_notes':tc_notes,'notes':notes,'approved':0})
    else:
        c.insert('requirements',job_id=job['id'],product_id=product['id'],quantity=qty,department=dept,tc_required=int(tc),tc_notes=tc_notes,notes=notes,created_by=user['id'])
    bump(c,job['id']);history(c,job['id'],user,'Material requirement saved',f'{product["name"]}: {qty} units. '+notes)

def transition(c,d,user):
    job=get_job(c,d.get('job_id'),user);version(job,d);action=d.get('action');stage=job['stage'];notes=str(d.get('notes','')).strip()[:4000]
    if not notes:raise ValueError('Add a review note for the next department')
    target=None
    if action=='design_approve':
        require(user,('Design',))
        if stage!='Design review':raise ValueError('Job is not awaiting Design review')
        machining=d.get('machining_required')
        if type(machining) is not bool:raise ValueError('Choose whether machining is required')
        if machining and not c.one('job_documents',{'job_id':job['id'],'kind':'Drawing'}):raise ValueError('Upload the approved drawing before routing a job to Machining')
        c.update('work_jobs',{'id':job['id']},{'machining_required':int(machining),'design_notes':notes})
        target='Machining requirements' if machining else 'Fabrication review'
    elif action=='return_admin':
        require(user,('Design',))
        if stage!='Design review':raise ValueError('Only Design review can return a PO to Admin')
        target='Admin revision'
    elif action=='resubmit':
        require(user)
        if stage!='Admin revision':raise ValueError('Job is not awaiting an Admin revision')
        target='Design review'
    elif action=='machining_submit':
        require(user,('Machining',))
        if stage!='Machining requirements':raise ValueError('Job is not awaiting Machining requirements')
        if not c.one('requirements',{'job_id':job['id'],'department':'Machining'}):raise ValueError('Add basic machining material and TC requirements first')
        target='Fabrication review'
    elif action=='fabrication_approve':
        require(user,('Fabrication',))
        if stage!='Fabrication review':raise ValueError('Job is not awaiting Fabrication review')
        if not c.one('requirements',{'job_id':job['id']}):raise ValueError('Add at least one material requirement before approval')
        c.update('requirements',{'job_id':job['id']},{'approved':1})
        target='Machining execution' if job['machining_required'] else 'Fabrication execution'
    elif action=='request_changes':
        require(user,('Fabrication',))
        if stage!='Fabrication review':raise ValueError('Changes can only be requested during Fabrication review')
        target='Machining requirements' if job['machining_required'] else 'Design review'
    elif action=='machining_complete':
        require(user,('Machining',))
        if stage!='Machining execution':raise ValueError('Job is not ready for machining completion')
        if c.one('requirements',{'job_id':job['id'],'department':{'$in':['Machining','Design']},'$expr':{'$lt':['$issued','$quantity']}}):raise ValueError('Store must issue all machining and design materials before completion')
        target='Fabrication execution'
    elif action=='fabrication_complete':
        require(user,('Fabrication',))
        if stage!='Fabrication execution':raise ValueError('Job is not ready for fabrication completion')
        if c.one('requirements',{'job_id':job['id'],'$expr':{'$lt':['$issued','$quantity']}}):raise ValueError('Store must issue all outstanding materials before completion')
        target='Completed'
    else:raise ValueError('Unknown workflow action')
    c.update('work_jobs',{'id':job['id']},{'stage':target},inc={'version':1})
    history(c,job['id'],user,stage+' → '+target,notes)

def issue(c,d,user):
    require(user,('Store',))
    r=c.one('requirements',{'id':identifier(d.get('requirement_id'))})
    if not r:raise ValueError('Requirement not found')
    job=get_job(c,r['job_id'],user);version(job,d)
    if not r['approved'] or job['stage'] not in ('Machining execution','Fabrication execution'):raise ValueError('Fabrication must approve requirements before Store can issue material')
    qty=whole(d.get('quantity'))
    if qty>r['quantity']-r['issued']:raise ValueError('Quantity exceeds the remaining requirement')
    tc_id=identifier(d['tc_document_id']) if d.get('tc_document_id') else None;reference=str(d.get('tc_reference','')).strip()[:200]
    if r['tc_required'] and (not tc_id or not reference):raise ValueError('Attach a Test Certificate and enter its reference before issuing this material')
    if tc_id and not c.one('job_documents',{'id':tc_id,'job_id':job['id'],'kind':'TC'}):raise ValueError('Choose a Test Certificate attached to this job')
    if not c.update('products',{'id':r['product_id'],'stock':{'$gte':qty}},inc={'stock':-qty}):raise ValueError('Insufficient stock. Receive material into Store first.')
    c.update('requirements',{'id':r['id']},inc={'issued':qty})
    c.insert('movements',product_id=r['product_id'],quantity=-qty,reason=f'Job JOB-{job["id"]:04} / requirement {r["id"]}',date=datetime.date.today().isoformat())
    c.insert('material_issues',requirement_id=r['id'],quantity=qty,tc_document_id=tc_id,tc_reference=reference,issued_by=user['id'],created_at=now())
    bump(c,job['id']);history(c,job['id'],user,f'Issued {qty} units against requirement {r["id"]}',reference)

def state(c,data,user):
    query={} if user['role'] in ('Admin','Design','Fabrication','Store') else {'machining_required':1,'stage':{'$nin':['Design review','Admin revision']}} if user['role']=='Machining' else {'id':-1}
    jobs=c.all('work_jobs',query,sort=[('id',-1)])
    ids={j['id'] for j in jobs};data['work_jobs']=jobs
    query={'job_id':{'$in':list(ids)}}
    data['requirements']=c.all('requirements',query,sort=[('id',1)])
    data['job_documents']=c.all('job_documents',query,sort=[('id',1)],projection={'content':0})
    data['work_history']=c.all('work_history',query,sort=[('id',-1)])
    req_ids={r['id'] for r in data['requirements']}
    data['material_issues']=c.all('material_issues',{'requirement_id':{'$in':list(req_ids)}})
