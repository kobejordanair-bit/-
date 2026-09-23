const {test}=require('node:test');
const assert=require('node:assert/strict');
const {XMath:X}=require('./experience.js');

test('null, empty and invalid numerics never become zero',()=>{
  for(const v of [null,undefined,'',' ',NaN,Infinity,'NULL'])assert.equal(X.number(v),null);
  assert.equal(X.number('0'),0);
});
test('appearance rates require a known positive denominator',()=>{
  for(const [a,b] of [[null,10],[3,null],[3,0],[3,-1]])assert.equal(X.divide(a,b),null);
  assert.equal(X.divide(0,10),0);assert.equal(X.divide(3,10),.3);
});
test('season formats join without joining calendar years',()=>{
  assert.equal(X.season('2024-25'),'2024/25');assert.equal(X.season('2024/2025'),'2024/25');assert.equal(X.season('2024'),'2024');
});
test('career is its own scope; seasons are not accumulated',()=>{
  const p={apps:521,seasons:[{season:'2024-25',apps:52}]};assert.equal(X.record(p,'career').apps,521);assert.equal(X.record(p,'2024/25').apps,52);assert.equal(X.record(p,'2030/31'),null);
});
test('ambiguous multiple season observations are not picked arbitrarily',()=>{
  assert.equal(X.record({seasons:[{season:'2024-25'},{season:'2024/25'}]},'2024/25'),null);
});
test('rating is never divided by appearances',()=>{
  assert.equal(X.stat({apps:40,rating:7.3},'rating',true),7.3);assert.equal(X.stat({apps:40,goals:20},'goals',true),.5);assert.equal(X.stat(null,'goals'),null);
});
test('away scores are reversed for Barca summaries, unknowns preserved',()=>{
  assert.deepEqual(X.matchScore({score:'1-3',homeIsBarca:false}),{gf:3,ga:1});assert.equal(X.matchScore({score:'unknown',homeIsBarca:true}),null);
});
test('penalty draw does not become a guessed win and unknown ends streak',()=>{
  const r=X.matches([{score:'2-1',homeIsBarca:true,verdict:'W'},{score:'1-1',homeIsBarca:false,verdict:'D',decider:'pens'},{score:null,verdict:null},{score:'0-1',homeIsBarca:false,verdict:'W'}]);
  assert.deepEqual(r,{w:2,d:1,l:0,unknown:1,gf:4,ga:2,scored:3,streak:1,bestUnbeaten:2});
});
test('unconfirmed leaders are not champions',()=>{
  const world={champions:{'L|2024/25':{club:'A',final:false,confirmedElsewhere:false}}};assert.equal(X.champion(world,'L','2024/25'),null);world.champions['L|2024/25'].confirmedElsewhere=true;assert.equal(X.champion(world,'L','2024/25').club,'A');
});
test('poster text escapes XML markup from source data',()=>{
  assert.equal(X.xml('<script a="x">A&B\'</script>'),'&lt;script a=&quot;x&quot;&gt;A&amp;B&apos;&lt;/script&gt;');
});
test('undated matches cannot extend a chronological unbeaten streak',()=>{
  const r=X.matches([{date:'2034-01-01',verdict:'W'},{date:null,verdict:'W'}]);assert.equal(r.w,2);assert.equal(r.bestUnbeaten,1);
});
test('selecting a player already on the pitch swaps rather than duplicates',()=>{
  const before=['A','B',''];assert.deepEqual(X.place(before,0,'B'),['B','A','']);assert.deepEqual(before,['A','B','']);
});
test('clearing a position does not move its former player elsewhere',()=>{
  assert.deepEqual(X.place(['','A','B'],1,''),['','','B']);
});
test('shared lineup validates IDs, removes duplicates and has eleven slots',()=>{
  const r=X.lineup('A,A,FAKE,B',['A','B']);assert.equal(r.length,11);assert.deepEqual(r.slice(0,4),['A','','','B']);
});
