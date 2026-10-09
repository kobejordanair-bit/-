import { MAX_PAGES, LINES_PER_PAGE, LINE_HEIGHT, changeNumbering, enterParagraph, replaceSelection, layoutAnswer, remainingSeconds, decodeSession } from './exam-tools.mjs?v=20261009-exam-save-2';
import { loadNotebook, persistNotebook, decodeNotebook, mergeNotebooks, createEntryId } from './exam-storage.mjs?v=20261009-exam-save-2';

const FONT = '20px "Noto Sans Mono CJK TC", "Microsoft JhengHei", monospace';
const DEFAULT_QUESTIONS = [
  { id: 'exam-example-1', title: '比例原則', content: '國家為維護公共利益而限制人民基本權時，應如何依憲法第二十三條檢驗其合憲性？請說明比例原則的各項要求。' },
  { id: 'exam-example-2', title: '侵權行為', content: '請說明民法第一百八十四條第一項前段侵權行為的成立要件，並分析相當因果關係的判斷方法。' },
];
const createSession = (questions) => ({ version: 1, questions: questions.length ? questions : DEFAULT_QUESTIONS, answers: (questions.length ? questions : DEFAULT_QUESTIONS).map(() => ''), active: 0, durationMinutes: 120, startedAt: null, deadline: null, finishedAt: null });
const clock = seconds => [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map(v => String(v).padStart(2, '0')).join(':');

export function ExamPractice({ questions = [], active, onImport }) {
  const { createElement: h, useState, useEffect, useRef, useMemo } = window.React;
  const [notebook, setNotebook] = useState(() => loadNotebook(localStorage, createSession(questions)));
  const notebookRef = useRef(notebook);
  const [session, setSession] = useState(() => notebook.entries.find(entry => entry.id === notebook.activeId).session);
  const [selectedArchive, setSelectedArchive] = useState('');
  const [saveState, setSaveState] = useState({ savedAt: notebook.entries.find(entry => entry.id === notebook.activeId).savedAt, failed: false });
  const [now, setNow] = useState(Date.now());
  const [notice, setNotice] = useState('');
  const [popup, setPopup] = useState(null);
  const [preview, setPreview] = useState(false);
  const [undoVersion, setUndoVersion] = useState(0);
  const editor = useRef(null);
  const selection = useRef([0, 0]);
  const stacks = useRef({});
  const composing = useRef(null);
  const measure = useMemo(() => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = FONT;
    return text => ctx.measureText(text).width;
  }, []);
  const answer = session.answers[session.active];
  const layout = useMemo(() => layoutAnswer(answer, measure, 708, measure(' ') * 4), [answer, measure]);
  const seconds = session.startedAt ? remainingSeconds(session.deadline, session.finishedAt || now) : session.durationMinutes * 60;
  const locked = !session.startedAt || !!session.finishedAt || seconds === 0;
  const history = stacks.current[session.active] || { undo: [], redo: [] };
  const savedSession = useRef(session);
  savedSession.current = session;
  const save = (value = savedSession.current, manual = false, id) => {
    try {
      const result = persistNotebook(localStorage, notebookRef.current, value, { id });
      notebookRef.current = result.notebook; setNotebook(result.notebook);
      setSaveState({ savedAt: result.entry.savedAt, failed: false });
      if (result.adoptedRemote) {
        savedSession.current = result.entry.session; setSession(result.entry.session); stacks.current = {}; setNow(Date.now());
        setNotice('已載入另一分頁最新保存的作答。');
      } else if (result.conflict) setNotice('偵測到另一分頁的作答，已分別保留為兩份存檔。');
      else if (manual) setNotice('已儲存完整作答、分段與編號，可從「已保存作答」開啟。');
      return result;
    } catch { setSaveState(state => ({ ...state, failed: true })); setNotice('儲存失敗，請立即下載完整作答或備份檔，避免關閉後遺失。'); return false; }
  };
  // Persist in the edit handler before rendering, so a quick reload keeps the last keystroke.
  const commitSession = (update, id, requireSave = false) => {
    const value = typeof update === 'function' ? update(savedSession.current) : update;
    const result = save(value, false, id);
    if (!result && requireSave) return false;
    const next = result ? result.entry.session : value;
    savedSession.current = next; setSession(next); return result;
  };
  useEffect(() => {
    save();
    const persist = event => {
      save();
      if (event?.detail && typeof event.detail === 'object') {
        event.detail.examSession = savedSession.current;
        event.detail.examNotebook = { ...notebookRef.current, entries: notebookRef.current.entries.map(entry => entry.id === notebookRef.current.activeId ? { ...entry, session: savedSession.current } : entry) };
      }
    };
    const restore = event => {
      const incoming = decodeNotebook(event.detail?.examNotebook);
      const restored = decodeSession(event.detail?.examSession || event.detail);
      if (!incoming && !restored) return;
      if (!save()) return;
      const previous = notebookRef.current;
      const merged = incoming ? mergeNotebooks(previous, incoming) : previous;
      const id = incoming ? merged.activeId : createEntryId();
      const value = incoming ? merged.entries.find(entry => entry.id === id).session : restored;
      notebookRef.current = merged;
      if (!commitSession(value, id, true)) { notebookRef.current = previous; return; }
      stacks.current = {}; setPreview(false); setNow(Date.now());
      setNotice('已還原模擬作答備份。');
      if (event.detail?.result) event.detail.result.ok = true;
    };
    window.addEventListener('pagehide', persist);
    window.addEventListener('exam-save', persist);
    window.addEventListener('exam-restore', restore);
    return () => { persist(); window.removeEventListener('pagehide', persist); window.removeEventListener('exam-save', persist); window.removeEventListener('exam-restore', restore); };
  }, []);
  useEffect(() => {
    if (!active) return;
    const shortcut = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(savedSession.current, true); }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [active]);
  useEffect(() => {
    if (!session.startedAt || session.finishedAt) return;
    const tick = () => {
      const timestamp = Date.now();
      setNow(timestamp);
      if (remainingSeconds(savedSession.current.deadline, timestamp) === 0) {
        if (!savedSession.current.finishedAt && commitSession(current => ({ ...current, finishedAt: current.deadline }))) setNotice('時間已到，練習已結束；完整答案保留在已保存作答。');
      }
    };
    tick();
    const timer = setInterval(tick, 1000);
    window.addEventListener('focus', tick);
    return () => { clearInterval(timer); window.removeEventListener('focus', tick); };
  }, [session.startedAt, session.finishedAt]);
  const restoreCaret = position => {
    selection.current = [position, position];
    requestAnimationFrame(() => { editor.current?.focus(); editor.current?.setSelectionRange(position, position); });
  };
  const updateAnswer = (value, caret, track = true) => {
    if (locked || preview) return;
    if (track && value !== answer) {
      const stack = stacks.current[session.active] ||= { undo: [], redo: [] };
      stack.undo.push({ text: answer, caret: selection.current[0] });
      stack.undo = stack.undo.slice(-4);
      stack.redo = [];
      setUndoVersion(v => v + 1);
    }
    commitSession(current => ({ ...current, answers: current.answers.map((item, i) => i === current.active ? value : item) }));
    if (caret !== undefined) restoreCaret(caret);
  };
  const edit = operation => { const result = operation(answer, ...selection.current); updateAnswer(result.text, result.caret); };
  const undo = redo => {
    if (locked || preview) return;
    const stack = stacks.current[session.active];
    const from = redo ? stack?.redo : stack?.undo;
    if (!from?.length) return;
    (redo ? stack.undo : stack.redo).push({ text: answer, caret: selection.current[0] });
    const previous = from.pop();
    updateAnswer(previous.text, previous.caret, false);
    setUndoVersion(v => v + 1);
  };
  const clipboard = async action => {
    if (action === 'paste') {
      try { const text = await navigator.clipboard.readText(); edit((value, start, end) => replaceSelection(value, start, end, text)); }
      catch { setNotice('請在作答區按 Ctrl＋V 貼上（Mac：⌘＋V）。'); }
      return;
    }
    const [start, end] = selection.current;
    if (start === end) { setNotice('請先選取文字。'); return; }
    try {
      await navigator.clipboard.writeText(answer.slice(start, end));
      if (action === 'cut') edit((value, a, b) => replaceSelection(value, a, b, ''));
      else editor.current?.focus();
    } catch { setNotice('請在作答區使用 Ctrl＋C／Ctrl＋X（Mac：⌘＋C／⌘＋X）。'); }
  };
  const onKeyDown = event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); event.stopPropagation(); save(savedSession.current, true); return; }
    if (event.isComposing || event.nativeEvent?.isComposing || event.keyCode === 229 || locked) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); undo(event.shiftKey); return; }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') { event.preventDefault(); undo(true); return; }
    if (event.key === 'Enter') { event.preventDefault(); edit((value, start, end) => enterParagraph(value, start, end, event.shiftKey)); }
    if (event.key === 'Tab') { event.preventDefault(); edit((value, start) => changeNumbering(value, start, event.shiftKey ? 'outdent' : 'indent')); }
    if (event.key === 'Backspace' && selection.current[0] === selection.current[1]) {
      const start = answer.lastIndexOf('\n', selection.current[0] - 1) + 1;
      const line = answer.slice(start).split('\n')[0];
      if (/^\t*([（(].+[）)]|\w+\.) $/.test(line) && selection.current[0] === start + line.length) {
        event.preventDefault(); edit((value, position) => changeNumbering(value, position, 'toggle'));
      }
    }
  };
  const rememberSelection = event => { selection.current = [event.target.selectionStart, event.target.selectionEnd]; };
  const switchQuestion = index => { selection.current = [0, 0]; commitSession(current => ({ ...current, active: index })); };
  const startExam = () => { const timestamp = Date.now(); setNow(timestamp); commitSession(current => ({ ...current, startedAt: timestamp, deadline: timestamp + current.durationMinutes * 60000 })); setNotice('練習開始，倒數計時持續進行。'); requestAnimationFrame(() => editor.current?.focus()); };
  const finish = () => {
    if (!window.confirm('確定結束練習？結束後仍可預覽與下載答案。')) return;
    const value = { ...session, finishedAt: Date.now() };
    const ok = commitSession(value); setPreview(true); if (ok) setNotice('練習已結束，答案已保留。');
  };
  const newExam = () => {
    if (!save() || !commitSession(createSession(questions), createEntryId(), true)) return;
    stacks.current = {}; setPreview(false); selection.current = [0, 0]; setSelectedArchive(''); setNotice('上一份作答已保留；已載入題庫，可設定時間後開始新練習。');
  };
  const openArchive = () => {
    if (!selectedArchive || !save()) return;
    const entry = notebookRef.current.entries.find(item => item.id === selectedArchive);
    if (!entry || !commitSession(entry.session, entry.id, true)) return;
    stacks.current = {}; selection.current = [0, 0]; setNow(Date.now()); setPreview(!!entry.session.finishedAt); setNotice('已開啟保存的作答，原有分段與標題編號已還原。');
  };
  const continueCopy = () => {
    if (!save() || !commitSession({ ...savedSession.current, startedAt: null, deadline: null, finishedAt: null }, createEntryId(), true)) return;
    stacks.current = {}; setPreview(false); setNotice('已保留原作答並建立副本，按「開始練習」即可繼續修改。');
  };
  const downloadFile = (content, type, filename) => {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement('a'); link.href = url; link.download = filename;
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  };
  const download = () => {
    save();
    const content = savedSession.current.questions.map((question, index) => {
      return `第${index + 1}題：${question.title}\n${question.content}\n\n${savedSession.current.answers[index]}`;
    }).join('\n\n──────────\n\n');
    downloadFile('\uFEFF' + content, 'text/plain;charset=utf-8', '模擬考試完整作答.txt');
  };
  const backup = () => {
    save();
    const data = { examSession: savedSession.current, examNotebook: notebookRef.current };
    // Include unsaved text even if browser storage is full.
    data.examNotebook = { ...data.examNotebook, entries: data.examNotebook.entries.map(entry => entry.id === data.examNotebook.activeId ? { ...entry, session: savedSession.current } : entry) };
    downloadFile(JSON.stringify(data, null, 2), 'application/json', '模擬考試作答備份.json');
  };
  const button = (label, callback, disabled = false, cls = '') => h('button', { type: 'button', className: cls, onClick: callback, disabled, key: label }, label);
  const tool = (label, title, callback, disabled = locked || preview) => h('button', { type: 'button', title, 'aria-label': title, key: title, disabled, onMouseDown: e => e.preventDefault(), onClick: callback }, label);
  const answered = session.answers.filter(a => a.trim()).length;
  const pages = preview ? Math.min(MAX_PAGES, layout.pages) : layout.pages;
  return h('section', { className: 'exam-practice', hidden: !active, 'aria-label': '模擬考試作答' },
    h('div', { className: 'exam-summary' },
      h('h2', null, '考試名稱：司法官、律師考試第二試模擬作答'),
      h('div', { className: 'exam-identity' }, h('span', null, '類科：各類科'), h('span', null, '姓名：應考人 先生／女士'), h('span', null, '應試座位：A01')),
      h('p', null, '科目：申論題練習'),
      h('div', { className: 'exam-status' }, h('span', null, '座號：', h('b', null, '10100001')), h('span', null, '題數：', h('b', null, session.questions.length)), h('span', null, '已作答題數：', h('b', null, answered)), h('span', null, '未作答題數：', h('b', null, session.questions.length - answered)), h('span', null, '離開考時間：', h('b', { role: 'timer', 'aria-label': '剩餘時間' }, clock(seconds))))),
    h('div', { className: 'exam-controls' },
      button('下一題', () => switchQuestion((session.active + 1) % session.questions.length)),
      button('儲存', () => save(savedSession.current, true)),
      button(preview ? '返回作答' : '預覽', () => setPreview(!preview)),
      button('操作引導', () => setPopup(popup === 'guide' ? null : 'guide'), false, 'exam-help-button'),
      button('作答注意事項', () => setPopup(popup === 'rules' ? null : 'rules'), false, 'exam-help-button'),
      h('label', null, '目前在 ', h('select', { 'aria-label': '切換題目', value: session.active, onChange: e => switchQuestion(Number(e.target.value)) }, session.questions.map((q, i) => h('option', { value: i, key: q.id }, `第${i + 1}題`)))),
      button('結束練習', finish, !session.startedAt || !!session.finishedAt)),
    h('div', { className: 'exam-setup' },
      !session.startedAt && h('label', null, '練習時間 ', h('input', { type: 'number', min: 1, max: 600, value: session.durationMinutes, 'aria-label': '練習分鐘數', onChange: e => commitSession(s => ({ ...s, durationMinutes: Math.min(600, Math.max(1, Number(e.target.value) || 1)) })) }), ' 分鐘'),
      !session.startedAt && button('開始練習', startExam), button('匯入申論題', onImport), button('載入題庫／新練習', newExam), button('下載作答檔', download),
      button('下載作答備份', backup), session.finishedAt && button('以副本繼續練習', continueCopy),
      h('span', null, session.finishedAt ? '已結束，可開啟原作答或以副本繼續練習。' : !session.startedAt ? '先按「開始練習」；匯入題目後按「載入題庫／新練習」。' : '每次編輯立即自動儲存，重新整理會繼續倒數。')),
    h('div', { className: 'exam-saved-work' },
      h('span', { role: 'status', className: saveState.failed ? 'exam-save-failed' : 'exam-save-status' }, saveState.failed ? '尚有未儲存內容' : `已儲存 ${new Date(saveState.savedAt).toLocaleTimeString('zh-TW')}（此瀏覽器）`),
      h('label', null, '已保存作答 ', h('select', { 'aria-label': '已保存作答', value: selectedArchive, onChange: e => setSelectedArchive(e.target.value) },
        h('option', { value: '' }, `選擇存檔（共 ${notebook.entries.length} 份）`),
        [...notebook.entries].sort((a, b) => b.savedAt - a.savedAt).map(entry => h('option', { value: entry.id, key: entry.id }, `${new Date(entry.savedAt).toLocaleString('zh-TW')}｜${entry.session.questions[0].title}｜已答 ${entry.session.answers.filter(answer => answer.trim()).length}/${entry.session.questions.length} 題｜${entry.session.finishedAt ? '已結束' : '草稿'}${entry.id === notebook.activeId ? '（目前）' : ''}`)))),
      button('開啟作答', openArchive, !selectedArchive),
      h('small', null, '作答存於此瀏覽器；換裝置前請下載備份，再用「匯入備份」還原。')),
    notice && h('p', { role: 'status', className: 'exam-notice' }, notice),
    layout.overflow && h('p', { role: 'alert', className: 'exam-overflow-warning' }, '作答超過八頁，考試預覽僅收錄前八頁，請自行刪減。保存作答、下載作答與備份均保留完整文字。'),
    h('div', { className: 'exam-question' }, h('h3', null, `第${session.active + 1}題（${(100 / session.questions.length).toFixed(2)}分）`), h('details', { open: true, key: session.active }, h('summary', null, session.questions[session.active].title), h('p', null, session.questions[session.active].content))),
    h('div', { className: 'exam-paper-scroll' }, h('div', { className: 'exam-paper-shell' },
      h('div', { className: 'exam-editor-toolbar' },
        ...['，', '。', '、', '；', '：', '！', '？', '—', '○', '（', '）', '「', '」', '『', '』', '§', '…'].map(char => tool(char, `插入${char}`, () => edit((v, a, b) => replaceSelection(v, a, b, char)))),
        h('span', { className: 'exam-tool-separator' }), tool('✂', '剪下', () => clipboard('cut')), tool('▱', '複製', () => clipboard('copy'), !answer || preview), tool('▣', '貼上', () => clipboard('paste')),
        tool('↶', '復原（最多四次）', () => undo(false), locked || preview || !history.undo.length), tool('↷', '重做', () => undo(true), locked || preview || !history.redo.length),
        h('span', { className: 'exam-tool-separator' }), tool('1≡', '插入或取消編號清單', () => edit((v, a) => changeNumbering(v, a, 'toggle'))), tool('⇤', '上一層', () => edit((v, a) => changeNumbering(v, a, 'outdent'))), tool('⇥', '下一層', () => edit((v, a) => changeNumbering(v, a, 'indent')))),
      h('div', { className: 'exam-format-toolbar', 'aria-label': '段落與標題設定' },
        h('span', null, '段落格式：'),
        ...['一般段落', '大標（一）', '小標 1.', '第3層 (1)', '第4層 A.', '第5層 a.', '第6層 (a)'].map((label, level) => tool(label, `套用${label}`, () => edit((v, a) => changeNumbering(v, a, level)))),
        tool('分段', '分段並接續編號（Enter）', () => edit((v, a, b) => enterParagraph(v, a, b, false))),
        tool('段內換行', '段內換行不新增編號（Shift＋Enter）', () => edit((v, a, b) => enterParagraph(v, a, b, true))),
        h('small', null, 'Enter 分段 · Shift＋Enter 段內換行 · Tab／Shift＋Tab 調整階層 · Ctrl／⌘＋S 儲存')),
      h('div', { className: 'exam-paper', style: { height: pages * LINES_PER_PAGE * LINE_HEIGHT } },
        h('div', { className: 'exam-paper-background', 'aria-hidden': true }, Array.from({ length: pages }, (_, i) => h('div', { key: i, className: 'exam-paper-page' + (i >= MAX_PAGES ? ' exam-paper-overflow' : '') }, h('span', { className: 'exam-page-label' }, `第${session.active + 1}題 第${i + 1}頁`), h('span', { className: 'exam-page-instruction' }, '（請從本頁第1行依序開始登打）')))),
        preview ? h('div', { className: 'exam-text exam-preview', 'aria-label': '作答預覽' }, layout.lines.slice(0, MAX_PAGES * LINES_PER_PAGE).join('\n'))
          : h('textarea', { ref: editor, className: 'exam-text exam-answer', 'aria-label': '模擬考試作答區', value: answer, readOnly: locked, spellCheck: false, wrap: 'soft', onSelect: rememberSelection, onClick: rememberSelection, onKeyUp: rememberSelection, onKeyDown,
            onCompositionStart: () => { composing.current = { text: answer, caret: selection.current[0] }; },
            onCompositionEnd: e => {
              const base = composing.current; composing.current = null;
              if (base && base.text !== e.target.value) {
                const stack = stacks.current[session.active] ||= { undo: [], redo: [] };
                stack.undo = [...stack.undo, base].slice(-4); stack.redo = []; setUndoVersion(v => v + 1);
              }
              updateAnswer(e.target.value, undefined, false);
            },
            onChange: e => { const value = e.target.value; updateAnswer(value, undefined, !composing.current); selection.current = [e.target.selectionStart, e.target.selectionEnd]; } })))),
    popup && h('div', { className: 'exam-dialog-backdrop', onClick: () => setPopup(null) }, h('div', { className: 'exam-dialog', role: 'dialog', 'aria-modal': true, 'aria-label': popup === 'guide' ? '操作引導' : '作答注意事項', onClick: e => e.stopPropagation() },
      h('h3', null, popup === 'guide' ? '==[操作引導]==' : '==[作答注意事項]=='),
      popup === 'guide' ? h('div', null,
        h('p', null, '1. 開始作答前，請先選擇輸入法。'), h('p', null, '2. 作答區提供一般段落與編號段落，並提供四次復原功能。'),
        h('p', null, '3. 直接按「大標」「小標」或各層按鈕套用格式；「一般段落」取消編號並保留文字。也可用「上一層／下一層」切換六個階層：'), h('pre', null, '（一）\n　1.\n　　(1)\n　　　A.\n　　　　a.\n　　　　　(a)'),
        h('p', null, 'Enter：分段，接續下一個編號。Shift＋Enter：在同一編號下換行。Tab／Shift＋Tab：下一層／上一層。'),
        h('p', null, '空白編號按 Enter 會回上一層；第一層按 Enter 或空白編號末端按 Backspace 可取消編號。也可用「1≡」保留文字並取消編號。'),
        h('p', null, '4. 每次編輯立即儲存在此瀏覽器，Ctrl／⌘＋S 或「儲存」可再次保存。「新練習」會保留上一份，可從「已保存作答」開啟。下載備份後可用主選單「匯入備份」換裝置還原。'),
        h('p', null, '5. 超過八頁的深灰底內容不會納入考試預覽；保存作答、作答檔與備份仍保留全部文字。'))
        : h('div', null, h('p', null, '1. 請務必按照題號作答。', h('strong', null, '未依題號作答部分不予計分。')), h('p', null, '2. 電子試卷作答區計八頁，請自行斟酌使用，不得跨題作答。'), h('p', null, '3. 電子試卷上不可登打姓名、座號或其他不應有之文字、標記。'), h('p', null, '此處為模擬練習；實際考試規則請以考選部公告為準。')),
      button('關閉', () => setPopup(null)))));
}
