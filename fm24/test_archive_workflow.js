const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const crypto=require('node:crypto');
const vm=require('node:vm');
const {WFlow}=require('./archive_workflow.js');
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const page=()=>fs.readFileSync(__dirname+'/archive.html','utf8');

test('current HTML parser ignores runtime template decoys',()=>{
  const p=WFlow.extract(page());
  assert.equal(p.format,'FM24_EXCHANGE_V1');
  assert.equal(hash(p.payloadJSON),p.payloadSha256);
  assert.equal(hash(Buffer.from(p.workbook,'base64')),p.workbookSha256);
  assert.equal(p.manifest.sheets.length,122);
});
test('browser HTML export can be reimported with exact Excel bytes',()=>{
  const html=page(), p=WFlow.extract(html);
  const runtime=JSON.parse(html.match(/id="fm24-runtime">([\s\S]*?)<\/script>/)[1]);
  const exported=WFlow.html(p,runtime), restored=WFlow.extract(exported);
  assert.equal(restored.workbook,p.workbook);
  assert.equal(restored.payloadSha256,p.payloadSha256);
  assert.equal(restored.payloadJSON,p.payloadJSON);
  const script=exported.match(/<script id="fm24-app">([\s\S]*?)<\/script>/)[1];
  assert.doesNotThrow(()=>new vm.Script(script));
  const published=WFlow.extract(WFlow.html(p,runtime,false));
  assert.equal(published.portable,false);
  assert.equal(restored.portable,true);
});
test('legacy HTML is only a snapshot and never executes trailing code',()=>{
  const p=WFlow.extract('<script>const DATA = {"escaped":"}\\\"{","nested":{"a":1}}; throw new Error("do not execute");</script>');
  assert.equal(p.format,'FM24_SNAPSHOT_V1');
  assert.equal(p.workbook,undefined);
  assert.equal(JSON.parse(p.payloadJSON).nested.a,1);
});
test('reject incomplete JSON, unrelated files and missing sections',()=>{
  assert.throws(()=>WFlow.extract('<script>const DATA = {"a":1;</script>'));
  assert.throws(()=>WFlow.extract('{"batches":[]}'));
  assert.throws(()=>WFlow.validatePayload({meta:{}}));
});
const sheet=(name,hashes,columns=['Player_ID','Goals'])=>({name,rowHashes:hashes,columns,rows:hashes.length,sha256:hash(JSON.stringify([hashes,columns]))});
test('row multiset diff preserves duplicates instead of using sets',()=>{
  const diff=WFlow.diff({sheets:[sheet('Stats',['a','a','b'])]},{sheets:[sheet('Stats',['a','b','c'])]});
  assert.equal(diff[0].added,1);assert.equal(diff[0].removed,1);
  assert.equal(diff[0].before,3);assert.equal(diff[0].after,3);
});
test('removed sheets and removed columns visible even if row totals unchanged',()=>{
  const d=WFlow.diff({sheets:[sheet('Old',['a']),sheet('Stats',['b'])]},{sheets:[sheet('New',['a']),sheet('Stats',['b'],['Player_ID'])]});
  assert.equal(d.length,3);
  assert.equal(d.find(r=>r.name==='Old').kind,'移除工作表');
  assert.deepEqual(d.find(r=>r.name==='Stats').removedColumns,['Goals']);
});
test('identical source has no changes; legacy source cannot invent a diff',()=>{
  const source={sheets:[sheet('Same',['a','b'])]};
  assert.deepEqual(WFlow.diff(source,source),[]);assert.equal(WFlow.diff(null,source),null);
});
test('personal backup merges new entries and preserves conflicting existing notes',()=>{
  const current={one:{text:'newer'},same:{text:'same'}};
  const incoming={one:{text:'older'},same:{text:'same'},two:{text:'extra'}};
  const r=WFlow.mergeMaps(current,incoming);
  assert.deepEqual(r.conflicts,['one']);assert.equal(r.added,1);assert.equal(r.same,1);
  assert.equal(r.merged.one.text,'newer');assert.equal(current.two,undefined);
});
test('personal backup rejects prototype keys',()=>{
  assert.throws(()=>WFlow.mergeMaps({},JSON.parse('{"__proto__":{"polluted":true}}')));
  assert.equal({}.polluted,undefined);
});
test('inline JSON cannot terminate script element',()=>{
  const raw=WFlow.safeJSON({name:'</script><script>alert(1)</script>'});
  assert.equal(raw.includes('<'),false);assert.equal(JSON.parse(raw).name,'</script><script>alert(1)</script>');
});
test('pending batch identity ignores column and row order but preserves repeated observations',()=>{
  const a={rawName:'A',values:{Goals:'1',Season:'2034/35'}};
  const b={rawName:'B',values:{Goals:null,Season:'2034/35'}};
  const reordered={rawName:'A',values:{Season:'2034/35',Goals:'1'}};
  assert.equal(WFlow.batchContent('season',[a,b]),WFlow.batchContent('season',[b,reordered]));
  assert.notEqual(WFlow.batchContent('season',[a,b]),WFlow.batchContent('season',[a,a,b]));
  assert.notEqual(WFlow.batchContent('season',[a,b]),WFlow.batchContent('profile',[a,b]));
});
