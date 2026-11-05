// C13: vendored deepmerge 4.3.1+ctm.1 (GHSA-gcqx-w48m-w2h4 guard).
// DEEPMERGE_UNDER_TEST=/abs/path/to/dist/cjs.js runs the attack/parity cases
// against another build (e.g. the upstream 4.3.1 tarball) — upstream must FAIL T1–T6.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vendored = path.join(root, "vendor-js/deepmerge/dist/cjs.js");
const require = createRequire(import.meta.url);
const target = process.env.DEEPMERGE_UNDER_TEST || vendored;
const merge = require(target);
const J = JSON.parse;

function clean(obj) {
  assert.equal(Object.getPrototypeOf(obj), Object.prototype);
  assert.equal(obj.admin, undefined);
  assert.equal(Object.prototype.admin, undefined);
}

test("T1 null placeholder + nested __proto__", () => {
  clean(merge({ session: null }, J('{"session":{"__proto__":{"admin":true}}}')).session);
});
test("T2 Object.create(null) target", () => {
  clean(merge(Object.create(null), J('{"__proto__":{"admin":true}}')));
});
test("T3 target own __proto__ key (target-copy loop)", () => {
  clean(merge(J('{"__proto__":{"admin":true}}'), {}));
});
test("T4 primitive placeholder", () => {
  clean(merge({ s: 1 }, J('{"s":{"__proto__":{"admin":true}}}')).s);
});
test("T5 merge.all with null placeholder", () => {
  clean(merge.all([{ a: null }, J('{"a":{"__proto__":{"admin":true}}}')]).a);
});
test("T6 constructor/prototype keys dropped", () => {
  const r = merge({ x: null }, J('{"x":{"constructor":{"prototype":{"admin":true}},"prototype":{"admin":true}}}')).x;
  clean(r);
  assert.equal(Object.hasOwn(r, "constructor"), false);
  assert.equal(Object.hasOwn(r, "prototype"), false);
  const t = merge(J('{"constructor":{"admin":true},"prototype":1}'), { ok: 1 });
  assert.deepEqual(Object.keys(t), ["ok"]);
  clean(t);
});

test("P1 parity: nested merge + array concat", () => {
  assert.deepEqual(merge({ a: { b: 1, l: [1] }, k: "x" }, { a: { c: 2, l: [2] } }), { a: { b: 1, c: 2, l: [1, 2] }, k: "x" });
});
test("P2 parity: arrayMerge override (as vite-plugin-svelte uses)", () => {
  const arrayMerge = (_t, s) => s;
  assert.deepEqual(merge({ p: [1, 2], o: { q: [3] } }, { p: [9], o: { q: [8] } }, { arrayMerge }), { p: [9], o: { q: [8] } });
});
test("P3 parity: clone:false keeps references", () => {
  const inner = { z: 1 };
  assert.equal(merge({}, { inner }, { clone: false }).inner, inner);
  assert.notEqual(merge({}, { inner }).inner, inner);
});
test("P4 parity: symbols, null placeholder, all()", () => {
  const s = Symbol("s");
  const r = merge({ [s]: 1 }, { session: { a: 1 } });
  assert.equal(r[s], 1);
  assert.deepEqual(merge({ session: null }, { session: { a: 1 } }), { session: { a: 1 } });
  assert.deepEqual(merge.all([{ a: 1 }, { b: 2 }, { a: 3 }]), { a: 3, b: 2 });
});

test("R1 vite-plugin-svelte resolves the vendored copy", { skip: !!process.env.DEEPMERGE_UNDER_TEST }, () => {
  const vps = realpathSync(require.resolve("@sveltejs/vite-plugin-svelte/package.json", { paths: [root] }));
  const fromVps = createRequire(vps).resolve("deepmerge");
  assert.equal(realpathSync(fromVps), realpathSync(vendored));
  assert.equal(realpathSync(require.resolve("deepmerge", { paths: [root] })), realpathSync(vendored));
  assert.equal(createRequire(vps)("deepmerge/package.json").version, "4.3.1+ctm.1");
});
