import test from 'node:test';
import assert from 'node:assert/strict';
import { parseQueryPackage } from '../src/lib/query-package.mjs';

const valid = () => ({ question: '应收账款是多少？', model: 'BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620', query_prefix: '为这个句子生成表示以用于检索相关文章：', company_code: '002475', period: '2026H1', embedding: [1, ...Array(511).fill(0)] });
test('bind query text, model, scope and real vector as one request', () => {
  const result = parseQueryPackage(JSON.stringify(valid()));
  assert.equal(result.query, valid().question);
  assert.equal(result.vector.length, 512);
  assert.equal(result.top_k, 5);
});
test('reject corrupt, mismatched, non-normalized and empty packages', () => {
  for (const patch of [{ model: 'other' }, { question: ' ' }, { embedding: [1] }, { embedding: Array(512).fill(0) }, { embedding: Array(512).fill('0') }, { company_code: '' }, { query_prefix: '' }]) {
    assert.throws(() => parseQueryPackage(JSON.stringify({ ...valid(), ...patch })));
  }
  assert.throws(() => parseQueryPackage('{bad'));
  assert.throws(() => parseQueryPackage('null'));
});
