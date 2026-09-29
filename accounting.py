"""Local double-entry books. Monetary postings are integer paise, never floats."""
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import sqlite3

TYPES = ('Customer', 'Supplier', 'Cash', 'Bank', 'Asset', 'Liability', 'Equity', 'Income', 'Expense')

def cents(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or abs(n) > Decimal('100000000000'):
            raise ValueError('Amount is outside the supported range')
        return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid amount')

def positive(value):
    n = cents(value)
    if n <= 0:
        raise ValueError('Amount must be greater than zero')
    return n

def date(value=None):
    return datetime.date.fromisoformat(str(value or datetime.date.today())).isoformat()

def text(data, key):
    v = str(data.get(key, '')).strip()
    if not v or len(v) > 500:
        raise ValueError(f'Enter a valid {key.replace("_", " ")}')
    return v

def account(c, account_id):
    r = c.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()
    if not r:
        raise ValueError('Account not found')
    return r

def system(c, name):
    return c.execute('SELECT id FROM accounts WHERE name=? COLLATE NOCASE', (name,)).fetchone()[0]

def party(c, name, kind):
    name = str(name).strip()
    r = c.execute('SELECT * FROM accounts WHERE name=? COLLATE NOCASE', (name,)).fetchone()
    if r:
        if r['type'] != kind:
            raise ValueError(f'{name} already exists as a {r["type"]} account. Use a separate {kind.lower()} ledger name.')
        return r['id']
    return c.execute('INSERT INTO accounts(name,type) VALUES(?,?)', (name, kind)).lastrowid

def balance(c, aid):
    return c.execute('SELECT COALESCE(SUM(debit-credit),0) FROM journal_lines WHERE account_id=?', (aid,)).fetchone()[0]

def journal(c, day, reference, description, lines, source=None):
    if len(lines) < 2 or sum(x[1] for x in lines) != sum(x[2] for x in lines):
        raise ValueError('Debits and credits must balance')
    if sum(x[1] for x in lines) <= 0:
        raise ValueError('Voucher must have a positive amount')
    for aid, debit, credit in lines:
        account(c, aid)
        if min(debit, credit) < 0 or (debit > 0 and credit > 0):
            raise ValueError('Each line must be a debit or a credit')
    jid = c.execute('INSERT INTO journals(date,reference,description,source) VALUES(?,?,?,?)',
                    (date(day), reference, description, source)).lastrowid
    c.executemany('INSERT INTO journal_lines(journal_id,account_id,debit,credit) VALUES(?,?,?,?)',
                  [(jid, *line) for line in lines if line[1] or line[2]])
    return jid

def initialize(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        type TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '', system INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS journals(id INTEGER PRIMARY KEY, date TEXT NOT NULL, reference TEXT NOT NULL,
        description TEXT NOT NULL, source TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS journal_lines(id INTEGER PRIMARY KEY, journal_id INTEGER NOT NULL REFERENCES journals(id),
        account_id INTEGER NOT NULL REFERENCES accounts(id), debit INTEGER NOT NULL CHECK(debit>=0), credit INTEGER NOT NULL CHECK(credit>=0));
    CREATE TABLE IF NOT EXISTS invoice_items(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
        product_id INTEGER NOT NULL REFERENCES products(id), description TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0),
        unit_price INTEGER NOT NULL CHECK(unit_price>=0), amount INTEGER NOT NULL CHECK(amount>=0));
    CREATE TABLE IF NOT EXISTS settlements(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
        money_account_id INTEGER NOT NULL REFERENCES accounts(id), order_id INTEGER REFERENCES orders(id), purchase_id INTEGER REFERENCES purchases(id),
        amount INTEGER NOT NULL CHECK(amount>0), date TEXT NOT NULL, reference TEXT NOT NULL, journal_id INTEGER NOT NULL REFERENCES journals(id));
    CREATE TABLE IF NOT EXISTS requests(token TEXT PRIMARY KEY);
    CREATE INDEX IF NOT EXISTS idx_lines_account ON journal_lines(account_id);
    ''')
    cols = {r[1] for r in c.execute('PRAGMA table_info(orders)')}
    for name, definition in [('account_id', 'INTEGER REFERENCES accounts(id)'), ('due', 'TEXT'), ('notes', "TEXT NOT NULL DEFAULT ''")]:
        if name not in cols:
            c.execute(f'ALTER TABLE orders ADD COLUMN {name} {definition}')
    if 'account_id' not in {r[1] for r in c.execute('PRAGMA table_info(purchases)')}:
        c.execute('ALTER TABLE purchases ADD COLUMN account_id INTEGER REFERENCES accounts(id)')
    c.executemany('INSERT OR IGNORE INTO accounts(name,type,system) VALUES(?,?,1)',
                  [('Cash in hand','Cash'),('Main bank','Bank'),('Sales revenue','Income'),('Material purchases','Expense'),('Opening balance equity','Equity')])
    # One-time conversion: do not deduct stock again or post historical invoices twice.
    for o in c.execute('SELECT * FROM orders WHERE account_id IS NULL').fetchall():
        aid = party(c, o['customer'], 'Customer')
        c.execute('UPDATE orders SET account_id=?,due=? WHERE id=?', (aid,o['date'],o['id']))
        p = c.execute('SELECT name FROM products WHERE id=?', (o['product_id'],)).fetchone()
        amount = cents(o['total'])
        c.execute('INSERT INTO invoice_items(order_id,product_id,description,quantity,unit_price,amount) VALUES(?,?,?,?,?,?)',
                  (o['id'],o['product_id'],p['name'],o['quantity'],int((Decimal(amount)/Decimal(o['quantity'])).quantize(Decimal('1'),rounding=ROUND_HALF_UP)),amount))
        if amount:
            journal(c,o['date'],f'INV-{o["id"]:04}',f'Migrated sale to {o["customer"]}',[(aid,amount,0),(system(c,'Sales revenue'),0,amount)],f'invoice:{o["id"]}')
            if o['status']=='Paid':
                bank=system(c,'Main bank')
                jid=journal(c,o['date'],f'LEGACY-{o["id"]}', 'Previously marked paid; bank assumed for demo migration',[(bank,amount,0),(aid,0,amount)],f'legacy-payment:{o["id"]}')
                c.execute('INSERT INTO settlements(account_id,money_account_id,order_id,amount,date,reference,journal_id) VALUES(?,?,?,?,?,?,?)',
                          (aid,bank,o['id'],amount,o['date'],'Legacy paid status',jid))
    for p in c.execute('SELECT * FROM purchases WHERE account_id IS NULL').fetchall():
        aid=party(c,p['supplier'],'Supplier')
        c.execute('UPDATE purchases SET account_id=? WHERE id=?',(aid,p['id']))
        if p['status']=='Received':
            post_purchase(c,p['id'],p['date'])

def post_purchase(c, pid, day=None):
    p=c.execute('SELECT * FROM purchases WHERE id=?',(pid,)).fetchone()
    amount=cents(p['unit_cost'])*p['quantity']
    if amount:
        journal(c,day,f'BILL-{pid:04}',f'Materials received from {p["supplier"]}',
                [(system(c,'Material purchases'),amount,0),(p['account_id'],0,amount)],f'purchase:{pid}')

def create_account(c,d):
    kind=text(d,'type')
    if kind not in TYPES: raise ValueError('Select a valid account type')
    opening=cents(d.get('opening',0))
    if opening<0: raise ValueError('Opening amount must not be negative')
    side=d.get('opening_side','Debit')
    if side not in ('Debit','Credit'): raise ValueError('Select debit or credit')
    aid=c.execute('INSERT INTO accounts(name,type,email,phone,address) VALUES(?,?,?,?,?)',
                  (text(d,'name'),kind,str(d.get('email','')).strip(),str(d.get('phone','')).strip(),str(d.get('address','')).strip())).lastrowid
    if opening:
        debit=opening if side=='Debit' else 0; credit=opening if side=='Credit' else 0
        journal(c,d.get('date'),f'OPEN-{aid:04}','Opening balance',[(aid,debit,credit),(system(c,'Opening balance equity'),credit,debit)],f'opening:{aid}')

def create_invoice(c,d):
    aid=d.get('account_id')
    if aid:
        a=account(c,aid)
        if a['type']!='Customer': raise ValueError('Select a customer ledger')
        aid=a['id']; customer=a['name']
    else:
        customer=text(d,'customer'); aid=party(c,customer,'Customer')
    day=date(d.get('date')); due=date(d.get('due') or day)
    if due<day: raise ValueError('Due date cannot be before invoice date')
    items=d.get('items')
    if items is None: items=[{'product_id':d.get('product_id'),'quantity':d.get('quantity')}]
    if not isinstance(items,list) or not 1<=len(items)<=100: raise ValueError('Add between 1 and 100 invoice items')
    prepared=[]; demand={}
    for item in items:
        if not isinstance(item,dict): raise ValueError('Each invoice item must be an object')
        p=c.execute('SELECT * FROM products WHERE id=?',(item.get('product_id'),)).fetchone()
        if not p: raise ValueError('Select an existing product')
        try:
            quantity=Decimal(str(item.get('quantity')))
            if not quantity.is_finite() or quantity!=int(quantity) or quantity<=0 or quantity>10000000: raise ValueError()
            qty=int(quantity)
        except (InvalidOperation,ValueError,OverflowError): raise ValueError('Quantity must be a positive whole number')
        price=cents(item.get('unit_price',p['price']))
        if price<0: raise ValueError('Price cannot be negative')
        demand[p['id']]=demand.get(p['id'],0)+qty
        if demand[p['id']]>p['stock']: raise ValueError(f'Insufficient stock for {p["name"]}: {p["stock"]} available')
        prepared.append((p['id'],p['name'],qty,price,qty*price))
    amount=sum(i[4] for i in prepared)
    if amount<=0: raise ValueError('Invoice total must be greater than zero')
    if amount>10000000000000: raise ValueError('Invoice total is outside the supported range')
    oid=c.execute('INSERT INTO orders(customer,product_id,quantity,total,status,date,account_id,due,notes) VALUES(?,?,?,?,?,?,?,?,?)',
                  (customer,prepared[0][0],sum(i[2] for i in prepared),amount/100,'Pending',day,aid,due,str(d.get('notes','')).strip())).lastrowid
    c.executemany('INSERT INTO invoice_items(order_id,product_id,description,quantity,unit_price,amount) VALUES(?,?,?,?,?,?)',[(oid,*i) for i in prepared])
    for pid,qty in demand.items():
        c.execute('UPDATE products SET stock=stock-? WHERE id=?',(qty,pid))
        c.execute('INSERT INTO movements(product_id,quantity,reason,date) VALUES(?,?,?,?)',(pid,-qty,f'Invoice INV-{oid:04} · {customer}',day))
    journal(c,day,f'INV-{oid:04}',f'Sales invoice · {customer}',[(aid,amount,0),(system(c,'Sales revenue'),0,amount)],f'invoice:{oid}')
    return oid

def settle(c,d):
    a=account(c,d.get('account_id'))
    if a['type'] not in ('Customer','Supplier'): raise ValueError('Select a customer or supplier')
    bank=account(c,d.get('money_account_id'))
    if bank['type'] not in ('Cash','Bank'): raise ValueError('Select a cash or bank account')
    amount=positive(d.get('amount')); day=date(d.get('date')); reference=text(d,'reference')
    oid=d.get('order_id') or None; pid=d.get('purchase_id') or None
    if oid and pid: raise ValueError('Select only one document')
    if oid:
        doc=c.execute('SELECT * FROM orders WHERE id=? AND account_id=?',(oid,a['id'])).fetchone()
        if not doc or a['type']!='Customer': raise ValueError('Invoice does not belong to this customer')
        remaining=cents(doc['total'])-c.execute('SELECT COALESCE(SUM(amount),0) FROM settlements WHERE order_id=?',(oid,)).fetchone()[0]
    elif pid:
        doc=c.execute("SELECT * FROM purchases WHERE id=? AND account_id=? AND status='Received'",(pid,a['id'])).fetchone()
        if not doc or a['type']!='Supplier': raise ValueError('Select a received supplier bill')
        remaining=cents(doc['unit_cost'])*doc['quantity']-c.execute('SELECT COALESCE(SUM(amount),0) FROM settlements WHERE purchase_id=?',(pid,)).fetchone()[0]
    else:
        doc=None
        opening=c.execute("SELECT COALESCE(SUM(l.debit-l.credit),0) FROM journal_lines l JOIN journals j ON j.id=l.journal_id WHERE l.account_id=? AND j.source=?",(a['id'],f'opening:{a["id"]}')).fetchone()[0]
        settled=c.execute('SELECT COALESCE(SUM(amount),0) FROM settlements WHERE account_id=? AND order_id IS NULL AND purchase_id IS NULL',(a['id'],)).fetchone()[0]
        remaining=(opening if a['type']=='Customer' else -opening)-settled
        opening_date=c.execute('SELECT date FROM journals WHERE source=?',(f'opening:{a["id"]}',)).fetchone()
        if opening_date and day<opening_date[0]: raise ValueError('Payment date cannot precede opening balance')
    if doc and day<doc['date']: raise ValueError('Payment date cannot precede document date')
    if pid:
        bill_day=c.execute('SELECT date FROM journals WHERE source=?',(f'purchase:{pid}',)).fetchone()
        if bill_day and day<bill_day[0]: raise ValueError('Payment date cannot precede goods receipt')
    if amount>remaining: raise ValueError(f'Amount exceeds outstanding balance of ₹{remaining/100:,.2f}')
    lines=[(bank['id'],amount,0),(a['id'],0,amount)] if a['type']=='Customer' else [(a['id'],amount,0),(bank['id'],0,amount)]
    jid=journal(c,day,reference,('Customer receipt · ' if a['type']=='Customer' else 'Supplier payment · ')+a['name'],lines)
    c.execute('INSERT INTO settlements(account_id,money_account_id,order_id,purchase_id,amount,date,reference,journal_id) VALUES(?,?,?,?,?,?,?,?)',
              (a['id'],bank['id'],oid,pid,amount,day,reference,jid))
    if oid: c.execute('UPDATE orders SET status=? WHERE id=?',('Paid' if amount==remaining else 'Part paid',oid))

def manual_journal(c,d):
    debit=account(c,d.get('debit_account_id')); credit=account(c,d.get('credit_account_id'))
    if debit['id']==credit['id']: raise ValueError('Choose different debit and credit accounts')
    if debit['type'] in ('Customer','Supplier') or credit['type'] in ('Customer','Supplier'):
        raise ValueError('Use invoices and payments for customer/supplier ledgers')
    amount=positive(d.get('amount'))
    journal(c,d.get('date'),text(d,'reference'),text(d,'description'),[(debit['id'],amount,0),(credit['id'],0,amount)])

def state(c,data):
    data['accounts']=[dict(r) for r in c.execute('SELECT a.*,COALESCE(SUM(l.debit),0) debit,COALESCE(SUM(l.credit),0) credit,COALESCE(SUM(l.debit-l.credit),0) balance FROM accounts a LEFT JOIN journal_lines l ON l.account_id=a.id GROUP BY a.id ORDER BY a.name')]
    for t in ('journals','journal_lines','invoice_items','settlements'):
        data[t]=[dict(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY id')]
    for o in data['orders']:
        o['total_paise']=cents(o['total'])
        o['paid_paise']=sum(s['amount'] for s in data['settlements'] if s['order_id']==o['id'])
        o['outstanding_paise']=o['total_paise']-o['paid_paise']
    for p in data['purchases']:
        p['total_paise']=cents(p['unit_cost'])*p['quantity']
        p['paid_paise']=sum(s['amount'] for s in data['settlements'] if s['purchase_id']==p['id'])
        p['outstanding_paise']=p['total_paise']-p['paid_paise'] if p['status']=='Received' else 0
