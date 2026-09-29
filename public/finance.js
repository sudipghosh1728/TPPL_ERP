let selectedLedger=null, ledgerFrom='', ledgerTo='', salesFilter='All', accountFilter='All';
const rupees=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:2,maximumFractionDigits:2}).format((n||0)/100);
const acct=id=>state.accounts.find(a=>a.id===Number(id));
const balanceText=n=>`${rupees(Math.abs(n))}${n?' '+(n>0?'Dr':'Cr'):''}`;
const invoiceName=o=>`INV-${String(o.id).padStart(4,'0')}`;
const financeButton=(label,action,secondary=false)=>`<button class="${secondary?'secondary':'primary'}" data-finance="${action}">${label}</button>`;
const accountOptions=types=>state.accounts.filter(a=>types.includes(a.type)).map(a=>[a.id,a.name]);
function financeSales(){
 const orders=filtered(state.orders).filter(o=>salesFilter==='All'||(salesFilter==='Overdue'?o.outstanding_paise>0&&o.due<today():o.status===salesFilter));
 return heading('Sales & invoices','Create an invoice, track what is due, and record every receipt.',financeButton('＋ Add customer','customer',true)+button('+ Create invoice','order'))+
 `<div class="stats three">${stat('Total invoiced',rupees(sum(state.orders,'total_paise')),'Sales excluding tax','↗')}${stat('Payments received',rupees(sum(state.orders,'paid_paise')),'Receipts allocated to invoices','✓')}${stat('Still to collect',rupees(sum(state.orders,'outstanding_paise')),'Unpaid and partially paid invoices','◷')}</div>`+
 `<div class="workflow-strip"><span><b>1</b> Choose a customer</span><i>→</i><span><b>2</b> Add products & quantities</span><i>→</i><span><b>3</b> Save invoice & collect payment</span></div>`+
 `<section class="panel">${toolbar('Search invoice number, customer, or date…')}<div class="filter-tabs">${['All','Pending','Part paid','Paid','Overdue'].map(s=>`<button class="${salesFilter===s?'selected':''}" data-sales-filter="${s}">${s==='Pending'?'Unpaid':s}</button>`).join('')}<span>${orders.length} invoices</span></div>`+
 table(['INVOICE','CUSTOMER','DATE / DUE','INVOICE TOTAL','STILL DUE','STATUS',''],orders.map(o=>[`<button class="text-button" data-invoice="${o.id}">${invoiceName(o)}</button>`,`<strong>${esc(o.customer)}</strong><small>${state.invoice_items.filter(i=>i.order_id===o.id).length} item(s)</small>`,`${o.date}<small>Due ${o.due}${o.outstanding_paise>0&&o.due<today()?' · Overdue':''}</small>`,rupees(o.total_paise),`<strong>${rupees(o.outstanding_paise)}</strong>`,badge(o.status),`<div class="actions"><button class="secondary small-button" data-invoice="${o.id}">View</button>${o.outstanding_paise>0?`<button class="primary small-button" data-receipt="${o.id}">Receive payment</button>`:''}</div>`]))+'</section>';
}
function accounts(){
 const cash=state.accounts.filter(a=>['Cash','Bank'].includes(a.type)).reduce((s,a)=>s+a.balance,0),receivable=state.accounts.filter(a=>a.type==='Customer').reduce((s,a)=>s+a.balance,0),payable=-state.accounts.filter(a=>a.type==='Supplier').reduce((s,a)=>s+a.balance,0);
 const rows=filtered(state.accounts).filter(a=>accountFilter==='All'||a.type===accountFilter);
 return heading('Accounts & ledgers','Know who owes you, what you owe, and where your money goes.',financeButton('Record payment','payment',true)+financeButton('+ Add account','account'))+
 `<div class="stats three">${stat('Cash & bank',rupees(cash),'Net recorded balance','▤')}${stat('Customers owe you',rupees(receivable),'Includes customer opening balances','↙')}${stat('You owe suppliers',rupees(payable),'Received bills and opening balances','↗')}</div>`+
 `<div class="quick-actions"><button data-finance="customer"><span class="quick-icon blue">♧</span><strong>Add customer</strong><small>For sales and collections</small><span>↗</span></button><button data-finance="supplier"><span class="quick-icon orange">▦</span><strong>Add supplier</strong><small>For purchases and payments</small><span>↗</span></button><button data-finance="expense"><span class="quick-icon purple">▤</span><strong>Record expense</strong><small>Pay from cash or bank</small><span>↗</span></button></div>`+
 `<section class="panel">${toolbar('Search account name, type, phone, or email…')}<div class="filter-tabs">${['All','Customer','Supplier','Cash','Bank','Expense'].map(t=>`<button class="${accountFilter===t?'selected':''}" data-account-filter="${t}">${t==='All'?'All accounts':t+'s'}</button>`).join('')}</div>`+
 table(['ACCOUNT','TYPE','CONTACT','TOTAL DEBITS','TOTAL CREDITS','BALANCE',''],rows.map(a=>[`<button class="account-name" data-ledger="${a.id}"><span class="account-avatar ${a.type==='Supplier'?'orange':a.type==='Customer'?'blue':'purple'}">${esc(a.name[0].toUpperCase())}</span><strong>${esc(a.name)}</strong></button>`,badge(a.type),`${esc(a.phone||'—')}<small>${esc(a.email)}</small>`,rupees(a.debit),rupees(a.credit),`<strong>${balanceText(a.balance)}</strong>`,`<button class="text-button" data-ledger="${a.id}">Open ledger →</button>`]))+'</section>';
}
function ledgerData(){
 const a=acct(selectedLedger)||state.accounts[0];if(!a)return {a:null,rows:[],opening:0,closing:0};selectedLedger=a.id;
 const entries=state.journal_lines.filter(l=>l.account_id===a.id).map(l=>({...l,...state.journals.find(j=>j.id===l.journal_id)})).sort((x,y)=>x.date.localeCompare(y.date)||x.journal_id-y.journal_id);
 const opening=entries.filter(e=>ledgerFrom&&e.date<ledgerFrom).reduce((s,e)=>s+e.debit-e.credit,0);
 let running=opening;
 const rows=entries.filter(e=>(!ledgerFrom||e.date>=ledgerFrom)&&(!ledgerTo||e.date<=ledgerTo)).map(e=>{running+=e.debit-e.credit;return {...e,running}});
 return {a,rows,opening,closing:running};
}
function ledgers(){
 const {a,rows,opening,closing}=ledgerData();
 return heading('Ledger statement','Every transaction, with a running balance you can follow.',financeButton('↓ Export statement','ledger-export',true))+
 `<section class="panel"><div class="ledger-controls">${select('Choose account','ledger_account',state.accounts.map(a=>[a.id,`${a.name} · ${a.type}`]))}${field('From date','ledger_from','date',ledgerFrom)}${field('To date','ledger_to','date',ledgerTo)}<button class="secondary" data-finance="clear-dates">Clear dates</button></div></section>`+
 `<div class="stats three">${stat('Opening balance',balanceText(opening),'Before selected start date','↳')}${stat('Debits / credits',`${rupees(sum(rows,'debit'))} / ${rupees(sum(rows,'credit'))}`,'Movements in selected period','⇄')}${stat('Closing balance',balanceText(closing),esc(a?.name||'Choose an account'),'▤')}</div>`+
 panel(esc(a?.name||'Account ledger'),`${rows.length} entries · Dr = debit balance · Cr = credit balance`,table(['DATE','REFERENCE','DESCRIPTION','DEBIT','CREDIT','RUNNING BALANCE'],rows.map(r=>[r.date,esc(r.reference),`<span class="wrap-text">${esc(r.description)}</span>`,r.debit?rupees(r.debit):'—',r.credit?rupees(r.credit):'—',`<strong>${balanceText(r.running)}</strong>`])));
}
function vouchers(){
 const debit=sum(state.accounts,'debit'),credit=sum(state.accounts,'credit');
 return heading('Books & vouchers','Review posted transactions and check that your books balance.',financeButton('Record expense','expense',true)+financeButton('+ Journal voucher','journal'))+
 `<div class="book-status"><span class="dot"></span><strong>${debit===credit?'Your books are balanced':'Books need review'}</strong><span>Total debits ${rupees(debit)} = total credits ${rupees(credit)}</span></div>`+
 panel('Day book','Every sale, receipt, payment, and journal in one place.',table(['DATE','VOUCHER','DESCRIPTION','DEBIT','CREDIT'],[...state.journals].sort((a,b)=>b.date.localeCompare(a.date)||b.id-a.id).map(j=>{const lines=state.journal_lines.filter(l=>l.journal_id===j.id);return [j.date,esc(j.reference),`<span class="wrap-text">${esc(j.description)}</span>`,rupees(sum(lines,'debit')),rupees(sum(lines,'credit'))]})))+
 panel('Trial balance','Net balance of each account. Purchase expenses use a simple periodic bookkeeping model.',table(['ACCOUNT','TYPE','DEBIT BALANCE','CREDIT BALANCE'],state.accounts.map(a=>[`<button class="text-button" data-ledger="${a.id}">${esc(a.name)}</button>`,a.type,a.balance>0?rupees(a.balance):'—',a.balance<0?rupees(-a.balance):'—']).concat([['<strong>Total</strong>','',`<strong>${rupees(state.accounts.reduce((s,a)=>s+Math.max(a.balance,0),0))}</strong>`,`<strong>${rupees(state.accounts.reduce((s,a)=>s+Math.max(-a.balance,0),0))}</strong>`]])));
}
function bindFinance(){
 const a=$('[name=ledger_account]');if(a){a.value=selectedLedger;a.onchange=()=>{selectedLedger=+a.value;render()};for(const key of ['from','to'])$(`[name=ledger_${key}]`).onchange=e=>{const value=e.target.value;const from=key==='from'?value:ledgerFrom,to=key==='to'?value:ledgerTo;if(from&&to&&from>to){toast('Start date must be on or before end date');e.target.value=key==='from'?ledgerFrom:ledgerTo;return}ledgerFrom=from;ledgerTo=to;render()}}
}
function financeForm(title,body,path,transform=x=>x,after){
 modal(title,`<form id="finance-form">${body}<div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="secondary" data-close>Cancel</button><button type="submit" class="primary">Save & post</button></div></form>`);
 const token=crypto.randomUUID();
 $('#finance-form').onsubmit=async e=>{e.preventDefault();const f=e.target,btn=f.querySelector('[type=submit]');btn.disabled=true;try{const data=transform(Object.fromEntries(new FormData(f)));await post(path,{...data,request_id:token});$('#modal').close();if(after)after()}catch(err){f.querySelector('.form-error').textContent=err.message}finally{btn.disabled=false}};
}
function accountForm(kind='Customer'){
 financeForm(kind==='Customer'?'Add a customer':kind==='Supplier'?'Add a supplier':'Add an account',
 `<p class="form-intro">Create a ledger once, then use it for invoices, payments, and statements.</p><div class="form-grid">${field('Account / business name','name')}${select('Account type','type',['Customer','Supplier','Cash','Bank','Asset','Liability','Equity','Income','Expense'].map(t=>[t,t]))}${optionalField('Email','email','email')}${optionalField('Phone','phone','tel')}</div>${optionalField('Billing address','address')}<details class="opening-details"><summary>Have an opening balance? <span>Optional</span></summary><p class="form-intro">Enter only the balance from before you began using this workspace. It is posted against opening balance equity.</p><div class="form-grid">${field('Opening amount (₹)','opening','number',0)}${select('Balance side','opening_side',[['Debit','Debit · amount owed to you / asset'],['Credit','Credit · amount you owe / liability']])}${field('Opening date','date','date',today())}</div></details>`, 'accounts');
 $('[name=type]').value=kind;$('[name=opening_side]').value=kind==='Supplier'?'Credit':'Debit';
}
function optionalField(label,name,type='text'){return `<label class="field">${label} <span class="optional">Optional</span><input name="${name}" type="${type}" maxlength="500"></label>`}
function invoiceRow(){return `<div class="invoice-line"><label class="field">Product<select class="line-product" required><option value="">Choose product…</option>${state.products.map(p=>`<option value="${p.id}">${esc(p.name)} · ${p.stock} in stock</option>`).join('')}</select></label><label class="field">Quantity<input class="line-qty" type="number" min="1" step="1" value="1" required></label><label class="field">Unit price (₹)<input class="line-price" type="number" min="0" step="0.01" value="0" required></label><div class="line-total">₹0.00</div><button class="icon-button remove-line" type="button" aria-label="Remove item">×</button></div>`}
function openInvoice(){
 const customers=accountOptions(['Customer']);
 if(!customers.length){toast('Add your first customer, then create an invoice.');return accountForm('Customer')}
 financeForm('Create sales invoice',`<p class="form-intro">Saving posts the sale to the customer ledger and deducts the listed products from stock.</p><div class="form-grid">${select('Customer','account_id',[['','Choose customer…'],...customers])}${field('Invoice date','date','date',today())}${field('Payment due','due','date',today())}</div><div class="section-label">ITEMS TO INVOICE <span>Prices exclude tax</span></div><div id="invoice-lines">${invoiceRow()}</div><button type="button" class="secondary" id="add-line">+ Add another item</button><div class="invoice-summary"><span>Invoice total</span><strong id="invoice-total">₹0.00</strong></div>${optionalField('Notes / delivery reference','notes')}<div class="info-note">This is a tax-exclusive sales document. GST computation and statutory tax invoice fields are not configured.</div>`, 'invoices',d=>({...d,items:[...document.querySelectorAll('.invoice-line')].map(row=>({product_id:row.querySelector('.line-product').value,quantity:row.querySelector('.line-qty').value,unit_price:row.querySelector('.line-price').value}))}));
 $('#modal').classList.add('wide');
 const update=()=>{let total=0;document.querySelectorAll('.invoice-line').forEach(row=>{const amount=Math.round(Number(row.querySelector('.line-price').value)*100)*Number(row.querySelector('.line-qty').value);row.querySelector('.line-total').textContent=rupees(amount);total+=amount});$('#invoice-total').textContent=rupees(total)};
 $('#invoice-lines').addEventListener('input',update);
 $('#invoice-lines').addEventListener('change',e=>{if(e.target.matches('.line-product')){e.target.closest('.invoice-line').querySelector('.line-price').value=product(+e.target.value)?.price||0;update()}});
 $('#invoice-lines').addEventListener('click',e=>{if(e.target.closest('.remove-line')){if(document.querySelectorAll('.invoice-line').length===1)return toast('Keep at least one invoice item');e.target.closest('.invoice-line').remove();update()}});
 $('#add-line').onclick=()=>$('#invoice-lines').insertAdjacentHTML('beforeend',invoiceRow());
}
function paymentForm(orderId=null,purchaseId=null){
 const order=state.orders.find(o=>o.id===Number(orderId)),purchase=state.purchases.find(p=>p.id===Number(purchaseId));
 const parties=accountOptions(['Customer','Supplier']),banks=accountOptions(['Cash','Bank']);
 if(!parties.length)return accountForm('Customer');
 financeForm('Record receipt or payment',`<p class="form-intro">Select who paid you or who you are paying. Choose the invoice or bill to settle.</p>${select('Customer / supplier','account_id',parties)}<div id="payment-documents"></div><div class="payment-balance" id="payment-balance"></div><div class="form-grid">${field('Amount (₹)','amount','number','')}${select('Cash / bank account','money_account_id',banks)}${field('Payment date','date','date',today())}${field('Reference / transaction number','reference')}</div><div class="info-note" id="payment-direction"></div>`, 'settlements',d=>{const doc=d.document||'';return {...d,order_id:doc.startsWith('sale:')?doc.slice(5):null,purchase_id:doc.startsWith('bill:')?doc.slice(5):null}});
 if(order||purchase)$('[name=account_id]').value=(order||purchase).account_id;
 function documents(){
  const a=acct($('[name=account_id]').value),customer=a.type==='Customer';
  let docs=(customer?state.orders:state.purchases).filter(x=>x.account_id===a.id&&x.outstanding_paise>0).map(x=>({id:(customer?'sale:':'bill:')+x.id,name:(customer?invoiceName(x):'BILL-'+String(x.id).padStart(4,'0'))+' · due '+rupees(x.outstanding_paise),amount:x.outstanding_paise}));
  const open=state.journals.find(j=>j.source==='opening:'+a.id),opening=state.journal_lines.filter(l=>l.journal_id===open?.id&&l.account_id===a.id).reduce((s,l)=>s+l.debit-l.credit,0)*(customer?1:-1)-state.settlements.filter(s=>s.account_id===a.id&&!s.order_id&&!s.purchase_id).reduce((s,x)=>s+x.amount,0);
  if(opening>0)docs.push({id:'opening',name:'Opening balance · '+rupees(opening),amount:opening});
  $('#payment-documents').innerHTML=select('Invoice / supplier bill','document',docs.length?docs.map(x=>[x.id,x.name]):[['','No outstanding balance']]);
  $('#payment-direction').textContent=customer?'Money received: increases your cash/bank balance and reduces what this customer owes.':'Money paid: reduces your cash/bank balance and reduces what you owe this supplier.';
  const desired=order?'sale:'+order.id:purchase?'bill:'+purchase.id:null;if(docs.some(x=>x.id===desired))$('[name=document]').value=desired;
  const update=()=>{const doc=docs.find(x=>x.id===$('[name=document]').value);$('#payment-balance').textContent='Available to settle: '+rupees(doc?.amount||0);$('[name=amount]').value=doc?(doc.amount/100).toFixed(2):'';$('[name=amount]').max=doc?doc.amount/100:0;$('[name=amount]').min='.01';$('[name=amount]').step='.01';$('#finance-form [type=submit]').disabled=!doc};
  $('[name=document]').onchange=update;update();
 }
 $('[name=account_id]').onchange=documents;documents();
}
function journalForm(expense=false){
 const nonparty=state.accounts.filter(a=>!['Customer','Supplier'].includes(a.type)).map(a=>[a.id,`${a.name} · ${a.type}`]);
 const expenses=accountOptions(['Expense']);
 financeForm(expense?'Record a business expense':'Post a journal voucher',`<p class="form-intro">${expense?'Choose the expense account and where you paid from.':'Use for bank transfers and general adjustments. Customer and supplier transactions are handled through invoices and payments.'}</p><div class="form-grid">${select(expense?'Expense account':'Debit account','debit_account_id',expense?expenses:nonparty)}${select(expense?'Paid from':'Credit account','credit_account_id',expense?accountOptions(['Cash','Bank']):nonparty)}${field('Amount (₹)','amount','number','')}${field('Date','date','date',today())}</div>${field('Voucher / transaction reference','reference')}${field('Description / purpose','description')}`, 'journals');
 if(!expense&&nonparty.length>1)$('[name=credit_account_id]').value=nonparty[1][0];
 $('[name=amount]').min='.01';$('[name=amount]').step='.01';
}
function viewInvoice(id){
 const o=state.orders.find(x=>x.id===Number(id));if(!o)return;
 const a=acct(o.account_id),items=state.invoice_items.filter(i=>i.order_id===o.id),payments=state.settlements.filter(s=>s.order_id===o.id);
 modal('Invoice details',`<div class="invoice-paper"><div class="invoice-paper-heading"><div><h2>${esc(state.settings.company)}</h2><p>SALES INVOICE · TAX EXCLUSIVE</p></div><div><strong>${invoiceName(o)}</strong><small>${badge(o.status)}</small></div></div><div class="invoice-parties"><div><small>BILL TO</small><h3>${esc(o.customer)}</h3><p>${esc(a?.address||'')}</p><p>${esc(a?.email||'')} ${esc(a?.phone||'')}</p></div><div><p>Invoice date <strong>${o.date}</strong></p><p>Payment due <strong>${o.due}</strong></p></div></div>${table(['DESCRIPTION','QUANTITY','UNIT PRICE','AMOUNT'],items.map(i=>[esc(i.description),i.quantity,rupees(i.unit_price),rupees(i.amount)]))}<div class="invoice-totals"><p>Total <strong>${rupees(o.total_paise)}</strong></p><p>Received <strong>${rupees(o.paid_paise)}</strong></p><p class="amount-due">Amount due <strong>${rupees(o.outstanding_paise)}</strong></p></div>${o.notes?`<p class="invoice-notes">${esc(o.notes)}</p>`:''}<p class="invoice-notes">Amounts exclude tax. This document is not a GST tax invoice.</p>${payments.length?`<h3>Payment history</h3>${table(['DATE','REFERENCE','ACCOUNT','AMOUNT'],payments.map(p=>[p.date,esc(p.reference),esc(acct(p.money_account_id)?.name),rupees(p.amount)]))}`:''}</div><div class="modal-actions">${o.outstanding_paise>0?`<button class="primary" data-receipt="${o.id}">Receive payment</button>`:''}<button class="secondary" data-finance="print-invoice">Print / Save PDF</button></div>`);
 $('#modal').classList.add('wide','invoice-view');
}
document.addEventListener('click',e=>{
 const el=e.target.closest('[data-finance],[data-ledger],[data-invoice],[data-receipt],[data-bill-payment],[data-sales-filter],[data-account-filter]');if(!el)return;
 if(el.dataset.ledger){selectedLedger=+el.dataset.ledger;ledgerFrom='';ledgerTo='';if(page==='ledgers')render();else location.hash='ledgers'}
 else if(el.dataset.invoice)viewInvoice(el.dataset.invoice);
 else if(el.dataset.receipt){$('#modal').close();paymentForm(el.dataset.receipt)}
 else if(el.dataset.billPayment)paymentForm(null,el.dataset.billPayment);
 else if(el.dataset.salesFilter){salesFilter=el.dataset.salesFilter;render()}
 else if(el.dataset.accountFilter){accountFilter=el.dataset.accountFilter;render()}
 else {const action=el.dataset.finance;if(action==='customer')accountForm('Customer');else if(action==='supplier')accountForm('Supplier');else if(action==='account')accountForm('Bank');else if(action==='payment')paymentForm();else if(action==='expense')journalForm(true);else if(action==='journal')journalForm();else if(action==='clear-dates'){ledgerFrom='';ledgerTo='';render()}else if(action==='print-invoice')window.print();else if(action==='ledger-export'){const {a,rows,opening,closing}=ledgerData();csv('ledger-'+a.id+'.csv',['Date','Reference','Description','Debit INR','Credit INR','Balance INR (debit positive)'],[[ledgerFrom,'','Opening balance','','',opening/100],...rows.map(r=>[r.date,r.reference,r.description,r.debit/100,r.credit/100,r.running/100]),[ledgerTo,'','Closing balance','','',closing/100]])}}
});
