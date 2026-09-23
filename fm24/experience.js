/* Pure calculations are shared by the UI and the Node regression tests. */
const XMath = {
  number(v) { return v === null || v === undefined || String(v).trim() === '' || !Number.isFinite(Number(v)) ? null : Number(v); },
  divide(a,b) { a=this.number(a); b=this.number(b); return a===null || b===null || b<=0 ? null : a/b; },
  season(v) { const m=String(v||'').match(/(\d{4})[/-](\d{2}|\d{4})$/); return m ? `${m[1]}/${m[2].slice(-2)}` : String(v||''); },
  record(player,scope) {
    if (!player) return null;
    if (scope==='career') return player;
    const rows=player.seasons.filter(r=>this.season(r.season)===this.season(scope));
    return rows.length===1 ? rows[0] : null;
  },
  stat(record,key,rate=false) { if (!record) return null; return rate && ['goals','assists','motm'].includes(key) ? this.divide(record[key],record.apps) : this.number(record[key]); },
  honours(person,scope='all') {
    const facts=(person?.awards||[]).filter(f=>scope==='all'||this.season(f.periodDisplay||f.season)===this.season(scope));
    const counts={winner:0,selection:0,placing:0};facts.forEach(f=>{if(f.kind in counts)counts[f.kind]++;});
    return {facts,counts};
  },
  teamHonours(player,scope='career') {
    const labels=['西甲','歐冠','國王盃','西超盃','歐超盃','世俱盃'];
    const matches=(player?.seasonHonours||[]).filter(r=>this.season(r.season)===this.season(scope));
    const titles=scope==='career'?player?.titles:matches.length===1?matches[0].titles:null;
    return Object.fromEntries(labels.map(k=>[k,this.number(titles?.[k])]));
  },
  parseTable(text) {
    text=text.replace(/^\uFEFF/,'').replace(/^(?:\r?\n)+/,'');
    const first=text.split(/\r?\n/)[0], sep=first.includes('\t')?'\t':first.includes(',')?',':null;
    if(!sep){const lines=text.split(/\r?\n/).filter(l=>l.trim());if(lines.length<2||! /\S\s{2,}\S/.test(lines[0]))return null;
      const rows=lines.map(l=>l.trim().split(/\s{2,}/));return rows.slice(1).some(r=>r.length!==rows[0].length)?{error:'資料列與標題欄數不同，請使用 Tab 或標準 CSV。'}:{headers:rows[0],rows:rows.slice(1)};}
    const records=[];let row=[],cell='',quoted=false,closed=false;
    for(let i=0;i<text.length;i++){const c=text[i];
      if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=c;continue;}
      if(c==='"'){if(cell.trim()||closed)return {error:'引號位置不正確，請檢查 CSV 格式。'};cell='';quoted=true;continue;}
      if(c===sep||c==='\n'||c==='\r'){row.push(cell.trim());cell='';closed=false;if(c!==sep){if(row.some(v=>v!==''))records.push(row);row=[];if(c==='\r'&&text[i+1]==='\n')i++;}continue;}
      if(closed&&!/\s/.test(c))return {error:'結束引號後須為分隔符或換行。'};cell+=c;
    }
    if(quoted)return {error:'引號尚未閉合，未匯入任何資料。'};
    row.push(cell.trim());if(row.some(v=>v!==''))records.push(row);
    if(records.length<2)return null;
    const headers=records.shift();
    if(new Set(headers).size!==headers.length||headers.some(h=>!h))return {error:'欄名重複或空白，請修正後再解析。'};
    if(records.some(r=>r.length!==headers.length))return {error:'資料列與標題欄數不同，請檢查分隔符；不會捨棄多出的欄位。'};
    return {headers,rows:records};
  },
  matchScore(m) { const p=String(m.score||'').match(/^(\d+)\s*[-:：]\s*(\d+)$/); return p ? {gf:Number(p[m.homeIsBarca?1:2]),ga:Number(p[m.homeIsBarca?2:1])} : null; },
  matches(rows) {
    const out={w:0,d:0,l:0,unknown:0,gf:0,ga:0,scored:0,streak:0,bestUnbeaten:0};
    for(const m of rows){ if(['W','D','L'].includes(m.verdict))out[m.verdict.toLowerCase()]++;else out.unknown++;
      const s=this.matchScore(m);if(s){out.gf+=s.gf;out.ga+=s.ga;out.scored++;}
      out.streak=m.date!==null&&['W','D'].includes(m.verdict)?out.streak+1:0;out.bestUnbeaten=Math.max(out.bestUnbeaten,out.streak);
    } return out;
  },
  champion(world,league,season) { const c=world.champions[`${league}|${season}`]; return c && (c.final||c.confirmedElsewhere) ? c : null; },
  xml(v) { return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c])); },
  place(lineup,index,id) { const next=[...lineup],other=next.indexOf(id);if(id&&other>=0&&other!==index)next[other]=next[index]||'';next[index]=id;return next; },
  lineup(raw,ids) { const used=new Set();return Array.from({length:11},(_,i)=>{const id=String(raw||'').split(',')[i]||'';if(!ids.includes(id)||used.has(id))return '';used.add(id);return id;}); },
};

const X_ROUTES={hub:[],lab:['labA','labB','labMetric'],duel:['duelA','duelB','duelScope','duelRate','duelHonourScope'],
  atlas:['atlasSeason'],derby:['derbyComp','derbyVenue','derbyIndex'],studio:['studioKind','studioItem','studioStyle','cardClock','cardPeriod','cardAward','cardKind'],
  eleven:['xiFormation','xiRoster']};
function xPick(key,items,fallback){if(!items.includes(state[key]))state[key]=fallback??items[0];return state[key];}
function xSelect(label,key,options){return el('label',{class:'x-control'},el('span',{},label),el('select',{'aria-label':label,onChange:e=>{state[key]=e.target.value;if(key==='studioKind')state.studioItem=null;if(key==='derbyComp'||key==='derbyVenue')state.derbyIndex=0;paint();}},options.map(([v,l])=>el('option',{value:v,selected:String(state[key])===String(v)},l))));}
function xHeader(kicker,title,description){return el('div',{class:'x-topline'},el('div',{class:'view-head'},el('div',{class:'eyebrow'},kicker),el('h2',{},title),el('p',{},description)),el('div',{class:'btnrow'},el('button',{class:'btn ghost',onClick:()=>go('hub')},'互動中心'),el('button',{class:'btn ghost',onClick:xShare},'複製此比較連結')),el('span',{class:'x-status','aria-live':'polite',id:'xShareStatus'}));}
async function xShare(){const status=document.getElementById('xShareStatus');try{await navigator.clipboard.writeText(location.href);if(status)status.textContent='連結已複製，選擇條件會一起帶過去。';}catch(e){if(status){status.replaceChildren(el('span',{},'複製下方網址：'),el('input',{'aria-label':'可複製分享網址',value:location.href,readonly:true,style:'width:100%'}));}}}
function xOpen(view,key,value){go(view);if(key){state[key]=value;paint();}}
function xMetric(label,value,unit=''){return el('div',{},el('div',{class:'n tnum'},fmt(value,Number.isInteger(value)?0:2)),el('div',{class:'l'},label+(unit?' · '+unit:'')));}
function xSource(ref,label='統計來源'){return ref?evidenceDetails([ref],label):null;}
function xBars(label,a,b,digits=0){const max=Math.max(a??0,b??0,1);return el('div',{class:'x-compare-row'},...[
  el('div',{class:'x-meter'},el('strong',{},fmt(a,digits)),el('div',{class:'x-meter-track'},el('i',{style:`width:${a===null?0:Math.max(0,a)/max*100}%` }))),
  el('div',{class:'x-compare-label'},label),
  el('div',{class:'x-meter b'},el('strong',{},fmt(b,digits)),el('div',{class:'x-meter-track'},el('i',{style:`width:${b===null?0:Math.max(0,b)/max*100}%` }))) ]);}
function xChart(labels,series,{label='趨勢比較',height=245,zero=true}={}){
  const width=800,pad={l:48,r:22,t:24,b:40},values=series.flatMap(s=>s.values).filter(v=>v!==null&&Number.isFinite(v));
  if(!values.length)return el('p',{class:'x-muted'},'這個範圍沒有可繪製的數值。');
  let min=zero?Math.min(0,...values):Math.min(...values)-.1,max=Math.max(...values);if(max<=min)max=min+1;else max+=(max-min)*.08;
  const x=i=>pad.l+i*(width-pad.l-pad.r)/Math.max(labels.length-1,1),y=v=>height-pad.b-(v-min)/(max-min)*(height-pad.t-pad.b);
  const chart=svg('svg',{viewBox:`0 0 ${width} ${height}`,class:'x-chart',role:'img','aria-label':label},svg('title',{},label));
  for(let i=0;i<5;i++){const val=min+(max-min)*i/4;chart.append(svg('line',{x1:pad.l,x2:width-pad.r,y1:y(val),y2:y(val),class:'x-gridline'}),svg('text',{x:pad.l-10,y:y(val)+4,'text-anchor':'end','font-size':10},fmt(val,max<10?1:0)));}
  labels.forEach((l,i)=>{if(labels.length<15||i%Math.ceil(labels.length/12)===0||i===labels.length-1)chart.append(svg('text',{x:x(i),y:height-12,'text-anchor':'middle','font-size':9},String(l)));});
  series.forEach((s,si)=>{const color=si?'var(--azul)':'var(--garnet)';let segment=[];
    const flush=()=>{if(segment.length)chart.append(svg('polyline',{points:segment.join(' '),fill:'none',stroke:color,'stroke-width':3,'stroke-linejoin':'round'}));segment=[];};
    s.values.forEach((v,i)=>{if(v===null||!Number.isFinite(v)){flush();return;}segment.push(`${x(i)},${y(v)}`);});flush();
    s.values.forEach((v,i)=>{if(v!==null&&Number.isFinite(v))chart.append(svg('circle',{cx:x(i),cy:y(v),r:4,fill:color},svg('title',{},`${s.name} · ${labels[i]}：${fmt(v,max<10?2:0)}`)));});});
  return el('div',{},chart,el('div',{class:'x-legend'},series.map((s,i)=>el('span',{},el('i',{class:'x-dot'+(i?' b':'')}),s.name))));
}

function renderHub(){
  const ss=DATA.seasons,metrics=DATA.experience.seasons,latest=ss[ss.length-1],best=ss.reduce((a,b)=>metrics[a.id].points>=metrics[b.id].points?a:b);
  const trophies=ss.reduce((n,s)=>n+(metrics[s.id].trophies??0),0);
  const tiles=[['eleven','06 / DREAM ELEVEN','王朝夢幻 XI','跨年代排出你的十一人、自由換位，保存並分享陣容圖。'],['lab','01 / SEASON LAB','王朝實驗室','兩季並排、勝率與積分效率、十二季趨勢。'],['duel','02 / HEAD TO HEAD','球員對決','生涯與同季比較，出場效率、實際屬性與來源日期。'],['atlas','03 / WORLD ATLAS','足壇時光機','滑動年份，打開五大聯賽冠軍版圖與爭冠差距。'],['derby','04 / EL CLÁSICO','國家德比劇場','逐場走過宿敵交鋒，切換賽事與主客場紀錄。'],['studio','05 / POSTER STUDIO','戰績製卡室','把球季、球員或德比變成可下載的專屬海報。']];
  tiles.unshift(['honourlab','WORLD HONOURS','世界榮譽對決',`${DATA.people.players.length} 個受控身分，比得獎、入選與逐期榮譽。`],['honourtime','HONOUR TIMELINE','榮譽時間軸','走過每個得獎年份，把目前範圍做成分享卡。'],['review','EVIDENCE DESK','優先核對工作台','按影響排序資料缺口、查看證據、記錄核對筆記。']);
  return [el('section',{class:'x-hero x-enter'},el('div',{class:'eyebrow'},'THE MANAGER’S ROOM / INTERACTIVE ARCHIVE'),el('h2',{},`${ss.length} 季，`,el('br'), '把王朝拿出來玩。'),el('p',{},'不只翻紀錄。把球季拉到同一張圖，把兩名球員放上擂台，再把你最得意的那一刻做成海報。'),el('div',{class:'btnrow'},el('button',{class:'btn',onClick:()=>go('lab')},'進入王朝實驗室 →'),el('button',{class:'btn ghost',onClick:()=>go('studio')},'製作我的戰績卡')),el('small',{},`${ss[0].season} — ${latest.season} · WORLD MASTER v6.4.0 · 資料留在本機`)),
    el('div',{class:'strip x-strip'},xMetric('主表團隊冠軍',trophies),xMetric('巴薩生涯檔案',DATA.players.length),xMetric('國家德比紀錄',DATA.clasico.length),xMetric('最高聯賽積分',metrics[best.id].points)),
    el('div',{class:'x-grid'},tiles.map(([view,kicker,title,text])=>el('button',{class:'x-tile',onClick:()=>go(view)},el('span',{class:'eyebrow'},kicker),el('span',{class:'x-icon'},view==='lab'?'↗':view==='duel'?'VS':view==='atlas'?'◎':view==='derby'?String(DATA.clasico.length):'▧'),el('h3',{},title),el('p',{},text))),el('section',{class:'x-side',style:'grid-column:1/-1'},el('div',{class:'eyebrow'},'THE SEASON TO BEAT'),el('h3',{},best.season),el('div',{class:'x-big'},`${metrics[best.id].points} 分`),el('p',{class:'x-muted'},`主檔十二季中聯賽積分最高；同分時顯示較早球季。${best.titles.join('、')||'未列冠軍'}`),el('button',{class:'btn ghost',onClick:()=>{state.labA=best.id;go('lab');}},'用這季接受挑戰'))),
    el('section',{class:'panel'},el('h3',{},'王朝心跳'),el('p',{class:'cap'},'聯賽積分 · Barcelona_Season_Master'),xChart(ss.map(s=>s.season),[{name:'巴塞隆納',values:ss.map(s=>metrics[s.id].points)}],{label:'巴塞隆納十二季聯賽積分'}))];
}

function renderLab(){
  const seasons=DATA.seasons,ids=seasons.map(s=>s.id),ms=DATA.experience.seasons;
  xPick('labA',ids,ids[ids.length-1]);xPick('labB',ids,ids[ids.length-2]);xPick('labMetric',['points','trophies','gf','ga'],'points');
  const a=seasons.find(s=>s.id===state.labA),b=seasons.find(s=>s.id===state.labB),am=ms[a.id],bm=ms[b.id];
  const stats=[['聯賽積分','points',0],['勝場','w',0],['和局','d',0],['敗場','l',0],['聯賽進球','gf',0],['聯賽失球','ga',0],['團隊冠軍','trophies',0]];
  const metricNames={points:'聯賽積分',trophies:'團隊冠軍',gf:'聯賽進球',ga:'聯賽失球'};
  const side=(s,m,i)=>el('section',{class:'x-side'+(i?' b':'')},el('div',{class:'eyebrow'},i?'CHALLENGER B':'SEASON A'),el('h3',{},s.season),el('div',{class:'x-big'},`${fmt(m.points)} 分`),el('p',{class:'x-muted'},`${fmt(m.w)} 勝 / ${fmt(m.d)} 和 / ${fmt(m.l)} 負 · 西甲第 ${s.position} 名`),el('div',{class:'x-tags'},s.titles.map(t=>el('span',{class:'x-tag gold'},t))),el('button',{class:'btn ghost',onClick:()=>xOpen('seasons','season',s.id)},'開啟完整賽季與來源'),xSource(m.source));
  return [xHeader('01 / SEASON LAB','王朝實驗室','同一份賽季主表，同一套統計範圍。比較累計戰果，也比較每場效率。'),
    el('div',{class:'x-controls'},xSelect('球季 A','labA',seasons.map(s=>[s.id,s.season])),xSelect('球季 B','labB',seasons.map(s=>[s.id,s.season])),el('button',{class:'btn ghost',onClick:()=>{[state.labA,state.labB]=[state.labB,state.labA];paint();}},'交換 ⇄')),
    el('div',{class:'x-grid x-enter'},side(a,am,0),side(b,bm,1)),
    el('section',{class:'panel'},el('h3',{},'數字正面交鋒'),el('p',{class:'cap'},'長條只表示數量。失球與敗場較少通常較好；不把不同指標混成不透明的總分。'),stats.map(([l,k,d])=>xBars(l,am[k],bm[k],d)),xBars('聯賽每場積分',XMath.divide(am.points,am.played),XMath.divide(bm.points,bm.played),2),xBars('聯賽勝率 %',XMath.divide(am.w,am.played)===null?null:100*am.w/am.played,XMath.divide(bm.w,bm.played)===null?null:100*bm.w/bm.played,1)),
    el('section',{class:'panel'},el('div',{class:'x-topline'},el('h3',{},'放回十二季，看它有多特別'),xSelect('王朝趨勢指標','labMetric',Object.entries(metricNames))),xChart(seasons.map(s=>s.season),[{name:metricNames[state.labMetric],values:seasons.map(s=>ms[s.id][state.labMetric])}],{label:'王朝'+metricNames[state.labMetric]+'趨勢'}),el('p',{class:'cap'},'來源未提供的數值會留空並中斷折線；不以零或其他表的數值補入。'),evidenceTable(['球季',metricNames[state.labMetric]],seasons.map(s=>[s.season,fmt(ms[s.id][state.labMetric])]))),
    el('button',{class:'btn',onClick:()=>{state.studioKind='season';state.studioItem=a.id;go('studio');}},`把 ${a.season} 做成海報 →`)];
}

function xRadar(a,b){
  if(!a.attrs||!b.attrs||a.attrs.schema!==b.attrs.schema)return el('p',{class:'x-muted'},'兩人沒有可比的相同類型屬性快照。出場表現仍可比較，能力雷達不混用門將與外場欄位。');
  const axes=Object.keys(a.attrs.groups).filter(k=>b.attrs.groups[k]);
  const pairs=axes.map(group=>{const aa=new Map(a.attrs.groups[group]),bb=new Map(b.attrs.groups[group]);const keys=[...aa.keys()].filter(k=>bb.has(k));return {group,keys,a:keys.length?keys.reduce((n,k)=>n+aa.get(k),0)/keys.length:null,b:keys.length?keys.reduce((n,k)=>n+bb.get(k),0)/keys.length:null};}).filter(r=>r.keys.length);
  const chart=svg('svg',{viewBox:'0 0 480 340',class:'x-chart',role:'img','aria-label':'實際屬性分類平均雷達，範圍 0 到 20'},svg('title',{},'共同已提供屬性的分類平均；不是 CA 或 PA'));
  const point=(i,val)=>{const ang=-Math.PI/2+2*Math.PI*i/pairs.length;return [240+Math.cos(ang)*val/20*125,170+Math.sin(ang)*val/20*125];};
  if(pairs.length<3)return el('p',{class:'x-muted'},'共同屬性分類不足三組，請查看原始球員頁。');
  [5,10,15,20].forEach(v=>chart.append(svg('polygon',{points:pairs.map((_,i)=>point(i,v).join(',')).join(' '),fill:'none',stroke:'var(--line)'})));
  pairs.forEach((r,i)=>{const p=point(i,23);chart.append(svg('text',{x:p[0],y:p[1],'text-anchor':'middle','font-size':12},r.group));});
  ['a','b'].forEach((key,i)=>chart.append(svg('polygon',{points:pairs.map((r,j)=>point(j,r[key]).join(',')).join(' '),fill:i?'#527acf25':'#bf355425',stroke:i?'var(--azul)':'var(--garnet)','stroke-width':2})));
  return el('div',{},chart,el('p',{class:'x-muted'},`${a.name}：${a.attrs.date} ／ ${b.name}：${b.attrs.date}。僅平均兩人共同提供的欄位；快照日期可能不同，這不是 CA／PA。`),evidenceTable(['分類','共同屬性欄位',a.name,b.name],pairs.map(r=>[r.group,r.keys.join('、'),fmt(r.a,2),fmt(r.b,2)])),xSource({source:a.attrs.source,sheet:a.attrs.schema==='GOALKEEPER'?'Player_Attr_Snap_G':'Player_Attr_Snap_O'},a.name+'屬性來源'),xSource({source:b.attrs.source,sheet:b.attrs.schema==='GOALKEEPER'?'Player_Attr_Snap_G':'Player_Attr_Snap_O'},b.name+'屬性來源'));
}
function xHonourDuel(a,b){
  const pa=DATA.people.players.find(p=>p.id===a.id),pb=DATA.people.players.find(p=>p.id===b.id);
  const periods=[...new Set([...(pa?.awards||[]),...(pb?.awards||[])].map(f=>f.periodDisplay||f.season))].sort().reverse();
  xPick('duelHonourScope',['all',...periods],'all');
  const ha=XMath.honours(pa,state.duelHonourScope),hb=XMath.honours(pb,state.duelHonourScope);
  const names=[...new Set([...ha.facts,...hb.facts].map(f=>f.award))].sort();
  const summary=(h,name)=>{const c=XMath.honours({awards:h.facts.filter(f=>f.award===name)}).counts;
    return `${c.winner} 得獎 / ${c.selection} 入選 / ${c.placing} 其他名次`;};
  const ta=XMath.teamHonours(a,state.duelScope),tb=XMath.teamHonours(b,state.duelScope);
  return [el('section',{class:'panel'},el('h3',{},'個人榮譽對決'),
    el('p',{class:'cap'},'依球員名錄同一份去重明細，涵蓋已收錄的全生涯個人獎項，不限效力巴薩期間。0 表示這個範圍沒有已收錄且綁定的紀錄，不保證從未得獎。'),
    xSelect('個人榮譽範圍','duelHonourScope',[['all','全部已收錄生涯榮譽'],...periods.map(s=>[s,/^\d{4}$/.test(s)?s+' 曆年':s+' 球季'])]),
    el('p',{class:'cap'},'曆年獎項與跨年球季分開篩選；不把 2034 年自動塞進 2034/35。下方數字不套用每場效率。'),
    [['得獎','winner'],['最佳陣容入選','selection'],['其他名次','placing']].map(([label,key])=>xBars(label,ha.counts[key],hb.counts[key])),
    evidenceTable(['獎項',a.name,b.name],names.map(name=>[name,summary(ha,name),summary(hb,name)])),
    !names.length?el('p',{class:'x-muted'},'此範圍沒有已收錄的個人獎項。'):null,
    el('div',{class:'x-grid'},[[a,ha],[b,hb]].map(([p,h])=>el('details',{},el('summary',{},`${p.name} · ${h.facts.length} 筆明細與來源`),
      evidenceTable(['期間','獎項','結果','來源'],h.facts.map(f=>[f.periodDisplay||f.season,f.award,f.kind==='winner'?'得獎':f.kind==='selection'?'入選':`第 ${f.rank} 名`,awardEvidence(f)]))))),
    el('div',{class:'btnrow'},[a,b].map(p=>el('button',{class:'btn ghost',onClick:()=>xOpen('people','person',p.id)},`開啟 ${p.name} 榮譽檔案`)))),
    el('section',{class:'panel'},el('h3',{},'效力巴薩期間的團隊冠軍'),
      el('p',{class:'cap'},`${state.duelScope==='career'?'巴薩生涯主表':state.duelScope+' 逐季 A1 表'}。此為在隊期間的團隊成就，不宣稱個人正式冠軍資格；與個人獎項分開比較。逐季表未提供世俱盃欄位，維持未知。`),
      Object.keys(ta).map(k=>xBars(k,ta[k],tb[k])),
      el('div',{class:'btnrow'},[a,b].map(p=>xSource(state.duelScope==='career'?DATA.experience.players[p.id].source:
        p.seasonHonours.find(r=>XMath.season(r.season)===XMath.season(state.duelScope))?.evidence,p.name+'團隊歸屬來源'))))];
}
function renderDuel(){
  const ps=DATA.players,ids=ps.map(p=>p.id);xPick('duelA',ids,ids[0]);xPick('duelB',ids,ids[1]);
  const a=ps.find(p=>p.id===state.duelA),b=ps.find(p=>p.id===state.duelB),ma=DATA.experience.players[a.id],mb=DATA.experience.players[b.id];
  const years=[...new Set([...ma.seasons,...mb.seasons].map(r=>XMath.season(r.season)))].sort();
  xPick('duelScope',['career',...years],'career');xPick('duelRate',['totals','appearance'],'totals');
  const ar=XMath.record(ma,state.duelScope),br=XMath.record(mb,state.duelScope),rate=state.duelRate==='appearance';
  const side=(p,r,i)=>el('section',{class:'x-side'+(i?' b':'')},el('div',{class:'eyebrow'},p.id),el('h3',{},p.name),el('p',{class:'x-muted'},[p.nationality,p.position].filter(Boolean).join(' · ')||'最新 Profile 未提供國籍／位置'),el('div',{class:'x-big'},`${fmt(r?.apps)} 場`),el('p',{class:'x-muted'},r?`${state.duelScope==='career'?'巴薩生涯主表':state.duelScope+' 正式逐季觀測'}`:'這個球季沒有唯一正式採用觀測；不視為零出場。'),el('button',{class:'btn ghost',onClick:()=>xOpen('squad','player',p.id)},'完整球員檔案'),xSource(r?.source));
  return [xHeader('02 / HEAD TO HEAD','球員對決','比較巴薩生涯與逐季表現。累計數據、出場效率、遊戲內屬性各自分開解讀。'),el('div',{class:'x-controls'},xSelect('球員 A','duelA',ps.map(p=>[p.id,p.name])),xSelect('球員 B','duelB',ps.map(p=>[p.id,p.name])),el('button',{class:'btn ghost',onClick:()=>{[state.duelA,state.duelB]=[state.duelB,state.duelA];paint();}},'交換 ⇄')),
    el('div',{class:'x-controls'},xSelect('比較範圍','duelScope',[['career','巴薩生涯主表'],...years.map(y=>[y,y])]),xSelect('表現顯示方式','duelRate',[['totals','原始總量'],['appearance','每次出場效率']])),
    el('div',{class:'x-grid x-enter'},side(a,ar,0),side(b,br,1)),
    el('section',{class:'panel'},el('h3',{},rate?'每次出場的產出':'主檔原始表現'),el('p',{class:'cap'},rate?'進球、助攻、最佳球員除以出場次數，包含替補；沒有分鐘資料，因此不是每 90 分鐘。':'巴薩生涯主表與球員名錄的聯賽生涯是不同統計範圍。未從零散逐季列重算總計。'),
      [['出場','apps'],['進球','goals'],['助攻','assists'],['最佳球員','motm'],['平均評分','rating']].map(([l,k])=>xBars(l+(rate&&['goals','assists','motm'].includes(k)?'／出場':''),XMath.stat(ar,k,rate),XMath.stat(br,k,rate),k==='rating'||rate&&k!=='apps'?2:0))),
    el('section',{class:'panel'},el('h3',{},'逐季進球軌跡'),xChart(years,[{name:a.name,values:years.map(y=>XMath.stat(XMath.record(ma,y),'goals',rate))},{name:b.name,values:years.map(y=>XMath.stat(XMath.record(mb,y),'goals',rate))}],{label:rate?'兩名球員逐季每次出場進球':'兩名球員逐季進球'}),el('p',{class:'cap'},'只使用明示 ADOPTED 的巴薩逐季列；缺季中斷折線，不接成零。'),el('details',{},el('summary',{},'查看圖表原始數值'),evidenceTable(['球季',a.name,b.name],years.map(y=>[y,fmt(XMath.stat(XMath.record(ma,y),'goals',rate),rate?2:0),fmt(XMath.stat(XMath.record(mb,y),'goals',rate),rate?2:0)])))),
    ...xHonourDuel(a,b),
    el('section',{class:'panel'},el('h3',{},'屬性快照對照'),xRadar(a,b)),
    el('button',{class:'btn',onClick:()=>{state.studioKind='player';state.studioItem=a.id;go('studio');}},'把球員 A 做成典藏卡 →')];
}

function xLeagueName(name){return {'LaLiga EA Sports':'西甲','Premier League':'英超','Bundesliga':'德甲','Serie A TIM':'義甲','Ligue 1 Uber Eats':'法甲'}[name]||name;}
function xLeagueJump(league,season){state.league=league;state.leagueSeason=season;state.snapshot=null;go('leagues');}
function renderAtlas(){
  const w=DATA.world,years=w.seasons,leagues=w.leagues;xPick('atlasSeason',years,years[years.length-1]);const season=state.atlasSeason,index=years.indexOf(season);
  const champions=leagues.map(l=>XMath.champion(w,l,season)).filter(Boolean),ucl=w.ucl.find(r=>r.season===season);
  const pick=i=>{state.atlasSeason=years[Math.max(0,Math.min(years.length-1,i))];paint();};
  return [xHeader('03 / WORLD ATLAS','足壇時光機','一個年份，五條冠軍戰線。檢視各季最新可用快照，未確認榜首不會被算成冠軍。'),
    el('section',{class:'x-hero x-enter'},el('div',{class:'eyebrow'},'WORLD FOOTBALL / '+season),el('h2',{},season),el('p',{},`五大聯賽已確認 ${champions.length} 位冠軍。`+(ucl?`歐洲之巔：${ucl.winnerCanonical||ucl.winner}。`:'')),el('div',{class:'x-controls'},el('button',{class:'btn ghost',disabled:index===0,onClick:()=>pick(index-1)},'← 上一季'),el('label',{class:'x-control'},el('span',{style:'color:#d7dcec'},'拖動年份'),el('input',{type:'range',min:0,max:years.length-1,value:index,'aria-label':'世界史球季時間軸',onChange:e=>pick(Number(e.target.value))})),el('button',{class:'btn ghost',disabled:index===years.length-1,onClick:()=>pick(index+1)},'下一季 →'))),
    el('div',{class:'x-controls'},xSelect('世界史球季','atlasSeason',years.map(y=>[y,y]))),
    el('div',{class:'x-grid'},leagues.map(l=>{const c=w.champions[`${l}|${season}`],confirmed=XMath.champion(w,l,season),snap=w.snapshots[`${l}|${season}`]?.[0],rows=snap?w.standings[snap.key]:[],first=rows?.find(r=>r[0]===1),second=rows?.find(r=>r[0]===2),gap=first&&second&&first[9]!==null&&second[9]!==null?first[9]-second[9]:null;
      return el('section',{class:'x-side'},el('div',{class:'eyebrow'},xLeagueName(l)),el('h3',{},c?.club||'來源未提供'),el('div',{class:'x-tags'},el('span',{class:'x-tag'+(confirmed?' gold':'')},confirmed?'已確認冠軍':c?.state==='provisional'?'季中榜首':'榜首／冠軍未確認')),el('div',{class:'strip x-strip'},xMetric('快照積分',first?.[9]??null),xMetric('快照賽數',first?.[2]??null),xMetric('領先次席',gap,'分')),el('p',{class:'x-muted'},`${snap?.snapshot||'無快照日期'} · ${snap?.state==='final'?'正式季末':snap?.state==='provisional'?'賽季中':snap?.state==='mixed'?'混合狀態':'來源未標註階段'}`),el('button',{class:'btn ghost',onClick:()=>xLeagueJump(l,season)},'進入完整積分榜 →'));})),
    el('section',{class:'panel'},el('h3',{},'冠軍版圖 · 點一格，走進那一季'),el('p',{class:'cap'},'每季只取一份優先快照。冠軍確認來自正式季末或 Domestic_Leagues；上方卡片保留快照積分與階段。'),el('div',{class:'x-matrix'},el('table',{},el('thead',{},el('tr',{},el('th',{scope:'col'},'球季'),leagues.map(l=>el('th',{scope:'col'},xLeagueName(l))))),el('tbody',{},years.map(y=>el('tr',{'data-selected':String(y===season)},el('th',{scope:'row'},y),leagues.map(l=>{const c=w.champions[`${l}|${y}`],confirmed=XMath.champion(w,l,y);return el('td',{},el('button',{'aria-label':`${y} ${xLeagueName(l)} ${c?.club||'未知'}`,onClick:()=>xLeagueJump(l,y)},c?.club||'—',el('small',{},confirmed?'冠軍已確認':c?.state==='provisional'?'季中榜首':'待確認')));}))))))),
    el('section',{class:'panel'},el('h3',{},'同季的歐洲之巔'),ucl?el('div',{},el('h3',{},ucl.winnerCanonical||ucl.winner),el('p',{class:'x-muted'},`歐冠決賽對手：${ucl.runnerUp} · ${ucl.season}`)):el('p',{class:'x-muted'},'沒有對應的歐冠決賽紀錄。'),el('button',{class:'btn ghost',onClick:()=>go('world')},'查看完整世界總覽'))];
}

let xPlayback=null;
function xStopPlayback(){if(xPlayback){clearInterval(xPlayback);xPlayback=null;}}
function xDerbyRows(){return DATA.clasico.filter(m=>(!state.derbyComp||state.derbyComp==='all'||m.competition===state.derbyComp)&&(!state.derbyVenue||state.derbyVenue==='all'||(state.derbyVenue==='home'?m.homeIsBarca:!m.homeIsBarca)));}
function renderDerby(){
  const comps=[...new Set(DATA.clasico.map(m=>m.competition))];xPick('derbyComp',['all',...comps],'all');xPick('derbyVenue',['all','home','away'],'all');
  const rows=xDerbyRows();state.derbyIndex=Math.max(0,Math.min(rows.length-1,Number(state.derbyIndex)||0));const index=state.derbyIndex,m=rows[index],summary=XMath.matches(rows),through=XMath.matches(rows.slice(0,index+1));
  const jump=i=>{xStopPlayback();state.derbyIndex=Math.max(0,Math.min(rows.length-1,i));paint();};
  const toggle=()=>{if(xPlayback){xStopPlayback();paint();return;}if(index>=rows.length-1)state.derbyIndex=0;xPlayback=setInterval(()=>{if(state.view!=='derby'){xStopPlayback();return;}const n=xDerbyRows().length;state.derbyIndex=Number(state.derbyIndex)+1;if(state.derbyIndex>=n-1){state.derbyIndex=Math.max(0,n-1);xStopPlayback();}paint();},1600);paint();};
  return [xHeader('04 / EL CLÁSICO','國家德比劇場','從第一場走到最新一戰。播放的是已收錄紀錄的時間軸，不重建未提供的比賽過程。'),el('div',{class:'x-controls'},xSelect('德比賽事','derbyComp',[['all','全部賽事'],...comps.map(c=>[c,c])]),xSelect('主客隊身分','derbyVenue',[['all','全部'],['home','巴薩列為主隊'],['away','巴薩列為客隊']])),
    el('div',{class:'strip x-strip'},xMetric('篩選場次',rows.length),xMetric('勝',summary.w),xMetric('和',summary.d),xMetric('負',summary.l),xMetric('最長連續不敗',summary.bestUnbeaten)),
    el('p',{class:'x-muted'},'主客依賽程列示，不推定中立場地。點球註記保留，但不猜晉級者。未註日期紀錄置末，不計連續不敗；連續不敗只計目前篩選範圍。'),
    m?el('section',{class:'x-match x-enter'},el('div',{class:'eyebrow',style:'color:#e6bd79'},`${m.date||'未提供日期'} · ${m.competition}`),el('div',{class:'x-teams'},el('span',{},m.home),el('span',{class:'x-muted'},'VS'),el('span',{},m.away)),el('div',{class:'x-score'},m.score||'—'),el('div',{class:'x-tags',style:'justify-content:center'},el('span',{class:'x-tag'},({W:'巴薩勝',D:'和局',L:'巴薩負'})[m.verdict]||'結果未知'),m.decider?el('span',{class:'x-tag'},m.decider==='pens'?'點球註記 · 晉級者未推定':'含延長賽'):null),el('p',{class:'x-muted'},`第 ${index+1} / ${rows.length} 場 · 走到此刻：${through.w} 勝 ${through.d} 和 ${through.l} 負`),el('p',{class:'x-muted'},`來源比分原文：${m.result||'—'} · El_Clasico_Match_History`)):el('p',{class:'x-muted'},'這個篩選沒有比賽紀錄。'),
    el('div',{class:'x-topline'},el('button',{class:'btn ghost',disabled:index===0||!rows.length,onClick:()=>jump(index-1)},'← 上一場'),el('button',{class:'btn',disabled:rows.length<2,'aria-pressed':String(!!xPlayback),onClick:toggle},xPlayback?'暫停播放':'逐場播放 ▶'),el('button',{class:'btn ghost',disabled:index>=rows.length-1||!rows.length,onClick:()=>jump(index+1)},'下一場 →')),
    el('div',{class:'x-match-strip','aria-label':'德比逐場索引'},rows.map((r,i)=>el('button',{'data-result':r.verdict,'aria-current':String(i===index),'aria-label':`第 ${i+1} 場 ${r.date||'日期未提供'} ${r.home} ${r.result} ${r.away}`,title:`${r.date||'日期未提供'} ${r.result}`,onClick:()=>jump(i)},i+1))),
    el('section',{class:'panel'},el('h3',{},'這段交鋒的天平'),el('div',{class:'x-balance'},['w','d','l','unknown'].map((k,i)=>el('i',{style:`width:${rows.length?summary[k]/rows.length*100:0}%;background:${['var(--ok)','var(--gold)','var(--bad)','var(--line)'][i]}`}))),el('p',{class:'x-muted'},`${summary.w} 勝／${summary.d} 和／${summary.l} 負／${summary.unknown} 未知 · 可解析比分 ${summary.scored} 場：巴薩 ${summary.gf} 球，皇馬 ${summary.ga} 球。`),el('details',{},el('summary',{},'查看篩選範圍全部比賽'),evidenceTable(['日期','賽事','主隊','原始比分','客隊'],rows.map(r=>[r.date,r.competition,r.home,r.result,r.away])))),
    m?xSource(m.source,'這場比賽的來源'):null,
    m?el('button',{class:'btn',onClick:()=>{xStopPlayback();state.studioKind='match';state.studioItem=String(DATA.clasico.indexOf(m));go('studio');}},'把這一戰做成海報 →'):null];
}

function xPosterModel(){
  xPick('studioKind',['season','player','match','honour'],'season');xPick('studioStyle',['midnight','garnet','paper'],'midnight');
  const kind=state.studioKind;
  if(kind==='honour'){
    xPick('studioItem',DATA.people.players.map(p=>p.id),'P-0060');const p=DATA.people.players.find(p=>p.id===state.studioItem),f=hFilters('card',[p]);
    const facts=HMath.filter(p,f.filters),honour=HMath.card(p,facts,f.filters,DATA.meta.generated);
    return {title:p.name,honour,source:null};
  }
  if(kind==='season'){
    const ss=DATA.seasons;xPick('studioItem',ss.map(s=>s.id),ss[ss.length-1].id);const s=ss.find(r=>r.id===state.studioItem),m=DATA.experience.seasons[s.id];
    return {kicker:'FC BARCELONA / SEASON ARCHIVE',title:s.season,subtitle:'巴塞隆納 · 賽季典藏',hero:fmt(m.points),unit:'西甲積分',stats:[['勝',fmt(m.w)],['和',fmt(m.d)],['負',fmt(m.l)],['冠軍',fmt(m.trophies)],['聯賽進球',fmt(m.gf)],['聯賽失球',fmt(m.ga)]],ribbon:s.titles.join(' · ')||'主檔未列團隊冠軍',scope:'Barcelona_Season_Master · 球季主表',source:m.source};
  }
  if(kind==='player'){
    xPick('studioItem',DATA.players.map(p=>p.id),DATA.players[0].id);const p=DATA.players.find(r=>r.id===state.studioItem),m=DATA.experience.players[p.id];
    return {kicker:'FC BARCELONA / PLAYER ARCHIVE',title:p.name,subtitle:'巴薩生涯 · '+p.id,hero:fmt(m.apps),unit:'巴薩生涯出場',stats:[['進球',fmt(m.goals)],['助攻',fmt(m.assists)],['平均評分',fmt(m.rating,2)],['最佳球員',fmt(m.motm)],['零封',fmt(m.cleanSheets)],['失球',fmt(m.goalsConceded)]],ribbon:'BARÇA CAREER · 每段生涯，都有自己的形狀。',scope:'Barcelona_Player_Career · 生涯主表總計',source:m.source};
  }
  xPick('studioItem',DATA.clasico.map((m,i)=>String(i)),String(DATA.clasico.length-1));const m=DATA.clasico[Number(state.studioItem)];
  return {kicker:'EL CLÁSICO / MATCH ARCHIVE',title:m.date||'日期未提供',subtitle:m.competition,hero:m.score||'—',unit:'主隊比分在前',stats:[],ribbon:`${m.home} vs ${m.away}`,match:m,scope:'El_Clasico_Match_History · '+(m.decider==='pens'?'點球註記；不推定晉級':m.decider==='aet'?'含延長賽比分':'逐場紀錄'),source:m.source};
}
function xPosterSVG(model,style){
  if(model.honour)return hCardSVG(model.honour,style);
  const palettes={midnight:['#101a30','#263a64','#edc580','#f7f5f2','#adb9d1'],garnet:['#330f22','#791932','#e8c681','#fff5ed','#d5aaba'],paper:['#f2eee5','#e6dfd0','#936425','#152b4d','#5e6976']};
  const [bg,accent,gold,fg,muted]=palettes[style]||palettes.midnight,esc=XMath.xml;
  const text=(x,y,size,value,color=fg,extra='')=>`<text x="${x}" y="${y}" fill="${color}" font-size="${size}" font-family="Arial, Noto Sans TC, Microsoft JhengHei, sans-serif" ${extra}>${esc(value)}</text>`;
  const wrap=(value,max)=>{const chars=Array.from(value),lines=[];for(let i=0;i<chars.length;i+=max)lines.push(chars.slice(i,i+max).join(''));return lines;};
  const titleSize=Array.from(model.title).length>14?29:41;
  let out=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 900" width="720" height="900" role="img" aria-label="${esc(model.title)} 戰績海報"><title>${esc(model.title)} 戰績海報</title><defs><linearGradient id="posterBg" x2="1" y2="1"><stop stop-color="${bg}"/><stop offset="1" stop-color="${accent}"/></linearGradient></defs><rect width="720" height="900" fill="url(#posterBg)"/><circle cx="660" cy="240" r="265" fill="none" stroke="${gold}" stroke-opacity=".17"/><circle cx="660" cy="240" r="210" fill="none" stroke="${gold}" stroke-opacity=".1"/><path d="M-20 690L690 -20M50 920L920 50" stroke="${gold}" stroke-opacity=".08" stroke-width="60"/><rect x="36" y="36" width="648" height="828" rx="2" fill="none" stroke="${gold}" stroke-opacity=".45"/><rect x="64" y="70" width="9" height="28" fill="#ad2548"/><rect x="77" y="70" width="9" height="28" fill="#4268b1"/>`;
  out+=text(104,88,12,'藍紅檔案館 · THE MANAGER’S ROOM',muted,'letter-spacing="1"');out+=text(64,139,10,model.kicker,gold,'letter-spacing="2"');
  wrap(model.title,21).slice(0,2).forEach((l,i)=>out+=text(64,199+i*44,titleSize,l,fg,'font-weight="700"'));
  out+=text(64,270,16,model.subtitle,muted);out+=text(64,426,112,model.hero,fg,'font-weight="800"');out+=text(70,461,16,model.unit,gold);
  out+=`<path d="M64 498H656" stroke="${gold}" stroke-opacity=".4"/>`;
  model.stats.forEach(([label,value],i)=>{const x=64+i%3*205,y=552+Math.floor(i/3)*88;out+=text(x,y,12,label,muted)+text(x,y+38,29,value,fg,'font-weight="700"');});
  if(model.match){wrap(model.match.home,19).forEach((l,i)=>out+=text(64,555+i*29,25,l));out+=text(64,609,12,'VS',gold);wrap(model.match.away,19).forEach((l,i)=>out+=text(64,650+i*29,25,l));}
  wrap(model.ribbon,37).slice(0,2).forEach((l,i)=>out+=text(64,746+i*22,13,l,gold));
  out+=text(64,808,10,model.scope,muted);out+=text(64,831,10,`MASTER v6.4.0 · 建置 ${DATA.meta.generated} · — 代表來源未提供`,muted);
  return out+'</svg>';
}
function xDownloadStatus(status,url,message){status.replaceChildren(el('span',{},message+' '),el('a',{href:url,target:'_blank',rel:'noopener'},'未自動下載？開啟圖片另存（5 分鐘內有效）'));}
function xSaveBlob(blob,name){const url=URL.createObjectURL(blob),a=el('a',{href:url,download:name});document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),300000);return url;}
async function xExportPoster(format){
  const status=document.getElementById('posterStatus'),model=xPosterModel(),content=xPosterSVG(model,state.studioStyle),name=`fm24-${state.studioKind}-${String(state.studioItem).replace(/[^a-zA-Z0-9-]/g,'_')}`;
  try{if(format==='svg'){const saved=xSaveBlob(new Blob([content],{type:'image/svg+xml;charset=utf-8'}),name+'.svg');xDownloadStatus(status,saved,'SVG 已交給瀏覽器下載，可無損放大。');return;}
    status.textContent='正在製作 1440 × 1800 PNG…';if(document.fonts?.ready)await document.fonts.ready;
    const url=URL.createObjectURL(new Blob([content],{type:'image/svg+xml;charset=utf-8'}));try{const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('海報影像載入失敗'));img.src=url;});const canvas=document.createElement('canvas');canvas.width=1440;canvas.height=1800;canvas.getContext('2d').drawImage(img,0,0,1440,1800);const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('瀏覽器未能輸出 PNG');const saved=xSaveBlob(blob,name+'.png');xDownloadStatus(status,saved,'PNG 已交給瀏覽器下載：1440 × 1800。');}finally{URL.revokeObjectURL(url);}
  }catch(e){status.textContent='下載未完成：'+e.message+'。可以改試 SVG。';}
}
function renderStudio(){
  const model=xPosterModel(),kind=state.studioKind;
  const options=kind==='season'?DATA.seasons.map(s=>[s.id,s.season]):kind==='honour'?hPeople().map(p=>[p.id,p.name]):kind==='player'?DATA.players.map(p=>[p.id,p.name]):DATA.clasico.map((m,i)=>[String(i),`${m.date||'日期未提供'} · ${m.result}`]);
  return [xHeader('05 / POSTER STUDIO','戰績製卡室','挑一個值得留下的球季、球員或德比。海報保留統計範圍與資料版本，直接在瀏覽器產生。'),
    el('div',{class:'x-controls'},xSelect('海報類型','studioKind',[['season','球季戰績'],['player','球員生涯'],['match','國家德比'],['honour','世界球員榮譽卡']]),kind==='honour'?hPicker('海報主角','studioItem','P-0060'):xSelect('海報主角','studioItem',options),xSelect('海報配色','studioStyle',[['midnight','午夜歐冠'],['garnet','藍紅榮耀'],['paper','典藏羊皮紙']])),
    model.honour?hFilters('card',[DATA.people.players.find(p=>p.id===state.studioItem)]).ui:null,
    el('div',{class:'btnrow'},el('button',{class:'btn',onClick:()=>xExportPoster('png')},'下載 PNG · 高清圖片'),el('button',{class:'btn ghost',onClick:()=>xExportPoster('svg')},'下載 SVG · 向量海報')),
    el('p',{id:'posterStatus',class:'x-status','aria-live':'polite'},'720 × 900 預覽 · PNG 輸出 1440 × 1800 · 無浮水印'),
    el('div',{class:'x-poster x-enter',html:xPosterSVG(model,state.studioStyle)}),xSource(model.source),
    model.honour?el('details',{class:'panel'},el('summary',{},`${model.honour.total} 筆製卡依據與來源`),hFactsTable(HMath.filter(DATA.people.players.find(p=>p.id===state.studioItem),model.honour.filters))):null,
    el('p',{class:'x-muted'},'圖片在本機生成，不上傳任何資料。分享連結會保留主角、篩選範圍與配色；SVG 的字型外觀依開啟裝置而異。')];
}

const X_FORMATIONS={
  '4-3-3':[['GK',50,88],['LB',17,68],['CB',39,71],['CB',61,71],['RB',83,68],['DM',50,53],['CM',31,38],['CM',69,38],['LW',17,17],['ST',50,12],['RW',83,17]],
  '4-2-3-1':[['GK',50,88],['LB',17,69],['CB',39,72],['CB',61,72],['RB',83,69],['DM',34,51],['DM',66,51],['AM',50,32],['LW',17,29],['ST',50,12],['RW',83,29]],
  '3-4-3':[['GK',50,88],['CB',25,70],['CB',50,73],['CB',75,70],['RWB',87,45],['CM',38,47],['CM',62,47],['LWB',13,45],['LW',23,20],['ST',50,12],['RW',77,20]],
};
function xXIRoster(){return XMath.lineup(state.xiRoster,DATA.players.map(p=>p.id));}
function xXISVG(){
  const roster=xXIRoster(),slots=X_FORMATIONS[state.xiFormation]||X_FORMATIONS['4-3-3'],esc=XMath.xml;
  let content='<svg xmlns="http://www.w3.org/2000/svg" width="720" height="900" viewBox="0 0 720 900" role="img" aria-label="王朝夢幻十一人"><title>使用者自選的王朝夢幻十一人</title><rect width="720" height="900" fill="#0c1b22"/><text x="40" y="55" fill="#eccb8a" font-size="12" font-family="Arial, Microsoft JhengHei">THE MANAGER’S ROOM / YOUR DREAM ELEVEN</text><text x="40" y="103" fill="#f2f5f0" font-size="32" font-weight="700" font-family="Arial, Microsoft JhengHei">我的王朝 XI · '+esc(state.xiFormation)+'</text><rect x="35" y="135" width="650" height="660" rx="8" fill="#133c35"/>';
  content+='<g fill="none" stroke="#8bba9b" stroke-opacity=".38"><rect x="55" y="155" width="610" height="620"/><path d="M55 465H665M240 155V245H480V155M240 775V685H480V775"/><circle cx="360" cy="465" r="65"/></g>';
  slots.forEach(([role,x,y],i)=>{const p=DATA.players.find(p=>p.id===roster[i]),cx=55+x/100*610,cy=155+y/100*620;
    content+=`<circle cx="${cx}" cy="${cy-10}" r="21" fill="${p?'#a72949':'#284e46'}" stroke="#e6c785" stroke-width="1.5"/><text x="${cx}" y="${cy-6}" text-anchor="middle" fill="#fff" font-size="12" font-family="Arial">${esc(role)}</text>`;
    const name=p?p.name:'待選';const chars=Array.from(name);for(let j=0;j<Math.ceil(chars.length/8);j++)content+=`<text x="${cx}" y="${cy+29+j*16}" text-anchor="middle" fill="#f2f5ef" font-size="12" font-family="Arial, Microsoft JhengHei">${esc(chars.slice(j*8,j*8+8).join(''))}</text>`;
  });
  return content+`<text x="40" y="831" fill="#c7d2c5" font-size="12" font-family="Arial, Microsoft JhengHei">使用者跨年代自選陣容 · 不是遊戲內當前陣容或戰術建議</text><text x="40" y="855" fill="#94a79d" font-size="11" font-family="Arial, Microsoft JhengHei">球員來源：Barcelona_Player_Career · MASTER v6.4.0 · ${esc(DATA.meta.generated)}</text></svg>`;
}
async function xExportXI(){const status=document.getElementById('xiStatus');try{const url=URL.createObjectURL(new Blob([xXISVG()],{type:'image/svg+xml;charset=utf-8'}));try{const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url;});const c=document.createElement('canvas');c.width=1440;c.height=1800;c.getContext('2d').drawImage(img,0,0,1440,1800);const blob=await new Promise(resolve=>c.toBlob(resolve,'image/png'));if(!blob)throw new Error('PNG 輸出失敗');const saved=xSaveBlob(blob,'fm24-dream-eleven.png');xDownloadStatus(status,saved,'陣容圖已交給瀏覽器下載：1440 × 1800。');}finally{URL.revokeObjectURL(url);}}catch(e){status.textContent='無法輸出 PNG，請改用 SVG。';}}
function renderEleven(){
  xPick('xiFormation',Object.keys(X_FORMATIONS),'4-3-3');const roster=xXIRoster();state.xiRoster=roster.join(',');state.xiSlot=Math.max(0,Math.min(10,Number(state.xiSlot)||0));
  const slots=X_FORMATIONS[state.xiFormation],p=DATA.players.find(p=>p.id===roster[state.xiSlot]);
  const assign=id=>{state.xiRoster=XMath.place(roster,state.xiSlot,id).join(',');paint();};
  const save=()=>{try{localStorage.setItem('fm24-dream-eleven-v1',JSON.stringify({formation:state.xiFormation,roster:state.xiRoster}));document.getElementById('xiStatus').textContent='已儲存在這個瀏覽器。';}catch(e){document.getElementById('xiStatus').textContent='此瀏覽器無法儲存，請用分享連結保存。';}};
  const load=()=>{try{const saved=JSON.parse(localStorage.getItem('fm24-dream-eleven-v1'));if(!saved)throw new Error('尚未儲存過陣容。');state.xiFormation=saved.formation;state.xiRoster=saved.roster;paint();document.getElementById('xiStatus').textContent='已載入本機陣容。';}catch(e){document.getElementById('xiStatus').textContent='沒有可載入的本機陣容，或瀏覽器不允許讀取。';}};
  return [xHeader('06 / DREAM ELEVEN','王朝夢幻 XI','把不同年代的巴薩球員排在同一張球場。這是你自選的夢幻陣容，不代表目前註冊名單，也不自動判斷角色適配。'),
    el('div',{class:'x-controls'},xSelect('夢幻陣型','xiFormation',Object.keys(X_FORMATIONS).map(f=>[f,f])),el('button',{class:'btn ghost',onClick:save},'儲存本機陣容'),el('button',{class:'btn ghost',onClick:load},'載入本機陣容')),
    el('div',{class:'x-xi-layout'},el('section',{class:'x-pitch','aria-label':'夢幻十一人站位板'},el('div',{class:'x-pitch-lines'},el('i',{class:'centre'}),el('i',{class:'box top'}),el('i',{class:'box bottom'})),slots.map(([role,x,y],i)=>{const player=DATA.players.find(p=>p.id===roster[i]);return el('button',{class:'x-shirt','aria-pressed':String(i===state.xiSlot),'aria-label':`${i+1} ${role} ${player?.name||'待選'}`,style:`left:${x}%;top:${y}%`,onClick:()=>{state.xiSlot=i;paint();}},el('b',{},role),el('span',{},player?.name||'＋ 選人'));})),
      el('section',{class:'x-side'},el('div',{class:'eyebrow'},`SLOT ${state.xiSlot+1} / ${slots[state.xiSlot][0]}`),el('h3',{},p?.name||'這格交給誰？'),el('p',{class:'x-muted'},'先點球場位置，再選球員。重複選到場上球員時會交換兩格，不會出現兩個同一人。'),
        el('label',{class:'x-control'},el('span',{},'指派球員'),el('select',{'aria-label':'指派夢幻陣容球員',onChange:e=>assign(e.target.value)},el('option',{value:'',selected:!p},'— 空位 —'),DATA.players.map(player=>el('option',{value:player.id,selected:p?.id===player.id},player.name)))),
        p?el('div',{},el('p',{class:'x-muted'},`Profile 位置：${p.position||'主檔未提供'}`),el('p',{class:'x-muted'},`屬性快照日期：${p.attrs?.date||'未提供'}`),el('button',{class:'btn ghost',onClick:()=>xOpen('squad','player',p.id)},'查看球員完整資料')):null,
        el('p',{class:'x-muted'},`已選 ${roster.filter(Boolean).length} / 11 人。變更陣型會保留名額，請重新確認每格站位。`))),
    el('div',{class:'btnrow'},el('button',{class:'btn',onClick:xExportXI},'下載陣容 PNG'),el('button',{class:'btn ghost',onClick:()=>{xSaveBlob(new Blob([xXISVG()],{type:'image/svg+xml;charset=utf-8'}),'fm24-dream-eleven.svg');document.getElementById('xiStatus').textContent='SVG 已交給瀏覽器下載。';}},'下載陣容 SVG')),
    el('p',{id:'xiStatus',class:'x-status','aria-live':'polite'},'本機儲存只保留最新一組；分享網址可以保存不同版本。'),el('p',{class:'x-muted'},'位置標籤是你選定的陣型格位，並非替球員新增遊戲內位置、能力或適配度。')];
}

function xSearch(){
  let dialog=document.getElementById('xSearchDialog');if(dialog){dialog.close();dialog.remove();return;}
  const rows=[...VIEWS.map(v=>({name:v.label,kind:'頁面',id:v.id,open:()=>go(v.id)})),...DATA.people.players.map(p=>({name:p.name,search:(p.aliases||[]).join(' '),kind:'球員',id:p.id,open:()=>xOpen('people','person',p.id)})),...DATA.seasons.map(s=>({name:s.season+' 巴薩賽季',kind:'球季',id:s.id,open:()=>xOpen('seasons','season',s.id)}))];
  const results=el('div',{class:'x-search-results'}),input=el('input',{type:'search','aria-label':'全站快速搜尋',placeholder:'找球員、年份或功能…',autocomplete:'off'});
  const draw=()=>{const q=input.value.trim().normalize('NFKC').toLowerCase(),found=rows.filter(r=>!q||(r.name+' '+r.id+' '+(r.search||'')).normalize('NFKC').toLowerCase().includes(q)).slice(0,30);results.replaceChildren(...found.map(r=>el('button',{onClick:()=>{dialog.close();r.open();}},el('span',{},r.name),el('small',{},r.kind+' · '+r.id))));if(!found.length)results.append(el('p',{class:'x-muted',style:'padding:12px'},'沒有符合的項目，試試球員 ID 或完整姓名。'));};
  input.addEventListener('input',draw);input.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();results.querySelector('button')?.focus();}if(e.key==='Enter'){e.preventDefault();results.querySelector('button')?.click();}});
  results.addEventListener('keydown',e=>{const buttons=[...results.querySelectorAll('button')],i=buttons.indexOf(document.activeElement);if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=i+(e.key==='ArrowDown'?1:-1);if(n<0)input.focus();else buttons[Math.min(buttons.length-1,n)]?.focus();}});
  dialog=el('dialog',{id:'xSearchDialog',class:'x-dialog','aria-label':'全站快速搜尋'},el('div',{class:'x-dialog-head'},el('div',{class:'x-topline'},el('strong',{},'你想去哪裡？'),el('button',{class:'btn ghost',onClick:()=>dialog.close()},'關閉 Esc')),input),results);
  dialog.addEventListener('close',()=>dialog.remove());dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});document.body.append(dialog);draw();dialog.showModal();input.focus();
}
function xInit(){
  const nav=document.getElementById('nav');nav.before(el('button',{class:'x-search-trigger',onClick:xSearch,'aria-label':'開啟全站快速搜尋'},'搜尋檔案與功能',el('kbd',{},'Ctrl / ⌘ K')));
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();xSearch();}});
}

if(typeof module!=='undefined'&&module.exports)module.exports={XMath};
