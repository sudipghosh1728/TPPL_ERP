"""Physical stock, conversion journals, and linked Store return controls."""
import datetime
import accounting
from storage import identifier

SPECIAL=('Physical stock','Stock journal')
RETURN_KINDS={'Return in':'Issue','Return out':'Inbound'}
PREFIX={'Inbound':'GRN','Issue':'DC','Return in':'RI','Return out':'RO','Physical stock':'PS','Stock journal':'SJ'}

def quantity(value,zero=False):
 if zero and str(value)=='0':return 0
 n=identifier(value)
 if n>1000000000:raise ValueError('Quantity is too large')
 return n

def prepare(c,d):
 import store_ops
 kind=d['kind'];remarks=store_ops.text(d,'remarks',True)
 day=accounting.date(d.get('date'))
 if day>datetime.date.today().isoformat():raise ValueError('Voucher date cannot be in the future')
 rows=d.get('items')
 if not isinstance(rows,list) or not 1<=len(rows)<=50:raise ValueError('Add between 1 and 50 material lines')
 result={k:'' for k in ('address','reference','order_number','vehicle','transporter','lr_number','ir_number','eway_number','dispatch_address','party_gstin','company_gstin','order_date','lr_date','ir_date')}
 result.update(kind=kind,date=day,party='Internal stock control',remarks=remarks,company=c.one('settings',{'key':'company'})['value'],items=[],assessable=0,total=0,cgst=0,sgst=0,igst=0,cgst_rate=0,sgst_rate=0,igst_rate=0)
 seen=set();directions=set()
 for row in rows:
  if not isinstance(row,dict):raise ValueError('Invalid material line')
  pid=identifier(row.get('product_id'))
  if pid in seen:raise ValueError('Choose each material once per voucher')
  seen.add(pid);p=c.one('products',{'id':pid})
  if not p:raise ValueError('Material not found')
  qty=quantity(row.get('quantity'),kind=='Physical stock')
  if kind=='Physical stock':
   expected=quantity(row.get('book_quantity'),True)
   if p['stock']!=expected:raise ValueError('Stock changed since counting. Refresh and verify the count again.')
   delta=qty-expected;direction='Count'
  else:
   expected=None;direction=row.get('direction')
   if direction not in ('Consume','Produce'):raise ValueError('Select Consume or Produce for every journal line')
   directions.add(direction);delta=qty if direction=='Produce' else -qty
  result['items'].append(dict(product_id=pid,description=p['name'],sku=p['sku'],unit=p.get('unit','pcs'),warehouse=p.get('warehouse',''),quantity=qty,book_quantity=expected,delta=delta,direction=direction,rate=0,amount=0,hsn='',remarks=store_ops.text(row,'remarks')))
 if kind=='Stock journal' and directions!={'Consume','Produce'}:raise ValueError('A stock journal needs at least one consumption and one production line')
 return result

def validate_return(c,doc):
 source=c.one('store_documents',{'id':identifier(doc.get('source_id'))})
 if not source or source['status']!='Posted' or source['kind']!=RETURN_KINDS[doc['kind']]:raise ValueError('Select a posted original receipt or delivery note')
 if doc['date']<source['date']:raise ValueError('Return date cannot precede the original voucher')
 c.touch('store_documents',source['id'])
 returns=c.all('store_documents',{'source_id':source['id'],'status':'Posted','kind':doc['kind']})
 for line in doc['items']:
  original=next((x for x in source['items'] if x['product_id']==line['product_id']),None)
  used=sum(x['quantity'] for r in returns for x in r['items'] if x['product_id']==line['product_id'])
  if not original or line['quantity']>original['quantity']-used:raise ValueError('Return exceeds the unreturned quantity on '+source['number'])
 return source

def move_special(c,doc,user,reverse=False):
 import store_ops
 for line in doc['items']:
  delta=line['delta']*(-1 if reverse else 1);query={'id':line['product_id']}
  if not reverse and doc['kind']=='Physical stock':query['stock']=line['book_quantity']
  elif delta<0:query['stock']={'$gte':-delta}
  if not c.update('products',query,inc={'stock':delta}):raise ValueError('Stock changed or is insufficient for '+line['description']+'. Refresh and verify before posting.')
  c.insert('movements',product_id=line['product_id'],quantity=delta,reason=('Reversal ' if reverse else '')+doc['number']+' · '+doc['remarks'],date=accounting.date() if reverse else doc['date'],kind='stock_adjustment'+('_reversal' if reverse else ''),store_document_id=doc['id'],actor_id=user['id'])
