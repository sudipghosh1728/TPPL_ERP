"""Company configuration shared by API validation and the setup screen."""
import datetime
import access
TEMPLATES={
 'Factory':dict(categories=['Raw materials','Consumables','Finished goods'],warehouses=['Main store','Production store'],units=['pcs','kg','m','litre'],fields=['Grade','Drawing reference'],manufacturing=True),
 'Supermarket':dict(categories=['Grocery','Household','Personal care'],warehouses=['Shop floor','Back store'],units=['pcs','pack','kg','litre'],fields=['Brand','Pack size'],manufacturing=False),
 'General business':dict(categories=['Goods','Supplies'],warehouses=['Main store'],units=['pcs','box','pack'],fields=['Brand','Model'],manufacturing=False)}

def get(c):
 row=c.one('settings',{'key':'workspace'})
 return row['value'] if row else dict(industry='Factory',configured=False,address='',financial_year='',**TEMPLATES['Factory'])

def text(value,label,maximum=200):
 if not isinstance(value,str) or not value.strip() or len(value.strip())>maximum:raise ValueError('Enter a valid '+label)
 return value.strip()

def save(c,d):
 industry=d.get('industry')
 if industry not in TEMPLATES:raise ValueError('Choose a supported industry template')
 company=text(d.get('company'),'company name',100)
 value=dict(industry=industry,configured=True,address=text(d.get('address'),'company address',500),financial_year=datetime.date.fromisoformat(d.get('financial_year','')).isoformat())
 for key in ('categories','warehouses','units','fields'):
  items=d.get(key)
  if not isinstance(items,list) or len(items)>50 or (key!='fields' and not items):raise ValueError('Enter valid '+key)
  value[key]=[text(x,key,60) for x in items]
  if len({x.casefold() for x in value[key]})!=len(items):raise ValueError('Remove duplicate '+key)
 if type(d.get('manufacturing')) is not bool:raise ValueError('Choose whether manufacturing is enabled')
 value['manufacturing']=d['manufacturing']
 if not value['manufacturing'] and (c.one('work_jobs',{'stage':{'$ne':'Completed'}}) or c.one('jobs',{'status':{'$ne':'Completed'}})):
  raise ValueError('Complete active production jobs before disabling manufacturing')
 for key,v in [('workspace',value),('company',company)]:
  if c.one('settings',{'key':key}):c.update('settings',{'key':key},{'value':v})
  else:c.insert('settings',key=key,value=v)
 return value

def guard(c,path):
 if (path.startswith('/api/work/') or path.startswith('/api/documents/') or path in ('/api/jobs','/api/job-action')) and not get(c)['manufacturing']:
  raise access.AccessError('Manufacturing is disabled for this company',403)

def product_details(c,d):
 cfg=get(c)
 if cfg['configured']:
  for key,choices in [('category','categories'),('warehouse','warehouses'),('unit','units')]:
   if d.get(key) not in cfg[choices]:raise ValueError('Choose a configured '+key)
 unit=text(d.get('unit','pcs'),'unit',30)
 barcode=d.get('barcode','')
 if not isinstance(barcode,str) or len(barcode)>80:raise ValueError('Invalid barcode')
 if barcode and c.one('products',{'barcode':barcode}):raise ValueError('Barcode already exists')
 attrs=d.get('attributes',{})
 if not isinstance(attrs,dict) or any(k not in cfg['fields'] for k in attrs):raise ValueError('Unknown product field')
 attrs={k:text(v,k) for k,v in attrs.items() if v!=''}
 return dict(unit=unit,barcode=barcode,attributes=attrs)
