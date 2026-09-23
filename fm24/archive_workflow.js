/* Full-workbook updates are separate from pending observations. */
const WFlow = {
  limit:80*1024*1024,
  jsonAt(text, offset) {
    while (/\s/.test(text[offset] || '') && offset < text.length) offset++;
    if (text[offset] !== '{') throw new Error('網站資料不是 JSON 物件。');
    let depth=0, quoted=false, escape=false;
    for(let i=offset;i<text.length;i++) {
      const c=text[i];
      if(quoted) { if(escape)escape=false; else if(c==='\\')escape=true; else if(c==='"')quoted=false; }
      else if(c==='"')quoted=true;
      else if(c==='{')depth++;
      else if(c==='}' && --depth===0) {const raw=text.slice(offset,i+1); return {raw, value:JSON.parse(raw)};}
    }
    throw new Error('JSON 資料不完整，已停止匯入。');
  },
  extract(text) {
    if(new TextEncoder().encode(text).length>this.limit)throw new Error('檔案超過 80 MB。');
    text=text.replace(/^\uFEFF/,'');
    if(text.trimStart().startsWith('{')) {
      const p=JSON.parse(text);
      if(p.format==='FM24_EXCHANGE_V1')return p;
      if(p.meta && p.people) return this.snapshot(JSON.stringify(p));
      throw new Error('這是其他種類的 JSON。待審觀測請使用下方的待併入區；完整更新請選 Excel 或 FM24 HTML。');
    }
    const meta=text.match(/<script\b[^>]*\bid=["']fm24-exchange["'][^>]*>([\s\S]*?)<\/script\s*>/i);
    const app=text.match(/<script\b[^>]*\bid=["']fm24-app["'][^>]*>([\s\S]*?)<\/script\s*>/i);
    const source=app?app[1]:text;
    const start=/\b(?:let|const) DATA = /.exec(source);
    if(!start)throw new Error('找不到 FM24 網站資料；不會執行這份 HTML 的程式。');
    const payload=this.jsonAt(source,start.index+start[0].length).raw;
    return meta ? {...JSON.parse(meta[1]),payloadJSON:payload} : this.snapshot(payload);
  },
  snapshot(raw) {return {format:'FM24_SNAPSHOT_V1',payloadJSON:raw,filename:'舊版網站快照',manifest:null};},
  validatePayload(data) {
    if(!data || typeof data!=='object')throw new Error('無效的網站資料。');
    for(const k of ['meta','world','people','sources','resolution','clubs','competitions','timetravel','integrity','honours','reference','history','experience','honourReview','comparison']) {
      if(!data[k] || typeof data[k]!=='object')throw new Error('網站快照缺少 '+k+'；請選完整 Excel 重新建置。');
    }
    for(const k of ['seasons','players','chronicle','clasico'])if(!Array.isArray(data[k]))throw new Error('網站快照欄位不完整：'+k);
    if(!data.seasons.length || !Array.isArray(data.people.players) || !data.world.seasons?.length || !Array.isArray(data.world.leagues))throw new Error('缺少球員或賽季資料。');
    if(!Number.isSafeInteger(data.meta.sheet_count)||!Number.isSafeInteger(data.meta.row_count))throw new Error('表數或列數無效。');
    return data;
  },
  diff(before, after) {
    if(!before?.sheets || !after?.sheets)return null;
    const a=new Map(before.sheets.map(s=>[s.name,s])),b=new Map(after.sheets.map(s=>[s.name,s]));
    return [...new Set([...a.keys(),...b.keys()])].sort().map(name=>{
      const x=a.get(name), y=b.get(name);
      if(x?.sha256===y?.sha256)return null;
      const counts=new Map();
      for(const h of x?.rowHashes||[])counts.set(h,(counts.get(h)||0)+1);
      let added=0;
      for(const h of y?.rowHashes||[]) {const n=counts.get(h)||0; if(n)counts.set(h,n-1);else added++;}
      return {name,kind:!x?'新增工作表':!y?'移除工作表':'內容變動',before:x?.rows||0,after:y?.rows||0,
        added,removed:[...counts.values()].reduce((s,n)=>s+n,0),
        columns:JSON.stringify(x?.columns)!==JSON.stringify(y?.columns),
        addedColumns:(y?.columns||[]).filter(c=>!(x?.columns||[]).includes(c)),
        removedColumns:(x?.columns||[]).filter(c=>!(y?.columns||[]).includes(c))};
    }).filter(Boolean);
  },
  safeJSON(value) {return JSON.stringify(value).replace(/</g,'\\u003c');},
  batchContent(kind,rows) {
    const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
    return JSON.stringify({kind,rows:(rows||[]).map(r=>JSON.stringify(canonical({values:r.values,rawName:r.rawName}))).sort()});
  },
  mergeMaps(current, incoming) {
    const merged={...current},conflicts=[];let added=0,same=0;
    for(const [id,value] of Object.entries(incoming)) {
      if(['__proto__','constructor','prototype'].includes(id))throw new Error('備份包含不允許的識別碼。');
      if(Object.hasOwn(current,id)) {if(JSON.stringify(current[id])===JSON.stringify(value))same++;else conflicts.push(id);}
      else {merged[id]=value;added++;}
    }
    return {merged,conflicts,added,same};
  },
  html(packet, runtime, portable=true) {
    let html=runtime.files['template.html'];
    for(const [marker,name] of [['/*__EXPERIENCE_JS__*/','experience.js'],['/*__EXPERIENCE_CSS__*/','experience.css'],['/*__HONOUR_JS__*/','honour_features.js'],['/*__COMPARISON_JS__*/','player_compare.js'],['/*__WORKFLOW_JS__*/','archive_workflow.js']])html=html.replace(marker,()=>runtime.files[name]);
    const {payloadJSON,...meta}=packet;
    html=html.replace('"__ARCHIVE_DATA__"',()=>payloadJSON.replace(/</g,'\\u003c'))
      .replace('"__ARCHIVE_EXCHANGE__"',()=>this.safeJSON({...meta,portable}))
      .replace('"__ARCHIVE_RUNTIME__"',()=>this.safeJSON(runtime));
    return '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0}[hidden]{display:none!important}</style></head><body>'+html+'</body></html>';
  },
};
if(typeof module!=='undefined')module.exports={WFlow};

let wfPacket=null, wfCandidate=null, wfWorker=null, wfCancel=null, wfMessage='', wfBusy=false, wfHistory=[], wfError='';
let wfBase=null, wfRuntime=null, wfScope='website', wfStorage=true, wfReady=false;
let wfExpectedActive;
let wfPersonal=null;
const WF_NOTE_KEYS=['fm24:imports','fm24:identity_decisions','fm24:club_decisions','fm24:competition_decisions','fm24-review-notes-v1'];
async function wfExportNotes() {
  const data={};
  for(const key of WF_NOTE_KEYS) {
    const value=JSON.parse(localStorage.getItem(key)||'{}');
    if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('本機資料損壞：'+key+'；已停止，請先保留原始資料。');
    data[key]=value;
  }
  const raw=JSON.stringify(data);
  wfDownload('fm24-personal-backup.json',JSON.stringify({format:'FM24_PERSONAL_V1',created:new Date().toISOString(),dataJSON:raw,sha256:await wfHash(raw)}),'application/json');
}
async function wfReadNotes(value) {
  let data;
  if(value.schema==='FM24_IMPORT_BATCH_V1') {
    if(!Array.isArray(value.batches))throw new Error('待審批次格式不完整。');
    data={'fm24:imports':{}};
    for(const batch of value.batches) {
      if(!batch.id||!Array.isArray(batch.rows)||!IMPORT_KINDS[batch.kind])throw new Error('待審批次缺少 ID、類型或資料列。');
      const {id,...body}=batch;
      if(Object.hasOwn(data['fm24:imports'],id))throw new Error('檔案內含重複批次 ID，請先核對。');
      Object.defineProperty(data['fm24:imports'],id,{value:body,enumerable:true});
    }
  } else {
    if(await wfHash(value.dataJSON)!==value.sha256)throw new Error('個人備份校驗失敗。');
    data=JSON.parse(value.dataJSON);
  }
  const changes=[];
  for(const [key,incoming] of Object.entries(data)) {
    if(!WF_NOTE_KEYS.includes(key)||!incoming||typeof incoming!=='object'||Array.isArray(incoming))throw new Error('不支援的個人資料欄位：'+key);
    const before=localStorage.getItem(key),current=JSON.parse(before||'{}');
    if(!current||typeof current!=='object'||Array.isArray(current))throw new Error('目前資料損壞，沒有覆寫。');
    changes.push({key,before,...WFlow.mergeMaps(current,incoming)});
  }
  wfPersonal=changes;
  wfMessage='個人備份預覽完成。新增內容可還原；相同 ID 的不同內容保留目前版本，衝突會列出。';
}
async function wfApplyNotes() {
  const before=[];
  try {
    for(const r of wfPersonal) {
      if(localStorage.getItem(r.key)!==r.before)throw new Error('其他分頁已更新個人資料，請重新選檔比對。');
    }
    for(const r of wfPersonal) {before.push(r);localStorage.setItem(r.key,JSON.stringify(r.merged));}
    wfPersonal=null;wfMessage='個人備份已還原；正式主檔與球員統計未變動。';
    state.batches=null;state.decisions=null;state.clubDecisions=null;state.compDecisions=null;
  }catch(e){for(const r of before.reverse()){if(r.before===null)localStorage.removeItem(r.key);else localStorage.setItem(r.key,r.before);}wfError='還原失敗，已回復原資料：'+e.message;}
  paint();
}
async function wfHash(bytes) {
  if(!crypto?.subtle)throw new Error('請在 HTTPS 網站或本機開啟頁面，才能使用檔案校驗。');
  const raw=typeof bytes==='string'?new TextEncoder().encode(bytes):bytes;
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(n=>n.toString(16).padStart(2,'0')).join('');
}
function wfBytes(base64) {
  if(typeof base64!=='string'||base64.length>WFlow.limit*1.4)throw new Error('Excel 附件格式或大小無效。');
  return Uint8Array.from(atob(base64), c=>c.charCodeAt(0));
}
async function wfValidate(packet) {
  if(!['FM24_EXCHANGE_V1','FM24_SNAPSHOT_V1'].includes(packet.format))throw new Error('不支援的交換格式。');
  WFlow.validatePayload(JSON.parse(packet.payloadJSON));
  const hash=await wfHash(packet.payloadJSON);
  if(packet.payloadSha256 && packet.payloadSha256!==hash)throw new Error('網站資料校驗失敗；原版本未變動。');
  packet.payloadJSON=packet.payloadJSON.replace(/</g,'\\u003c');
  packet.payloadSha256=await wfHash(packet.payloadJSON);
  if(packet.format==='FM24_EXCHANGE_V1') {
    const bytes=wfBytes(packet.workbook);
    if(await wfHash(bytes)!==packet.workbookSha256)throw new Error('Excel 校驗失敗；原版本未變動。');
    if(!packet.manifest?.sheets?.length)throw new Error('缺少工作表清單。');
  }
  return packet;
}
function wfID(p) {return p.workbookSha256||p.payloadSha256;}
async function wfDB() {
  return new Promise((resolve,reject)=>{
    const r=indexedDB.open('fm24-workbook-versions',1);
    r.onupgradeneeded=()=>{r.result.createObjectStore('versions',{keyPath:'key'});r.result.createObjectStore('settings');};
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
    r.onblocked=()=>reject(new Error('版本儲存被其他分頁阻擋，請關閉舊分頁後重試。'));
  });
}
async function wfRead() {
  const db=await wfDB();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(['versions','settings'],'readonly');
    const all=tx.objectStore('versions').getAll(),active=tx.objectStore('settings').get('active:'+wfScope);
    tx.oncomplete=()=>{db.close();resolve({all:all.result.filter(r=>r.scope===wfScope),active:active.result});};
    tx.onerror=()=>{db.close();reject(tx.error);};
  });
}
async function wfSave(packet) {
  const db=await wfDB(),key=wfScope+':'+wfID(packet);
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(['versions','settings'],'readwrite');
    const store=tx.objectStore('versions');
    let conflict=false;
    const active=tx.objectStore('settings').get('active:'+wfScope);
    active.onsuccess=()=>{
      if(active.result!==wfExpectedActive){conflict=true;tx.abort();return;}
      if(wfID(wfPacket)!==wfID(packet))store.put({key:wfScope+':'+wfID(wfPacket),scope:wfScope,base:wfID(wfBase),packet:wfPacket,saved:new Date(Date.now()-1).toISOString()});
      store.put({key,scope:wfScope,base:wfID(wfBase),packet,saved:new Date().toISOString()});
      tx.objectStore('settings').put(key,'active:'+wfScope);
      const all=store.getAll();
      all.onsuccess=()=>all.result.filter(r=>r.scope===wfScope&&r.key!==key).sort((a,b)=>b.saved.localeCompare(a.saved)).slice(4).forEach(r=>store.delete(r.key));
    };
    tx.oncomplete=()=>{db.close();resolve();};
    tx.onabort=tx.onerror=()=>{db.close();reject(conflict?new Error('其他分頁已切換版本，請重新整理後再比對。'):tx.error||new Error('儲存空間不足，沒有切換版本。'));};
  });
}
async function wfRestore() {
  try {
    wfRuntime=JSON.parse(document.getElementById('fm24-runtime').textContent);
    const meta=JSON.parse(document.getElementById('fm24-exchange').textContent);
    // Hash the original lexical JSON, avoiding Python 1.0 → JavaScript 1 changes.
    const source=document.getElementById('fm24-app').textContent;
    const start=/\blet DATA = /.exec(source);
    const raw=WFlow.jsonAt(source,start.index+start[0].length).raw;
    wfBase=meta?.format?{...meta,payloadJSON:raw}:WFlow.snapshot(raw);
    await wfValidate(wfBase);
    wfPacket=wfBase;
    wfScope=meta.portable?'portable:'+wfID(wfBase):'website';
    try {
      const saved=await wfRead();
      wfExpectedActive=saved.active;
      wfHistory=saved.all;
      const active=saved.all.find(r=>r.key===saved.active);
      if(active) {
        await wfValidate(active.packet);
        if(active.base && active.base!==wfID(wfBase))wfMessage='公開網站的主檔已更新，目前顯示新版基準資料。本機歷史仍保留，可先預覽差異再決定是否回復。';
        else if(active.packet.engine && active.packet.engine!==wfRuntime.engine)wfMessage='網站程式已更新，目前先顯示網站基準版。歷史版本仍保留，可按「重新建置」套用最新程式。';
        else {wfPacket=active.packet;DATA=JSON.parse(wfPacket.payloadJSON);wfMessage='目前顯示此瀏覽器保存的版本；公開網站與 Excel 原檔不會自動改寫。';}
      }
    }catch(e){wfStorage=false;wfError='本機版本儲存無法使用：'+e.message+'。仍可選檔預覽並下載成果。';}
    wfReady=true;
  }catch(e){wfError='更新中心啟動失敗：'+e.message;}
}
function wfDownload(name,content,type) {
  const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');
  a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
function wfExport(kind,packet=wfPacket) {
  const stem='fm24-'+wfID(packet).slice(0,10);
  if(kind==='xlsx') {
    if(!packet.workbook)throw new Error('這個快照沒有保存原始 Excel。');
    wfDownload(stem+'.xlsx',wfBytes(packet.workbook),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  } else if(kind==='html') wfDownload(stem+'.html',WFlow.html(packet,wfRuntime),'text/html;charset=utf-8');
  else if(kind==='publish') wfDownload('archive.html',WFlow.html(packet,wfRuntime,false),'text/html;charset=utf-8');
  else wfDownload(stem+'-exchange.json',WFlow.safeJSON(packet),'application/json');
}
async function wfBuild(bytes,filename) {
  const url=URL.createObjectURL(new Blob([wfRuntime.files['archive_worker.js']],{type:'text/javascript'}));
  return new Promise((resolve,reject)=>{
    let timer;
    const finish=(value,error)=>{clearTimeout(timer);wfWorker?.terminate();wfWorker=null;wfCancel=null;URL.revokeObjectURL(url);error?reject(error):resolve(value);};
    try {
      wfWorker=new Worker(url,{type:'module'});
      wfCancel=()=>finish(null,new Error('已取消，本來的資料與歷史版本都保留。'));
      timer=setTimeout(()=>finish(null,new Error('建置超過 10 分鐘，已停止。請用本機更新工具或再試一次。')),600000);
      wfWorker.onerror=e=>finish(null,new Error(e.message||'匯入引擎啟動失敗。請確認網路可連線至 jsDelivr 與 PyPI，或使用本機更新工具。'));
      wfWorker.onmessage=async({data})=>{
        if(data.type==='progress'){wfMessage=data.message;paint();}
        if(data.type==='error')finish(null,new Error(data.message));
        if(data.type==='result') {data.packet.filename=filename;finish(data.packet);}
      };
      const buffer=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
      wfWorker.postMessage({runtime:wfRuntime,bytes:buffer},[buffer]);
    }catch(e){finish(null,e);}
  });
}
async function wfSelect(file, force=false) {
  if(!file||wfBusy)return;
  wfBusy=true;wfCandidate=null;wfPersonal=null;wfError='';wfMessage='讀取並核對 '+file.name+'…';paint();
  try {
    if(file.size>WFlow.limit)throw new Error('檔案超過 80 MB，請使用本機工具。');
    let packet,bytes;
    if(/\.xlsx$/i.test(file.name))bytes=new Uint8Array(await file.arrayBuffer());
    else {
      const text=await file.text();
      if(text.trimStart().startsWith('{')) {
        const value=JSON.parse(text);
        if(value.format==='FM24_PERSONAL_V1'||value.schema==='FM24_IMPORT_BATCH_V1'){await wfReadNotes(value);return;}
      }
      packet=await wfValidate(WFlow.extract(text));
      if(packet.workbook)bytes=wfBytes(packet.workbook);
    }
    if(bytes) {
      if(!force && await wfHash(bytes)===wfPacket.workbookSha256 && wfPacket.engine===wfRuntime.engine) {
        wfMessage='這份 Excel 與目前版本完全相同，沒有重複匯入。';return;
      }
      packet=await wfBuild(bytes,packet?.filename||file.name);
    }
    await wfValidate(packet);
    if(wfID(packet)===wfID(wfPacket)&&packet.engine===wfPacket.engine){wfMessage='與目前版本相同，沒有重複匯入。';return;}
    wfCandidate=packet;wfMessage='預覽已完成。按「套用此版本」才會更新這台瀏覽器的網站。';
  }catch(e){wfError=e.message||String(e);wfMessage='匯入未完成，目前版本未變動。';}
  finally {wfBusy=false;paint();}
}
async function wfApply(packet) {
  if(wfBusy)return;
  wfBusy=true;wfError='';paint();
  try {await wfValidate(packet);await wfSave(packet);location.reload();}
  catch(e){wfError='套用失敗：'+e.message;wfBusy=false;paint();}
}
async function wfReset() {
  try {
    const db=await wfDB();
    await new Promise((resolve,reject)=>{const tx=db.transaction('settings','readwrite');tx.objectStore('settings').delete('active:'+wfScope);tx.oncomplete=()=>{db.close();resolve();};tx.onerror=()=>{db.close();reject(tx.error);};});
    location.reload();
  }catch(e){wfError=e.message;paint();}
}
async function wfRebuild(packet) {
  const bytes=wfBytes(packet.workbook);
  await wfSelect(new File([bytes],packet.filename||'World_Master.xlsx'),true);
}
function wfAction(fn) {return async()=>{try{await fn();}catch(e){wfError=e.message;paint();}};}
function wfButtons(packet) {
  return el('div',{class:'btnrow'},
    el('button',{class:'btn',onClick:wfAction(()=>wfExport('html',packet))},'下載完整 HTML'),
    el('button',{class:'btn ghost',disabled:!packet.workbook,onClick:wfAction(()=>wfExport('xlsx',packet))},'取回原始 Excel'),
    el('button',{class:'btn ghost',onClick:wfAction(()=>wfExport('json',packet))},'下載交換備份'));
}
function renderWorkflow() {
  const panel=el('section',{class:'panel',style:'border-top:4px solid var(--accent);margin-bottom:24px'},
    el('div',{class:'eyebrow'},'Excel ⇄ HTML　完整工作簿更新'),
    el('h2',{},'更新與備份中心'),
    el('p',{},'選擇新版 World Master Excel、完整 HTML 或交換 JSON。先核對差異，再套用；原始 Excel 保留原檔位元組、公式與格式。選 HTML 時只讀資料，不執行檔案內的程式。'),
    el('div',{class:'hint'},'更新只儲存在這台瀏覽器，分享請下載完整 HTML。首次重建 Excel 需要網路下載引擎；檔案內容在本機處理。此處更新整份正式主檔，下方貼上功能則保存待審觀測。'),
    el('p',{role:'status','aria-live':'polite'},wfMessage||'① 選檔　→　② 預覽差異　→　③ 套用或下載'),
    wfError?el('div',{class:'note',role:'alert',style:'white-space:pre-wrap;overflow-wrap:anywhere'},wfError):null);
  if(!wfReady)return panel;
  panel.append(el('div',{class:'btnrow'},el('label',{},'選擇 Excel／HTML／JSON ',el('input',{type:'file',accept:'.xlsx,.html,.htm,.json',disabled:wfBusy,onChange:e=>wfSelect(e.target.files[0]),'aria-label':'選擇更新檔案'})),
    wfCancel?el('button',{class:'btn ghost',onClick:()=>wfCancel?.()},'取消建置'):null));
  panel.append(el('p',{class:'cap'},`目前：${wfPacket.filename||'網站快照'} · ${DATA.meta.sheet_count} 表 / ${DATA.meta.row_count.toLocaleString()} 列 · ${wfID(wfPacket).slice(0,12)}`));
  if(!wfPacket.workbook)panel.append(el('div',{class:'note'},'此舊版網站快照未保存原始 Excel，無法完整還原工作簿。請另選原始 Excel 以建立可往返的新版本。'));
  panel.append(wfButtons(wfPacket));
  panel.append(el('details',{style:'margin-top:16px'},el('summary',{},'更新公開網站'),
    el('p',{},'確認目前版本後，下載發布版 archive.html，再到 GitHub 的 fm24 資料夾上傳同名檔並提交。GitHub Pages 發布完成後，其他人就能看到新版；本機套用不會自動發布。'),
    el('div',{class:'btnrow'},el('button',{class:'btn ghost',onClick:wfAction(()=>wfExport('publish'))},'下載 GitHub 發布版'),
      el('a',{class:'btn ghost',href:'https://github.com/kobejordanair-bit/-/upload/main/fm24',target:'_blank',rel:'noopener'},'開啟 GitHub 上傳頁'))));
  panel.append(el('button',{class:'btn ghost',style:'margin-top:12px',disabled:wfBusy||!wfStorage,onClick:()=>wfApply(wfPacket)},'保留目前版本至本機歷史'));
  panel.append(el('p',{class:'cap'},'分享 HTML 與交換備份只包含主檔。待審批次、身分決定及核對筆記請另存個人備份；選同一個檔案欄位即可還原。'),
    el('button',{class:'btn ghost',onClick:wfAction(wfExportNotes)},'備份此瀏覽器的待審資料與筆記'));
  if(wfPacket.workbook)panel.append(el('button',{class:'btn ghost',style:'margin-top:12px',disabled:wfBusy,onClick:()=>wfRebuild(wfPacket)},'重新驗證目前 Excel'));
  if(wfCandidate) {
    const p=JSON.parse(wfCandidate.payloadJSON),diff=WFlow.diff(wfPacket.manifest,wfCandidate.manifest);
    const risk=!diff || diff.some(r=>r.removed||r.kind==='移除工作表'||r.removedColumns.length);
    const box=el('section',{class:'panel',style:'margin-top:22px'},el('h3',{},'套用前預覽'),
      el('p',{},`${DATA.meta.sheet_count} → ${p.meta.sheet_count} 表　${DATA.meta.row_count.toLocaleString()} → ${p.meta.row_count.toLocaleString()} 列`),
      el('p',{class:'cap'},'逐列內容指紋核對；新增／替換與移除／替換可能是同一筆修正，不當作兩筆新事實。排序與來源 Excel 列號變動也會列出。'),
      diff?el('details',{open:true},el('summary',{},`${diff.length} 張表有變動`),evidenceTable(['工作表','變動','前 → 後','新增／替換列','移除／替換列','欄位變動'],diff.map(r=>[r.name,r.kind,`${r.before} → ${r.after}`,r.added,r.removed,r.columns?`新增：${r.addedColumns.join('、')||'無'}；移除：${r.removedColumns.join('、')||'無'}（含順序核對）`:'—']))):el('div',{class:'note'},'舊快照沒有逐表清單，不能核對工作簿差異，也不能匯出原始 Excel。'),
      el('p',{},`個人榮譽紀錄：${DATA.people.awardCoverage?.records??'—'} → ${p.people.awardCoverage?.records??'—'}；最新聯賽賽季：${DATA.world.seasons.at(-1)} → ${p.world.seasons.at(-1)}`));
    const apply=el('button',{class:'btn',disabled:wfBusy||!wfStorage||risk,onClick:()=>wfApply(wfCandidate)},'套用此版本');
    if(risk)box.append(el('label',{style:'display:block;margin:14px 0'},el('input',{type:'checkbox',onChange:e=>{apply.disabled=!e.target.checked||!wfStorage;}}),' 我已檢查移除／替換的內容，或接受舊快照無法逐表核對，確定改用此版本。'));
    box.append(el('div',{class:'btnrow'},apply,el('button',{class:'btn ghost',onClick:()=>{wfCandidate=null;paint();}},'放棄這次更新')),el('p',{class:'cap'},'也可以先下載預覽成果，不套用到目前網站。'),wfButtons(wfCandidate));
    panel.append(box);
  }
  if(wfPersonal)panel.append(el('section',{class:'panel',style:'margin-top:18px'},el('h3',{},'個人備份還原預覽'),
    evidenceTable(['分類','新增','相同','衝突（保留現有）'],wfPersonal.map(r=>[r.key,r.added,r.same,r.conflicts.length])),
    wfPersonal.some(r=>r.conflicts.length)?el('details',{},el('summary',{},'查看衝突識別碼'),el('pre',{style:'white-space:pre-wrap;overflow-wrap:anywhere'},wfPersonal.filter(r=>r.conflicts.length).map(r=>r.key+': '+r.conflicts.join(', ')).join('\n'))):null,
    el('button',{class:'btn',onClick:wfAction(wfApplyNotes)},'還原可新增的個人資料'),
    el('button',{class:'btn ghost',onClick:()=>{wfPersonal=null;paint();}},'取消還原')));
  panel.append(el('details',{style:'margin-top:22px'},el('summary',{},`版本歷史（保留最近 5 版，目前 ${wfHistory.length} 版）`),
    el('p',{class:'cap'},'瀏覽器清除網站資料會移除本機歷史，重要版本請下載交換備份。回復版本保留待審觀測與核對筆記。'),
    el('button',{class:'btn ghost',disabled:wfBusy,onClick:wfReset},'回到這份網頁的基準版'),
    wfHistory.sort((a,b)=>b.saved.localeCompare(a.saved)).map(r=>el('div',{style:'margin-top:14px'},
      el('p',{},`${r.saved.slice(0,19).replace('T',' ')} UTC · ${r.packet.filename} · ${wfID(r.packet).slice(0,10)}`),
      el('button',{class:'btn ghost',disabled:wfBusy,onClick:()=>{if(r.packet.engine&&r.packet.engine!==wfRuntime.engine&&r.packet.workbook)wfRebuild(r.packet);else {wfCandidate=r.packet;paint();}}},r.packet.engine&&r.packet.engine!==wfRuntime.engine?'重新建置並預覽':'預覽此版本'),wfButtons(r.packet)))));
  return panel;
}
