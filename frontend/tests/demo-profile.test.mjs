import test from 'node:test';
import assert from 'node:assert/strict';
import {safeReturnPath} from '../src/lib/demo-profile.mjs';
test('return path cannot redirect away from known workbench routes', () => {
  for (const path of ['https://evil.test', '//evil.test', '/login', null, '/compare?next=https://evil.test']) assert.equal(safeReturnPath(path), '/');
  assert.equal(safeReturnPath('/compare'), '/compare');
  assert.equal(safeReturnPath('/settings'), '/settings');
});
