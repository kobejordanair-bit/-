import assert from 'node:assert/strict';
import { buildEssayQuestion, buildEssayRecord } from '../essay-tools.mjs';

const question = buildEssayQuestion({ title: '民法第184條', content: '請說明侵權行為的成立要件。' }, 123);
assert.equal(question.id, 'essay-123');
assert.equal(question.title, '民法第184條');
assert.equal(question.content, '請說明侵權行為的成立要件。');
assert.throws(() => buildEssayQuestion({ title: '', content: '題目' }, 1), /題名/);

const record = buildEssayRecord(question, '第一，須有故意或過失。\n第二，須有損害。', 0, 60_000, 456);
assert.equal(record.id, 'essay-record-456');
assert.equal(record.cpm, 19);
assert.equal(record.accuracy, null);
assert.equal(record.netCpm, null);
assert.equal(record.answerChars, 19);

console.log('essay tools tests: PASS');
