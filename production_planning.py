"""Dispatch-lot design planning and material visibility; existing stock stays authoritative."""
import math,uuid
import access,manufacturing as m,project_flow as p,qc_ops as q,dispatch_structure as ds
from storage import identifier

def dispatch_lot(c,d,user):
 access.require(user,('Design',));j=p.project(c,d,user);m.version(j,d);p.open_job(j)
 lots=j.get('dispatch_lots',[]);lid=str(d.get('lot_id') or uuid.uuid4().hex)
 if d.get('lot_id') and not any(l['id']==lid for l in lots):raise ValueError('Choose an existing dispatch lot to update')
 previous=next((l for l in lots if l['id']==lid),{})
 basis=d.get('quantity_basis',previous.get('quantity_basis','pieces'))
 if basis not in ('assemblies','pieces'):raise ValueError('Choose finished assemblies or individual parts')
 row={**previous,**dict(id=lid,name=m.text(d,'name')[:100],quantity=m.whole(d.get('quantity')),date=p.date(d.get('date')),quantity_basis=basis)}
 if sum(r['quantity'] for r in lots if r['id']!=lid)+row['quantity']>j['quantity']:raise ValueError('Dispatch quantities exceed the PO quantity')
 batches=c.all('qc_batches',{'job_id':j['id'],'lot_id':lid})
 if (batches or previous.get('work_items')) and basis!=previous.get('quantity_basis','pieces'):raise ValueError('Quantity basis cannot change after jobs or drawings have been planned')
 if ds.assemblies(row):
  if sum(i['quantity'] for i in row.get('work_items',[]) if not i.get('parent_id'))>row['quantity']:raise ValueError('Dispatch quantity cannot be below its planned assemblies')
 elif sum(b['quantity'] for b in batches)>row['quantity']:raise ValueError('Dispatch quantity cannot be below its planned drawing quantities')
 if any(b.get('actual_date') for b in batches):raise ValueError('A dispatched lot cannot be rescheduled')
 for b in batches:
  c.update('qc_batches',{'id':b['id']},{'planned_date':row['date']},inc={'version':1})
 c.update('work_jobs',{'id':j['id']},{'dispatch_lots':[r for r in lots if r['id']!=lid]+[row]})
 p.record(c,j,user,'Dispatch lot planned',row['name']+' · '+str(row['quantity'])+' '+basis+' · '+row['date'])

def work_item(c,d,user):
 access.require(user,('Design',));j=p.project(c,d,user);m.version(j,d);p.open_job(j)
 lots=j.get('dispatch_lots',[]);lot=next((l for l in lots if l['id']==d.get('lot_id')),None)
 if not lot or not ds.assemblies(lot):raise ValueError('Choose a dispatch lot measured in finished assemblies')
 if c.one('qc_batches',{'job_id':j['id'],'lot_id':lot['id'],'actual_date':{'$nin':['',None]}}):raise ValueError('A lot with dispatched drawings cannot be changed')
 items=lot.get('work_items',[]);parent=d.get('parent_id') or None
 if len(items)>=200:raise ValueError('Use at most 200 jobs per dispatch')
 if parent:
  ds.item_context(lot,parent)
 name=m.text(d,'name')[:100];quantity=m.whole(d.get('quantity'))
 if any(i.get('parent_id')==parent and i['name'].casefold()==name.casefold() for i in items):raise ValueError('Use a unique job name under this parent')
 if not parent and sum(i['quantity'] for i in items if not i.get('parent_id'))+quantity>lot['quantity']:raise ValueError('Job quantities exceed the finished assemblies in this dispatch')
 item=dict(id=uuid.uuid4().hex,parent_id=parent,name=name,quantity=quantity)
 lot={**lot,'work_items':items+[item]};total,path=ds.item_context(lot,item['id'])
 c.update('work_jobs',{'id':j['id']},{'dispatch_lots':[lot if l['id']==lot['id'] else l for l in lots],'final_inspection':False})
 p.record(c,j,user,'Dispatch job planned',path+' · '+str(total)+' units in dispatch')
 return item['id']

def dim(d,key,required=False):
 try:v=float(d.get(key) or 0)
 except (TypeError,ValueError):raise ValueError('Enter numeric dimensions in mm')
 if not math.isfinite(v) or v<0 or v>1000000 or (required and not v):raise ValueError('Enter valid '+key.replace('_',' '))
 return v

def requirement(c,d,user):
 access.require(user,('Design',));b,j=q.batch(c,d,user,True,author=True);m.version(j,{'version':d.get('job_version')})
 product=c.one('products',{'id':identifier(d.get('product_id'))})
 if not product:raise ValueError('Choose a Store material')
 per=m.whole(d.get('pieces_per_job'));qty=per*b['quantity'];shape=d.get('shape')
 if shape not in ('Plate','Bar','Other'):raise ValueError('Choose Plate, Bar or Other')
 dims={k:dim(d,k,k in ('length_mm','thickness_mm') or k=='width_mm' and shape=='Plate') for k in ('length_mm','width_mm','thickness_mm','blank_length_mm','blank_width_mm')}
 if dims['blank_length_mm'] and dims['blank_length_mm']<dims['length_mm'] or dims['blank_width_mm'] and dims['blank_width_mm']<dims['width_mm']:raise ValueError('Blank dimensions cannot be smaller than finished dimensions')
 rid=c.insert('requirements',job_id=j['id'],batch_id=b['id'],lot_id=b.get('lot_id'),drawing=b['drawing'],product_id=product['id'],quantity=qty,pieces_per_job=per,shape=shape,dimensions=dims,department='Design',material_group='Raw material',notes=m.text(d,'notes'),cut_quantity=0,created_by=user['id'])
 p.revise(c,j,user,'Drawing material requirement changed');p.record(c,j,user,'Drawing material planned',b['drawing']+' · '+str(qty)+' stock units')
 p.notify(c,j,user,'Design requirements ready for '+b['drawing'],('Fabrication','Store','Purchase'))
 return rid

def cut(c,d,user):
 access.require(user,('Design',));j=p.project(c,d,user);m.version(j,d);p.open_job(j)
 r=c.one('requirements',{'id':identifier(d.get('requirement_id')),'job_id':j['id']})
 if not r or not r.get('batch_id'):raise ValueError('Choose a drawing material requirement')
 b,_=q.batch(c,{'batch_id':r['batch_id']},user)
 if b.get('actual_date'):raise ValueError('Dispatched requirements are read-only')
 try:qty=int(d.get('cut_quantity'));scrap=float(d.get('scrap_kg') or 0)
 except (TypeError,ValueError):raise ValueError('Enter a whole cut quantity and numeric scrap weight')
 if isinstance(d.get('cut_quantity'),bool) or float(d.get('cut_quantity'))!=qty or not 0<=qty<=r['quantity']:raise ValueError('Cut quantity must be within the drawing requirement')
 if not math.isfinite(scrap) or scrap<0:raise ValueError('Scrap weight cannot be negative')
 c.update('requirements',{'id':r['id']},{'cut_quantity':qty,'scrap_kg':scrap,'cut_updated_by':user['name'],'cut_updated_at':m.now()})
 p.record(c,j,user,'Design cutting quantities updated',r['drawing']+' · cut '+str(qty)+' · scrap '+str(scrap)+' kg · '+m.text(d,'notes'))
 p.notify(c,j,user,'Cut material update for '+r['drawing'],('Fabrication','Purchase','Store'))

def specifications(c,d,user):
 access.require(user,access.ROLES);j=p.project(c,d,user);m.version(j,d);p.open_job(j)
 values={k:str(d.get(k,'')).strip() for k in ('painting','material')}
 if any(len(v)>4000 for v in values.values()):raise ValueError('Specifications must be under 4000 characters each')
 c.update('work_jobs',{'id':j['id']},{'po_specs':{**j.get('po_specs',{}),**values,'status':'User reviewed','reviewed_by':user['name'],'reviewed_at':m.now()}})
 if any(values[k]!=j.get('po_specs',{}).get(k,'') for k in values):
  for b in c.all('qc_batches',{'job_id':j['id']}):
   if not b.get('actual_date'):
    q.invalidate(c,b,j);q.log(c,b,user,'PO specifications changed; fresh QC review required',m.text(d,'notes'))
 c.insert('work_history',job_id=j['id'],actor_id=user['id'],actor_name=user['name'],department=user['role'],action='PO specifications revision',notes=m.text(d,'notes'),created_at=m.now(),specifications_before={k:j.get('po_specs',{}).get(k,'') for k in values},specifications_after=values)
 p.record(c,j,user,'PO specifications reviewed',m.text(d,'notes'));p.notify(c,j,user,'Painting / special material specifications updated',('Design','Fabrication','QC','Purchase'))

def extract_po(c,d,user):
 import po_entities
 access.require(user,access.ROLES);j=p.project(c,d,user);m.version(j,d);p.open_job(j)
 docs=c.all('job_documents',{'job_id':j['id'],'kind':{'$in':['PO','Revised PO']}},sort=[('id',-1)])
 if not docs:raise ValueError('Upload a PO before extracting specifications')
 doc=docs[0];suggestion={**po_entities.suggestions(doc['content'],doc['name']),'document_id':doc['id']}
 c.update('work_jobs',{'id':j['id']},{'po_spec_suggestions':suggestion,**({'po_specs':suggestion} if not j.get('po_specs') else {})})
 p.record(c,j,user,'PO extraction refreshed','Review the painting and material suggestions against the original PO')

HANDLERS={'work-item':work_item,'extract-po':extract_po,'dispatch-lot':dispatch_lot,'drawing-requirement':requirement,'cut-material':cut,'specifications':specifications}
