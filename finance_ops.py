"""Additional Accounts vouchers; run inside the application's MongoDB transaction."""
import accounting as books
from storage import identifier


def contra(c,d):
 source=books.account(c,d.get('from_account_id'));target=books.account(c,d.get('to_account_id'))
 if source['type'] not in ('Bank','Cash') or target['type'] not in ('Bank','Cash'):raise ValueError('Select cash or bank accounts for both sides')
 if source['id']==target['id']:raise ValueError('Choose different source and destination accounts')
 amount=books.positive(d.get('amount'));day=books.date(d.get('date'))
 if day>books.date():raise ValueError('Posting date cannot be in the future')
 jid=books.journal(c,day,books.text(d,'reference'),books.text(d,'description'),[(target['id'],amount,0),(source['id'],0,amount)])
 c.update('journals',{'id':jid},{'voucher_type':'Contra'})


def note_total(c,key,record_id):
 return sum(j['note_amount'] for j in c.all('journals',{key:record_id}))


def note(c,d):
 kind=d.get('kind')
 if kind not in ('Credit note','Debit note'):raise ValueError('Choose credit or debit note')
 sales=kind=='Credit note';key='note_order_id' if sales else 'note_purchase_id'
 doc=c.one('orders' if sales else 'purchases',{'id':identifier(d.get('document_id'))})
 if not doc or (not sales and doc['status']!='Received'):raise ValueError('Select a sales invoice or a received supplier bill')
 c.touch('accounts',doc['account_id'])
 amount=books.positive(d.get('amount'));day=books.date(d.get('date'))
 original=c.one('journals',{'source':('invoice:' if sales else 'purchase:')+str(doc['id'])})
 if day<(original['date'] if original else doc['date']) or day>books.date():raise ValueError('Note date must be between the original posting date and today')
 total=books.cents(doc['total']) if sales else books.cents(doc['unit_cost'])*doc['quantity']
 paid=sum(s['amount'] for s in c.all('settlements',{'order_id' if sales else 'purchase_id':doc['id']}))
 remaining=total-paid-note_total(c,key,doc['id'])
 if amount>remaining:raise ValueError('Note exceeds the unpaid document balance. Paid-document refunds are not supported yet.')
 offset=books.system(c,'Sales revenue' if sales else 'Material purchases')
 lines=[(offset,amount,0),(doc['account_id'],0,amount)] if sales else [(doc['account_id'],amount,0),(offset,0,amount)]
 jid=books.journal(c,day,books.text(d,'reference'),books.text(d,'description'),lines)
 c.update('journals',{'id':jid},{'voucher_type':kind,key:doc['id'],'note_amount':amount})
 if sales:c.update('orders',{'id':doc['id']},{'status':'Settled' if remaining==amount else 'Part paid' if paid else 'Pending'})


def reconcile(c,d):
 line=c.one('journal_lines',{'id':identifier(d.get('line_id'))})
 if not line or books.account(c,line['account_id'])['type']!='Bank':raise ValueError('Select a bank ledger entry')
 journal=c.one('journals',{'id':line['journal_id']})
 day=books.date(d['cleared_date']) if d.get('cleared_date') else ''
 if day and not journal['date']<=day<=books.date():raise ValueError('Clearance date must be between voucher date and today')
 expected=d.get('previous_date','')
 if expected!=line.get('cleared_date',''):raise ValueError('Clearance was changed by another user. Refresh before continuing.')
 c.update('journal_lines',{'id':line['id']},{'cleared_date':day})
