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
  return { level, prefix: match[0], content: line.slice(match[0].length) };
}
function ordinalBefore(text, position, level) {
  let count = 0;
  for (const line of text.slice(0, position).split('\n').reverse()) {
    const item = parseNumberedLine(line);
    if (item?.level < level) break;
    if (item?.level === level) count++;
  }
  return count + 1;
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
  if (action === 'toggle' && current) level = 0;
  if (action === 'outdent') level = Math.max(1, level - 1);
  if (action === 'indent') level = Math.min(6, level + 1);
  const body = current ? current.content : line.replace(/^\t+/, '');
  const prefix = level ? '\t'.repeat(level - 1) + numbering(level, ordinalBefore(text, start, level)) + ' ' : '';
  const replacement = prefix + body;
  return { text: text.slice(0, start) + replacement + text.slice(end < 0 ? text.length : end), caret: Math.max(start + prefix.length, position + prefix.length - (current?.prefix.length || 0)) };
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
  const prefix = soft ? '\t'.repeat(current.level - 1) + ' '.repeat(current.prefix.trimStart().length)
    : '\t'.repeat(current.level - 1) + numbering(current.level, ordinalBefore(text, start, current.level)) + ' ';
  return replaceSelection(text, start, end, '\n' + prefix);
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
