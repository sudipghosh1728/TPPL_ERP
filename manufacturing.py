"""Department workflow, controlled documents, and material requirements."""
import base64, binascii, datetime, pathlib
from access import require, AccessError

STAGES=('Design review','Admin revision','Machining requirements','Fabrication review','Machining execution','Fabrication execution','Completed')
EDIT_STAGES={'Design':('Design review',),'Machining':('Machining requirements',),'Fabrication':('Fabrication review',)}

def initialize(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS work_jobs(id INTEGER PRIMARY KEY,title TEXT NOT NULL,customer TEXT NOT NULL,po_number TEXT NOT NULL,
      due TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '',stage TEXT NOT NULL DEFAULT 'Design review',
      machining_required INTEGER,design_notes TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,
      created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS job_documents(id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES work_jobs(id),
      kind TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL,uploaded_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS requirements(id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES work_jobs(id),
      product_id INTEGER NOT NULL REFERENCES products(id),quantity INTEGER NOT NULL CHECK(quantity>0),issued INTEGER NOT NULL DEFAULT 0,
      department TEXT NOT NULL,tc_required INTEGER NOT NULL DEFAULT 0,tc_notes TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',
      approved INTEGER NOT NULL DEFAULT 0,created_by INTEGER NOT NULL REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS work_history(id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES work_jobs(id),
      actor_id INTEGER NOT NULL REFERENCES users(id),actor_name TEXT NOT NULL,department TEXT NOT NULL,action TEXT NOT NULL,
      notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS material_issues(id INTEGER PRIMARY KEY,requirement_id INTEGER NOT NULL REFERENCES requirements(id),
      quantity INTEGER NOT NULL,tc_document_id INTEGER REFERENCES job_documents(id),tc_reference TEXT NOT NULL DEFAULT '',
      issued_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
    ''')

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
    c.execute('INSERT INTO work_history(job_id,actor_id,actor_name,department,action,notes,created_at) VALUES(?,?,?,?,?,?,?)',
              (jid,user['id'],user['name'],user['role'],action,str(notes)[:4000],now()))
def visible(job,user):
    role=user['role']
    if role in ('Admin','Design','Fabrication','Store'):return True
    if role=='Machining':return job['machining_required']==1 and job['stage'] not in ('Design review','Admin revision')
    return False
def get_job(c,jid,user):
    job=c.execute('SELECT * FROM work_jobs WHERE id=?',(jid,)).fetchone()
    if not job or not visible(job,user):raise AccessError('Job not available to your department',404)
    return dict(job)
def version(job,d):
    if d.get('version')!=job['version']:raise ValueError('This job has changed. Refresh it before saving.')
def bump(c,jid):c.execute('UPDATE work_jobs SET version=version+1 WHERE id=?',(jid,))

def upload(c,jid,user,kind,file):
    if kind not in ('PO','Drawing','TC','Supporting'):raise ValueError('Invalid document type')
    if not isinstance(file,dict):raise ValueError('Choose a document to upload')
    name=str(file.get('name','')).replace('\\','/').split('/')[-1][:180]
    extensions={'.pdf','.png','.jpg','.jpeg','.txt','.dwg','.dxf','.step','.stp','.xlsx','.docx','.csv'}
    if pathlib.Path(name).suffix.lower() not in extensions:raise ValueError('Use PDF, image, text, CAD, Word, or Excel documents')
    try:content=base64.b64decode(file.get('content',''),validate=True)
    except (ValueError,binascii.Error):raise ValueError('Invalid document data')
    if not 0<len(content)<=5*1024*1024:raise ValueError('Document must be between 1 byte and 5 MB')
    return c.execute('INSERT INTO job_documents(job_id,kind,name,mime,content,uploaded_by,created_at) VALUES(?,?,?,?,?,?,?)',
                     (jid,kind,name,'application/octet-stream',content,user['id'],now())).lastrowid

def create(c,d,user):
    require(user)
    due=datetime.date.fromisoformat(text(d,'due')).isoformat()
    jid=c.execute('INSERT INTO work_jobs(title,customer,po_number,due,instructions,created_by,created_at) VALUES(?,?,?,?,?,?,?)',
                  (text(d,'title'),text(d,'customer'),text(d,'po_number'),due,str(d.get('instructions',''))[:4000],user['id'],now())).lastrowid
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
    product=c.execute('SELECT * FROM products WHERE id=?',(d.get('product_id'),)).fetchone()
    if not product:raise ValueError('Choose a material from the Store catalogue')
    qty=whole(d.get('quantity'));tc=d.get('tc_required',False)
    if type(tc) is not bool:raise ValueError('Select whether a test certificate is required')
    notes=str(d.get('notes',''))[:4000];tc_notes=str(d.get('tc_notes',''))[:4000]
    if d.get('id'):
        r=c.execute('SELECT * FROM requirements WHERE id=? AND job_id=?',(d['id'],job['id'])).fetchone()
        if not r or r['department']!=dept or r['issued']:raise ValueError('You can only update your department’s unissued requirement')
        c.execute('UPDATE requirements SET product_id=?,quantity=?,tc_required=?,tc_notes=?,notes=?,approved=0 WHERE id=?',
                  (product['id'],qty,int(tc),tc_notes,notes,r['id']))
    else:
        c.execute('INSERT INTO requirements(job_id,product_id,quantity,department,tc_required,tc_notes,notes,created_by) VALUES(?,?,?,?,?,?,?,?)',
                  (job['id'],product['id'],qty,dept,int(tc),tc_notes,notes,user['id']))
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
        if machining and not c.execute("SELECT 1 FROM job_documents WHERE job_id=? AND kind='Drawing'",(job['id'],)).fetchone():raise ValueError('Upload the approved drawing before routing a job to Machining')
        c.execute('UPDATE work_jobs SET machining_required=?,design_notes=? WHERE id=?',(int(machining),notes,job['id']))
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
        if not c.execute("SELECT 1 FROM requirements WHERE job_id=? AND department='Machining'",(job['id'],)).fetchone():raise ValueError('Add basic machining material and TC requirements first')
        target='Fabrication review'
    elif action=='fabrication_approve':
        require(user,('Fabrication',))
        if stage!='Fabrication review':raise ValueError('Job is not awaiting Fabrication review')
        if not c.execute('SELECT 1 FROM requirements WHERE job_id=?',(job['id'],)).fetchone():raise ValueError('Add at least one material requirement before approval')
        c.execute('UPDATE requirements SET approved=1 WHERE job_id=?',(job['id'],))
        target='Machining execution' if job['machining_required'] else 'Fabrication execution'
    elif action=='request_changes':
        require(user,('Fabrication',))
        if stage!='Fabrication review':raise ValueError('Changes can only be requested during Fabrication review')
        target='Machining requirements' if job['machining_required'] else 'Design review'
    elif action=='machining_complete':
        require(user,('Machining',))
        if stage!='Machining execution':raise ValueError('Job is not ready for machining completion')
        if c.execute("SELECT 1 FROM requirements WHERE job_id=? AND department IN ('Machining','Design') AND issued<quantity",(job['id'],)).fetchone():raise ValueError('Store must issue all machining and design materials before completion')
        target='Fabrication execution'
    elif action=='fabrication_complete':
        require(user,('Fabrication',))
        if stage!='Fabrication execution':raise ValueError('Job is not ready for fabrication completion')
        if c.execute('SELECT 1 FROM requirements WHERE job_id=? AND issued<quantity',(job['id'],)).fetchone():raise ValueError('Store must issue all outstanding materials before completion')
        target='Completed'
    else:raise ValueError('Unknown workflow action')
    c.execute('UPDATE work_jobs SET stage=?,version=version+1 WHERE id=?',(target,job['id']))
    history(c,job['id'],user,stage+' → '+target,notes)

def issue(c,d,user):
    require(user,('Store',))
    r=c.execute('SELECT * FROM requirements WHERE id=?',(d.get('requirement_id'),)).fetchone()
    if not r:raise ValueError('Requirement not found')
    job=get_job(c,r['job_id'],user);version(job,d)
    if not r['approved'] or job['stage'] not in ('Machining execution','Fabrication execution'):raise ValueError('Fabrication must approve requirements before Store can issue material')
    qty=whole(d.get('quantity'))
    if qty>r['quantity']-r['issued']:raise ValueError('Quantity exceeds the remaining requirement')
    tc_id=d.get('tc_document_id') or None;reference=str(d.get('tc_reference','')).strip()[:200]
    if r['tc_required'] and (not tc_id or not reference):raise ValueError('Attach a Test Certificate and enter its reference before issuing this material')
    if tc_id and not c.execute("SELECT 1 FROM job_documents WHERE id=? AND job_id=? AND kind='TC'",(tc_id,job['id'])).fetchone():raise ValueError('Choose a Test Certificate attached to this job')
    if not c.execute('UPDATE products SET stock=stock-? WHERE id=? AND stock>=?',(qty,r['product_id'],qty)).rowcount:raise ValueError('Insufficient stock. Receive material into Store first.')
    c.execute('UPDATE requirements SET issued=issued+? WHERE id=?',(qty,r['id']))
    c.execute('INSERT INTO movements(product_id,quantity,reason,date) VALUES(?,?,?,?)',(r['product_id'],-qty,f'Job JOB-{job["id"]:04} / requirement {r["id"]}',datetime.date.today().isoformat()))
    c.execute('INSERT INTO material_issues(requirement_id,quantity,tc_document_id,tc_reference,issued_by,created_at) VALUES(?,?,?,?,?,?)',(r['id'],qty,tc_id,reference,user['id'],now()))
    bump(c,job['id']);history(c,job['id'],user,f'Issued {qty} units against requirement {r["id"]}',reference)

def state(c,data,user):
    jobs=[dict(j) for j in c.execute('SELECT * FROM work_jobs ORDER BY id DESC') if visible(j,user)]
    ids={j['id'] for j in jobs};data['work_jobs']=jobs
    data['requirements']=[dict(r) for r in c.execute('SELECT * FROM requirements') if r['job_id'] in ids]
    data['job_documents']=[dict(r) for r in c.execute('SELECT id,job_id,kind,name,uploaded_by,created_at,length(content) size FROM job_documents') if r['job_id'] in ids]
    data['work_history']=[dict(r) for r in c.execute('SELECT * FROM work_history ORDER BY id DESC') if r['job_id'] in ids]
    req_ids={r['id'] for r in data['requirements']}
    data['material_issues']=[dict(r) for r in c.execute('SELECT * FROM material_issues') if r['requirement_id'] in req_ids]
