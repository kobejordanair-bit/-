const MAX_EXACT_ALIGNMENT_CELLS = 2_000_000;

function graphemes(text) {
  const normalized = String(text || '').normalize('NFC');
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    return [...new Intl.Segmenter('zh-TW', { granularity: 'grapheme' }).segment(normalized)].map(part => part.segment);
  }
  return Array.from(normalized);
}

export function countWritingCharacters(text) {
  return graphemes(text).filter(char => char !== '\n' && char !== '\r').length;
}

export function calculateCpm(text, elapsedMilliseconds) {
  if (!Number.isFinite(elapsedMilliseconds) || elapsedMilliseconds <= 0) return 0;
  return Math.round(countWritingCharacters(text) / (elapsedMilliseconds / 60_000));
}

function buildExactAlignment(expected, actual) {
  const n = expected.length;
  const m = actual.length;
  const width = m + 1;
  const matrix = new Uint32Array((n + 1) * width);
  const at = (i, j) => i * width + j;

  for (let i = 0; i <= n; i++) matrix[at(i, 0)] = i;
  for (let j = 0; j <= m; j++) matrix[at(0, j)] = j;

  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      if (expected[i - 1] === actual[j - 1]) {
        matrix[at(i, j)] = matrix[at(i - 1, j - 1)];
      } else {
        matrix[at(i, j)] = Math.min(
          matrix[at(i - 1, j - 1)] + 1,
          matrix[at(i - 1, j)] + 1,
          matrix[at(i, j - 1)] + 1,
        );
      }
    }
  }

  const operations = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && expected[i - 1] === actual[j - 1]) {
      operations.push({ kind: 'match', expected: expected[i - 1], actual: actual[j - 1] });
      i--; j--;
      continue;
    }
    const current = matrix[at(i, j)];
    // Prefer a missing expected character on ties. It stops one omission from
    // visually turning every following character into a substitution.
    if (i > 0 && matrix[at(i - 1, j)] + 1 === current) {
      operations.push({ kind: 'deletion', expected: expected[i - 1], actual: '' });
      i--;
    } else if (j > 0 && matrix[at(i, j - 1)] + 1 === current) {
      operations.push({ kind: 'insertion', expected: '', actual: actual[j - 1] });
      j--;
    } else {
      operations.push({ kind: 'substitution', expected: expected[i - 1], actual: actual[j - 1] });
      i--; j--;
    }
  }
  operations.reverse();
  return operations;
}

function buildGreedyAlignment(expected, actual) {
  const operations = [];
  let i = 0;
  let j = 0;
  const lookahead = 24;
  while (i < expected.length || j < actual.length) {
    if (expected[i] === actual[j]) {
      operations.push({ kind: 'match', expected: expected[i], actual: actual[j] });
      i++; j++;
    } else if (i < expected.length && actual.slice(j, j + lookahead).includes(expected[i])) {
      operations.push({ kind: 'insertion', expected: '', actual: actual[j] || '' });
      j++;
    } else if (j < actual.length && expected.slice(i, i + lookahead).includes(actual[j])) {
      operations.push({ kind: 'deletion', expected: expected[i] || '', actual: '' });
      i++;
    } else if (i < expected.length && j < actual.length) {
      operations.push({ kind: 'substitution', expected: expected[i], actual: actual[j] });
      i++; j++;
    } else if (i < expected.length) {
      operations.push({ kind: 'deletion', expected: expected[i], actual: '' });
      i++;
    } else {
      operations.push({ kind: 'insertion', expected: '', actual: actual[j] });
      j++;
    }
  }
  return operations;
}

export function analyzeTyping(expectedText, actualText) {
  const expected = graphemes(expectedText);
  const actual = graphemes(actualText);
  const operations = expected.length * actual.length <= MAX_EXACT_ALIGNMENT_CELLS
    ? buildExactAlignment(expected, actual)
    : buildGreedyAlignment(expected, actual);
  const matches = operations.filter(op => op.kind === 'match').length;
  const distance = operations.filter(op => op.kind !== 'match').length;
  const denominator = Math.max(expected.length, actual.length, 1);
  const accuracy = Math.round((matches / denominator) * 100);
  const wrongMap = new Map();
  for (const op of operations) {
    if ((op.kind === 'deletion' || op.kind === 'substitution') && op.expected && op.expected !== '\n') {
      wrongMap.set(op.expected, (wrongMap.get(op.expected) || 0) + 1);
    }
  }
  return {
    accuracy,
    distance,
    matches,
    operations,
    wrongTargetChars: [...wrongMap.entries()].sort((a, b) => b[1] - a[1]),
    exact: expected.length * actual.length <= MAX_EXACT_ALIGNMENT_CELLS,
  };
}
