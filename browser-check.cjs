const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
 const browser = await chromium.launch({headless:true});
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8000/admin');
 await page.locator('#login-form').waitFor();
 if(!process.env.ERP_USER||!process.env.ERP_PASSWORD)throw Error('Set ERP_USER and ERP_PASSWORD for an existing Admin account; use test_browser.py for isolated tests.');
 await page.locator('[name=username]').fill(process.env.ERP_USER);
 await page.locator('[name=password]').fill(process.env.ERP_PASSWORD);
 await page.locator('#login-form button').click();
 await page.locator('#nav a').first().waitFor();
 for(const name of ['sales','accounts','ledgers','vouchers','inventory','purchases','jobs','requirements','users','reports','integrations','settings','dashboard']){
   await page.locator(`nav a[href="#${name}"]`).click();
   await page.locator('h1').waitFor();
   if(!await page.locator('h1').textContent())throw Error('Missing heading: '+name);
 }
 for(const [route,action] of [['sales','order'],['inventory','product'],['inventory','stock'],['purchases','purchase']]){
   await page.locator(`nav a[href="#${route}"]`).click();
   await page.locator(`[data-action="${action}"]`).click();
   await page.locator('dialog[open] form').waitFor();
   await page.getByRole('button',{name:'Close dialog'}).click();
 }
 await page.locator('nav a[href="#inventory"]').click();
 await page.locator('#search').fill('grinding');
 if(await page.locator('tbody').first().locator('tr').count()!==1)throw Error('Search filtering failed');
 await page.setViewportSize({width:390,height:844});
 await page.locator('nav a[href="#dashboard"]').click();
 await page.screenshot({path:'test-results/mobile.png',fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile viewport overflow');
 await browser.close();
 if(errors.length)throw Error(errors.join('\n'));
 console.log('PASS: all 13 Admin screens, 4 entry dialogs, material search, mobile layout; no browser errors.');
})().catch(e=>{console.error(e);process.exit(1)});
