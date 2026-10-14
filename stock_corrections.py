"""Audited cumulative receipt/issue corrections; never overwrite movement history."""
import access,accounting,store_catalog
from storage import identifier

def totals(c,p):
    inbound=outbound=adjustments=0
    for m in c.all('movements',{'product_id':p['id']}):
        kind=m.get('kind','');q=m['quantity']
        if kind=='catalog_opening':continue
        if kind.startswith('stock_adjustment'):adjustments+=q
        elif kind in ('outbound_correction','store_issue_reversal','return_in','return_in_reversal'):outbound-=q
        elif kind in ('inbound_correction','store_receipt_reversal','return_out','return_out_reversal'):inbound+=q
        elif q>0:inbound+=q
        else:outbound-=q
    return {'inbound':inbound,'outbound':outbound,'adjustments':adjustments,'opening':p['stock']-inbound+outbound-adjustments}
def whole(value):
    n=int(value)
    if str(n)!=str(value) or not 0<=n<=1000000000:raise ValueError('Use non-negative whole quantities')
    return n
def save(c,d,user):
    access.require(user,('Store',));p=c.one('products',{'id':identifier(d.get('product_id'))})
    if not p:raise ValueError('Material not found')
    store_catalog.require_ready(p);t=totals(c,p)
    if any(d.get('expected_'+k)!=v for k,v in {'stock':p['stock'],'inbound':t['inbound'],'outbound':t['outbound']}.items()):raise ValueError('Stock changed. Refresh before correcting totals.')
    inbound=whole(d.get('inbound'));outbound=whole(d.get('outbound'));reason=accounting.text(d,'reason');day=accounting.date(d.get('date'))
    if day>accounting.date():raise ValueError('Correction date cannot be in the future')
    available=t['opening']+inbound+t['adjustments']-outbound
    if available<0:raise ValueError('Outbound exceeds available stock')
    if inbound==t['inbound'] and outbound==t['outbound']:raise ValueError('No quantity changed')
    cid=c.insert('stock_corrections',product_id=p['id'],before={**t,'stock':p['stock']},after={'inbound':inbound,'outbound':outbound,'stock':available},reason=reason,date=day,actor_id=user['id'],actor=user['name'])
    c.update('products',{'id':p['id']},{'stock':available})
    for kind,delta in [('inbound_correction',inbound-t['inbound']),('outbound_correction',t['outbound']-outbound)]:
        if delta:c.insert('movements',product_id=p['id'],quantity=delta,kind=kind,date=day,correction_id=cid,actor_id=user['id'],reason=f'Stock correction {cid} · {reason}')
    c.insert('activity',message=f'Stock totals corrected for {p["name"]} by {user["name"]}: {reason}',date=day)
