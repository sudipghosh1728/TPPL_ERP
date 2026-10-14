"""Domestic forward-charge GST snapshots and balanced tax ledger posting."""
import re
from decimal import Decimal,ROUND_HALF_UP
import accounting as a

def gstin(value,required=False):
    value=str(value or '').strip().upper()
    if not value and not required:return ''
    if not re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]',value):raise ValueError('Enter a valid 15-character GSTIN')
    return value
def prepare(c,d,items):
    supplier=gstin(d.get('supplier_gstin'),True);customer=gstin(d.get('customer_gstin'))
    pos=str(d.get('place_of_supply','')).strip()
    if not re.fullmatch(r'\d{2}',pos) or not 1<=int(pos)<=38:raise ValueError('Enter the two-digit place-of-supply state code')
    intra=supplier[:2]==pos;taxes={'cgst_paise':0,'sgst_paise':0,'igst_paise':0}
    for item,raw in zip(items,d['items']):
        hsn=str(raw.get('hsn','')).strip()
        if not re.fullmatch(r'\d{4}|\d{6}|\d{8}',hsn):raise ValueError('Enter the HSN code for each line (4, 6 or 8 digits)')
        try:rate=Decimal(str(raw.get('gst_rate')))
        except Exception:raise ValueError('Enter GST percentage for each material')
        if not rate.is_finite() or rate<=0 or rate>40:raise ValueError('Use a positive GST rate up to 40%; exempt supplies need a bill of supply')
        def tax(r):return int((Decimal(item['amount'])*r/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        item.update(hsn=hsn,gst_rate=str(rate),cgst_paise=tax(rate/2) if intra else 0,sgst_paise=tax(rate/2) if intra else 0,igst_paise=0 if intra else tax(rate))
        for key in taxes:taxes[key]+=item[key]
    w=c.one('settings',{'key':'workspace'}) or {};company=c.one('settings',{'key':'company'})
    return dict(document_mode='gst_dispatch',supplier_gstin=supplier,customer_gstin=customer,place_of_supply=pos,supply_type='Intrastate' if intra else 'Interstate',company_name=company['value'],company_address=a.text(d,'company_address'),customer_address=a.text(d,'customer_address'),delivery_address=a.text(d,'delivery_address'),taxable_paise=sum(i['amount'] for i in items),reverse_charge=False,**taxes)
def ledger(c,name):
    row=c.one('accounts',{'name_key':name.casefold()})
    if row:
        if row['type']!='Liability':raise ValueError(name+' must be a liability ledger')
        return row['id']
    return c.insert('accounts',name=name,type='Liability',system=1)
