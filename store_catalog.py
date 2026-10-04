"""Private catalogue imports and explicit opening-stock confirmation."""
import hashlib,json,re
import accounting,access,company
from storage import identifier

def normalized(name):return re.sub(r'\s+',' ',name.strip()).casefold()

def import_names(c,rows,source_key,apply=False):
 if not isinstance(rows,list) or not 1<=len(rows)<=2000:raise ValueError('Provide 1–2000 catalogue rows')
 existing=c.all('products');seen=set();result=[];cfg=company.get(c)
 if apply:c.update('settings',{'key':'company'},inc={'_revision':1})
 for row in rows:
  name=company.text(row.get('name'),'material name',200);key=normalized(name)
  if key in seen:raise ValueError('Duplicate material name in import: '+name)
  seen.add(key);number=identifier(row.get('row'));sku='CAT-'+source_key[:8].upper()+'-'+str(number).zfill(3)
  matches=[p for p in existing if p['sku']==sku or normalized(p['name'])==key]
  if matches:
   result.append(dict(row=number,name=name,action='Existing material retained',id=matches[0]['id']));continue
  record=dict(name=name,sku=sku,stock=0,unit='',minimum=0,price=0,category='Consumables' if 'Consumables' in cfg['categories'] else cfg['categories'][0],warehouse=cfg['warehouses'][0],catalog_pending=True,catalog_source=source_key,catalog_row=number,catalog_values=row.get('source_values',[]))
  pid=c.insert('products',**record) if apply else None
  existing.append({**record,'id':pid});result.append(dict(row=number,name=name,action='Added pending opening stock' if apply else 'New material',id=pid))
 if apply:c.insert('activity',message=f'Imported material catalogue: {sum(r["action"]=="Added pending opening stock" for r in result)} new names; existing stock unchanged',date=accounting.date())
 return result

def confirm(c,d,user):
 access.require(user,('Store',));pid=identifier(d.get('id'));p=c.one('products',{'id':pid})
 if not p or not p.get('catalog_pending'):raise ValueError('This material has already been confirmed or does not exist')
 unit=company.text(d.get('unit'),'stock unit',30);cfg=company.get(c)
 if unit not in cfg['units']:raise ValueError('Choose a configured stock unit')
 qty=d.get('quantity');qty=0 if str(qty)=='0' else identifier(qty)
 if qty>1000000000:raise ValueError('Opening stock is too large')
 day=accounting.date(d.get('date'))
 if day>accounting.date():raise ValueError('Opening date cannot be in the future')
 if p['stock']!=0 or c.one('movements',{'product_id':pid}):raise ValueError('Material has stock activity; refresh and review before confirming')
 c.update('products',{'id':pid},{'unit':unit,'stock':qty,'catalog_pending':False,'stock_started_on':day,'catalog_confirmed_by':user['name']})
 c.insert('movements',product_id=pid,quantity=qty,date=day,kind='catalog_opening',reason='Confirmed opening stock · '+user['name'],actor_id=user['id'])
 c.insert('activity',message='Opening stock and unit confirmed: '+p['name'],date=accounting.date())

def require_ready(product):
 if product and product.get('catalog_pending'):raise ValueError('Confirm the stock unit and opening balance for '+product['name']+' in Store first')

def invoice_register(c):
 """Read-only invoice projections; exclude ledgers, settlements and bank details."""
 received_dates={j['source']:j['date'] for j in c.all('journals',{'source':{'$regex':'^purchase:'}},projection={'source':1,'date':1})}
 items=c.all('invoice_items');products={p['id']:p for p in c.all('products')};result=[]
 for o in c.all('orders',sort=[('id',-1)]):
  result.append(dict(key='sale:'+str(o['id']),number=f'INV-{o["id"]:04}',kind='Sales invoice',party=o['customer'],date=o['date'],total=accounting.cents(o['total']),items=[{k:i.get(k) for k in ('product_id','description','quantity','unit_price','amount')} for i in items if i['order_id']==o['id']]))
 for p in c.all('purchases',{'status':'Received'},sort=[('id',-1)]):
  price=accounting.cents(p['unit_cost']);amount=price*p['quantity']
  result.append(dict(key='bill:'+str(p['id']),number=f'BILL-{p["id"]:04}',kind='Supplier bill',party=p['supplier'],date=received_dates.get('purchase:'+str(p['id']),p['date']),total=amount,items=[dict(product_id=p['product_id'],description=products.get(p['product_id'],{}).get('name','Material'),quantity=p['quantity'],unit_price=price,amount=amount)]))
 return result

if __name__=='__main__':
 import argparse,pathlib
 from storage import MongoStore
 parser=argparse.ArgumentParser(description='Import material names without assuming stock quantities or units')
 parser.add_argument('path');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 payload=pathlib.Path(args.path).read_bytes();rows=json.loads(payload);key=hashlib.sha256(payload).hexdigest();store=MongoStore()
 try:
  result=store.run(lambda c:import_names(c,rows,key,args.apply))
  out=pathlib.Path('data/catalog-import-result.json');out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8')
  print(json.dumps({'rows':len(result),'added':sum(r['action']=='Added pending opening stock' for r in result),'existing':sum(r['action']=='Existing material retained' for r in result),'applied':args.apply}))
 finally:store.close()
