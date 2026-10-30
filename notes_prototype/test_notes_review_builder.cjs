'use strict';
const assert=require('assert'),fs=require('fs'),path=require('path'),crypto=require('crypto');
const {build}=require('./build_notes_review.cjs');
function run(){
 const folder=fs.mkdtempSync(path.join(__dirname,'builder-test-'));
 const image=Buffer.from('synthetic-image-bytes');fs.writeFileSync(path.join(folder,'sample.png'),image);
 const template=path.join(folder,'template.html');fs.writeFileSync(template,'<script id="reference-data" type="application/json">__REFERENCE_DATA__</script>');
 const original={schema:'smartinis-notes-reference-set/1',pages:[{file:'sample.png',title:'Text </script><script>bad()</script>',page:{image_sha256:crypto.createHash('sha256').update(image).digest('hex')}}]};
 const reference=path.join(folder,'reference.json');fs.writeFileSync(reference,JSON.stringify(original));
 const output=path.join(folder,'review.html');
 const args={template,reference,images:folder,output};
 const result=build(args);assert.equal(result.pages,1);const html=fs.readFileSync(output,'utf8');assert(!html.includes('Text </script>'));assert(html.includes('data:image/png;base64,'));
 assert.throws(()=>build(args),/EEXIST/);
 const bad=structuredClone(original);bad.pages[0].page.image_sha256='0'.repeat(64);fs.writeFileSync(reference,JSON.stringify(bad));assert.throws(()=>build({...args,output:path.join(folder,'bad-hash.html')}),/hash does not match/);
 bad.pages[0].file='../sample.png';fs.writeFileSync(reference,JSON.stringify(bad));assert.throws(()=>build({...args,output:path.join(folder,'bad-path.html')}),/basename/);
 bad.schema='wrong';fs.writeFileSync(reference,JSON.stringify(bad));assert.throws(()=>build({...args,output:path.join(folder,'bad-schema.html')}),/Invalid reference set/);
 fs.writeFileSync(reference,JSON.stringify(original));fs.writeFileSync(template,'No placeholder');assert.throws(()=>build({...args,output:path.join(folder,'bad-template.html')}),/placeholder missing/);
 return{checks:6,result:'passed',fixtures:folder};
}
module.exports={run};
if(require.main===module)console.log(run());
