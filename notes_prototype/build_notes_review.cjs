/* Build a private offline review from an external reference set and original images.
   No private reference text or images belong in the source repository. */
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
function build({template,reference,images,output}){
 const data=JSON.parse(fs.readFileSync(reference,'utf8'));
 if(data.schema!=='smartinis-notes-reference-set/1'||!Array.isArray(data.pages)||!data.pages.length||data.pages.length>20)throw Error('Invalid reference set');
 const root=fs.realpathSync(images);
 for(const p of data.pages){
  if(typeof p.file!=='string'||path.basename(p.file)!==p.file||!/^.+\.(png|jpe?g)$/i.test(p.file))throw Error('Use a PNG/JPEG basename, not a path');
  const filename=fs.realpathSync(path.join(root,p.file));
  if(path.dirname(filename)!==root)throw Error('Image must be directly inside the supplied source directory');
  if(fs.statSync(filename).size>12*1024*1024)throw Error('Reference image exceeds 12 MiB');
  const raw=fs.readFileSync(filename),sha=crypto.createHash('sha256').update(raw).digest('hex');
  if(sha!==p.page.image_sha256)throw Error('Original image hash does not match: '+p.file);
  p.image_data='data:image/'+(/\.png$/i.test(p.file)?'png':'jpeg')+';base64,'+raw.toString('base64');
 }
 const markup=fs.readFileSync(template,'utf8');
 if(!markup.includes('__REFERENCE_DATA__'))throw Error('Review template placeholder missing');
 const html=markup.replace('__REFERENCE_DATA__',JSON.stringify(data).replaceAll('<','\\u003c'));
 fs.writeFileSync(output,html,{flag:'wx'});
 return {pages:data.pages.length,bytes:Buffer.byteLength(html)};
}
module.exports={build};
if(require.main===module){
 const [reference,images,output]=process.argv.slice(2);
 if(!reference||!images||!output){console.error('Usage: node build_notes_review.cjs reference.json image-directory output.html');process.exitCode=2;}
 else build({template:path.join(__dirname,'notes_review_template.html'),reference,images,output});
}
