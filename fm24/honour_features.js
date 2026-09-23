/* World honours share the existing accepted ledger; review candidates never enter it. */
const HMath={
  clock(period){return /^\d{4}$/.test(period)?'year':/^\d{4}\/\d{2}$/.test(period)?'season':'other';},
  filter(person,{clock='all',period='all',award='all',kind='all'}={}){
    return (person?.awards||[]).filter(f=>(clock==='all'||this.clock(f.periodDisplay||f.season)===clock)&&
      (period==='all'||(f.periodDisplay||f.season)===period)&&(award==='all'||f.award===award)&&(kind==='all'||f.kind===kind));
  },
  counts(facts){const c={winner:0,selection:0,placing:0};for(const f of facts)if(f.kind in c)c[f.kind]++;return c;},
  timeline(facts){const groups=new Map();for(const f of facts){const p=f.periodDisplay||f.season||'期間未提供';if(!groups.has(p))groups.set(p,[]);groups.get(p).push(f);}
    return [...groups].sort(([a],[b])=>a.localeCompare(b)).map(([period,rows])=>({period,facts:rows,counts:this.counts(rows)}));},
  csv(rows){return '\uFEFF'+rows.map(r=>r.map(v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';}).join(',')).join('\r\n');},
  reviewRows(items,{priority='all',kind='all',query=''}={}){const q=query.trim().normalize('NFKC').toLowerCase();return items.filter(r=>(priority==='all'||r.priority===priority)&&(kind==='all'||r.kind===kind)&&(!q||JSON.stringify([r.title,r.id,r.periods,r.clubs,r.candidates,r.details]).normalize('NFKC').toLowerCase().includes(q)));},
  card(person,facts,filters,version){const counts=this.counts(facts),periods=[...new Set(facts.map(f=>f.periodDisplay||f.season))].sort();
    return {name:person.name,id:person.id,counts,total:facts.length,awardTypes:new Set(facts.map(f=>f.award)).size,
      first:periods[0]||'—',last:periods.at(-1)||'—',filters,version,
      facts:facts.map(f=>({key:f.key,award:f.award,period:f.periodDisplay||f.season,kind:f.kind,rank:f.rank,primary:f.primary,evidence:f.evidence}))};},
};
if(typeof X_ROUTES!=='undefined')Object.assign(X_ROUTES,{
  honourtime:['htPlayer','htClock','htPeriod','htAward','htKind','htOrder'],
  review:['reviewPriority','reviewKind','reviewQuery'],
});
const H_KIND={winner:'得獎',selection:'最佳陣容入選',placing:'其他名次'};
function hPeople(){return DATA.people.players.slice().sort((a,b)=>a.name.localeCompare(b.name,'zh-Hant'));}
function hPicker(label,key,fallback){const ps=hPeople();xPick(key,ps.map(p=>p.id),fallback||ps[0].id);
  const matches=el('div',{class:'h-search-results','aria-live':'polite'}),input=el('input',{type:'search','aria-label':label+'姓名搜尋',placeholder:'輸入姓名、別名或 ID…',onInput:e=>{
    const q=e.target.value.trim().normalize('NFKC').toLowerCase();const found=q?ps.filter(p=>(p.id+' '+p.name+' '+p.aliases.join(' ')).normalize('NFKC').toLowerCase().includes(q)):[];
    matches.replaceChildren(...found.slice(0,16).map(p=>el('button',{class:'btn ghost',onClick:()=>{state[key]=p.id;paint();}},p.name+' · '+p.id)));
    if(q)matches.append(el('p',{class:'cap'},found.length?`${found.length} 個身分${found.length>16?'，先列前 16 個，請縮小查詢':''}`:'查無受控身分'));
  }});
  return el('div',{class:'h-picker'},xSelect(label,key,ps.map(p=>[p.id,p.name+' · '+p.id])),el('details',{},el('summary',{},'按姓名／別名尋找'),input,matches));
}
function hFilters(prefix){const all=DATA.people.players.flatMap(p=>p.awards||[]);
  xPick(prefix+'Clock',['all','season','year','other'],'all');
  const periods=[...new Set(all.filter(f=>state[prefix+'Clock']==='all'||HMath.clock(f.periodDisplay||f.season)===state[prefix+'Clock']).map(f=>f.periodDisplay||f.season))].filter(Boolean).sort().reverse();
  const awards=[...new Set(all.map(f=>f.award))].sort();
  xPick(prefix+'Period',['all',...periods],'all');xPick(prefix+'Award',['all',...awards],'all');xPick(prefix+'Kind',['all',...Object.keys(H_KIND)],'all');
  return {filters:{clock:state[prefix+'Clock'],period:state[prefix+'Period'],award:state[prefix+'Award'],kind:state[prefix+'Kind']},
    ui:el('div',{class:'x-controls'},xSelect('時間口徑',prefix+'Clock',[['all','全部口徑（分列）'],['season','跨年球季'],['year','單一曆年'],['other','其他原始期間']]),
      xSelect('榮譽期間',prefix+'Period',[['all','全部已收錄期間'],...periods.map(p=>[p,p])]),
      xSelect('榮譽獎項',prefix+'Award',[['all','全部獎項'],...awards.map(a=>[a,a])]),
      xSelect('榮譽結果',prefix+'Kind',[['all','全部結果'],...Object.entries(H_KIND)]))};
}
function hScope(filters){return [({all:'全部時間口徑',season:'跨年球季',year:'單一曆年',other:'其他期間'})[filters.clock],filters.period==='all'?'全部期間':filters.period,filters.award==='all'?'全部獎項':filters.award,filters.kind==='all'?'全部結果':H_KIND[filters.kind]].join(' / ');}
function hOpenTimeline(id,filters){state.htPlayer=id;for(const [k,v] of Object.entries(filters||{clock:'all',period:'all',award:'all',kind:'all'}))state['ht'+k[0].toUpperCase()+k.slice(1)]=v;go('honourtime');}
function hCardJump(id,filters){state.studioKind='honour';state.studioItem=id;for(const [k,v] of Object.entries(filters||{clock:'all',period:'all',award:'all',kind:'all'}))state['card'+k[0].toUpperCase()+k.slice(1)]=v;go('studio');}
function hCompareJump(id,filters={clock:'all',period:'all',award:'all',kind:'all'}){state.duelA=id;state.compareTab='honours';for(const [k,v] of Object.entries(filters))state['hc'+k[0].toUpperCase()+k.slice(1)]=v;go('duel');}
function hFactsTable(facts){return evidenceTable(['期間','獎項','結果','俱樂部','來源'],facts.map(f=>[f.periodDisplay||f.season,f.award,f.kind==='placing'?`第 ${f.rank} 名`:H_KIND[f.kind],f.club,awardEvidence(f)]));}
function hCoverage(){return el('p',{class:'cap'},`資料涵蓋 ${DATA.people.players.length} 個受控球員身分。${DATA.people.awardCoverage.unassigned.length} 筆獎項來源尚未唯一綁定，未計入任何個人比較；0 表示此範圍未收錄，不保證生涯從未得獎。`);}
function hHonourPanels(a,b){
  const f=hFilters('hc');
  const af=HMath.filter(a,f.filters),bf=HMath.filter(b,f.filters),ac=HMath.counts(af),bc=HMath.counts(bf);
  const names=[...new Set([...af,...bf].map(x=>x.award))].sort();
  const count=(facts,name)=>{const c=HMath.counts(name===undefined?facts:facts.filter(x=>x.award===name));return `${c.winner} 得獎 / ${c.selection} 入選 / ${c.placing} 其他名次`;};
  const side=(p,fs,i)=>el('section',{class:'x-side'+(i?' b':'')},el('div',{class:'eyebrow'},p.id),el('h3',{},p.name),el('div',{class:'x-big'},String(fs.length)),el('p',{class:'cap'},'篩選內已收錄個人榮譽紀錄'),
    el('div',{class:'btnrow'},el('button',{class:'btn ghost',onClick:()=>hOpenTimeline(p.id,f.filters)},'得獎時間軸'),el('button',{class:'btn ghost',onClick:()=>hCardJump(p.id,f.filters)},'製作榮譽卡'),el('button',{class:'btn ghost',onClick:()=>xOpen('people','person',p.id)},'個人檔案')));
  const periods=[...new Set([...af,...bf].map(x=>x.periodDisplay||x.season))].sort();
  return [hCoverage(),f.ui,
    el('div',{class:'x-grid'},side(a,af,0),side(b,bf,1)),
    el('section',{class:'panel'},el('h3',{},'三種結果，分開對決'),el('p',{class:'cap'},`${a.name} 在左，${b.name} 在右。${hScope(f.filters)}。不加權排名，也不把其他名次算成得獎。`),
      Object.entries(H_KIND).map(([k,l])=>xBars(l,ac[k],bc[k])),names.length?evidenceTable(['獎項',a.name,b.name],names.map(n=>[n,count(af,n),count(bf,n)])):el('p',{class:'hint'},'這個篩選沒有已收錄紀錄。')),
    el('section',{class:'panel'},el('h3',{},'逐期榮譽交鋒'),el('p',{class:'cap'},'曆年與跨年球季是不同列；空白期間表示沒有已關聯紀錄，不推定未曾得獎。'),evidenceTable(['期間／口徑',a.name,b.name],periods.map(p=>[p+' · '+(HMath.clock(p)==='year'?'曆年':HMath.clock(p)==='season'?'球季':'原文'),count(af.filter(x=>(x.periodDisplay||x.season)===p)),count(bf.filter(x=>(x.periodDisplay||x.season)===p))]))),
    ...[[a,af],[b,bf]].map(([p,fs])=>el('details',{class:'panel'},el('summary',{},`${p.name} · ${fs.length} 筆明細及來源`),hFactsTable(fs)))];
}
function renderHonourTime(){const picker=hPicker('時間軸球員','htPlayer','P-0060'),p=DATA.people.players.find(p=>p.id===state.htPlayer),f=hFilters('ht',[p]),facts=HMath.filter(p,f.filters),counts=HMath.counts(facts);
  xPick('htOrder',['new','old'],'new');const periods=HMath.timeline(facts);if(state.htOrder==='new')periods.reverse();
  return [xHeader('HONOUR TIMELINE','球員榮譽時間軸','每個節點是一個來源期間，並非精確頒獎日。展開即可核對獎項、名次與原始證據。'),picker,f.ui,
    el('div',{class:'strip x-strip'},Object.entries(H_KIND).map(([k,l])=>xMetric(l,counts[k]))),hCoverage(),
    el('div',{class:'x-controls'},xSelect('時間軸排序','htOrder',[['new','新到舊'],['old','舊到新']]),el('button',{class:'btn',onClick:()=>hCardJump(p.id,f.filters)},'把目前範圍做成榮譽卡'),el('button',{class:'btn ghost',onClick:()=>hCompareJump(p.id,f.filters)},'帶入球員比較')),
    facts.length?el('div',{class:'h-timeline'},periods.map(g=>el('section',{class:'h-event'},el('div',{class:'h-period'},el('strong',{},g.period),el('span',{class:'pill flat'},HMath.clock(g.period)==='year'?'曆年':HMath.clock(g.period)==='season'?'球季':'原始期間')),
      el('div',{class:'h-event-body'},el('h3',{},`${g.counts.winner} 得獎 · ${g.counts.selection} 入選 · ${g.counts.placing} 其他名次`),el('div',{class:'chips'},g.facts.map(a=>el('span',{class:'chip'},a.award+' · '+(a.kind==='placing'?`第 ${a.rank} 名`:H_KIND[a.kind])))),el('details',{},el('summary',{},`${g.facts.length} 筆明細與來源`),hFactsTable(g.facts)))))):el('p',{class:'hint'},'這個範圍沒有已收錄且綁定的個人獎項。')];
}
function hCardSVG(card,style='midnight'){
  const colors={midnight:['#0c172c','#233761','#f7f3eb','#e7be78'],garnet:['#310f21','#751b39','#fff5ed','#eacb87'],paper:['#f4efe5','#e2d8c4','#182944','#976b2e']};
  const [bg,accent,fg,gold]=colors[style]||colors.midnight,esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
  const wrap=(value,max)=>{const lines=[];let line='',width=0;for(const c of String(value)){const n=/[\u0000-\u007f]/.test(c)?.58:1;if(width+n>max){lines.push(line);line='';width=0;}line+=c;width+=n;}if(line)lines.push(line);return lines;};
  const text=(x,y,size,value,color=fg,extra='')=>`<text x="${x}" y="${y}" font-size="${size}" fill="${color}" font-family="Arial, Microsoft JhengHei, sans-serif" ${extra}>${esc(value)}</text>`;
  let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="720" height="900" viewBox="0 0 720 900" role="img" aria-label="${esc(card.name)} 榮譽卡"><title>${esc(card.name)} 榮譽卡</title><desc>${esc(hScope(card.filters))}；僅計已收錄且綁定的紀錄；${card.total} 筆。</desc><metadata>${esc(JSON.stringify(card))}</metadata><defs><linearGradient id="honourBg" x2="1" y2="1"><stop stop-color="${bg}"/><stop offset="1" stop-color="${accent}"/></linearGradient></defs><rect width="720" height="900" fill="url(#honourBg)"/><rect x="34" y="34" width="652" height="832" fill="none" stroke="${gold}" opacity=".6"/><circle cx="620" cy="345" r="200" fill="none" stroke="${gold}" opacity=".13"/>`;
  svg+=text(62,85,12,'藍紅檔案館 / WORLD HONOURS',gold,'letter-spacing="2"');
  const nameLines=wrap(card.name,19);nameLines.slice(0,3).forEach((l,i)=>svg+=text(62,148+i*40,nameLines.length>2?28:34,l,fg,'font-weight="700"'));
  svg+=text(62,265,14,card.id+' · 已收錄個人榮譽',gold);
  svg+=text(62,401,108,card.counts.winner,fg,'font-weight="800"')+text(65,438,20,'得獎',gold);
  const stats=[['最佳陣容入選',card.counts.selection],['其他名次',card.counts.placing],['涉及獎項種類',card.awardTypes]];
  stats.forEach(([label,n],i)=>svg+=text(62+i*205,516,13,label,gold)+text(62+i*205,562,36,n,fg,'font-weight="700"'));
  svg+=`<path d="M62 592H658" stroke="${gold}" opacity=".5"/>`;
  wrap(hScope(card.filters),42).forEach((l,i)=>svg+=text(62,622+i*20,13,l));
  svg+=text(62,749,12,'多來源只計一次；曆年與球季不互換。',gold)+text(62,774,12,'僅計已收錄且綁定的紀錄；0 不代表生涯從未得獎。',gold);
  svg+=text(62,813,11,`MASTER v6.4.0 · ${card.version} · ${card.total} 筆來源紀錄`)+text(62,838,11,'來源明細內嵌於 SVG metadata；網站可展開逐筆核對。');
  return svg+'</svg>';
}
function hReviewNotes(){try{const notes=JSON.parse(localStorage.getItem('fm24-review-notes-v1')||'{}');return notes&&typeof notes==='object'&&!Array.isArray(notes)?notes:{};}catch(e){return {};}}
function hReviewExport(items){const notes=hReviewNotes();return {schema:'fm24-review-report-v1',mode:'REVIEW_ONLY_NOT_ADOPTED',master:'v6.4.0',generated:DATA.meta.generated,scope:{priority:state.reviewPriority,kind:state.reviewKind,query:state.reviewQuery||''},policy:DATA.honourReview.policy,items:items.map(r=>({...r,note:notes[r.id]||null}))};}
function hReviewItem(r){const notes=hReviewNotes(),saved=notes[r.id]||{},status=el('span',{class:'x-status','aria-live':'polite'});
  const stage=el('select',{'aria-label':r.title+'核對進度'},['未處理','核對中','已寫核對筆記'].map(s=>el('option',{value:s,selected:s===saved.stage},s)));
  const note=el('textarea',{'aria-label':r.title+'核對筆記',rows:3,placeholder:'記下缺少的截圖、來源位置與核對結論…'},saved.text||'');
  const save=()=>{try{const current=hReviewNotes();current[r.id]={stage:stage.value,text:note.value.slice(0,12000),fingerprint:r.fingerprint,updated:new Date().toISOString()};localStorage.setItem('fm24-review-notes-v1',JSON.stringify(current));status.textContent='已存於此瀏覽器；未修改主檔或榮譽統計。';}catch(e){status.textContent='無法儲存，請複製筆記自行保存。';}};
  return el('details',{class:'panel h-review-case'},el('summary',{},el('span',{class:'pill '+(r.priority==='P0'?'warn':'flat')},r.priority),` ${r.title} · ${r.count} 影響列／引用 · ${r.status}`),
    el('p',{},r.reason),r.countScope?el('p',{class:'cap'},r.countScope):null,el('p',{class:'cap'},r.recommendation),
    r.counts?el('p',{},`${r.counts.winner} 得獎列、${r.counts.selection} 入選列、${r.counts.placing} 其他名次列；仍未加進個人頁。`):null,
    r.periods?el('p',{class:'cap'},'期間：'+r.periods.join('、')):null,r.clubs?el('p',{class:'cap'},'來源俱樂部：'+(r.clubs.join('、')||'未提供')):null,
    r.groups?el('p',{},'矛盾分組：'+r.groups.join(' / ')):null,
    r.candidates?el('div',{},el('h3',{},'身分證據與候選'),!r.candidates.length?el('p',{},'現有資料沒有可列出的既有身分候選。'):r.candidates.map(c=>el('div',{class:'note'},
      el('button',{class:'btn ghost',onClick:()=>xOpen('people','person',c.id)},c.name+' · '+c.id),el('p',{},c.route),el('p',{class:'cap'},c.reasons.join('；')),
      c.evidence.length?evidenceTable(['受控原名','欄位','證據'],c.evidence.map(x=>[x.name,x.field,evidenceDetails([x.evidence])])):null)),
      r.proposal?el('p',{class:'hint'},'已有唯一正規化受控別名線索，可交主檔採用流程核對；不是已確認的新得獎，也沒有自動改 ID。'):null):null,
    r.members?evidenceTable(['Club_ID','名稱','引用列數','引用表'],r.members.map(m=>[m.id,m.name,m.rows,m.tables.map(t=>t.table+': '+t.n).join('；')])):null,
    r.details?evidenceTable(['來源列','現有姓名／期間','舊對照','舊對照證據'],r.details.map(d=>[d.row,d.name+' / '+d.period,d.old.map(o=>o.name+' / '+o.id+' / '+o.period).join('；'),evidenceDetails(d.old.map(o=>o.evidence))])):null,
    r.facts?hFactsTable(r.facts):evidenceDetails(r.evidence,'核對原始來源'),
    el('button',{class:'btn ghost',onClick:()=>{if(r.view==='reference'&&r.selection)xOpen('reference','referenceSheet',r.selection);else if(r.view==='tournaments'&&r.selection)xOpen('tournaments','tournament',r.selection);else go(r.view);}},'開啟相關來源頁'),
    el('div',{class:'h-note'},el('h3',{},'我的核對筆記'),el('p',{class:'cap'},'只存於此瀏覽器，不會自動更改來源、確認候選或減少待辦數。'),
      saved.fingerprint&&saved.fingerprint!==r.fingerprint?el('p',{class:'hint'},'來源內容已更新，舊筆記需要重新核對。'):null,stage,note,el('button',{class:'btn ghost',onClick:save},'儲存核對筆記'),status));
}
function hReviewPanel(){const rows=HMath.reviewRows(DATA.honourReview.items,{priority:state.reviewPriority,kind:state.reviewKind,query:state.reviewQuery||''}),shown=rows.slice(0,state.reviewLimit||30);
  return [el('p',{class:'cap'},`符合 ${rows.length} 項，已顯示 ${shown.length} 項。筆記進度不代表主檔已修正。`),
    el('div',{class:'btnrow'},el('button',{class:'btn ghost',onClick:()=>{xSaveBlob(new Blob([JSON.stringify(hReviewExport(rows),null,2)],{type:'application/json;charset=utf-8'}),'fm24-review-report.json');}},'匯出篩選結果與筆記 JSON'),
      el('button',{class:'btn ghost',onClick:()=>{const csv=HMath.csv([['優先','類別','項目','影響列或引用','狀態','原因','建議','證據位置'],...rows.map(r=>[r.priority,r.kind,r.title,r.count,r.status,r.reason,r.recommendation,r.evidence.map(e=>e.sheet+':'+e.row).join('; ')])]);xSaveBlob(new Blob([csv],{type:'text/csv;charset=utf-8'}),'fm24-review-priorities.csv');}},'匯出待核對清單 CSV')),
    ...shown.map(hReviewItem),!rows.length?el('p',{class:'hint'},'目前篩選沒有核對項目。'):null,
    shown.length<rows.length?el('button',{class:'btn',onClick:()=>{state.reviewLimit=(state.reviewLimit||30)+30;hRepaintReview();}},'載入更多核對項目'):null];
}
function hRepaintReview(){document.getElementById('hReviewPanel')?.replaceChildren(...hReviewPanel().filter(Boolean));writeRoute(true);}
function renderHonourReview(){const report=DATA.honourReview;xPick('reviewPriority',['all','P0','P1','P2'],'all');xPick('reviewKind',['all','player','club','tournament','mapping','source'],'all');
  return [xHeader('EVIDENCE DESK','優先核對工作台','先處理會改變歷史結論的來源矛盾，再核對漏掛得獎與影響多列的身分。每項都列影響範圍、證據及下一步。'),
    el('div',{class:'strip x-strip'},xMetric('P0 來源衝突',report.priorities.P0||0),xMetric('P1 優先核對',report.priorities.P1||0),xMetric('P2 其他缺口',report.priorities.P2||0),xMetric('唯一受控別名線索',report.aliasProposals)),
    el('p',{class:'cap'},report.policy),el('p',{class:'hint'},`${report.unresolvedFacts} 筆未綁定球員獎項，依原始姓名分成 ${report.rawNames} 個核對群；同名群不代表已證明同一人。修正提案與筆記均不自動採用。`),
    el('div',{class:'x-controls'},xSelect('核對優先級','reviewPriority',[['all','全部優先級'],['P0','P0 來源衝突'],['P1','P1 優先核對'],['P2','P2 其他缺口']]),
      xSelect('核對類別','reviewKind',[['all','全部類別'],['player','球員獎項'],['club','俱樂部身分'],['tournament','賽事分組'],['mapping','失效來源對照'],['source','其他來源缺口']]),
      el('input',{type:'search','aria-label':'搜尋核對項目',placeholder:'搜尋姓名、ID、期間、俱樂部…',value:state.reviewQuery||'',onInput:e=>{state.reviewQuery=e.target.value;state.reviewLimit=30;hRepaintReview();}})),
    el('div',{id:'hReviewPanel'},hReviewPanel())];
}
if(typeof module!=='undefined'&&module.exports)module.exports={HMath,hCardSVG,hScope};
