"""Double-entry books persisted in MongoDB; posting amounts are integer paise."""
import datetime
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from storage import identifier

TYPES=('Customer','Supplier','Cash','Bank','Asset','Liability','Equity','Income','Expense')

def cents(value):
    try:
        n=Decimal(str(value))
        if not n.is_finite() or abs(n)>Decimal('100000000000'):raise ValueError('Amount is outside the supported range')
        return int((n*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (InvalidOperation,TypeError):raise ValueError('Enter a valid amount')
def positive(value):
    n=cents(value)
    if n<=0:raise ValueError('Amount must be greater than zero')
    return n
def date(value=None):return datetime.date.fromisoformat(str(value or datetime.date.today())).isoformat()
def text(data,key):
    v=str(data.get(key,'')).strip()
    if not v or len(v)>500:raise ValueError(f'Enter a valid {key.replace("_"," ")}')
    return v
def account(c,aid):
    a=c.one('accounts',{'id':identifier(aid)})
    if not a:raise ValueError('Account not found')
    return a
def system(c,name):return c.one('accounts',{'name_key':name.casefold()})['id']
def party(c,name,kind):
    name=str(name).strip();a=c.one('accounts',{'name_key':name.casefold()})
    if a:
        if a['type']!=kind:raise ValueError(f'{name} already exists as a {a["type"]} account. Use a separate {kind.lower()} ledger name.')
        return a['id']
    return c.insert('accounts',name=name,type=kind)
def balance(c,aid):return sum(l['debit']-l['credit'] for l in c.all('journal_lines',{'account_id':aid}))

def journal(c,day,reference,description,lines,source=None):
    if len(lines)<2 or sum(x[1] for x in lines)!=sum(x[2] for x in lines):raise ValueError('Debits and credits must balance')
    if sum(x[1] for x in lines)<=0:raise ValueError('Voucher must have a positive amount')
    for aid,debit,credit in lines:
        account(c,aid)
        if min(debit,credit)<0 or (debit>0 and credit>0):raise ValueError('Each line must be a debit or a credit')
    jid=c.insert('journals',date=date(day),reference=reference,description=description,source=source)
    for aid,debit,credit in lines:
        if debit or credit:c.insert('journal_lines',journal_id=jid,account_id=aid,debit=debit,credit=credit)
    return jid

def initialize(c):
    for name,kind in [('Cash in hand','Cash'),('Main bank','Bank'),('Sales revenue','Income'),('Material purchases','Expense'),('Opening balance equity','Equity')]:
        if not c.one('accounts',{'name_key':name.casefold()}):c.insert('accounts',name=name,type=kind,system=1)
    for o in c.all('orders',{'account_id':None}):
        aid=party(c,o['customer'],'Customer');c.update('orders',{'id':o['id']},{'account_id':aid,'due':o['date']})
        p=c.one('products',{'id':o['product_id']});amount=cents(o['total'])
        c.insert('invoice_items',order_id=o['id'],product_id=o['product_id'],description=p['name'],quantity=o['quantity'],unit_price=int((Decimal(amount)/Decimal(o['quantity'])).quantize(Decimal('1'),rounding=ROUND_HALF_UP)),amount=amount)
        if amount:
            journal(c,o['date'],f'INV-{o["id"]:04}',f'Migrated sale to {o["customer"]}',[(aid,amount,0),(system(c,'Sales revenue'),0,amount)],f'invoice:{o["id"]}')
            if o['status']=='Paid':
                bank=system(c,'Main bank');jid=journal(c,o['date'],f'LEGACY-{o["id"]}','Previously marked paid; bank assumed for demo migration',[(bank,amount,0),(aid,0,amount)],f'legacy-payment:{o["id"]}')
                c.insert('settlements',account_id=aid,money_account_id=bank,order_id=o['id'],amount=amount,date=o['date'],reference='Legacy paid status',journal_id=jid)
    for p in c.all('purchases',{'account_id':None}):
        aid=party(c,p['supplier'],'Supplier');c.update('purchases',{'id':p['id']},{'account_id':aid})
        if p['status']=='Received':post_purchase(c,p['id'],p['date'])

def post_purchase(c,pid,day=None):
    p=c.one('purchases',{'id':pid});amount=cents(p['unit_cost'])*p['quantity']
    if amount:journal(c,day,f'BILL-{pid:04}',f'Materials received from {p["supplier"]}',[(system(c,'Material purchases'),amount,0),(p['account_id'],0,amount)],f'purchase:{pid}')

def create_account(c,d):
    kind=text(d,'type')
    if kind not in TYPES:raise ValueError('Select a valid account type')
    opening=cents(d.get('opening',0));side=d.get('opening_side','Debit')
    if opening<0:raise ValueError('Opening amount must not be negative')
    if side not in ('Debit','Credit'):raise ValueError('Select debit or credit')
    aid=c.insert('accounts',name=text(d,'name'),type=kind,email=str(d.get('email','')).strip(),phone=str(d.get('phone','')).strip(),address=str(d.get('address','')).strip())
    if opening:
        debit=opening if side=='Debit' else 0;credit=opening if side=='Credit' else 0
        journal(c,d.get('date'),f'OPEN-{aid:04}','Opening balance',[(aid,debit,credit),(system(c,'Opening balance equity'),credit,debit)],f'opening:{aid}')

def create_invoice(c,d):
    if d.get('account_id'):
        a=account(c,d['account_id'])
        if a['type']!='Customer':raise ValueError('Select a customer ledger')
        aid=a['id'];customer=a['name']
    else:customer=text(d,'customer');aid=party(c,customer,'Customer')
    day=date(d.get('date'));due=date(d.get('due') or day)
    if due<day:raise ValueError('Due date cannot be before invoice date')
    items=d.get('items')
    if items is None:items=[{'product_id':d.get('product_id'),'quantity':d.get('quantity')}]
    if not isinstance(items,list) or not 1<=len(items)<=100:raise ValueError('Add between 1 and 100 invoice items')
    prepared=[];demand={}
    for item in items:
        if not isinstance(item,dict):raise ValueError('Each invoice item must be an object')
        p=c.one('products',{'id':identifier(item.get('product_id'))})
        if not p:raise ValueError('Select an existing product')
        try:
            quantity=Decimal(str(item.get('quantity')))
            if not quantity.is_finite() or quantity!=int(quantity) or quantity<=0 or quantity>10000000:raise ValueError()
            qty=int(quantity)
        except (InvalidOperation,ValueError,OverflowError):raise ValueError('Quantity must be a positive whole number')
        price=cents(item.get('unit_price',p['price']))
        if price<0:raise ValueError('Price cannot be negative')
        demand[p['id']]=demand.get(p['id'],0)+qty
        if demand[p['id']]>p['stock']:raise ValueError(f'Insufficient stock for {p["name"]}: {p["stock"]} available')
        prepared.append(dict(product_id=p['id'],description=p['name'],quantity=qty,unit_price=price,amount=qty*price))
    amount=sum(i['amount'] for i in prepared)
    if not 0<amount<=10000000000000:raise ValueError('Invoice total is outside the supported range')
    oid=c.insert('orders',customer=customer,product_id=prepared[0]['product_id'],quantity=sum(i['quantity'] for i in prepared),total=amount/100,status='Pending',date=day,account_id=aid,due=due,notes=str(d.get('notes','')).strip())
    for item in prepared:c.insert('invoice_items',order_id=oid,**item)
    for pid,qty in demand.items():
        if not c.update('products',{'id':pid,'stock':{'$gte':qty}},inc={'stock':-qty}):raise ValueError('Insufficient stock')
        c.insert('movements',product_id=pid,quantity=-qty,reason=f'Invoice INV-{oid:04} · {customer}',date=day)
    journal(c,day,f'INV-{oid:04}',f'Sales invoice · {customer}',[(aid,amount,0),(system(c,'Sales revenue'),0,amount)],f'invoice:{oid}')
    return oid

def settle(c,d):
    a=account(c,d.get('account_id'));bank=account(c,d.get('money_account_id'))
    if a['type'] not in ('Customer','Supplier'):raise ValueError('Select a customer or supplier')
    if bank['type'] not in ('Cash','Bank'):raise ValueError('Select a cash or bank account')
    amount=positive(d.get('amount'));day=date(d.get('date'));reference=text(d,'reference')
    oid=identifier(d['order_id']) if d.get('order_id') else None;pid=identifier(d['purchase_id']) if d.get('purchase_id') else None
    if oid and pid:raise ValueError('Select only one document')
    c.touch('accounts',a['id'])
    if oid:
        doc=c.one('orders',{'id':oid,'account_id':a['id']})
        if not doc or a['type']!='Customer':raise ValueError('Invoice does not belong to this customer')
        remaining=cents(doc['total'])-sum(s['amount'] for s in c.all('settlements',{'order_id':oid}))
    elif pid:
        doc=c.one('purchases',{'id':pid,'account_id':a['id'],'status':'Received'})
        if not doc or a['type']!='Supplier':raise ValueError('Select a received supplier bill')
        remaining=cents(doc['unit_cost'])*doc['quantity']-sum(s['amount'] for s in c.all('settlements',{'purchase_id':pid}))
    else:
        doc=None;opening_doc=c.one('journals',{'source':f'opening:{a["id"]}'})
        opening=sum(l['debit']-l['credit'] for l in c.all('journal_lines',{'account_id':a['id'],'journal_id':opening_doc['id']})) if opening_doc else 0
        settled=sum(s['amount'] for s in c.all('settlements',{'account_id':a['id'],'order_id':None,'purchase_id':None}))
        remaining=(opening if a['type']=='Customer' else -opening)-settled
        if opening_doc and day<opening_doc['date']:raise ValueError('Payment date cannot precede opening balance')
    if doc and day<doc['date']:raise ValueError('Payment date cannot precede document date')
    if pid:
        bill=c.one('journals',{'source':f'purchase:{pid}'})
        if bill and day<bill['date']:raise ValueError('Payment date cannot precede goods receipt')
    if amount>remaining:raise ValueError(f'Amount exceeds outstanding balance of ₹{remaining/100:,.2f}')
    lines=[(bank['id'],amount,0),(a['id'],0,amount)] if a['type']=='Customer' else [(a['id'],amount,0),(bank['id'],0,amount)]
    jid=journal(c,day,reference,('Customer receipt · ' if a['type']=='Customer' else 'Supplier payment · ')+a['name'],lines)
    c.insert('settlements',account_id=a['id'],money_account_id=bank['id'],order_id=oid,purchase_id=pid,amount=amount,date=day,reference=reference,journal_id=jid)
    if oid:c.update('orders',{'id':oid},{'status':'Paid' if amount==remaining else 'Part paid'})

def manual_journal(c,d):
    debit=account(c,d.get('debit_account_id'));credit=account(c,d.get('credit_account_id'))
    if debit['id']==credit['id']:raise ValueError('Choose different debit and credit accounts')
    if debit['type'] in ('Customer','Supplier') or credit['type'] in ('Customer','Supplier'):raise ValueError('Use invoices and payments for customer/supplier ledgers')
    amount=positive(d.get('amount'));journal(c,d.get('date'),text(d,'reference'),text(d,'description'),[(debit['id'],amount,0),(credit['id'],0,amount)])

def state(c,data):
    for t in ('journals','journal_lines','invoice_items','settlements'):data[t]=c.all(t,sort=[('id',1)])
    data['accounts']=c.all('accounts',sort=[('name',1)])
    for a in data['accounts']:
        lines=[l for l in data['journal_lines'] if l['account_id']==a['id']]
        a['debit']=sum(l['debit'] for l in lines);a['credit']=sum(l['credit'] for l in lines);a['balance']=a['debit']-a['credit']
    for o in data['orders']:
        o['total_paise']=cents(o['total']);o['paid_paise']=sum(s['amount'] for s in data['settlements'] if s['order_id']==o['id']);o['outstanding_paise']=o['total_paise']-o['paid_paise']
    for p in data['purchases']:
        p['total_paise']=cents(p['unit_cost'])*p['quantity'];p['paid_paise']=sum(s['amount'] for s in data['settlements'] if s['purchase_id']==p['id']);p['outstanding_paise']=p['total_paise']-p['paid_paise'] if p['status']=='Received' else 0
