import test from 'node:test';
import assert from 'node:assert/strict';
import { filterAlerts, normalizeAlert, normalizeCollection, formatMetric, connectionStatusLabel, refreshLabel, metricStateLabel, alertEmptyLabel, evidenceStatusLabel } from '../src/lib/domain.mjs';

test('severity, company, status and keyword filters combine rather than replace each other', () => {
  const rows = [
    { id: '1', company_name: '立讯精密', severity: 'high', status: 'pending', title: '现金流异常' },
    { id: '2', company_name: '歌尔股份', severity: 'high', status: 'confirmed', title: '现金流异常' },
    { id: '3', company_name: '立讯精密', severity: 'low', status: 'pending', title: '存货变化' }
  ];
  assert.deepEqual(filterAlerts(rows, { severity: 'high', company: '立讯精密', status: 'pending', query: '现金' }).map(a => a.id), ['1']);
});
test('API response normalization accepts list and envelope without inventing records', () => {
  assert.deepEqual(normalizeCollection({ items: [{ id: 1 }] }), [{ id: 1 }]);
  assert.deepEqual(normalizeCollection({ alerts: [{ id: 2 }] }, 'alerts'), [{ id: 2 }]);
  assert.deepEqual(normalizeCollection({ error: 'offline' }), []);
});
test('backend alert field aliases normalize to stable view model', () => {
  const row = normalizeAlert({ id: 'a', company_id: '002475', title: '告警', risk_level: 'high', review_status: 'pending_review', evidence: [{ id: 'e' }] });
  assert.equal(row.severity, 'high');
  assert.equal(row.status, 'pending');
  assert.equal(row.evidence.length, 1);
});
test('missing and zero metrics remain distinct', () => {
  assert.equal(formatMetric(null, '%'), '—');
  assert.equal(formatMetric(0, '%'), '0.0%');
});
test('connection state exposes loading, connected and recoverable error messages', () => {
  assert.equal(connectionStatusLabel({ loading: true }), '正在连接数据服务…');
  assert.equal(connectionStatusLabel({ connected: true }), '数据服务已连接');
  assert.equal(connectionStatusLabel({ error: 'timeout' }), '数据服务暂时不可用，当前展示离线演示数据。');
});
test('refresh label distinguishes idle and active refresh', () => {
  assert.equal(refreshLabel(false), '刷新数据');
  assert.equal(refreshLabel(true), '刷新中…');
});
test('company metric state distinguishes loading, error and empty data', () => {
  assert.equal(metricStateLabel({ loading: true }), '正在加载指标…');
  assert.equal(metricStateLabel({ error: 'timeout' }), '指标加载失败，请重试。');
  assert.equal(metricStateLabel({ hasData: false }), '该公司暂无已入库指标。');
  assert.equal(metricStateLabel({ hasData: true }), '');
});
test('alert empty state distinguishes no data from filters with no matches', () => {
  assert.equal(alertEmptyLabel({ total: 0, filtered: 0 }), '当前没有风险告警。');
  assert.equal(alertEmptyLabel({ total: 0, filtered: 0, review: true }), '当前没有待复核告警。');
  assert.equal(alertEmptyLabel({ total: 3, filtered: 0 }), '没有匹配的告警，请调整筛选条件。');
});
test('evidence status reports the strongest available source locator', () => {
  assert.equal(evidenceStatusLabel({ source_url: 'https://example.test', page: 4 }), '原文与页码已定位');
  assert.equal(evidenceStatusLabel({ page: 4 }), '页码已定位');
  assert.equal(evidenceStatusLabel({}), '需要补充来源定位');
});
