import { decodeSession } from './exam-tools.mjs';

export const EXAM_NOTEBOOK_KEY = 'legalExamNotebookV1';
export const LEGACY_EXAM_KEY = 'legalExamPracticeV1';

export function createExamId() {
  return globalThis.crypto?.randomUUID?.() || `exam-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
export const createEntryId = createExamId;

// A notebook owns all attempts; no history is trimmed when a new exam starts.
export function decodeNotebook(value) {
  if (!value || value.version !== 1 || !Array.isArray(value.entries) || !value.entries.length || typeof value.activeId !== 'string') return null;
  const ids = new Set();
  for (const entry of value.entries) {
    if (!entry || typeof entry.id !== 'string' || !entry.id || ids.has(entry.id) || !Number.isFinite(entry.savedAt) || entry.savedAt < 0 || !decodeSession(entry.session)) return null;
    ids.add(entry.id);
  }
  return ids.has(value.activeId) ? value : null;
}

function readJson(storage, key) {
  const raw = storage.getItem(key);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function assertSession(session) {
  if (!decodeSession(session)) throw new TypeError('Invalid exam session.');
}

function comparable(value) {
  if (Array.isArray(value)) return value.map(comparable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, comparable(value[key])]));
  return value;
}

const sameSession = (left, right) => JSON.stringify(comparable(left)) === JSON.stringify(comparable(right));

export function loadNotebook(storage, fallbackSession) {
  let session = fallbackSession;
  try {
    const stored = decodeNotebook(readJson(storage, EXAM_NOTEBOOK_KEY));
    if (stored) return stored;
    session = decodeSession(readJson(storage, LEGACY_EXAM_KEY)) || fallbackSession;
  } catch { /* Storage may be blocked; keep the editor and download usable. */ }
  assertSession(session);
  const entry = { id: createExamId(), savedAt: 0, session };
  return { version: 1, activeId: entry.id, entries: [entry] };
}

// Read the latest notebook before every write so another tab's attempts survive.
// If that tab changed this attempt since our base, keep both versions.
export function persistNotebook(storage, notebook, session, options = {}) {
  const explicitId = options.id !== undefined;
  let id = options.id === undefined ? notebook?.activeId : options.id;
  const now = options.now === undefined ? Date.now() : options.now;
  if (!decodeNotebook(notebook)) throw new TypeError('Invalid exam notebook.');
  assertSession(session);
  if (!Number.isFinite(now) || now < 0) throw new TypeError('Invalid save time.');
  if (id == null) id = createExamId();
  if (typeof id !== 'string' || !id) throw new TypeError('Invalid exam attempt ID.');

  const stored = decodeNotebook(readJson(storage, EXAM_NOTEBOOK_KEY));
  const base = notebook.entries.find(entry => entry.id === id);
  const remote = stored?.entries.find(entry => entry.id === id);
  const remoteChanged = Boolean(remote && base && remote.savedAt > base.savedAt && !sameSession(remote.session, base.session));
  // Closing or saving an untouched stale tab must not resurrect an old answer
  // or switch the current attempt back after another tab started a new exam.
  // An explicit ID means the user deliberately opened/imported that attempt.
  const adoptedRemote = Boolean(!explicitId && stored && base && sameSession(base.session, session) && (remoteChanged || stored.activeId !== notebook.activeId));
  const conflict = Boolean(!adoptedRemote && remote && (!base || remoteChanged) && !sameSession(remote.session, session));
  if (conflict) id = createExamId();

  const entries = new Map();
  for (const entry of notebook.entries) entries.set(entry.id, entry);
  for (const entry of stored?.entries || []) {
    const previous = entries.get(entry.id);
    if (!previous || entry.savedAt >= previous.savedAt) entries.set(entry.id, entry);
  }
  if (adoptedRemote) id = stored.activeId;
  const previous = entries.get(id);
  const entry = adoptedRemote ? previous : { id, savedAt: Math.max(now, (previous?.savedAt ?? -1) + 1), session };
  entries.set(id, entry);
  const next = { version: 1, activeId: id, entries: [...entries.values()] };

  // The primary write is atomic. A quota error leaves the original notebook
  // untouched and propagates to the UI before it changes attempts.
  storage.setItem(EXAM_NOTEBOOK_KEY, JSON.stringify(next));
  // Keep old backups and older clients compatible without jeopardizing a save.
  try { storage.setItem(LEGACY_EXAM_KEY, JSON.stringify(entry.session)); } catch { /* Primary save already succeeded. */ }
  return { notebook: next, entry, conflict, adoptedRemote };
}

// Backup import is additive: a changed entry with a reused ID gets its own copy.
export function mergeNotebooks(base, incoming) {
  if (!decodeNotebook(base) || !decodeNotebook(incoming)) throw new TypeError('Invalid exam notebook backup.');
  const entries = new Map(base.entries.map(entry => [entry.id, entry]));
  let activeId = incoming.activeId;
  for (const entry of incoming.entries) {
    const previous = entries.get(entry.id);
    if (previous && !sameSession(previous.session, entry.session)) {
      const copy = { ...entry, id: createExamId() };
      entries.set(copy.id, copy);
      if (entry.id === incoming.activeId) activeId = copy.id;
    } else if (!previous || entry.savedAt > previous.savedAt) entries.set(entry.id, entry);
  }
  return { version: 1, activeId, entries: [...entries.values()] };
}
