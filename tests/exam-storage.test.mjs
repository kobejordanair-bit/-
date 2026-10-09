import test from 'node:test';
import assert from 'node:assert/strict';
import { EXAM_NOTEBOOK_KEY, LEGACY_EXAM_KEY, decodeNotebook, loadNotebook, persistNotebook, mergeNotebooks } from '../exam-storage.mjs';

const session = answers => ({ version: 1, questions: [{ id: 'q', title: '題目', content: '題目內容' }], answers: [answers], active: 0, durationMinutes: 120, startedAt: 1000, deadline: 7201000, finishedAt: null });
const memoryStorage = () => {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
};

test('legacy draft migrates without changing answer, line breaks, or timer', () => {
  const storage = memoryStorage();
  const old = session('（一） 大標\n\t1. 小標\n\t   同段換行');
  storage.setItem(LEGACY_EXAM_KEY, JSON.stringify(old));
  const loaded = loadNotebook(storage, session(''));
  assert.deepEqual(loaded.entries[0].session, old);
  const saved = persistNotebook(storage, loaded, old, { now: 10 }).notebook;
  assert.deepEqual(loadNotebook(storage, session('')).entries[0].session, old);
  assert.equal(saved.activeId, loaded.activeId);
});

test('new attempts keep prior attempts and preserve all text past eight pages', () => {
  const storage = memoryStorage();
  const full = Array(240).fill('完整作答 👩‍⚖️').join('\n');
  const first = persistNotebook(storage, loadNotebook(storage, session(full)), session(full), { now: 10 }).notebook;
  const next = persistNotebook(storage, first, session('新練習'), { id: null, now: 20 }).notebook;
  assert.equal(next.entries.length, 2);
  const restored = loadNotebook(storage, session(''));
  assert.equal(restored.entries[0].session.answers[0], full);
  assert.equal(restored.entries[1].session.answers[0], '新練習');
});

test('quota failure leaves saved attempts intact; legacy mirror failure does not undo primary save', () => {
  const storage = memoryStorage();
  const first = persistNotebook(storage, loadNotebook(storage, session('')), session('原作答'), { now: 10 }).notebook;
  const original = storage.getItem(EXAM_NOTEBOOK_KEY);
  const write = storage.setItem;
  storage.setItem = (key, value) => { if (key === EXAM_NOTEBOOK_KEY) throw new Error('quota'); write(key, value); };
  assert.throws(() => persistNotebook(storage, first, session('最後一字'), { now: 20 }), /quota/);
  assert.equal(storage.getItem(EXAM_NOTEBOOK_KEY), original);
  storage.setItem = (key, value) => { if (key === LEGACY_EXAM_KEY) throw new Error('quota'); write(key, value); };
  assert.doesNotThrow(() => persistNotebook(storage, first, session('最後一字'), { now: 20 }));
  assert.equal(loadNotebook(storage, session('')).entries[0].session.answers[0], '最後一字');
});

test('blocked storage still initializes the editor but saving reports the failure', () => {
  const storage = { getItem: () => { throw new Error('storage blocked'); }, setItem: () => assert.fail('Cannot write without reading the latest data.') };
  const fallback = session('未儲存內容');
  const notebook = loadNotebook(storage, fallback);
  assert.equal(notebook.entries.length, 1);
  assert.deepEqual(notebook.entries[0].session, fallback);
  assert.throws(() => persistNotebook(storage, notebook, fallback), /storage blocked/);
});

test('stale tabs fork competing answers and merge new attempts from other tabs', () => {
  const storage = memoryStorage();
  const base = persistNotebook(storage, loadNotebook(storage, session('')), session('原文'), { now: 10 }).notebook;
  const other = persistNotebook(storage, base, session('另一分頁的答案'), { now: 20 }).notebook;
  persistNotebook(storage, other, session('另一分頁新練習'), { id: null, now: 25 });
  const result = persistNotebook(storage, base, session('本分頁的最後字'), { now: 30 });
  assert.equal(result.conflict, true);
  assert.notEqual(result.entry.id, base.activeId);
  assert.deepEqual(result.notebook.entries.map(entry => entry.session.answers[0]).sort(), ['另一分頁新練習', '另一分頁的答案', '本分頁的最後字'].sort());
  assert.equal(loadNotebook(storage, session('')).activeId, result.entry.id);
});

test('untouched stale tab adopts the latest answer without forking or reviving old text', () => {
  const storage = memoryStorage();
  const base = persistNotebook(storage, loadNotebook(storage, session('')), session('舊內容'), { now: 10 }).notebook;
  const remote = persistNotebook(storage, base, session('最新內容'), { now: 20 }).notebook;
  const result = persistNotebook(storage, base, session('舊內容'), { now: 30 });
  assert.equal(result.adoptedRemote, true);
  assert.equal(result.conflict, false);
  assert.equal(result.notebook.entries.length, 1);
  assert.deepEqual(result.entry, remote.entries[0]);
  assert.equal(JSON.parse(storage.getItem(LEGACY_EXAM_KEY)).answers[0], '最新內容');
});

test('closing an untouched tab preserves another tab’s active attempt; explicit selection still opens an old attempt', () => {
  const storage = memoryStorage();
  const base = persistNotebook(storage, loadNotebook(storage, session('')), session('第一份答案'), { now: 10 }).notebook;
  const remote = persistNotebook(storage, base, session('第二份答案'), { id: null, now: 20 }).notebook;
  const result = persistNotebook(storage, base, session('第一份答案'), { now: 30 });
  assert.equal(result.adoptedRemote, true);
  assert.equal(result.notebook.activeId, remote.activeId);
  assert.equal(result.entry.session.answers[0], '第二份答案');
  assert.equal(result.notebook.entries.length, 2);
  const selected = persistNotebook(storage, result.notebook, session('第一份答案'), { id: base.activeId, now: 40 });
  assert.equal(selected.adoptedRemote, false);
  assert.equal(selected.notebook.activeId, base.activeId);
  assert.equal(selected.entry.session.answers[0], '第一份答案');
});

test('same-timestamp saves still advance revision; identical answer does not create a conflict', () => {
  const storage = memoryStorage();
  const first = persistNotebook(storage, loadNotebook(storage, session('')), session('原文'), { now: 10 }).notebook;
  const second = persistNotebook(storage, first, session('新文'), { now: 10 }).notebook;
  assert.equal(second.entries[0].savedAt, 11);
  const result = persistNotebook(storage, first, session('新文'), { now: 10 });
  assert.equal(result.conflict, false);
  assert.equal(result.notebook.entries.length, 1);
});

test('another tab saving unchanged content does not fork a later edit', () => {
  const storage = memoryStorage();
  const first = persistNotebook(storage, loadNotebook(storage, session('')), session('原文'), { now: 10 }).notebook;
  persistNotebook(storage, first, session('原文'), { now: 20 });
  const result = persistNotebook(storage, first, session('修改答案'), { now: 30 });
  assert.equal(result.conflict, false);
  assert.equal(result.notebook.entries.length, 1);
});

test('invalid notebook backups are rejected, and importing conflicting entries preserves both', () => {
  const storage = memoryStorage();
  const base = persistNotebook(storage, loadNotebook(storage, session('')), session('保留本機'), { now: 10 }).notebook;
  assert.equal(decodeNotebook({ ...base, activeId: 'missing' }), null);
  assert.equal(decodeNotebook({ ...base, entries: [base.entries[0], base.entries[0]] }), null);
  assert.equal(decodeNotebook({ ...base, entries: [{ ...base.entries[0], session: { version: 1 } }] }), null);
  assert.throws(() => mergeNotebooks(base, { version: 1 }), /Invalid/);
  const incoming = { ...base, entries: [{ ...base.entries[0], savedAt: 20, session: session('備份作答') }] };
  const merged = mergeNotebooks(base, incoming);
  assert.equal(merged.entries.length, 2);
  assert.notEqual(merged.activeId, base.activeId);
  assert.deepEqual(merged.entries.map(entry => entry.session.answers[0]).sort(), ['保留本機', '備份作答'].sort());
  assert.equal(mergeNotebooks(base, base).entries.length, 1);
});
