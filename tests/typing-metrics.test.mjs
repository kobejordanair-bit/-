import assert from 'node:assert/strict';
import { analyzeTyping, countWritingCharacters } from '../typing-metrics.mjs';

assert.equal(countWritingCharacters('甲\n乙'), 2);

const omission = analyzeTyping('甲乙丙丁戊', '甲丙丁戊');
assert.equal(omission.distance, 1);
assert.equal(omission.matches, 4);
assert.equal(omission.accuracy, 80);
assert.deepEqual(omission.wrongTargetChars, [['乙', 1]]);

const insertion = analyzeTyping('甲乙丙丁', '甲乙X丙丁');
assert.equal(insertion.distance, 1);
assert.equal(insertion.matches, 4);
assert.equal(insertion.accuracy, 80);

const substitution = analyzeTyping('甲乙丙丁', '甲X丙丁');
assert.equal(substitution.distance, 1);
assert.equal(substitution.matches, 3);
assert.equal(substitution.accuracy, 75);

const empty = analyzeTyping('甲乙', '');
assert.equal(empty.accuracy, 0);

console.log('typing metrics tests: PASS');
