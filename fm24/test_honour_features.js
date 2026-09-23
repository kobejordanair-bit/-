const {test}=require('node:test'),assert=require('node:assert/strict');
const {HMath:H,hCardSVG}=require('./honour_features.js');
const filters={clock:'all',period:'all',award:'all',kind:'all'};
const person={id:'P1',name:'A & B <球員>',awards:[
  {key:'1',award:'Kopa',periodDisplay:'2034',kind:'winner',rank:'1',primary:{sheet:'Kopa',row:2},evidence:[]},
  {key:'2',award:'XI',periodDisplay:'2034/35',kind:'selection',rank:'SELECTION-2',primary:{sheet:'XI',row:3},evidence:[]},
  {key:'3',award:'Kopa',periodDisplay:'2034/35',kind:'placing',rank:'2',primary:{sheet:'Kopa',row:4},evidence:[]} ]};
test('world comparison never assigns a calendar award to a season',()=>{
  assert.equal(H.filter(person,{clock:'year'}).length,1);
  assert.equal(H.filter(person,{period:'2034/35'}).length,2);
  assert.equal(H.filter(person,{clock:'year',period:'2034/35'}).length,0);
});
test('award and outcome filters intersect without changing accepted facts',()=>{
  assert.deepEqual(H.filter(person,{award:'Kopa',kind:'winner'}).map(f=>f.key),['1']);
  assert.equal(H.filter(person,{award:'Missing'}).length,0);
  assert.equal(person.awards.length,3);
});
test('timeline counts reproduce filtered facts and keeps precision distinct',()=>{
  const g=H.timeline(person.awards);assert.deepEqual(g.map(x=>x.period),['2034','2034/35']);
  assert.deepEqual(g[0].counts,{winner:1,selection:0,placing:0});
  assert.deepEqual(g[1].counts,{winner:0,selection:1,placing:1});
});
test('empty player and missing scope stay empty rather than infer a trophy',()=>{
  assert.deepEqual(H.counts(H.filter({awards:[]})),{winner:0,selection:0,placing:0});
  assert.deepEqual(H.timeline([]),[]);
});
test('moving a comparison filter to a player without that award preserves the empty scope',()=>{
  const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
  const context=vm.createContext({state:{htClock:'season',htPeriod:'2034/35',htAward:'XI',htKind:'selection'},
    DATA:{people:{players:[person,{id:'EMPTY',name:'Empty',awards:[]}]}},el:()=>({})});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'experience.js'),'utf8')+'\n'+fs.readFileSync(path.join(__dirname,'honour_features.js'),'utf8'),context);
  const result=vm.runInContext("hFilters('ht', [DATA.people.players[1]]).filters",context);
  assert.equal(result.award,'XI');assert.equal(result.period,'2034/35');
  assert.equal(H.filter({awards:[]},result).length,0);
});
test('honour card carries exact filters counts and source row metadata',()=>{
  const f={...filters,period:'2034/35'},facts=H.filter(person,f),c=H.card(person,facts,f,'2035-06-06');
  assert.equal(c.total,2);assert.deepEqual(c.counts,{winner:0,selection:1,placing:1});
  assert.deepEqual(c.facts.map(x=>x.primary.row),[3,4]);assert.deepEqual(c.filters,f);
  const svg=hCardSVG(c,'paper');assert.ok(svg.includes('<metadata>'));assert.ok(svg.includes('A &amp; B &lt;球員&gt;'));
  assert.ok(!svg.includes('<球員>'));assert.ok(svg.includes('0 不代表生涯從未得獎'));assert.ok(svg.includes('width="720" height="900"'));
});
test('all card themes have a self-contained safe SVG including unknown themes',()=>{
  const c=H.card(person,[],filters,'test');for(const style of ['midnight','garnet','paper','bogus']){
    const svg=hCardSVG(c,style);assert.ok(svg.endsWith('</svg>'));assert.ok(!svg.includes('undefined'));assert.ok(!svg.includes('NaN'));
  }
});
test('review filtering searches candidate identity without accepting it',()=>{
  const items=[{title:'原名',id:'R1',priority:'P1',kind:'player',candidates:[{id:'P1',name:'候選'}]},{title:'俱樂部',id:'R2',priority:'P0',kind:'club'}];
  assert.equal(H.reviewRows(items,{query:'候選'}).length,1);assert.equal(H.reviewRows(items,{priority:'P0',kind:'player'}).length,0);
  assert.equal(H.reviewRows(items,{priority:'P0'})[0].id,'R2');
});
test('CSV keeps quotes and newlines while neutralising spreadsheet formula text',()=>{
  const csv=H.csv([['Name','Note'],['A,"B"','line\nline'],['=HYPERLINK("bad")','x']]);
  assert.ok(csv.startsWith('\uFEFF'));assert.ok(csv.includes('"A,""B"""'));assert.ok(csv.includes('"\'=HYPERLINK'));
});
