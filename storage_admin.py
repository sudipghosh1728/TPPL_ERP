"""Admin-controlled, resumable offload; preserve the project and original bytes."""
import access,file_storage,manufacturing as m

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
    return {'configured':bool(c.files),'connected':connected,'message':message,'collections':counts(c,scopes(c))}

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
