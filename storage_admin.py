"""Admin-controlled, resumable offload; preserve the project and original bytes."""
import access,file_storage,manufacturing as m,os,secrets

def scopes(c,job_id=None,user=None):
    if job_id is None:return {name:{} for name in file_storage.FIELDS}
    j=m.get_job(c,job_id,user);jid=j['id']
    outbox=[r['id'] for r in c.all('dispatch_outbox',{'job_id':jid},projection={'id':1})]
    exports=[r['id'] for r in c.all('project_delete_exports',{'job_id':jid},projection={'id':1})]
    return {'job_documents':{'job_id':jid},'report_workbooks':{'job_id':jid},'dispatch_archives':{'outbox_id':{'$in':outbox}},'project_delete_parts':{'export_id':{'$in':exports}}}

def counts(c,queries):
    rows=[]
    for name,query in queries.items():
        field=file_storage.FIELDS[name]
        rows.append({'collection':name,'in_mongo':c.db[name].count_documents({**query,field:{'$type':'binData'}},session=c.session),'on_drive':c.db[name].count_documents({**query,field+'._grey_file':1},session=c.session)})
    return rows

def status(c,user):
    access.require(user)
    connected=False;message='Files are stored in MongoDB. Configure your company file server before moving files.'
    if c.files:
        try:c.files.health();connected=True;message='Company file server connected. New uploads use this drive.'
        except file_storage.StorageError as e:message=str(e)
    saved=c.db['_metadata'].find_one({'_id':'company-file-server'},session=c.session)
    server={k:saved[k] for k in ('name','url','store_id')} if saved else None
    return {'configured':bool(c.files),'connected':connected,'message':message,'server':server,'collections':counts(c,scopes(c))}

def connect(c,d,user):
    access.require(user)
    name=str(d.get('name','')).strip();url=str(d.get('url','')).strip().rstrip('/');sid=str(d.get('store_id','')).strip()
    if not name or len(name)>80:raise ValueError('Enter a server name of up to 80 characters')
    if len(url)>1000 or len(sid)>100:raise ValueError('Invalid server address or storage identity')
    if os.environ.get('VERCEL') and not url.startswith('https://'):raise ValueError('Vercel requires an HTTPS network server address')
    old=c.db['_metadata'].find_one({'_id':'company-file-server'},session=c.session)
    token=d.get('token') or ''
    if not isinstance(token,str) or len(token)>500:raise ValueError('Invalid private server key')
    if not token:
        if not old or old['url']!=url:raise ValueError('Enter the private server key for this address')
        token=old['token']
    candidate=file_storage.RemoteStore(url,token,sid)
    if c.files and c.files.store_id!=sid:raise ValueError('Reconnect the same storage identity; changing drives requires a verified restore first.')
    for name_,field in file_storage.FIELDS.items():
        if c.db[name_].find_one({field+'._grey_file':1,field+'.store_id':{'$ne':sid}},session=c.session):raise ValueError('Existing files use a different storage identity. Restore or reconnect that drive first.')
        sample=c.db[name_].find_one({field+'._grey_file':1},session=c.session)
        if sample:candidate.get(sample[field])
    candidate.health();probe=b'GREYone connection verification '+secrets.token_bytes(24)
    ref=candidate.put(probe);file_storage.checked(ref,candidate.get(ref),sid)
    c.db['_metadata'].update_one({'_id':'company-file-server'},{'$set':{'name':name,'url':url,'store_id':sid,'token':token,'updated_by':user['id'],'updated_at':m.now()}},upsert=True,session=c.session)
    c.files=candidate
    c.insert('activity',message='Company network file server connected: '+name,actor_id=user['id'],date=m.now())
    return {'ok':True,'server':{'name':name,'url':url,'store_id':sid}}

def move_one(c,d,user):
    access.require(user)
    if not c.files:raise ValueError('Configure and connect the company file server first')
    c.files.health();queries=scopes(c,d.get('job_id'),user)
    for name,query in queries.items():
        field=file_storage.FIELDS[name]
        row=c.db[name].find_one({**query,field:{'$type':'binData'}},session=c.session)
        if not row:continue
        raw=bytes(row[field]);ref=c.files.put(raw)
        # Read-back verification is mandatory before replacing the database copy.
        file_storage.checked(ref,c.files.get(ref),c.files.store_id)
        result=c.db[name].update_one({'_id':row['_id'],field:row[field]},{'$set':{field:ref}},session=c.session)
        if result.modified_count!=1:raise ValueError('File changed during transfer. Retry this operation.')
        c._reads.clear()
        c.insert('activity',message='File moved to company drive: '+name+' #'+str(row.get('id')),actor_id=user['id'],date=m.now())
        return {'moved':1,'bytes':len(raw),'remaining':sum(r['in_mongo'] for r in counts(c,queries))}
    return {'moved':0,'bytes':0,'remaining':0}
