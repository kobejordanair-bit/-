import { calculateCpm, countWritingCharacters } from './typing-metrics.mjs';

export function buildEssayQuestion(form, idSeed = Date.now()) {
  const title = String(form?.title || '').trim();
  const content = String(form?.content || '').trim().normalize('NFC');
  if (!title) throw new Error('請填寫申論題題名。');
  if (!content) throw new Error('請填寫申論題內容。');
  return {
    id: `essay-${idSeed}`,
    title,
    content,
    createdAt: new Date().toISOString(),
  };
}

export function buildEssayRecord(question, answer, startedAt, endedAt = Date.now(), idSeed = Date.now()) {
  const normalizedAnswer = String(answer || '').normalize('NFC');
  const elapsedMilliseconds = Math.max(0, Number(endedAt) - Number(startedAt));
  return {
    id: `essay-record-${idSeed}`,
    questionId: question.id,
    title: question.title,
    date: new Date(endedAt).toLocaleString('zh-TW'),
    answerChars: countWritingCharacters(normalizedAnswer),
    elapsedMilliseconds,
    cpm: calculateCpm(normalizedAnswer, elapsedMilliseconds),
    netCpm: null,
    accuracy: null,
  };
}
