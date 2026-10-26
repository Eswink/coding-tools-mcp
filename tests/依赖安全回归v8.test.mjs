/** Exercise cookie v2 API (kit3 transitive) and its validation boundary. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { parseCookie, stringifyCookie, stringifySetCookie } from 'cookie';

test('cookie正常编解码与中文内容保持兼容', () => {
  assert.equal(parseCookie(stringifyCookie({ session: '中文 & value' })).session, '中文 & value');
});
test('cookie常用安全属性保持兼容', () => {
  const value = stringifySetCookie({ name: 'sid', value: 'fixture', httpOnly: true, secure: true, sameSite: 'lax', path: '/' });
  for (const attribute of ['HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/']) assert.ok(value.includes(attribute));
});
for (const [name, invoke] of [
  ['name', () => stringifySetCookie({ name: 'bad;cookie', value: 'value' })],
  ['domain', () => stringifySetCookie({ name: 'sid', value: 'value', domain: 'example.com;evil=1' })],
  ['path', () => stringifySetCookie({ name: 'sid', value: 'value', path: '/;evil=1' })],
]) test(`cookie拒绝${name}字段越界注入`, () => assert.throws(invoke, TypeError));
