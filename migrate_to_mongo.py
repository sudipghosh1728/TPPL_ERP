"""One-time, verified SQLite-to-MongoDB migration. Never merges or overwrites a target."""
import argparse,datetime,hashlib,json,pathlib,sqlite3
from contextlib import closing
from pymongo.errors import PyMongoError
from storage import COLLECTIONS,DEFAULTS,KEYS,MongoStore,UnitOfWork,identifier

def canonical(rows):
    def default(v):
        if isinstance(v,(bytes,bytearray)):return {'binary_sha256':hashlib.sha256(v).hexdigest()}
        raise TypeError()
    return hashlib.sha256(json.dumps(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True,default=default)),sort_keys=True,default=default,separators=(',',':')).encode()).hexdigest()

def migrate(source,store):
    source=pathlib.Path(source).resolve()
    if not source.is_file():raise ValueError('SQLite source file not found')
    backup_dir=source.parent/'backups';backup_dir.mkdir(exist_ok=True)
    snapshot=backup_dir/('before-mongodb-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(snapshot)) as new:old.backup(new)
    rows={}
    with closing(sqlite3.connect(snapshot)) as c:
        c.row_factory=sqlite3.Row
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in COLLECTIONS:
            values=[dict(r) for r in c.execute('SELECT * FROM '+name)] if name in tables else []
            if name=='job_documents':
                for doc in values:doc['size']=len(doc['content'])
            rows[name]=values
    # Verify references via SQLite's own check before changing the remote target.
    with closing(sqlite3.connect(snapshot)) as c:
        if c.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Source has broken references; repair before migration')
    checksum=canonical([{'collection':k,'rows':v} for k,v in rows.items()])
    def copy(c):
        marker=c.db['_metadata'].find_one({'_id':'sqlite-migration'},session=c.session)
        if marker:
            if marker['checksum']==checksum:return {'already_migrated':True,'counts':marker['counts']}
            raise ValueError('Target was already migrated from a different snapshot; automatic merge is not supported')
        if any(c.one(name) for name in COLLECTIONS):raise ValueError('Target database is not empty. Migration will not overwrite or merge records.')
        for name,values in rows.items():
            # Batch each collection to keep cloud round trips within the transaction lifetime.
            documents=[]
            for value in values:
                doc={**DEFAULTS.get(name,{}),**value}
                doc['_id']=doc[KEYS[name]] if name in KEYS else identifier(doc['id'])
                if name=='accounts':doc['name_key']=doc['name'].casefold()
                if name=='users':doc['username_key']=doc['username'].casefold()
                documents.append(doc)
            if documents:
                c.db[name].insert_many(documents,session=c.session)
                if name not in KEYS:
                    c.db['_counters'].update_one({'_id':name},{'$max':{'value':max(d['id'] for d in documents)}},upsert=True,session=c.session)
        # Compare every source field and binary hash, not just row counts.
        for name,values in rows.items():
            migrated=c.all(name)
            if len(values)!=len(migrated):raise ValueError('Migration count verification failed for '+name)
            keys=set().union(*(v.keys() for v in values)) if values else set()
            projected=[{k:r.get(k) for k in keys} for r in migrated]
            if canonical(values)!=canonical(projected):raise ValueError('Migration content verification failed for '+name)
        counts={k:len(v) for k,v in rows.items()}
        c.db['_metadata'].insert_one({'_id':'sqlite-migration','checksum':checksum,'counts':counts,'at':datetime.datetime.now(datetime.timezone.utc)},session=c.session)
        return {'already_migrated':False,'counts':counts}
    result=store.run(copy)
    return {**result,'snapshot':str(snapshot)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',default=str(pathlib.Path(__file__).parent/'data'/'erp.db'));args=parser.parse_args()
    store=None
    try:
        store=MongoStore();store.prepare();result=migrate(args.source,store)
        print('MongoDB migration verified.' if not result['already_migrated'] else 'This source was already migrated; no changes made.')
        print('Database:',store.database);print('Records:',sum(result['counts'].values()));print('Local backup:',result['snapshot'])
    except ValueError as e:print(str(e));return 1
    except PyMongoError as e:print('MongoDB migration could not complete ('+type(e).__name__+'). Credentials were not logged.');return 1
    finally:
        if store:store.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
