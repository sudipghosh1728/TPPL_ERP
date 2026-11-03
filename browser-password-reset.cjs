const {chromium}=require('playwright'),assert=require('node:assert/strict');
const PHOTO='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/aEAAAAASUVORK5CYII=';
(async()=>{const browser=await chromium.launch(),page=await browser.newPage(),other=await browser.newPage(),errors=[],password='Reset-browser-old-123',newPassword='Reset-browser-new-456';page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
const api=async(p,path,data)=>p.evaluate(async({path,data})=>{const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});return {status:r.status,data:await r.json()}},{path,data});
try{
 await page.goto(process.env.ERP_TEST_URL+'/admin');await page.locator('[name=name]').fill('Reset admin');await page.locator('[name=username]').fill('reset-admin');await page.locator('[name=password]').fill(password);await page.locator('#login-form button').click();await page.getByRole('heading',{name:'My employee profile'}).waitFor();
 await api(page,'hr/profile',{name:'Reset admin',phone:'9999999999',email:'test@example.invalid',blood_group:'O+',dob:'1990-01-01',plant_id:'solu',photo:PHOTO});await api(page,'users',{name:'Second admin',username:'second-admin',role:'Admin',password});
 await other.goto(process.env.ERP_TEST_URL+'/admin');assert.equal((await api(other,'auth/login',{username:'second-admin',password})).status,200);
 await page.reload();await page.locator('#nav a[href="#users"]').click();assert.equal(await page.getByRole('button',{name:'Reset password',exact:true}).count(),1);await page.getByRole('button',{name:'Reset password',exact:true}).click();
 await page.locator('[name=password]').fill(newPassword);await page.locator('[name=confirm_password]').fill('Different-password-123');await page.getByRole('button',{name:'Reset password & sign out user'}).click();await page.getByText('The new passwords do not match',{exact:true}).waitFor();
 await page.locator('[name=confirm_password]').fill(newPassword);await page.getByRole('button',{name:'Reset password & sign out user'}).click();await page.waitForFunction(()=>!document.querySelector('#modal').open);
 assert.equal(await other.evaluate(async()=>(await fetch('/api/state')).status),401);
 assert.equal((await api(other,'auth/login',{username:'second-admin',password})).status,401);
 assert.equal((await api(other,'auth/login',{username:'second-admin',password:newPassword})).status,200);
 assert.deepEqual(errors,[]);console.log('PASS: Admin resets another Admin through UI; mismatch rejected, old sessions revoked, new password signs in.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
