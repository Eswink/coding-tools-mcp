# deepmerge 4.3.1+ctm.1 — vendored, narrow patch

Unmodified official npm tarball `deepmerge-4.3.1.tgz`
(integrity `sha512-3sUqbMEc77XqpdNO7FRyRog+eW3ph+GYCbj+rK+uYyRMuwsVy0rMiVtPn+QJlKFvWP/1PYpapqYn0Me2knFn+A==`)
plus one local guard for GHSA-gcqx-w48m-w2h4 (prototype poisoning of returned
objects; no upstream fix exists). `license.txt` (MIT, Copyright (c) 2012 James
Halliday, Josh Duff, and other contributors) is kept verbatim.

- **Modified:** `dist/cjs.js` (the file Node loads, `main`): `keyIsForbidden()` skips
  `__proto__`, `constructor`, `prototype` in **both** the target-copy loop and the
  source loop of `mergeObject`. Diff: `ctm.1.patch`.
  **Behavior change:** ordinary own keys literally named `constructor` or `prototype`
  (not only `__proto__`) are now dropped from merge results too.
  `package.json` reduced to name/version/description/license/main/types/engines
  (no scripts, devDependencies or dependencies) so npm installs nothing extra.
- **Removed:** `index.js` (source entry, requires `is-mergeable-object` which is not
  installed), `dist/umd.js` (unpatched browser bundle), `rollup.config.js`. None is loaded.
- **Kept verbatim:** `license.txt`, `readme.md`, `changelog.md`, `index.d.ts`.
- `provenance.json` records upstream and vendored per-file sha256, patch and license hashes.

Wiring: root `devDependencies.deepmerge = "file:vendor-js/deepmerge"` +
`overrides.deepmerge = "$deepmerge"`. The lockfile entry is a `link` with **no
integrity**; content is pinned only by the git tree.

**Audit scope:** npm audit does not audit `file:` dependencies, so a zero audit is
**not** evidence of the fix — deepmerge is vendored, outside npm audit scope.
Evidence is `tests/deepmerge-vendor.test.mjs` (T1–T6 fail on upstream 4.3.1, pass
here; P1–P4 parity; R1 proves vite-plugin-svelte resolves this copy) and upstream's
own suite. Recheck GHSA-gcqx-w48m-w2h4 `withdrawn_at` at every RC.

**Removal condition:** drop this directory and the root devDependency/override when
the GHSA is withdrawn or upstream ships a fixed release accepted by vite-plugin-svelte.
