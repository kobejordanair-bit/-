export const MAX_PAGES = 8;
export const LINES_PER_PAGE = 25;
export const LINE_HEIGHT = 36;

const CHINESE_DIGITS = '零一二三四五六七八九';
function chinese(n) {
  if (n < 10) return CHINESE_DIGITS[n];
  if (n < 100) return (n < 20 ? '' : CHINESE_DIGITS[Math.floor(n / 10)]) + '十' + (n % 10 ? CHINESE_DIGITS[n % 10] : '');
  return String(n);
}
export function numbering(level, n) {
  const letter = (upper) => {
    let value = n, result = '';
    while (value > 0) { value--; result = String.fromCharCode((upper ? 65 : 97) + value % 26) + result; value = Math.floor(value / 26); }
    return result;
  };
  return ['（' + chinese(n) + '）', n + '.', '(' + n + ')', letter(true) + '.', letter(false) + '.', '(' + letter(false) + ')'][level - 1];
}
export function parseNumberedLine(line) {
  const match = line.match(/^(\t*)(（[零一二三四五六七八九十\d]+）|\d+\.|\(\d+\)|[A-Z]+\.|[a-z]+\.|\([a-z]+\)) /);
  if (!match) return null;
  const marker = match[2];
  const level = marker.startsWith('（') ? 1 : /^\d/.test(marker) ? 2 : /^\(\d/.test(marker) ? 3 : /^[A-Z]/.test(marker) ? 4 : /^[a-z]/.test(marker) ? 5 : 6;
  const label = marker.replace(/[（）().]/g, '');
  let ordinal;
  if (/^\d+$/.test(label)) ordinal = Number(label);
  else if (level === 1) {
    const parts = label.split('十');
    ordinal = parts.length === 1 ? CHINESE_DIGITS.indexOf(label)
      : (parts[0] ? CHINESE_DIGITS.indexOf(parts[0]) : 1) * 10 + (parts[1] ? CHINESE_DIGITS.indexOf(parts[1]) : 0);
  } else ordinal = Array.from(label.toUpperCase()).reduce((value, letter) => value * 26 + letter.charCodeAt(0) - 64, 0);
  if (!Number.isSafeInteger(ordinal) || ordinal < 0) return null;
  return { level, ordinal, prefix: match[0], content: line.slice(match[0].length) };
}
function ordinalBefore(text, position, level) {
  for (const line of text.slice(0, position).split('\n').reverse()) {
    const item = parseNumberedLine(line);
    if (item?.level < level) break;
    if (item?.level === level) return item.ordinal + 1;
  }
  return 1;
}
// Chinese numerals and fullwidth parentheses occupy two columns in the paper's
// CJK monospace font; aligning by JavaScript string length puts text too far left.
const continuationPrefix = prefix => prefix.match(/^\t*/)[0] + ' '.repeat(
  Array.from(prefix.replace(/^\t*/, '')).reduce((columns, char) => columns + (char.charCodeAt(0) > 127 ? 2 : 1), 0),
);

// Only run after an explicit outline edit, never while loading a saved answer.
// Starting with the actual preceding labels preserves deliberately chosen first
// numbers, while insertion/removal keeps later siblings and child blocks coherent.
function repairFollowing(text, caret, scopeLevel, continuation = null) {
  const lines = text.split('\n');
  const anchor = text.slice(0, caret).split('\n').length - 1;
  const ordinals = Array(7).fill(0);
  const remember = item => {
    ordinals[item.level] = item.ordinal;
    ordinals.fill(0, item.level + 1);
  };
  for (let index = 0; index <= anchor; index++) {
    const item = parseNumberedLine(lines[index]);
    if (item) remember(item);
  }
  for (let index = anchor + 1; index < lines.length; index++) {
    const item = parseNumberedLine(lines[index]);
    if (item) {
      if (item.level < scopeLevel) break;
      const ordinal = ordinals[item.level] + 1;
      const prefix = item.prefix.match(/^\t*/)[0] + numbering(item.level, ordinal) + ' ';
      lines[index] = prefix + item.content;
      continuation = { before: continuationPrefix(item.prefix), after: continuationPrefix(prefix) };
      remember({ level: item.level, ordinal });
    } else if (continuation && lines[index].startsWith(continuation.before)) {
      lines[index] = continuation.after + lines[index].slice(continuation.before.length);
    } else continuation = null;
  }
  return { text: lines.join('\n'), caret };
}
export function replaceSelection(text, start, end, insertion) {
  return { text: text.slice(0, start) + insertion + text.slice(end), caret: start + insertion.length };
}
export function changeNumbering(text, position, action) {
  const start = text.lastIndexOf('\n', position - 1) + 1;
  const end = text.indexOf('\n', position);
  const line = text.slice(start, end < 0 ? text.length : end);
  const current = parseNumberedLine(line);
  let level = current?.level || 1;
  if (Number.isInteger(action) && action >= 0 && action <= 6) level = action;
  if (action === 'toggle' && current) level = 0;
  if (action === 'outdent') level = Math.max(1, level - 1);
  if (action === 'indent') level = Math.min(6, level + 1);
  const body = current ? current.content : line.replace(/^\t+/, '');
  const ordinal = current?.level === level ? current.ordinal : ordinalBefore(text, start, level);
  const prefix = level ? '\t'.repeat(level - 1) + numbering(level, ordinal) + ' ' : '';
  const replacement = prefix + body;
  const updated = text.slice(0, start) + replacement + text.slice(end < 0 ? text.length : end);
  const caret = Math.min(start + replacement.length, Math.max(start + prefix.length, position + prefix.length - (current?.prefix.length || line.length - body.length)));
  if (!current && !level) return { text: updated, caret };
  return repairFollowing(updated, caret, Math.min(current?.level || 7, level || 7), current ? {
    before: continuationPrefix(current.prefix), after: prefix ? continuationPrefix(prefix) : '',
  } : null);
}
export function enterParagraph(text, start, end, soft = false) {
  const lineStart = text.lastIndexOf('\n', start - 1) + 1;
  const lineEnd = text.indexOf('\n', start);
  const line = text.slice(lineStart, lineEnd < 0 ? text.length : lineEnd);
  let current = parseNumberedLine(line);
  // Shift+Enter creates an indented continuation of the same numbered paragraph.
  if (!current && /^\t* +/.test(line)) {
    for (const previous of text.slice(0, lineStart).split('\n').reverse()) {
      if (!previous.trim()) continue;
      current = parseNumberedLine(previous);
      if (current || !/^\t* +/.test(previous)) break;
    }
  }
  if (!current) return replaceSelection(text, start, end, '\n');
  if (!soft && parseNumberedLine(line) && !current.content.trim()) {
    if (current.level > 1) return changeNumbering(text, start, 'outdent');
    return changeNumbering(text, start, 'toggle');
  }
  const prefix = soft ? continuationPrefix(current.prefix)
    : '\t'.repeat(current.level - 1) + numbering(current.level, ordinalBefore(text, start, current.level)) + ' ';
  const result = replaceSelection(text, start, end, '\n' + prefix);
  return soft ? result : repairFollowing(result.text, result.caret, current.level, {
    before: continuationPrefix(current.prefix), after: continuationPrefix(prefix),
  });
}

// Measure each grapheme with the same font as the paper. Every explicit newline
// consumes a row; wrapped lines consume rows as well. Keep overflow in the draft.
export function layoutAnswer(text, measure, width = 708, tabWidth = 80) {
  const segments = Array.from(new Intl.Segmenter('zh-TW', { granularity: 'grapheme' }).segment(text), x => x.segment);
  const lines = [];
  let line = '', used = 0, offset = 0, acceptedEnd = text.length;
  const push = () => { lines.push(line); line = ''; used = 0; };
  for (const char of segments) {
    if (lines.length >= MAX_PAGES * LINES_PER_PAGE && acceptedEnd === text.length) acceptedEnd = offset;
    if (char === '\n') { push(); offset += char.length; continue; }
    const advance = char === '\t' ? tabWidth - used % tabWidth : measure(char);
    if (used + advance > width && line) push();
    if (lines.length >= MAX_PAGES * LINES_PER_PAGE && acceptedEnd === text.length) acceptedEnd = offset;
    line += char;
    used += char === '\t' ? tabWidth - used % tabWidth : advance;
    offset += char.length;
  }
  push();
  return { lines, pages: Math.max(1, Math.ceil(lines.length / LINES_PER_PAGE)), accepted: text.slice(0, acceptedEnd), overflow: acceptedEnd < text.length };
}
export function remainingSeconds(deadline, now = Date.now()) {
  return deadline ? Math.max(0, Math.ceil((deadline - now) / 1000)) : 0;
}
export function decodeSession(value) {
  if (!value || value.version !== 1 || !Array.isArray(value.questions) || !value.questions.length || !value.questions.every(q => q && typeof q.id === 'string' && typeof q.title === 'string' && typeof q.content === 'string') || !Array.isArray(value.answers) || value.answers.length !== value.questions.length || !value.answers.every(a => typeof a === 'string') || !Number.isInteger(value.active) || value.active < 0 || value.active >= value.questions.length || !Number.isFinite(value.durationMinutes) || value.durationMinutes < 1 || value.durationMinutes > 600 || ![value.startedAt, value.deadline, value.finishedAt].every(t => t === null || Number.isFinite(t))) return null;
  if ((value.startedAt === null) !== (value.deadline === null) || (value.finishedAt !== null && value.startedAt === null)) return null;
  return value;
}
