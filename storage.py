"""Native MongoDB collections and atomic, retryable units of work."""
from pymongo import ReturnDocument
from pymongo.errors import CollectionInvalid
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from pymongo.read_preferences import ReadPreference
import config,json,copy

COLLECTIONS=('products','orders','movements','activity','settings','purchases','jobs','accounts','journals',
             'journal_lines','invoice_items','settlements','requests','users','sessions','login_attempts',
             'work_jobs','job_documents','requirements','work_history','material_issues','store_documents')
KEYS={'settings':'key','requests':'token','sessions':'token_hash','login_attempts':'key'}
DEFAULTS={
 'accounts':dict(email='',phone='',address='',system=0),
 'users':dict(active=1),
 'orders':dict(notes='',account_id=None,due=None),
 'purchases':dict(account_id=None),
 'journals':dict(source=None),
 'settlements':dict(order_id=None,purchase_id=None),
 'work_jobs':dict(instructions='',stage='Design review',machining_required=None,design_notes='',version=1),
 'requirements':dict(issued=0,tc_required=0,tc_notes='',notes='',approved=0),
}

def identifier(value):
    if isinstance(value,bool):raise ValueError('Invalid record identifier')
    try:
        n=int(value)
        if str(n)!=str(value) or n<=0:raise ValueError()
        return n
    except (TypeError,ValueError):raise ValueError('Invalid record identifier')

def public(doc):
    if doc is None:return None
    return {k:v for k,v in doc.items() if k not in ('_id','name_key','username_key','_revision')}

class UnitOfWork:
    def __init__(self,db,session):self.db=db;self.session=session;self._reads={}
    def cached(self,key,read):
        # Only the lifetime of this transaction; never share company data between requests.
        key=json.dumps(key,sort_keys=True,default=str)
        if key not in self._reads:self._reads[key]=read()
        return copy.deepcopy(self._reads[key])
    def one(self,collection,query=None):
        return self.cached(('one',collection,query),lambda:public(self.db[collection].find_one(query or {},session=self.session)))
    def all(self,collection,query=None,sort=None,projection=None):
        def read():
            cursor=self.db[collection].find(query or {},projection,session=self.session)
            if sort:cursor=cursor.sort(sort)
            return [public(r) for r in cursor]
        return self.cached(('all',collection,query,sort,projection),read)
    def insert(self,collection,**values):
        self._reads.clear()
        doc={**DEFAULTS.get(collection,{}),**values}
        if collection in KEYS:
            doc['_id']=doc[KEYS[collection]]
        else:
            if 'id' not in doc:
                counter=self.db['_counters'].find_one_and_update({'_id':collection},{'$inc':{'value':1}},upsert=True,return_document=ReturnDocument.AFTER,session=self.session)
                doc['id']=counter['value']
            else:
                self.db['_counters'].update_one({'_id':collection},{'$max':{'value':identifier(doc['id'])}},upsert=True,session=self.session)
            doc['_id']=doc['id']
        if collection=='accounts':doc['name_key']=doc['name'].casefold()
        if collection=='users':doc['username_key']=doc['username'].casefold()
        self.db[collection].insert_one(doc,session=self.session)
        return doc.get('id',doc['_id'])
    def update(self,collection,query,values=None,inc=None,upsert=False):
        self._reads.clear()
        change={}
        if values:change['$set']=dict(values)
        if inc:change['$inc']=dict(inc)
        if collection=='accounts' and values and 'name' in values:change['$set']['name_key']=values['name'].casefold()
        if not change:return 0
        result=self.db[collection].update_many(query,change,upsert=upsert,session=self.session)
        return result.matched_count or int(result.upserted_id is not None)
    def delete(self,collection,query):
        self._reads.clear()
        return self.db[collection].delete_many(query,session=self.session).deleted_count
    def touch(self,collection,record_id):
        # Force a write conflict when concurrent payments read the same balance.
        return self.update(collection,{'id':record_id},inc={'_revision':1})

class MongoStore:
    def __init__(self,client=None,database=None):
        if client is None:client,database=config.client()
        self.client=client;self.db=client[database];self.database=database
    def prepare(self):
        self.client.admin.command('ping')
        hello=self.client.admin.command('hello')
        if not (hello.get('setName') or hello.get('msg')=='isdbgrid'):
            raise ValueError('MongoDB must be a replica set or Atlas cluster: transactions are required')
        existing=set(self.db.list_collection_names())
        for name in (*COLLECTIONS,'_counters','_metadata'):
            if name not in existing:
                try:self.db.create_collection(name)
                except CollectionInvalid:pass
        for collection,field in [('products','sku'),('accounts','name_key'),('users','username_key'),('settings','key'),('requests','token'),('sessions','token_hash'),('login_attempts','key')]:
            self.db[collection].create_index(field,unique=True)
        for collection in COLLECTIONS:
            if collection not in KEYS:self.db[collection].create_index('id',unique=True)
        self.db.products.create_index('barcode',unique=True,partialFilterExpression={'barcode':{'$gt':''}})
        self.db.journals.create_index('source',unique=True,partialFilterExpression={'source':{'$type':'string'}})
        for collection,field in [('journal_lines','account_id'),('journal_lines','journal_id'),('invoice_items','order_id'),('settlements','order_id'),('settlements','purchase_id'),('settlements','account_id'),('sessions','user_id'),('requirements','job_id'),('job_documents','job_id'),('work_history','job_id'),('material_issues','requirement_id')]:
            self.db[collection].create_index(field)
    def run(self,callback):
        # Responses and file downloads are sent only after this callback commits.
        with self.client.start_session() as session:
            return session.with_transaction(lambda s:callback(UnitOfWork(self.db,s)),read_concern=ReadConcern('snapshot'),write_concern=WriteConcern('majority'),read_preference=ReadPreference.PRIMARY,max_commit_time_ms=15000)
    def close(self):self.client.close()
