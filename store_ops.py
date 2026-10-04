"""Independent Store receipts, issues and delivery challans. All writes are transactional."""
import datetime,re
from decimal import Decimal,ROUND_HALF_UP
import access,accounting,inventory_vouchers as vouchers
from storage import identifier

def text(d,key,required=False,limit=500):
 v=d.get(key,'')
 if not isinstance(v,str) or len(v)>limit or (required and not v.strip()):raise ValueError('Enter a valid '+key.replace('_',' '))
 return v.strip()

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def prepare(c,d):
 kind=d.get('kind')
 if kind in vouchers.SPECIAL:return vouchers.prepare(c,d)
 if kind not in vouchers.PREFIX:raise ValueError('Choose a supported voucher type')
 result=dict(kind=kind,date=accounting.date(d.get('date')),party=text(d,'party',True),address=text(d,'address'),reference=text(d,'reference'),order_number=text(d,'order_number'),vehicle=text(d,'vehicle'),transporter=text(d,'transporter'),lr_number=text(d,'lr_number'),ir_number=text(d,'ir_number'),remarks=text(d,'remarks'),eway_number=text(d,'eway_number'),dispatch_address=text(d,'dispatch_address'),party_gstin=text(d,'party_gstin'),company_gstin=text(d,'company_gstin'))
 if result['date']>datetime.date.today().isoformat():raise ValueError('Document date cannot be in the future')
 if result['eway_number'] and not re.fullmatch(r'\d{12}',result['eway_number']):raise ValueError('Enter the 12-digit e-way bill number generated on the government portal')
 for key in ('order_date','lr_date','ir_date'):result[key]=accounting.date(d[key]) if d.get(key) else ''
 values=d.get('items')
 if not isinstance(values,list) or not 1<=len(values)<=50:raise ValueError('Add between 1 and 50 material lines')
 lines=[];seen=set()
 for row in values:
  if not isinstance(row,dict):raise ValueError('Invalid material line')
  pid=identifier(row.get('product_id'));qty=identifier(row.get('quantity'))
  if qty>1000000000:raise ValueError('Quantity is too large')
  if pid in seen:raise ValueError('Combine duplicate material lines')
  seen.add(pid);p=c.one('products',{'id':pid})
  if not p:raise ValueError('Material not found')
  import store_catalog;store_catalog.require_ready(p)
  rate=accounting.cents(row.get('rate',0))
  if rate<0:raise ValueError('Rate cannot be negative')
  lines.append(dict(product_id=pid,description=p['name'],sku=p['sku'],unit=p.get('unit','pcs'),quantity=qty,rate=rate,amount=rate*qty,hsn=text(row,'hsn',limit=8),remarks=text(row,'remarks')))
 if kind in vouchers.RETURN_KINDS:
  source=c.one('store_documents',{'id':identifier(d.get('source_id'))})
  if not source or source['kind']!=vouchers.RETURN_KINDS[kind]:raise ValueError('Choose the original voucher')
  result['source_id']=source['id'];result['source_number']=source['number']
 result['items']=lines;result['assessable']=sum(x['amount'] for x in lines)
 for key in ('cgst','sgst','igst'):
  value=accounting.cents(d.get(key,0))
  if not 0<=value<=10000:raise ValueError('Tax percentage must be between 0 and 100')
  result[key+'_rate']=value
  result[key]=int((Decimal(result['assessable'])*value/10000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
 if result['igst_rate'] and (result['cgst_rate'] or result['sgst_rate']):raise ValueError('Use either IGST or CGST/SGST')
 result['total']=result['assessable']+sum(result[x] for x in ('cgst','sgst','igst'))
 result['company']=c.one('settings',{'key':'company'})['value']
 return result

def movement(c,doc,user,reverse=False):
 if doc['kind'] in vouchers.SPECIAL:return vouchers.move_special(c,doc,user,reverse)
 if doc['kind'] in vouchers.RETURN_KINDS and not reverse:vouchers.validate_return(c,doc)
 sign=1 if doc['kind'] in ('Inbound','Return in') else -1
 if reverse:sign=-sign
 kind={'Inbound':'store_receipt','Issue':'store_issue','Return in':'return_in','Return out':'return_out'}[doc['kind']]+('_reversal' if reverse else '')
 for line in doc['items']:
  qty=sign*line['quantity'];query={'id':line['product_id']}
  if qty<0:query['stock']={'$gte':-qty}
  if not c.update('products',query,inc={'stock':qty}):raise ValueError('Insufficient stock for '+line['description'])
  c.insert('movements',product_id=line['product_id'],quantity=qty,reason=('Reversal ' if reverse else '')+doc['number']+' · '+doc['party'],date=accounting.date() if reverse else doc['date'],kind=kind,store_document_id=doc['id'],actor_id=user['id'])

def save(c,d,user):
 access.require(user,('Store',))
 action=d.get('action','save')
 doc=c.one('store_documents',{'id':identifier(d['id'])}) if d.get('id') else None
 if d.get('id') and not doc:raise ValueError('Store document not found')
 if doc and d.get('version')!=doc['version']:raise ValueError('This document changed. Refresh before continuing.')
 if action=='eway':
  if not doc or doc['status']!='Posted':raise ValueError('Only posted documents can record an e-way bill')
  number=text(d,'eway_number',True)
  if not re.fullmatch(r'\d{12}',number):raise ValueError('Enter a 12-digit e-way bill number')
  c.update('store_documents',{'id':doc['id']},{'eway_number':number,'eway_recorded_by':user['name'],'eway_recorded_at':now()},inc={'version':1})
 elif action=='cancel':
  if not doc or doc['status']=='Cancelled':raise ValueError('Document is already cancelled or missing')
  reason=text(d,'reason',True)
  if c.one('store_documents',{'source_id':doc['id'],'status':'Posted'}):raise ValueError('Cancel linked return vouchers before cancelling the original voucher')
  if doc.get('source_id'):c.touch('store_documents',doc['source_id'])
  if doc['status']=='Posted':movement(c,doc,user,True)
  c.update('store_documents',{'id':doc['id']},{'status':'Cancelled','cancel_reason':reason,'cancelled_by':user['name'],'cancelled_at':now()},inc={'version':1})
 elif action in ('save','post','save_post'):
  if doc and doc['status']!='Draft':raise ValueError('Posted records cannot be edited. Cancel with a reason to reverse stock.')
  if action=='post' and doc:
   values=doc
  else:values=prepare(c,d)
  if doc and values['kind']!=doc['kind']:raise ValueError('Document operation cannot be changed')
  if not doc:
   did=c.insert('store_documents',**values,status='Draft',version=1,created_by=user['name'],created_at=now())
   number=vouchers.PREFIX[values['kind']]+'-'+str(did).zfill(6)
   c.update('store_documents',{'id':did},{'number':number})
   doc=c.one('store_documents',{'id':did})
  elif action in ('save','save_post'):
   c.update('store_documents',{'id':doc['id']},values,inc={'version':1})
  if action in ('post','save_post'):
   doc=c.one('store_documents',{'id':doc['id']})
   movement(c,doc,user)
   c.update('store_documents',{'id':doc['id']},{'status':'Posted','posted_by':user['name'],'posted_at':now()},inc={'version':1})
 else:raise ValueError('Unknown store action')
 c.insert('activity',message='Store document '+action+' by '+user['name'],date=now())
