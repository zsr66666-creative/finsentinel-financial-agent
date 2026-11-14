import test from 'node:test';
import assert from 'node:assert/strict';
import { parseScopes, selectScope, createRequestGate, coverageText, groupScopedCompanies, scopesForCompany } from '../src/lib/evidence-scopes.mjs';
import { QUERY_MODEL } from '../src/lib/query-package.mjs';

const scope = (company, period) => ({ company_code: company, company_name: company, period, chunk_count: 2,
  documents: [{ document_id: period, document_sha256: 'a'.repeat(64), pages: [60, 63], chunk_count: 2,
    coverage_kind: 'selected_pages', total_pages: 100, source_statuses: ['unreviewed'] }] });

test('catalog validates model and actual coverage without inventing scopes', () => {
  assert.deepEqual(parseScopes({ model: QUERY_MODEL, total: 0, items: [] }), []);
  assert.equal(parseScopes({ model: QUERY_MODEL, total: 1, items: [scope('002475', '2024FY')] }).length, 1);
  for (const body of [{ model: 'other', total: 0, items: [] }, { model: QUERY_MODEL, total: 1, items: [] },
    { model: QUERY_MODEL, total: 1, items: [{ ...scope('002475', '2024FY'), chunk_count: 0 }] }]) {
    assert.throws(() => parseScopes(body));
  }
});

test('company and period selection never returns a nonexistent combination', () => {
  const items = [scope('002475', '2024FY'), scope('002475', '2026H1'), scope('other', '2023FY')];
  assert.equal(selectScope(items, '002475', '2026H1').period, '2026H1');
  assert.equal(selectScope(items, 'other', '2026H1').period, '2023FY');
  assert.equal(selectScope(items, 'unknown', '2024FY'), null);
  assert.match(coverageText(items[0]), /60、63/);
  assert.match(coverageText(items[0]), /不代表/);
});

test('scope changes invalidate late responses and abort in-flight work', () => {
  const gate = createRequestGate();
  const previous = gate.begin();
  const next = gate.begin();
  assert.equal(previous.controller.signal.aborted, true);
  assert.equal(gate.isCurrent(previous), false);
  assert.equal(gate.isCurrent(next), true);
  gate.cancel();
  assert.equal(next.controller.signal.aborted, true);
  assert.equal(gate.isCurrent(next), false);
});

test('real report library groups only indexed companies and preserves company-page scope', () => {
  assert.deepEqual(groupScopedCompanies([]), []);
  const items = [scope('002475', '2024FY'), scope('002475', '2026H1'), { ...scope('002555', '2024FY'), company_name: '三七互娱', industry: '互联网游戏' }];
  const companies = groupScopedCompanies(items);
  assert.equal(companies.length, 2);
  assert.equal(companies.find(c => c.company_code === '002475').chunk_count, 4);
  assert.equal(companies.find(c => c.company_code === '002555').industry, '互联网游戏');
  assert.equal(scopesForCompany(items, '002555').length, 1);
  assert.deepEqual(scopesForCompany(items, 'not-indexed'), []);
  assert.equal(scopesForCompany(items).length, 3);
});
