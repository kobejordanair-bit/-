/* One pair of world identities, separate statistical scopes. */
const CStat=typeof XMath!=='undefined'?XMath:require('./experience.js').XMath;
const C_FIELDS=['apps','goals','assists','motm','rating','cleanSheets','goalsConceded'];
const CMath={
  periods(rows){const known=[...new Set(rows.map(r=>CStat.season(r.season)))].filter(Boolean).sort(),standard=known.filter(s=>/^\d{4}\/\d{2}$/.test(s));
    if(standard.length){const first=Number(standard[0].slice(0,4)),last=Number(standard.at(-1).slice(0,4));if(last-first<150)for(let y=first;y<=last;y++)known.push(`${y}/${String(y+1).slice(-2)}`);}
    return [...new Set(known)].sort();},
  scopePeriods(pairRows,allRows,selected){const years=this.periods(pairRows);if(!years.includes(selected)&&this.periods(allRows).includes(selected))years.push(selected);return years.sort();},
  aggregate(rows){
    const periods=new Set(),facts=new Set();let conflict=false;
    for(const r of rows){const key=CStat.season(r.season)+'|'+(r.clubId||r.club||'');
      if(r.conflict||!r.season||(!r.clubId&&!r.club)||periods.has(key)||r.fact&&facts.has(r.fact))conflict=true;
      periods.add(key);if(r.fact)facts.add(r.fact);}
    const out={rows,rowCount:rows.length,conflict,fieldConflicts:[...new Set(rows.flatMap(r=>r.fieldConflicts||[]))]};
    for(const k of C_FIELDS){const values=rows.map(r=>CStat.number(r[k]));
      out[k]=!rows.length||conflict||out.fieldConflicts.includes(k)||values.some(v=>v===null)||k==='rating'&&rows.length!==1?null:values.reduce((n,v)=>n+v,0);}
    return out;
  },
  performance(data,id,basis,scope){
    if(basis==='league')return this.aggregate((data.comparison.players[id]?.league||[]).filter(r=>scope==='career'||CStat.season(r.season)===scope));
    const p=data.experience.players[id],rows=p?(scope==='career'?[{...p,season:'巴薩生涯主表',club:'巴塞隆納'}]:p.seasons.filter(r=>CStat.season(r.season)===scope).map(r=>({...r,club:'巴塞隆納'}))):[];
    const r=rows.length===1?rows[0]:null;return {...Object.fromEntries(C_FIELDS.map(k=>[k,CStat.number(r?.[k])])),rows,rowCount:rows.length,conflict:rows.length>1};
  },
  display(record,key,rate=false){
    const total=record.rows.length,isRate=rate&&['goals','assists','motm'].includes(key);
    const known=record.rows.filter(r=>CStat.number(r[key])!==null&&(!isRate||CStat.number(r.apps)!==null));
    if(record.conflict||record.fieldConflicts?.includes(key))return {value:null,note:'此欄來源衝突，待核對'};
    if(!known.length)return {value:null,note:total?'這些紀錄未提供此欄':'未收錄'};
    if(key==='rating')return {value:record.rating,note:record.rating===null?'多段評分無可靠合併分母；可查看下方原檔總計快照':'來源評分'};
    const sum=known.reduce((n,r)=>n+CStat.number(r[key]),0),partial=known.length<total;
    return {value:isRate?CStat.divide(sum,known.reduce((n,r)=>n+CStat.number(r.apps),0)):sum,
      note:(partial?'已知範圍':'已收錄範圍')+(isRate?'場均':'')+` · ${known.length}/${total} 段`+(isRate?`；分母 ${known.reduce((n,r)=>n+CStat.number(r.apps),0)} 場`:partial?'（小計）':'（合計）'),partial};
  },
  latest(rows){if(!rows.length)return null;const date=rows.map(r=>r.date||'').sort().at(-1),latest=rows.filter(r=>(r.date||'')===date);return latest.length===1?latest[0]:null;},
  snapshot(rows,id='latest'){return id==='latest'?this.latest(rows):rows.find(r=>r.id===id)||null;},
  migrate(view,params){const p=new URLSearchParams(params);
    if(view==='honourlab'){view='duel';p.set('compareTab','honours');for(const [a,b] of [['hA','duelA'],['hB','duelB']]){if(p.has(a))p.set(b,p.get(a));p.delete(a);}}
    if(view==='duel'&&!p.has('compareBasis')&&p.has('duelScope'))p.set('compareBasis','barca');
    if(view==='duel'&&p.has('duelHonourScope')&&!p.has('hcPeriod'))p.set('hcPeriod',p.get('duelHonourScope')==='all'?'all':CStat.season(p.get('duelHonourScope')));
    return {view,params:p};
  },
};
if(typeof X_ROUTES!=='undefined')X_ROUTES.duel=['duelA','duelB','compareTab','compareBasis','duelScope','duelRate','hcClock','hcPeriod','hcAward','hcKind','compareSnapA','compareSnapB'];
const C_TABS=[['overview','比較總覽'],['performance','表現與生涯'],['honours','個人榮譽'],['attributes','屬性快照'],['team','巴薩團隊榮譽']];
function cSetTab(tab){state.compareTab=tab;paint();}
function cPair(){const ps=DATA.people.players;xPick('duelA',ps.map(p=>p.id),'P-0060');xPick('duelB',ps.map(p=>p.id),'P-0037');return [ps.find(p=>p.id===state.duelA),ps.find(p=>p.id===state.duelB)];}
function cControls(a,b,team=false){xPick('compareBasis',['league','barca'],'league');xPick('duelRate',['totals','appearance'],'totals');
  const rows=p=>team?DATA.players.find(x=>x.id===p.id)?.seasonHonours||[]:state.compareBasis==='league'?DATA.comparison.players[p.id].league:DATA.experience.players[p.id]?.seasons||[];
  const years=CMath.periods([...rows(a),...rows(b)]);
  const allRows=[...Object.values(DATA.comparison.players).flatMap(p=>p.league),...Object.values(DATA.experience.players).flatMap(p=>p.seasons),...DATA.players.flatMap(p=>p.seasonHonours||[])];
  const choices=CMath.scopePeriods([...rows(a),...rows(b)],allRows,state.duelScope);
  xPick('duelScope',['career',...choices],'career');
  if(team)return {years,ui:xSelect('團隊榮譽期間','duelScope',[['career','效力巴薩期間累計'],...choices.map(y=>[y,y])])};
  return {years,ui:el('div',{class:'x-controls'},xSelect('統計口徑','compareBasis',[['league','聯賽紀錄 · 世界球員'],['barca','巴薩紀錄 · 各項賽事']]),
    xSelect('表現期間','duelScope',[['career',state.compareBasis==='league'?'已收錄聯賽累計':'巴薩生涯主表'],...choices.map(y=>[y,y])]),
    state.compareTab==='performance'?xSelect('表現顯示方式','duelRate',[['totals','原始總量'],['appearance','每次出場效率']]):null)};
}
function cScope(){return (state.compareBasis==='league'?'聯賽紀錄':'巴薩各項賽事')+' / '+(state.duelScope==='career'?(state.compareBasis==='league'?'已收錄累計':'生涯主表'):state.duelScope);}
function cScopeNote(){return el('p',{class:'cap'},state.compareBasis==='league'?
  '聯賽生涯表與分賽事表交叉核對，同季同俱樂部採較新快照，相容重複觀測僅計一次。不含盃賽與國家隊；累計只代表已收錄範圍，可能含季中資料。缺值不補零，多段評分不取簡單平均。':
  '巴薩生涯總計直接使用主表，逐季只採 ADOPTED 觀測；不同球季不重算生涯總計。非巴薩球員在此口徑顯示未收錄。');}
function cSources(record,name){return el('details',{},el('summary',{},`${name} · ${record.rows.length} 段統計依據`),
  evidenceTable(['期間','俱樂部','快照日期','出場','進球','助攻','最佳球員','評分','零封','失球','來源'],record.rows.map(r=>[r.season,r.club,r.date||'來源未明示',fmt(r.apps),fmt(r.goals),fmt(r.assists),fmt(r.motm),fmt(r.rating,2),fmt(r.cleanSheets),fmt(r.goalsConceded),
    r.observations?el('details',{},el('summary',{},r.resolution),evidenceTable(['來源快照','出場','進球','助攻','評分','處理','來源'],r.observations.map(o=>[o.date||o.context||'日期未明示',fmt(o.apps),fmt(o.goals),fmt(o.assists),fmt(o.rating,2),r.fieldConflicts?.length?'有欄位待核對':r.references.some(ref=>ref.sheet===o.source.sheet&&ref.row===o.source.row)?'採用／佐證':'舊快照，不加總',xSource(o.source)]))):xSource(r.source)])));}
function cCareerSnapshots(a,b){return el('section',{class:'panel'},el('h3',{},'原檔聯賽生涯總計快照'),
  el('p',{class:'cap'},'主檔另有直接記錄的生涯總計，按當時日期呈現。它可能早於上方逐季紀錄，也可能包含逐季未填的欄位；不拿舊總計冒充目前值，不與逐季數據相加。'),
  el('div',{class:'x-grid'},[a,b].map(p=>{const r=CMath.latest(DATA.comparison.players[p.id].leagueSummaries||[]);return el('div',{},el('h3',{},p.name),r?
    el('div',{},el('p',{},'截至 '+r.date),evidenceTable(['出場','進球','助攻','最佳球員','來源評分'],[[fmt(r.apps),fmt(r.goals),fmt(r.assists),fmt(r.motm),fmt(r.rating,2)]]),xSource(r.source)):
    el('p',{},'未收錄唯一可採用的生涯總計快照'));})));}
function cPairCards(a,b){return el('div',{class:'x-grid'},[a,b].map((p,i)=>{
  const d=DATA.comparison.players[p.id],profile=CMath.latest(d.profiles),r=CMath.performance(DATA,p.id,state.compareBasis,state.duelScope),hc=HMath.counts(p.awards),periods=d.league.map(r=>CStat.season(r.season)).sort();
  return el('section',{class:'x-side'+(i?' b':'')},el('div',{class:'eyebrow'},(i?'PLAYER B / ':'PLAYER A / ')+p.id),el('h3',{},p.name),
    el('p',{class:'x-muted'},profile?([profile.nationality,profile.position,profile.club].filter(Boolean).join(' · ')||'此 Profile 未提供國籍、位置與俱樂部'):'未收錄唯一可採用的 Profile 快照'),
    profile?el('p',{class:'cap'},'Profile 日期：'+(profile.date||'未提供')):null,
    el('div',{class:'x-big'},r.apps===null?'—':fmt(r.apps)+' 場'),el('p',{class:'cap'},cScope()),
    r.apps===null?el('p',{class:'cap'},!r.rowCount?'這個範圍未收錄表現。':r.conflict?'來源重複或範圍歧義，未加總。':`${r.rows.filter(x=>CStat.number(x.apps)===null).length} 段未提供出場，合計保留未知；可在表現分頁查證。`):null,
    el('p',{},`${hc.winner} 得獎 · ${hc.selection} 入選 · ${hc.placing} 其他名次`),el('p',{class:'cap'},'以上榮譽是全期間已收錄個人紀錄；獎項篩選請切換「個人榮譽」。'),
    el('div',{class:'chips'},el('span',{class:'chip'},`${d.league.length} 段聯賽紀錄`),el('span',{class:'chip'},`${d.snapshots.length} 份屬性快照`),el('span',{class:'chip'},DATA.experience.players[p.id]?'巴薩主表在檔':'無巴薩主表')),
    periods.length?el('p',{class:'cap'},`聯賽資料涵蓋 ${periods[0]} 至 ${periods.at(-1)}，中間可能缺季。`):el('p',{class:'cap'},'尚無正式採用的聯賽數據，數字保留未知。'),
    el('div',{class:'btnrow'},el('button',{class:'btn ghost',onClick:()=>xOpen('people','person',p.id)},'完整球員檔案'),el('button',{class:'btn ghost',onClick:()=>hOpenTimeline(p.id)},'榮譽時間軸'),el('button',{class:'btn ghost',onClick:()=>hCardJump(p.id)},'製作榮譽卡'),
      DATA.experience.players[p.id]?el('button',{class:'btn ghost',onClick:()=>{state.studioKind='player';state.studioItem=p.id;go('studio');}},'巴薩生涯卡'):null),
    profile?xSource(profile.source,'Profile 來源'):null); }));}
function cPerformance(a,b,years){const ar=CMath.performance(DATA,a.id,state.compareBasis,state.duelScope),br=CMath.performance(DATA,b.id,state.compareBasis,state.duelScope),rate=state.duelRate==='appearance';
  return [el('section',{class:'panel'},el('h3',{},'表現數據對照'),cScopeNote(),el('p',{class:'cap'},`${a.name} 在左，${b.name} 在右。${cScope()}。每場效率包含替補，不是每 90 分鐘。`),
    [ar,br].some(r=>r.conflict)?el('p',{class:'hint'},'範圍內出現重複或歧義紀錄，該側停止加總；原始列仍可展開查證。'):null,
    [ar,br].some(r=>!r.rowCount)?el('p',{class:'hint'},'有球員在此範圍未收錄資料；「—」是未知，不是 0。'):null,
    el('p',{class:'hint'},'有缺欄時顯示已知範圍的小計，不是完整生涯總數。每項數字下方列出涵蓋段數；兩人的資料涵蓋可能不同。'),
    state.compareBasis==='league'?el('div',{class:'x-grid cap'},...[a,b].map((p,i)=>{const dates=[...new Set((i?br:ar).rows.map(r=>r.date).filter(Boolean))].sort();return el('p',{},p.name+' 來源快照：'+(dates.length?dates[0]+(dates.length>1?' ～ '+dates.at(-1):''):'日期未明示')+'；僅代表在檔觀測，不宣稱每季皆為季末定版。');})):null,
    [['出場','apps'],['進球','goals'],['助攻','assists'],['最佳球員','motm'],['平均評分','rating'],['零封','cleanSheets'],['失球','goalsConceded']].map(([l,k])=>{const av=CMath.display(ar,k,rate),bv=CMath.display(br,k,rate);return el('div',{},xBars(l+(rate&&['goals','assists','motm'].includes(k)?'／出場':''),av.value,bv.value,k==='rating'||rate&&['goals','assists','motm'].includes(k)?2:0),el('div',{class:'x-grid cap'},el('span',{},a.name+'：'+av.note),el('span',{},b.name+'：'+bv.note)));}),
    el('details',{},el('summary',{},'為什麼有些數字是「—」？查看欄位完整度與已知小計'),el('p',{class:'cap'},'任一段缺值，完整總計保持未知。已知小計只加有值的紀錄，不代表完整生涯；不拿局部小計除以全生涯出場。評分僅在一段紀錄時顯示；多段不直接平均。'),
      evidenceTable(['欄位',a.name+' 已填／在檔段數',a.name+' 已知小計',b.name+' 已填／在檔段數',b.name+' 已知小計'],[['出場','apps'],['進球','goals'],['助攻','assists'],['最佳球員','motm'],['評分','rating'],['零封','cleanSheets'],['失球','goalsConceded']].map(([l,k])=>[l,...[ar,br].flatMap(r=>{const vals=r.rows.map(x=>CStat.number(x[k])).filter(v=>v!==null);return [r.rows.length?`${vals.length} / ${r.rows.length}`:'未收錄',r.conflict||r.fieldConflicts?.includes(k)||!vals.length||k==='rating'?'—':fmt(vals.reduce((s,v)=>s+v,0))];})]))),
    el('div',{class:'x-grid'},cSources(ar,a.name),cSources(br,b.name))),
    state.compareBasis==='league'&&state.duelScope==='career'?cCareerSnapshots(a,b):null,
    el('section',{class:'panel'},el('h3',{},rate?'逐季場均進球軌跡':'逐季進球軌跡'),xChart(years,[a,b].map(p=>({name:p.name,values:years.map(y=>CStat.stat(CMath.performance(DATA,p.id,state.compareBasis,y),'goals',rate))})),{label:'兩名球員同口徑逐季進球'}),
      el('p',{class:'cap'},'圖表展示目前統計口徑的全部已收錄球季；缺值中斷折線。上方期間只篩選數據對照區。'),
      el('details',{},el('summary',{},'查看逐季原始數值'),evidenceTable(['球季',a.name,b.name],years.map(y=>[y,...[a,b].map(p=>fmt(CStat.stat(CMath.performance(DATA,p.id,state.compareBasis,y),'goals',rate),rate?2:0))]))))];
}
function cSnapshotPicker(p,key){const rows=DATA.comparison.players[p.id].snapshots;xPick(key,['latest',...rows.map(r=>r.id)],'latest');
  return xSelect(p.name+'屬性日期',key,[['latest','最新唯一快照'],...rows.map(r=>[r.id,(r.date||'日期未提供')+' · '+(r.schema==='OUTFIELD'?'外場':'門將')+' · '+r.id])]);}
function cAttributes(a,b){const controls=el('div',{class:'x-controls'},cSnapshotPicker(a,'compareSnapA'),cSnapshotPicker(b,'compareSnapB')),
  aa=CMath.snapshot(DATA.comparison.players[a.id].snapshots,state.compareSnapA),bb=CMath.snapshot(DATA.comparison.players[b.id].snapshots,state.compareSnapB),same=aa&&bb&&aa.schema===bb.schema;
  const groups=[...new Set([...Object.keys(aa?.groups||{}),...Object.keys(bb?.groups||{})])];
  return [controls,el('section',{class:'panel'},el('h3',{},'屬性快照對照'),el('p',{class:'cap'},'預設使用主檔最新且唯一的屬性快照。同日多份時請明選來源，不自動挑一份。手動選擇舊日期只代表當時狀態；不推算 CA／PA。'),
    el('div',{class:'x-grid'},[[a,aa],[b,bb]].map(([p,s])=>el('div',{},el('h3',{},p.name),el('p',{},s?(s.date||'日期未提供')+' · '+(s.schema==='OUTFIELD'?'外場':'門將'):'沒有最新唯一屬性快照，可檢查日期選單'),s?xSource(s.evidence):null))),
    same?xRadar({...a,attrs:aa},{...b,attrs:bb}):el('p',{class:'hint'},'快照缺漏或門將／外場類型不同，保留各自欄位，不繪共同雷達或計算差值。'),
    ...groups.map(g=>{const left=new Map(aa?.groups[g]||[]),right=new Map(bb?.groups[g]||[]),keys=[...new Set([...left.keys(),...right.keys()])];
      return el('div',{},el('h3',{},g),evidenceTable(['屬性',a.name,b.name,'A − B'],keys.map(k=>[k,fmt(left.get(k)),fmt(right.get(k)),same&&left.has(k)&&right.has(k)?fmt(left.get(k)-right.get(k)):'—'])));}))];
}
function cTeam(a,b){const pa=DATA.players.find(p=>p.id===a.id),pb=DATA.players.find(p=>p.id===b.id),ta=CStat.teamHonours(pa,state.duelScope),tb=CStat.teamHonours(pb,state.duelScope);
  const source=p=>!p?null:state.duelScope==='career'?DATA.experience.players[p.id]?.source:p.seasonHonours.find(r=>CStat.season(r.season)===state.duelScope)?.evidence;
  return el('section',{class:'panel'},el('h3',{},'效力巴薩期間的團隊冠軍'),el('p',{class:'cap'},(state.duelScope==='career'?'巴薩生涯主表':state.duelScope+' 逐季 A1 表')+'。在隊期間團隊成就與個人獎項分開，不宣稱個人正式冠軍資格；沒有巴薩主表的球員保留未知。此區不採用聯賽累計口徑或每場效率。'),
    Object.keys(ta).map(k=>xBars(k,ta[k],tb[k])),el('div',{class:'x-grid'},xSource(source(pa),a.name+'團隊歸屬來源'),xSource(source(pb),b.name+'團隊歸屬來源')));
}
function renderCompare(){const [a,b]=cPair();xPick('compareTab',C_TABS.map(t=>t[0]),'overview');const tab=state.compareTab,controls=cControls(a,b,tab==='team');
  return [xHeader('WORLD PLAYER COMPARISON','球員比較','從全世界名錄選兩人，將生涯表現、個人榮譽與屬性放在同一個比較台。每項數字保留自己的統計範圍與來源。'),
    el('div',{class:'x-grid'},hPicker('球員 A','duelA','P-0060'),hPicker('球員 B','duelB','P-0037')),
    el('div',{class:'btnrow'},el('button',{class:'btn ghost',onClick:()=>{[state.duelA,state.duelB]=[state.duelB,state.duelA];[state.compareSnapA,state.compareSnapB]=[state.compareSnapB,state.compareSnapA];paint();}},'交換球員 ⇄')),
    a.id===b.id?el('p',{class:'hint'},'目前選到同一身分，兩側相同。'):null,
    el('div',{class:'chips',role:'group','aria-label':'球員比較分頁'},C_TABS.map(([id,label])=>el('button',{class:'chip','aria-pressed':String(id===tab),onClick:()=>cSetTab(id)},label))),
    ['overview','performance','team'].includes(tab)?controls.ui:null,
    ...(tab==='overview'?[el('p',{class:'cap'},`${DATA.people.players.length} 個受控身分；${DATA.comparison.leaguePlayers} 人有正式採用聯賽紀錄，${DATA.comparison.snapshotPlayers} 人有屬性快照。兩側資料涵蓋可能不同，不把未收錄當成零。`),cPairCards(a,b),cScopeNote(),
      el('section',{class:'panel'},el('h3',{},'把對決展開'),el('p',{},'「表現與生涯」看數據與逐季軌跡；「個人榮譽」看得獎、入選及來源；「屬性快照」可指定日期；團隊榮譽保留巴薩歸屬口徑。'))]:
    tab==='performance'?cPerformance(a,b,controls.years):tab==='honours'?hHonourPanels(a,b):tab==='attributes'?cAttributes(a,b):[cTeam(a,b)])];
}
if(typeof module!=='undefined'&&module.exports)module.exports={CMath};
