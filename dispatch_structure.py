"""Assembly quantities are delivery units; drawing quantities are component pieces."""
import manufacturing as m

def assemblies(lot):return lot.get('quantity_basis')=='assemblies'

def item_context(lot,item_id):
 items={r['id']:r for r in lot.get('work_items',[])};path=[];seen=set();quantity=1
 while item_id:
  if item_id in seen or len(seen)>=10:raise ValueError('Job hierarchy is too deep or contains a cycle')
  item=items.get(item_id)
  if not item:raise ValueError('Choose a job from this dispatch lot')
  seen.add(item_id);path.insert(0,item['name']);quantity=m.whole(quantity*item['quantity']);item_id=item.get('parent_id')
 return quantity,' / '.join(path)

def planning_errors(lot,batches):
 rows=[b for b in batches if b.get('lot_id')==lot['id']]
 if not assemblies(lot):
  return [] if sum(b['quantity'] for b in rows)==lot['quantity'] else ['Plan every drawing quantity for dispatch lot '+lot['name']]
 items=lot.get('work_items',[]);errors=[];ids={i['id'] for i in items}
 if not items or sum(i['quantity'] for i in items if not i.get('parent_id'))!=lot['quantity']:errors.append('Allocate all finished assemblies to jobs in '+lot['name'])
 for item in items:
  quantity,_=item_context(lot,item['id'])
  drawings=[b for b in rows if b.get('work_item_id')==item['id']]
  if not drawings and not any(i.get('parent_id')==item['id'] for i in items):errors.append('Add drawings for job '+item['name'])
  if any(b['quantity']!=quantity*b.get('pieces_per_item',0) for b in drawings):errors.append('Drawing quantities do not match job '+item['name'])
 if any(b.get('work_item_id') not in ids for b in rows):errors.append('Assign every drawing to a job in '+lot['name'])
 return errors

def dispatched(lot,batches):
 rows=[b for b in batches if b.get('lot_id')==lot['id']]
 return bool(rows) and not planning_errors(lot,rows) and all(b.get('actual_date') for b in rows)

def tc_applies(doc,batch,project):
 if doc.get('kind')!='TC':return False
 if doc.get('tc_batch_id'):return doc['tc_batch_id']==batch['id']
 if not doc.get('tc_item_id'):return doc.get('tc_scope')=='project'
 if doc.get('tc_lot_id')!=batch.get('lot_id'):return False
 lot=next((l for l in project.get('dispatch_lots',[]) if l['id']==batch.get('lot_id')),{})
 items={i['id']:i for i in lot.get('work_items',[])};item_id=batch.get('work_item_id');seen=set()
 while item_id and item_id not in seen:
  if item_id==doc['tc_item_id']:return True
  seen.add(item_id);item_id=items.get(item_id,{}).get('parent_id')
 return False
