const {test}=require('node:test');
const assert=require('node:assert/strict');
const {XMath:X}=require('./experience.js');

test('honours separate wins selections and placings and preserve year scope',()=>{
  const p={awards:[{kind:'winner',season:'2034'},{kind:'selection',season:'2034/35'},{kind:'placing',season:'2034/35'}]};
  assert.deepEqual(X.honours(p).counts,{winner:1,selection:1,placing:1});
  assert.deepEqual(X.honours(p,'2034-35').counts,{winner:0,selection:1,placing:1});
  assert.deepEqual(X.honours(p,'2034').counts,{winner:1,selection:0,placing:0});
});
test('team honours preserve unprovided trophy and ambiguous season as unknown',()=>{
  const p={titles:{'西甲':5,'世俱盃':0},seasonHonours:[{season:'2034/35',titles:{'西甲':1}}]};
  assert.equal(X.teamHonours(p)['西甲'],5);assert.equal(X.teamHonours(p)['世俱盃'],0);
  assert.equal(X.teamHonours(p,'2034/35')['世俱盃'],null);
  assert.equal(X.teamHonours(p,'2033/34')['西甲'],null);
  p.seasonHonours.push(p.seasonHonours[0]);assert.equal(X.teamHonours(p,'2034/35')['西甲'],null);
});
test('CSV preserves quoted commas escaped quotes and multiline cells',()=>{
  assert.deepEqual(X.parseTable('Name,Note,Apps\r\n"Doe, John","A ""quoted""\nline",5'),
    {headers:['Name','Note','Apps'],rows:[['Doe, John','A "quoted"\nline','5']]});
});
test('TSV preserves trailing blank fields and UTF8 BOM',()=>{
  assert.deepEqual(X.parseTable('\uFEFFName\tApps\tAssists\nA\t2\t\nB\t0\t0'),
    {headers:['Name','Apps','Assists'],rows:[['A','2',''],['B','0','0']]});
});
test('malformed table never silently drops columns or guesses quotes',()=>{
  for(const text of ['Name,Apps\nA,2,3','Name,Apps\n"A,2','Name,Apps\n"A"oops,2','Name,Name\nA,2','Name,\nA,2'])assert.ok(X.parseTable(text).error,text);
});

test('actual import resolver exposes a match only for a unique exact identity',()=>{
  const fs=require('node:fs'),vm=require('node:vm');
  const template=fs.readFileSync(require('node:path').join(__dirname,'template.html'),'utf8');
  const source=template.slice(template.indexOf('const normName ='),template.indexOf('/* --- parsers'));
  const context=vm.createContext({DATA:{people:{players:[
    {id:'P1',name:'拉明·亞馬爾',aliases:['共同別名']},
    {id:'P2',name:'佩德里',aliases:['共同別名']}]}}});
  vm.runInContext(source,context);
  const resolve=raw=>vm.runInContext(`resolveIdentity(${JSON.stringify(raw)})`,context);
  assert.equal(resolve('拉明·亞馬爾').match.id,'P1');
  assert.equal(resolve('拉明·亞馬').status,'fuzzy');
  assert.equal(resolve('拉明·亞馬').match,undefined);
  assert.equal(resolve('共同別名').status,'ambiguous');
  assert.equal(resolve('共同別名').match,undefined);
});

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
