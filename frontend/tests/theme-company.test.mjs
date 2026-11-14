import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeTheme, resolveTheme } from '../src/lib/theme.mjs';
import { safeReturnPath } from '../src/lib/demo-profile.mjs';
test('theme preference respects explicit mode and system fallback', () => {
  assert.equal(normalizeTheme('invalid'), 'system');
  assert.equal(resolveTheme('system', true), 'dark');
  assert.equal(resolveTheme('system', false), 'light');
  assert.equal(resolveTheme('light', true), 'light');
  assert.equal(resolveTheme('dark', false), 'dark');
});
test('login returns to safe company routes without accepting redirects', () => {
  assert.equal(safeReturnPath('/companies/002475'), '/companies/002475');
  for (const p of ['/companies/../../login', '/companies/a?next=https://evil.test', '//evil.test', '/companies/a/b', '/companies/%2f']) assert.equal(safeReturnPath(p), '/');
});
