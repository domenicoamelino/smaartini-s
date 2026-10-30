const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'}),page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[],remote=[];page.on('pageerror',e=>errors.push(e.message));
 const id='e'.repeat(32);
 const recap='# Planning recap\n\nA **clear overview** with *important context*.\n\n## Decisions\n\n- **Approved:** proceed with the plan.\n  - *Condition:* validate the backup first.\n- **Open:** confirm the owner.\n\n## Follow-ups\n\n1. Review the `migration-plan.md` document.\n2. Confirm the timeline.\n\n| Topic | Status |\n| --- | --- |\n| Migration | **Ready for review** |\n| Recovery | Tested |\n\n> Check the source before approving.\n\nEscaped legacy break.\\n* **Next:** confirm the date.\n\n```text\n**This code stays literal**\n\\n* not a list\n```\n\n[Unsafe link](javascript:alert(1))\n\n<img src="https://tracker.invalid/pixel" onerror="window.__xss=1">\n\n![External image](https://tracker.invalid/other)\n\n&lt;script&gt;window.__xss=2&lt;/script&gt;';
 const data={meeting:{id,title:'Planning and recovery',meeting_date:'2026-10-30',state:'completed',revision:3,status:'Ready for review',indexing_known:true},review:{id,revision:3,report:recap,transcript_reviewed:true,recap_ready:true,metadata:{meeting_title:'Planning and recovery',meeting_date:'2026-10-30',participants:[]},speaker_mapping:{},speakers:[],document_blocks:[],audio_url:'/audio',generation_attempts:[],recovered_draft:''},history:[]};
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());if(u.protocol==='data:')return route.continue();if(u.hostname!=='markdown.test'){remote.push(u.href);return route.abort();}
  const name=u.pathname.split('/').pop();if(u.pathname.includes('/api/'))return route.fulfill({json:name==='session'?{csrf:'fixture',user:{name:'Example reviewer'}}:data});
  if(name==='audio')return route.fulfill({status:404,body:''});const asset=['dashboard.js','dashboard.css'].includes(name)?name:'dashboard.html';return route.fulfill({body:fs.readFileSync(path.join(__dirname,'..',asset)),contentType:asset.endsWith('.js')?'text/javascript':asset.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://markdown.test/meeting-ui/dashboard/#'+id);await page.locator('#recap-preview h2').last().waitFor();
 assert.equal(await page.locator('#recap-preview h1').textContent(),'Planning recap');assert.equal(await page.locator('#recap-preview strong').count(),5);
 assert.equal(await page.locator('#recap-preview ul ul li').count(),1);assert.equal(await page.locator('#recap-preview ol li').count(),2);assert.equal(await page.locator('#recap-preview table tbody tr').count(),2);
 assert((await page.locator('#recap-preview pre code').textContent()).includes('**This code stays literal**'));
 assert.equal(await page.locator('#recap-preview img,#recap-preview script,#recap-preview iframe').count(),0);assert.equal(await page.locator('#recap-preview a[href^="javascript:"]').count(),0);
 assert.equal(await page.evaluate(()=>window.__xss),undefined);assert.deepEqual(remote,[]);assert.deepEqual(errors,[]);
 assert(await page.locator('.brand-logo').evaluate(img=>img.complete&&img.naturalWidth>0));
 const capture=process.env.DASHBOARD_TEST_OUTPUT||'dashboard-test-output';fs.mkdirSync(capture,{recursive:true});await page.screenshot({path:path.join(capture,'desktop.png'),fullPage:true});
 // Viewing and previewing Markdown must not rewrite the editor/source string.
 assert.equal(await page.locator('#recap').inputValue(),recap);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(capture,'mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 console.log('PASS: logo, headings, bold/italic, nested/ordered lists, tables, quotes, code, legacy breaks, source preservation, hostile markup/URLs, desktop/mobile layout.');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
