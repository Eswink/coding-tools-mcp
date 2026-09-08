/** Exercise the overridden cookie API and its patched validation boundary. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { parse, serialize } from 'cookie';

test('cookie正常编解码与中文内容保持兼容', () => {
  assert.equal(parse(serialize('session', '中文 & value')).session, '中文 & value');
});
test('cookie常用安全属性保持兼容', () => {
  const value = serialize('sid', 'fixture', { httpOnly: true, secure: true, sameSite: 'lax', path: '/' });
  for (const attribute of ['HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/']) assert.ok(value.includes(attribute));
});
for (const [name, invoke] of [
  ['name', () => serialize('bad;cookie', 'value')],
  ['domain', () => serialize('sid', 'value', { domain: 'example.com;evil=1' })],
  ['path', () => serialize('sid', 'value', { path: '/;evil=1' })],
]) test(`cookie拒绝${name}字段越界注入`, () => assert.throws(invoke, TypeError));
