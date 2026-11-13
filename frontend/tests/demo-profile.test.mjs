import test from 'node:test';
import assert from 'node:assert/strict';
import { demoCredentialsValid, normalizeProfile, readProfile, safeReturnPath } from '../src/lib/demo-profile.mjs';

test('demo accepts arbitrary nonempty credentials and rejects whitespace only', () => {
  assert.equal(demoCredentialsValid('任意账号', 'anything'), true);
  assert.equal(demoCredentialsValid('a', '1'), true);
  assert.equal(demoCredentialsValid(' ', '1'), false);
  assert.equal(demoCredentialsValid('a', ''), false);
});
test('profile serialization contains only nickname and approved image data', () => {
  assert.deepEqual(normalizeProfile({ nickname: '  小林  ', avatar: 'data:image/png;base64,YQ==', password: 'secret', account: 'admin' }), { nickname: '小林', avatar: 'data:image/png;base64,YQ==' });
});
test('corrupt storage and invalid nickname recover to defaults', () => {
  assert.deepEqual(readProfile('{bad'), { nickname: '研究员', avatar: '' });
  assert.equal(normalizeProfile({ nickname: 'x'.repeat(25) }).nickname, '研究员');
  assert.equal(normalizeProfile({ nickname: '😀'.repeat(24) }).nickname, '😀'.repeat(24));
});
test('avatar rejects external URLs, SVG, malformed and oversized data', () => {
  for (const avatar of ['https://example.com/a.png', 'data:image/svg+xml;base64,YQ==', 'data:image/png;base64,<>', 'data:image/png;base64,' + 'A'.repeat(200000)]) assert.equal(normalizeProfile({ avatar }).avatar, '');
});
test('return path cannot redirect away from known workbench routes', () => {
  for (const path of ['https://evil.test', '//evil.test', '/login', null, '/compare?next=https://evil.test']) assert.equal(safeReturnPath(path), '/');
  assert.equal(safeReturnPath('/compare'), '/compare');
  assert.equal(safeReturnPath('/settings'), '/settings');
});
