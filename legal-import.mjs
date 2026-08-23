export const DEFAULT_LEGAL_API_BASE = 'https://legal-typing-judgment-api.onrender.com';

export function normalizeApiBase(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

export function buildImportedDocument(judgment, section, idSeed = Date.now()) {
  const labels = {
    main_text: '主文',
    facts: '事實',
    reasoning: '理由',
    full_text: '全文',
  };
  const text = String(judgment?.[section] || '').trim();
  if (!text) throw new Error('這份裁判書沒有可匯入的文字段落。');

  const court = String(judgment.court || '司法院裁判書').trim();
  const caseId = String(judgment.case_id || '未載明案號').trim();
  const cause = String(judgment.cause || '裁判書').trim();
  const date = String(judgment.date || '日期未載明').trim();
  const source = String(judgment.source_url || '').trim();
  const label = labels[section] || '節錄';
  const sourceLine = source ? `\n【官方來源】${source}` : '';

  return {
    id: `judgment-${idSeed}`,
    category: `裁判書｜${court}`,
    title: `${caseId}｜${cause}｜${label}`,
    content: `【來源】${court}｜${caseId}｜${date}${sourceLine}\n\n${text}`,
    updatedAt: new Date().toISOString(),
  };
}
