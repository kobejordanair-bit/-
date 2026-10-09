import { MAX_PAGES, LINES_PER_PAGE, LINE_HEIGHT, changeNumbering, enterParagraph, replaceSelection, layoutAnswer, remainingSeconds, decodeSession } from './exam-tools.mjs';

const STORAGE_KEY = 'legalExamPracticeV1';
const FONT = '20px "Noto Sans Mono CJK TC", "Microsoft JhengHei", monospace';
const DEFAULT_QUESTIONS = [
  { id: 'exam-example-1', title: '比例原則', content: '國家為維護公共利益而限制人民基本權時，應如何依憲法第二十三條檢驗其合憲性？請說明比例原則的各項要求。' },
  { id: 'exam-example-2', title: '侵權行為', content: '請說明民法第一百八十四條第一項前段侵權行為的成立要件，並分析相當因果關係的判斷方法。' },
];
const createSession = (questions) => ({ version: 1, questions: questions.length ? questions : DEFAULT_QUESTIONS, answers: (questions.length ? questions : DEFAULT_QUESTIONS).map(() => ''), active: 0, durationMinutes: 120, startedAt: null, deadline: null, finishedAt: null });
const clock = seconds => [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map(v => String(v).padStart(2, '0')).join(':');

export function ExamPractice({ questions = [], active, onImport }) {
  const { createElement: h, useState, useEffect, useRef, useMemo } = window.React;
  const [session, setSession] = useState(() => {
    try { return decodeSession(JSON.parse(localStorage.getItem(STORAGE_KEY))) || createSession(questions); }
    catch { return createSession(questions); }
  });
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
  const save = (value = savedSession.current, manual = false) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); if (manual) setNotice('已儲存在此瀏覽器。'); return true; }
    catch { setNotice('儲存失敗，請下載作答檔保留答案。'); return false; }
  };
  useEffect(() => {
    const timer = setTimeout(() => save(session), 350);
    return () => clearTimeout(timer);
  }, [session]);
  useEffect(() => {
    const persist = () => save();
    const restore = event => {
      const restored = decodeSession(event.detail);
      if (!restored) return;
      setSession(restored); stacks.current = {}; setPreview(false); setNow(Date.now());
      setNotice('已還原模擬作答備份。');
    };
    window.addEventListener('pagehide', persist);
    window.addEventListener('exam-save', persist);
    window.addEventListener('exam-restore', restore);
    return () => { persist(); window.removeEventListener('pagehide', persist); window.removeEventListener('exam-save', persist); window.removeEventListener('exam-restore', restore); };
  }, []);
  useEffect(() => {
    if (!session.startedAt || session.finishedAt) return;
    const tick = () => {
      const timestamp = Date.now();
      setNow(timestamp);
      if (remainingSeconds(savedSession.current.deadline, timestamp) === 0) {
        setSession(current => current.finishedAt ? current : { ...current, finishedAt: current.deadline });
        setNotice('時間已到，練習已結束並自動暫存。');
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
    setSession(current => ({ ...current, answers: current.answers.map((item, i) => i === current.active ? value : item) }));
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
  const switchQuestion = index => { save(); selection.current = [0, 0]; setSession(current => ({ ...current, active: index })); };
  const startExam = () => { const timestamp = Date.now(); setNow(timestamp); setSession(current => ({ ...current, startedAt: timestamp, deadline: timestamp + current.durationMinutes * 60000 })); setNotice('練習開始，倒數計時持續進行。'); requestAnimationFrame(() => editor.current?.focus()); };
  const finish = () => {
    if (!window.confirm('確定結束練習？結束後仍可預覽與下載答案。')) return;
    const value = { ...session, finishedAt: Date.now() };
    setSession(value); save(value); setPreview(true); setNotice('練習已結束。');
  };
  const newExam = () => {
    if (!window.confirm('開始新練習會替換目前的暫存答案；需要保留時請先下載作答檔。確定繼續？')) return;
    setSession(createSession(questions)); stacks.current = {}; setPreview(false); selection.current = [0, 0]; setNotice('已載入目前申論題庫，可設定時間後開始。');
  };
  const download = () => {
    const content = session.questions.map((question, index) => {
      const result = layoutAnswer(session.answers[index], measure, 708, measure(' ') * 4);
      return `第${index + 1}題：${question.title}\n${question.content}\n\n${result.accepted}${result.overflow ? '\n\n〔第八頁之後的內容未納入作答檔〕' : ''}`;
    }).join('\n\n──────────\n\n');
    const url = URL.createObjectURL(new Blob(['\uFEFF' + content], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = '模擬考試作答.txt'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
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
      button('儲存', () => save(session, true)),
      button(preview ? '返回作答' : '預覽', () => setPreview(!preview)),
      button('操作引導', () => setPopup(popup === 'guide' ? null : 'guide'), false, 'exam-help-button'),
      button('作答注意事項', () => setPopup(popup === 'rules' ? null : 'rules'), false, 'exam-help-button'),
      h('label', null, '目前在 ', h('select', { 'aria-label': '切換題目', value: session.active, onChange: e => switchQuestion(Number(e.target.value)) }, session.questions.map((q, i) => h('option', { value: i, key: q.id }, `第${i + 1}題`)))),
      button('結束練習', finish, !session.startedAt || !!session.finishedAt)),
    h('div', { className: 'exam-setup' },
      !session.startedAt && h('label', null, '練習時間 ', h('input', { type: 'number', min: 1, max: 600, value: session.durationMinutes, 'aria-label': '練習分鐘數', onChange: e => setSession(s => ({ ...s, durationMinutes: Math.min(600, Math.max(1, Number(e.target.value) || 1)) })) }), ' 分鐘'),
      !session.startedAt && button('開始練習', startExam), button('匯入申論題', onImport), button('載入題庫／新練習', newExam), button('下載作答檔', download),
      h('span', null, session.finishedAt ? '已結束，可預覽答案' : !session.startedAt ? '先按「開始練習」；匯入題目後按「載入題庫／新練習」。' : '答案自動暫存，重新整理會繼續倒數。')),
    notice && h('p', { role: 'status', className: 'exam-notice' }, notice),
    layout.overflow && h('p', { role: 'alert', className: 'exam-overflow-warning' }, '作答超過八頁。深灰底內容保留在暫存中，預覽與作答檔僅收錄前八頁，請自行刪減。'),
    h('div', { className: 'exam-question' }, h('h3', null, `第${session.active + 1}題（${(100 / session.questions.length).toFixed(2)}分）`), h('details', { open: true, key: session.active }, h('summary', null, session.questions[session.active].title), h('p', null, session.questions[session.active].content))),
    h('div', { className: 'exam-paper-scroll' }, h('div', { className: 'exam-paper-shell' },
      h('div', { className: 'exam-editor-toolbar' },
        ...['，', '。', '、', '；', '：', '！', '？', '—', '○', '（', '）', '「', '」', '『', '』', '§', '…'].map(char => tool(char, `插入${char}`, () => edit((v, a, b) => replaceSelection(v, a, b, char)))),
        h('span', { className: 'exam-tool-separator' }), tool('✂', '剪下', () => clipboard('cut')), tool('▱', '複製', () => clipboard('copy'), !answer || preview), tool('▣', '貼上', () => clipboard('paste')),
        tool('↶', '復原（最多四次）', () => undo(false), locked || preview || !history.undo.length), tool('↷', '重做', () => undo(true), locked || preview || !history.redo.length),
        h('span', { className: 'exam-tool-separator' }), tool('1≡', '插入或取消編號清單', () => edit((v, a) => changeNumbering(v, a, 'toggle'))), tool('⇤', '上一層', () => edit((v, a) => changeNumbering(v, a, 'outdent'))), tool('⇥', '下一層', () => edit((v, a) => changeNumbering(v, a, 'indent')))),
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
        h('p', null, '3. 先按「1≡」插入編號，再用「上一層／下一層」切換六個階層：'), h('pre', null, '（一）\n　1.\n　　(1)\n　　　A.\n　　　　a.\n　　　　　(a)'),
        h('p', null, 'Enter：分段，接續下一個編號。Shift＋Enter：在同一編號下換行。Tab／Shift＋Tab：下一層／上一層。'),
        h('p', null, '空白編號按 Enter 會回上一層；第一層按 Enter 或空白編號末端按 Backspace 可取消編號。也可用「1≡」保留文字並取消編號。'),
        h('p', null, '4. 超過八頁的深灰底內容不會納入預覽及作答檔。刪減文字即可回到八頁以內；暫存仍保留全部文字。'))
        : h('div', null, h('p', null, '1. 請務必按照題號作答。', h('strong', null, '未依題號作答部分不予計分。')), h('p', null, '2. 電子試卷作答區計八頁，請自行斟酌使用，不得跨題作答。'), h('p', null, '3. 電子試卷上不可登打姓名、座號或其他不應有之文字、標記。'), h('p', null, '此處為模擬練習；實際考試規則請以考選部公告為準。')),
      button('關閉', () => setPopup(null)))));
}
