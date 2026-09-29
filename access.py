"""Password authentication, expiring sessions, and department permissions."""
import hashlib, hmac, secrets, time
from http.cookies import SimpleCookie
from storage import identifier

ROLES=('Admin','Design','Machining','Fabrication','Store','Accounts')
PERMISSIONS={
    'accounts':('Accounts',), 'settlements':('Accounts',), 'journals':('Accounts',),
    'invoices':('Accounts',), 'orders':('Accounts',), 'pay':('Accounts',),
    'purchases':('Accounts',), 'receive':('Store',), 'products':('Store',), 'stock':('Store',),
    'settings':(), 'jobs':(), 'job-action':(),
}

class AccessError(Exception):
    def __init__(self,message,status=403): self.status=status;super().__init__(message)

def initialize(c):
    pass  # MongoDB collections and indexes are initialized by storage.MongoStore.

def password_hash(password):
    if not isinstance(password,str) or not 10<=len(password)<=200:
        raise ValueError('Use a password between 10 and 200 characters')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return salt+':'+digest

def verify(password,stored):
    if not isinstance(password,str) or len(password)>200:return False
    salt,digest=stored.split(':')
    candidate=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return hmac.compare_digest(candidate,digest)

def public(user):return {k:user[k] for k in ('id','username','name','role','active')}

def current(c,cookie):
    try:
        cookies=SimpleCookie();cookies.load(cookie or '')
        token=cookies['tppl_session'].value
    except (KeyError,ValueError):return None
    session=c.one('sessions',{'token_hash':hashlib.sha256(token.encode()).hexdigest(),'expires':{'$gt':time.time()}})
    user=c.one('users',{'id':session['user_id'],'active':1}) if session else None
    return public(user) if user else None

def require(user,roles=()):
    if not user:raise AccessError('Please sign in to continue',401)
    if user['role']!='Admin' and user['role'] not in roles:raise AccessError('Your department does not have access to this action')

def create_user(c,d):
    username=str(d.get('username','')).strip().lower()
    if not username or len(username)>80 or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789._@-' for ch in username):
        raise ValueError('Username must contain letters, numbers, dots, @, underscores, or hyphens')
    name=str(d.get('name','')).strip();role=d.get('role')
    if not name or len(name)>100:raise ValueError('Enter a display name')
    if role not in ROLES:raise ValueError('Select a valid department')
    return c.insert('users',username=username,name=name,role=role,password_hash=password_hash(d.get('password')))

def login(c,d,ip):
    username=str(d.get('username','')).strip().lower();key=ip
    record=c.one('login_attempts',{'key':key})
    if record and record['until']>time.time() and record['failures']>=10:
        return None,None,'Too many sign-in attempts. Try again in 15 minutes.'
    user=c.one('users',{'username_key':username.casefold(),'active':1})
    if not user or not verify(d.get('password'),user['password_hash']):
        failures=(record['failures'] if record and record['until']>time.time() else 0)+1
        c.update('login_attempts',{'_id':key},{'key':key,'failures':failures,'until':time.time()+900},upsert=True)
        return None,None,'Incorrect username or password'
    c.delete('login_attempts',{'key':key})
    c.delete('sessions',{'expires':{'$lt':time.time()}})
    token=secrets.token_urlsafe(40)
    c.insert('sessions',token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=user['id'],expires=time.time()+86400)
    return public(user),token,None

def manage_user(c,d,actor):
    require(actor)
    if not d.get('id'):return create_user(c,d)
    u=c.one('users',{'id':identifier(d['id'])})
    if not u:raise ValueError('User not found')
    active=d.get('active',u['active']);role=d.get('role',u['role'])
    if active not in (0,1) or role not in ROLES:raise ValueError('Invalid user status or role')
    if u['id']==actor['id'] and (not active or role!='Admin'):raise ValueError('You cannot disable or demote your own Admin account')
    name=str(d.get('name',u['name'])).strip()
    if not name or len(name)>100:raise ValueError('Enter a display name')
    c.update('users',{'id':u['id']},{'name':name,'role':role,'active':active})
    if d.get('password'):c.update('users',{'id':u['id']},{'password_hash':password_hash(d['password'])})
    c.delete('sessions',{'user_id':u['id']})

def filter_state(c,data,user):
    role=user['role'];data['user']=user
    data['users']=[public(u) for u in c.all('users',sort=[('role',1),('name',1)])] if role=='Admin' else []
    if role not in ('Admin','Accounts'):
        for key in ('orders','accounts','journals','journal_lines','invoice_items','settlements','activity'):
            data[key]=[]
        data['settings']={'company':data['settings']['company']}
        for p in data['products']:p.pop('price',None)
        if role=='Store':
            for p in data['purchases']:
                for key in ('unit_cost','account_id','total_paise','paid_paise','outstanding_paise'):p.pop(key,None)
        else:data['purchases']=[]
    if role not in ('Admin',):data['jobs']=[]
    if role not in ('Admin','Store'):data['movements']=[]
