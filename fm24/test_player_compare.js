const {test}=require('node:test'),assert=require('node:assert/strict');
const {CMath:C}=require('./player_compare.js');
const row=(extra={})=>({season:'2034/35',clubId:'C1',fact:'F1',apps:10,goals:2,assists:0,motm:1,rating:7.1,cleanSheets:null,goalsConceded:null,...extra});
test('league cumulative rows retain missing fields and do not average ratings',()=>{
 const r=C.aggregate([row(),row({season:'2033/34',fact:'F2',apps:20,goals:3,assists:null})]);
 assert.equal(r.apps,30);assert.equal(r.goals,5);assert.equal(r.assists,null);assert.equal(r.rating,null);assert.equal(r.cleanSheets,null);
});
test('same-season transfers can sum but duplicate club periods block totals',()=>{
 assert.equal(C.aggregate([row(),row({clubId:'C2',fact:'F2'})]).apps,20);
 const r=C.aggregate([row(),row({fact:'F2'})]);assert.equal(r.conflict,true);assert.equal(r.apps,null);
});
test('a repeated fact under another period is not counted twice',()=>{
 assert.equal(C.aggregate([row(),row({season:'2033/34'})]).conflict,true);
});
test('absent periods and clubs cannot form reliable cumulative statistics',()=>{
 assert.equal(C.aggregate([row({season:null})]).apps,null);assert.equal(C.aggregate([row({clubId:null})]).apps,null);
});
test('empty data is unknown and an explicit zero remains zero',()=>{
 assert.equal(C.aggregate([]).goals,null);assert.equal(C.aggregate([row({goals:0})]).goals,0);
});
test('incomplete careers display known totals with coverage instead of hiding all goals',()=>{
 const r=C.aggregate([row(),row({season:'2033/34',fact:'F2',apps:20,goals:null,assists:null})]);
 assert.equal(r.goals,null);
 assert.deepEqual(C.display(r,'goals'),{value:2,note:'已知範圍 · 1/2 段（小計）',partial:true});
 assert.equal(C.display(r,'assists').value,0);
 assert.equal(C.display(r,'rating').value,null);
});
test('partial per-appearance rates use matching numerator and denominator records',()=>{
 const r=C.aggregate([row(),row({season:'2033/34',fact:'F2',apps:20,goals:null})]);
 assert.equal(C.display(r,'goals',true).value,.2);
 assert.equal(C.display(r,'goals',true).partial,true);
 assert.equal(C.display(C.aggregate([row({apps:0})]),'goals',true).value,null);
});
test('cross-table unresolved conflicts and empty columns cannot become known subtotals',()=>{
 assert.equal(C.display(C.aggregate([row({conflict:true})]),'goals').value,null);
 assert.equal(C.display(C.aggregate([row({goals:null})]),'goals').value,null);
 assert.equal(C.display(C.aggregate([]),'apps').value,null);
});
test('a source disagreement blocks only the disputed metric',()=>{
 const r=C.aggregate([row({fieldConflicts:['rating'],rating:null})]);
 assert.equal(C.display(r,'goals').value,2);
 assert.equal(C.display(r,'rating').value,null);
 assert.match(C.display(r,'rating').note,/衝突/);
});
test('global and Barcelona statistics remain separate even for same ID',()=>{
 const data={comparison:{players:{P1:{league:[row()]}}},experience:{players:{P1:{apps:900,goals:200,seasons:[]}}}};
 assert.equal(C.performance(data,'P1','league','career').apps,10);assert.equal(C.performance(data,'P1','barca','career').apps,900);
 assert.equal(C.performance(data,'P2','barca','career').apps,null);assert.equal(C.performance(data,'P1','league','2033/34').apps,null);
});
test('unprovided Barcelona season and ambiguous seasons stay unknown',()=>{
 const data={experience:{players:{P1:{seasons:[row(),row()]}}}};
 assert.equal(C.performance(data,'P1','barca','2034/35').conflict,true);
 assert.equal(C.performance(data,'P1','barca','2033/34').goals,null);
});
test('timeline includes years where both players lack a season to break the line',()=>{
 assert.deepEqual(C.periods([{season:'2031/32'},{season:'2033-34'}]),['2031/32','2032/33','2033/34']);
});
test('changing to players without the selected season preserves the known empty scope',()=>{
 assert.deepEqual(C.scopePeriods([],[row()],'2034/35'),['2034/35']);
 assert.deepEqual(C.scopePeriods([],[row()],'invalid'),[]);
});
test('latest snapshot is date-based; conflicting same-day observations need selection',()=>{
 const rows=[{id:'old',date:'2030-01-01'},{id:'new',date:'2035-01-01'}];
 assert.equal(C.snapshot(rows).id,'new');rows.push({id:'other',date:'2035-01-01'});assert.equal(C.snapshot(rows),null);
 assert.equal(C.snapshot(rows,'old').id,'old');assert.equal(C.snapshot([], 'latest'),null);
});
test('legacy world honour links preserve both people and exact award scope',()=>{
 const r=C.migrate('honourlab','hA=P-0036&hB=P-0060&hcPeriod=2034&hcClock=year&hcKind=winner');
 assert.equal(r.view,'duel');assert.equal(r.params.get('duelA'),'P-0036');assert.equal(r.params.get('duelB'),'P-0060');
 assert.equal(r.params.get('compareTab'),'honours');assert.equal(r.params.get('hcPeriod'),'2034');assert.equal(r.params.get('hcKind'),'winner');
 assert.equal(r.params.has('hA'),false);
});
test('legacy Barca links stay Barca and explicit current scopes are not overwritten',()=>{
 const r=C.migrate('duel','duelScope=2034/35&duelHonourScope=2034');assert.equal(r.params.get('compareBasis'),'barca');assert.equal(r.params.get('hcPeriod'),'2034');
 assert.equal(C.migrate('duel','compareBasis=league&duelScope=career').params.get('compareBasis'),'league');
});
test('all five comparison panels return flat render nodes, including empty world identities',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
 const player=id=>({id,name:id,aliases:[],awards:[]});
 const blank=()=>({league:[],profiles:[],snapshots:[]});
 const context=vm.createContext({URLSearchParams,state:{view:'duel'},DATA:{people:{players:[player('P-0060'),player('P-0037')],awardCoverage:{unassigned:[]}},
  players:[],comparison:{players:{'P-0060':blank(),'P-0037':blank()},leaguePlayers:0,snapshotPlayers:0},experience:{players:{}}},
  el:(type,attrs,...children)=>({type,attrs,children}),evidenceTable:()=>({type:'table'}),evidenceDetails:()=>({type:'details'}),fmt:v=>v==null?'—':String(v)});
 for(const f of ['experience.js','honour_features.js','player_compare.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,f),'utf8'),context);
 for(const tab of ['overview','performance','honours','attributes','team']){
  context.state.compareTab=tab;const nodes=vm.runInContext('renderCompare()',context);
  assert.ok(nodes.length>5);assert.ok(nodes.every(n=>n==null||!Array.isArray(n)&&typeof n==='object'),tab);
 }
});
