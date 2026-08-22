import assert from 'node:assert/strict';
import { buildImportedDocument, normalizeApiBase } from '../legal-import.mjs';

assert.equal(normalizeApiBase('https://example.test/'), 'https://example.test');
assert.equal(normalizeApiBase(''), '');

const document = buildImportedDocument({
  case_id: '112年度台上字第1號',
  court: '最高法院',
  date: '112-01-01',
  cause: '損害賠償',
  main_text: '主文',
  reasoning: '理由',
  source_url: 'https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&id=x',
}, 'reasoning', 123);

assert.equal(document.id, 'judgment-123');
assert.equal(document.category, '裁判書｜最高法院');
assert.equal(document.title, '112年度台上字第1號｜損害賠償｜理由');
assert.match(document.content, /【來源】最高法院/);
assert.match(document.content, /理由/);
assert.throws(() => buildImportedDocument({ case_id: 'x' }, 'reasoning', 1), /沒有可匯入/);

console.log('legal import helper tests: PASS');
