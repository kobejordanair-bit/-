import test from 'node:test';
import assert from 'node:assert/strict';
import { numbering, changeNumbering, enterParagraph, layoutAnswer, remainingSeconds, decodeSession } from '../exam-tools.mjs';

test('six numbering levels and numbering past Z', () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6].map(level => numbering(level, 1)), ['（一）', '1.', '(1)', 'A.', 'a.', '(a)']);
  assert.equal(numbering(1, 12), '（十二）');
  assert.equal(numbering(4, 27), 'AA.');
});
test('Enter advances a paragraph; Shift+Enter continues under its number', () => {
  const first = '（一） 第一段';
  assert.equal(enterParagraph(first, first.length, first.length).text, first + '\n（二） ');
  const continued = enterParagraph(first, first.length, first.length, true).text + '同段內容';
  assert.equal(enterParagraph(continued, continued.length, continued.length).text, continued + '\n（二） ');
});
test('empty numbered paragraphs leave a level without losing text', () => {
  assert.equal(enterParagraph('（一） ', 4, 4).text, '');
  assert.equal(enterParagraph('\t1. ', 4, 4).text, '（一） ');
  assert.equal(changeNumbering('（一） 文字', 6, 'toggle').text, '文字');
});
test('sibling numbers resume after nested paragraphs; new parent resets child numbering', () => {
  const text = '（一） 主段\n\t1. 子段\n\t\t(1) 細節\n新段';
  assert.equal(changeNumbering(text, text.length, 'indent').text, text.replace('新段', '\t2. 新段'));
  const next = '（一） 主段\n\t1. 子段\n（二） 新主段\n新段';
  assert.equal(changeNumbering(next, next.length, 'indent').text, next.replace('新段', '\t1. 新段'));
});
test('eight page limit counts wrapped rows and keeps the full overflow draft', () => {
  const text = '甲'.repeat(201);
  const layout = layoutAnswer(text, () => 20, 20);
  assert.equal(layout.pages, 9);
  assert.equal(layout.accepted.length, 200);
  assert.equal(layout.overflow, true);
  assert.equal(layout.lines.join('').length, 201);
  const explicit = Array(201).fill('甲').join('\n');
  assert.equal(layoutAnswer(explicit, () => 20).accepted, Array(200).fill('甲').join('\n') + '\n');
});
test('page boundaries never split a surrogate pair or combining sequence', () => {
  const text = '👩‍⚖️'.repeat(201);
  assert.equal(layoutAnswer(text, () => 20, 20).accepted, '👩‍⚖️'.repeat(200));
});
test('countdown uses an absolute deadline and expired sessions remain expired', () => {
  assert.equal(remainingSeconds(10000, 8500), 2);
  assert.equal(remainingSeconds(10000, 11000), 0);
});
test('invalid saved sessions cannot break the editor', () => {
  assert.equal(decodeSession({ version: 1 }), null);
  const value = { version: 1, questions: [{ id: 'q', title: '題', content: '內容' }], answers: ['答案'], active: 0, durationMinutes: 120, startedAt: null, deadline: null, finishedAt: null };
  assert.equal(decodeSession(value), value);
  assert.equal(decodeSession({ ...value, active: 1 }), null);
  assert.equal(decodeSession({ ...value, deadline: 10000 }), null);
});
