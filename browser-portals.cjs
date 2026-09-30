const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch();
 try{
  const base=process.env.ERP_TEST_URL;
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/admin');
  await page.locator('[name=name]').fill('Portal Admin');
  await page.locator('[name=username]').fill('portal-admin');
  await page.locator('[name=password]').fill('Portal-test-password-123');
  await page.locator('#login-form button').click();
  await page.locator('nav a[href="#users"]').waitFor();
  assert.equal(new URL(page.url()).pathname,'/admin');
  const created=await page.evaluate(async()=>{const r=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'portal-store',name:'Portal Store',role:'Store',password:'Portal-test-password-123'})});return r.status});assert.equal(created,200);
  await page.locator('[data-work=logout]').click();
  await page.goto(base+'/admin');
  await page.locator('[name=username]').fill('portal-store');
  await page.locator('[name=password]').fill('Portal-test-password-123');
  await page.locator('#login-form button').click();
  await page.getByText('Use the Admin panel for Admin accounts and the User portal for department accounts.',{exact:true}).waitFor();
  await page.goto(base+'/user');
  await page.locator('[name=username]').fill('portal-store');
  await page.locator('[name=password]').fill('Portal-test-password-123');
  await page.locator('#login-form button').click();
  await page.locator('nav a[href="#inventory"]').waitFor();
  assert.equal(await page.locator('nav a[href="#users"]').count(),0);
  await page.reload();await page.locator('nav a[href="#inventory"]').waitFor();
  const bad=await browser.newPage();
  await bad.route('**/api/auth/session',r=>r.fulfill({status:503,contentType:'application/json',body:'{"error":"unavailable"}'}));
  await bad.goto(base+'/admin');await bad.getByText('Workspace unavailable',{exact:true}).waitFor();
  assert(await bad.locator('#retry-connection').isVisible());assert(await bad.locator('aside').isHidden());
  await bad.unroute('**/api/auth/session');await bad.locator('#retry-connection').click();await bad.locator('#login-form').waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: admin/user deep links, role restrictions, session reload, database-error screen and retry.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
