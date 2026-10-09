import test from 'node:test';
import assert from 'node:assert/strict';
import { numbering, parseNumberedLine, changeNumbering, enterParagraph, layoutAnswer, remainingSeconds, decodeSession } from '../exam-tools.mjs';

test('six numbering levels and numbering past Z', () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6].map(level => numbering(level, 1)), ['（一）', '1.', '(1)', 'A.', 'a.', '(a)']);
  assert.equal(numbering(1, 12), '（十二）');
  assert.equal(numbering(4, 27), 'AA.');
});
test('Enter advances a paragraph; Shift+Enter continues under its number', () => {
  const first = '（一） 第一段';
  assert.equal(enterParagraph(first, first.length, first.length).text, first + '\n（二） ');
  const continued = enterParagraph(first, first.length, first.length, true).text + '同段內容';
  assert.equal(continued, first + '\n       同段內容');
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
test('heading levels can be selected directly and cleared without losing paragraph text', () => {
  for (let level = 1; level <= 6; level++) {
    const selected = changeNumbering('法律分析', 2, level);
    const prefix = '\t'.repeat(level - 1) + numbering(level, 1) + ' ';
    assert.equal(selected.text, prefix + '法律分析');
    assert.equal(selected.caret, prefix.length + 2);
    const plain = changeNumbering(selected.text, selected.caret, 0);
    assert.equal(plain.text, '法律分析');
    assert.equal(plain.caret, 2);
  }
  assert.equal(changeNumbering('\t縮排文字', 3, 0).caret, 2);
});
test('pasted heading labels determine the next ordinal at every level', () => {
  const labels = ['（二十八）', '12.', '(12)', 'Z.', 'z.', '(z)'];
  const nextLabels = ['（二十九）', '13.', '(13)', 'AA.', 'aa.', '(aa)'];
  labels.forEach((label, index) => {
    const first = '\t'.repeat(index) + label + ' 既有內容';
    assert.equal(parseNumberedLine(first).ordinal, index === 0 ? 28 : index < 3 ? 12 : 26);
    assert.equal(enterParagraph(first, first.length, first.length).text, first + '\n' + '\t'.repeat(index) + nextLabels[index] + ' ');
    assert.equal(changeNumbering(first, first.length, index + 1).text, first);
  });
});
test('inserting in the middle renumbers later siblings and preserves their text', () => {
  const text = '（一） 首段\n（二） 次段\n\t1. 子段\n（三） 尾段';
  const caret = text.indexOf('\n');
  const inserted = enterParagraph(text, caret, caret);
  assert.equal(inserted.text, '（一） 首段\n（二） \n（三） 次段\n\t1. 子段\n（四） 尾段');
  assert.equal(inserted.text.slice(inserted.caret - 4, inserted.caret), '（二） ');
  assert.equal(changeNumbering(text, text.indexOf('次段') + 1, 0).text, '（一） 首段\n次段\n\t1. 子段\n（二） 尾段');
});
test('turning a child into a parent resets its children and advances later parents', () => {
  const text = '（一） 首段\n\t1. 新主段\n\t2. 新子段\n\t\t(4) 子段細節\n（二） 尾段';
  const caret = text.indexOf('新主段') + 2;
  assert.equal(changeNumbering(text, caret, 1).text, '（一） 首段\n（二） 新主段\n\t1. 新子段\n\t\t(1) 子段細節\n（三） 尾段');
});
test('renumbering keeps continuation lines aligned across digit and level changes', () => {
  const text = '\t9. 甲\n\t10. 乙\n\t    同段延續\n\t11. 丙';
  const caret = text.indexOf('\n');
  assert.equal(enterParagraph(text, caret, caret).text, '\t9. 甲\n\t10. \n\t11. 乙\n\t    同段延續\n\t12. 丙');
  const heading = '\t9. 甲\n\t   延續內容\n\t10. 乙';
  assert.equal(changeNumbering(heading, heading.indexOf('甲'), 1).text, '（一） 甲\n       延續內容\n\t1. 乙');
  const throughBoundary = '\t8. 甲\n\t9. 乙\n\t   延續內容';
  assert.equal(enterParagraph(throughBoundary, throughBoundary.indexOf('\n'), throughBoundary.indexOf('\n')).text, '\t8. 甲\n\t9. \n\t10. 乙\n\t    延續內容');
});
test('formatting a child leaves the following parent scope untouched', () => {
  const text = '（一） 首段\n\t7. 子段\n\t9. 次段\n（二） 次主段\n\t5. 原樣子段';
  const caret = text.indexOf('子段') + 1;
  assert.equal(changeNumbering(text, caret, 2).text, '（一） 首段\n\t7. 子段\n\t8. 次段\n（二） 次主段\n\t5. 原樣子段');
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
