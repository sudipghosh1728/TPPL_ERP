const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch();const errors=[];const pages={};const url=process.env.ERP_TEST_URL;const password='Browser-department-test-123';
 try{
  const pageFor=async role=>{const context=await browser.newContext({viewport:{width:1440,height:1050}});const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));await p.goto(url);await p.locator('#login-form').waitFor();pages[role]=p;return p};
  const fill=(p,name,value)=>p.locator(`[name="${name}"]`).fill(value);
  const save=async p=>{await p.locator('dialog [type=submit]').click();await p.locator('dialog[open]').waitFor({state:'hidden'})};
  const nav=async(p,name)=>{await p.locator(`nav a[href="#${name}"]`).click();await p.locator('h1').waitFor()};
  const login=async role=>{const p=await pageFor(role);await fill(p,'username',role.toLowerCase());await fill(p,'password',password);await p.locator('#login-form button').click();await p.locator('nav a').first().waitFor();return p};
  const read=p=>p.evaluate(async()=>await (await fetch('/api/state')).json());
  const refresh=async p=>{await p.reload();await p.locator('nav a').first().waitFor()};
  const open=async(p,id)=>{const back=p.locator('[data-work=back]');if(await back.count())await back.click();await p.locator(`[data-work=open][data-id="${id}"]`).first().click();await p.locator('.job-route').waitFor()};
  const doc={name:'approved-document.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nTest manufacturing document')};
  const attachment=async(p,kind)=>{await p.locator('[data-work=attachment]').click();await p.locator('[name=kind]').selectOption(kind);await p.locator('[name=document_file]').setInputFiles(doc);await save(p)};
  const requirement=async(p,qty,tc)=>{await p.locator('[data-work=requirement]').filter({hasText:'Add requirement'}).click();await p.locator('[name=product_id]').selectOption('1');await fill(p,'quantity',String(qty));if(tc)await p.locator('[name=tc_required]').check();await fill(p,'notes','Plate for test base frame');await save(p)};
  const transition=async(p,action,machining)=>{await p.locator(`[data-action-name="${action}"]`).click();if(action==='design_approve')await p.locator('[name=machining_required]').selectOption(machining?'yes':'no');await fill(p,'notes','Reviewed and approved by department');await save(p)};
  const admin=await pageFor('Admin');await fill(admin,'name','Workflow Admin');await fill(admin,'username','admin');await fill(admin,'password',password);await admin.locator('#login-form button').click();await admin.locator('nav a').first().waitFor();
  await nav(admin,'users');
  for(const role of ['Design','Machining','Fabrication','Store','Accounts']){await admin.locator('[data-work=user]').filter({hasText:'Create user'}).click();await fill(admin,'name',role+' Team');await fill(admin,'username',role.toLowerCase());await fill(admin,'password',password);await admin.locator('[name=role]').selectOption(role);await save(admin)}
  await nav(admin,'jobs');
  for(const title of ['Machining job','Fabrication only job']){await admin.locator('[data-work=new-job]').click();await fill(admin,'title',title);await fill(admin,'customer','Test Customer');await fill(admin,'po_number',title==='Machining job'?'PO-100':'PO-200');await admin.locator('[name=document_file]').setInputFiles(doc);await save(admin)}
  let s=await read(admin);const m=s.work_jobs.find(j=>j.title==='Machining job').id,n=s.work_jobs.find(j=>j.title==='Fabrication only job').id;
  const design=await login('Design');await open(design,m);await attachment(design,'Drawing');await requirement(design,1,false);await transition(design,'design_approve',true);
  const machining=await login('Machining');assert.equal((await read(machining)).work_jobs.length,1);await open(machining,m);await requirement(machining,2,true);await transition(machining,'machining_submit');
  const fabrication=await login('Fabrication');await open(fabrication,m);await requirement(fabrication,3,false);await fabrication.screenshot({path:'test-results/fabrication-review.png',fullPage:true});await transition(fabrication,'fabrication_approve');
  const store=await login('Store');await store.screenshot({path:'test-results/store-requirements.png',fullPage:true});await open(store,m);await attachment(store,'TC');
  s=await read(store);const reqs=s.requirements.filter(r=>r.job_id===m),tc=s.job_documents.find(d=>d.job_id===m&&d.kind==='TC');
  for(const r of reqs){await store.locator(`[data-work=issue][data-req="${r.id}"]`).click();if(r.tc_required){await store.locator('[name=tc_document_id]').selectOption(String(tc.id));await fill(store,'tc_reference','HEAT-TEST-100')}await save(store)}
  await refresh(machining);await open(machining,m);await transition(machining,'machining_complete');
  await refresh(fabrication);await open(fabrication,m);await transition(fabrication,'fabrication_complete');
  await refresh(design);await open(design,n);await transition(design,'design_approve',false);
  await refresh(machining);assert.equal((await read(machining)).work_jobs.some(j=>j.id===n),false);
  await refresh(fabrication);await open(fabrication,n);await requirement(fabrication,1,false);await transition(fabrication,'fabrication_approve');
  await refresh(store);await nav(store,'requirements');await open(store,n);s=await read(store);const r=s.requirements.find(r=>r.job_id===n);await store.locator(`[data-work=issue][data-req="${r.id}"]`).click();await save(store);
  await refresh(fabrication);await open(fabrication,n);await transition(fabrication,'fabrication_complete');
  const accounts=await login('Accounts');assert.equal(await accounts.locator('nav a[href="#jobs"]').count(),0);assert.deepEqual((await read(accounts)).work_jobs,[]);
  s=await read(admin);assert.equal(s.work_jobs.filter(j=>j.stage==='Completed').length,2);
  await store.setViewportSize({width:390,height:844});await refresh(store);await nav(store,'requirements');assert.equal(await store.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await open(store,m);assert.equal(await store.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await store.screenshot({path:'test-results/workflow-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: six department logins, Admin user creation and PO uploads, Design approval, both job routes, TC upload, Store material issue, completions, Accounts isolation, and mobile layout.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
