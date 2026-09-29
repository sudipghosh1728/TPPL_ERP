"""Password authentication, expiring sessions, and department permissions."""
import hashlib, hmac, secrets, time
from http.cookies import SimpleCookie

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
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
      name TEXT NOT NULL, role TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL);
    ''')

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
    user=c.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>? AND u.active=1',
                   (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
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
    return c.execute('INSERT INTO users(username,name,role,password_hash) VALUES(?,?,?,?)',
                     (username,name,role,password_hash(d.get('password')))).lastrowid

def login(c,d,ip):
    username=str(d.get('username','')).strip().lower();key=ip
    record=c.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
    if record and record['until']>time.time() and record['failures']>=10:
        return None,None,'Too many sign-in attempts. Try again in 15 minutes.'
    user=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
    if not user or not verify(d.get('password'),user['password_hash']):
        failures=(record['failures'] if record and record['until']>time.time() else 0)+1
        c.execute('INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,until=excluded.until',(key,failures,time.time()+900))
        return None,None,'Incorrect username or password'
    c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
    token=secrets.token_urlsafe(40)
    c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],time.time()+86400))
    return public(user),token,None

def manage_user(c,d,actor):
    require(actor)
    if not d.get('id'):return create_user(c,d)
    u=c.execute('SELECT * FROM users WHERE id=?',(d['id'],)).fetchone()
    if not u:raise ValueError('User not found')
    active=d.get('active',u['active']);role=d.get('role',u['role'])
    if active not in (0,1) or role not in ROLES:raise ValueError('Invalid user status or role')
    if u['id']==actor['id'] and (not active or role!='Admin'):raise ValueError('You cannot disable or demote your own Admin account')
    name=str(d.get('name',u['name'])).strip()
    if not name or len(name)>100:raise ValueError('Enter a display name')
    c.execute('UPDATE users SET name=?,role=?,active=? WHERE id=?',(name,role,active,u['id']))
    if d.get('password'):c.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(d['password']),u['id']))
    c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))

def filter_state(c,data,user):
    role=user['role'];data['user']=user
    data['users']=[public(u) for u in c.execute('SELECT * FROM users ORDER BY role,name')] if role=='Admin' else []
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
