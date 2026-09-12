# Iteration 13: exact-source native acceptance

Base: `aadfbb05842214880dee25d7234538178c731fc7`, tree `3800e3438da0eefdfbc476eb0d57c79300279dd4`.

The repaired offline reviewer artifact from run `34684140665` was downloaded and verified against its published outer SHA-256 and inner archive SHA-256. All 22 locked package directories were validated. The temporary Svelte compiler adapter was removed completely. The repository's complete frontend runner now passes **119/119** with the default official ESM compiler and real cookie dependency. This closes the offline reproduction defect, not native acceptance.

## Order and safety boundaries

Before any new installer build, prepare patch version 0.3.2 in the five existing files/six application fields using the repository's already tested version helper. Preserve every dependency and unrelated file. The preparation follows the existing version-workflow pattern: fixed repository/repair branch, immutable checkout, required repaired ancestor, clean source, five-file scope guard, remote-head equality check, ordinary non-force fast-forward push, and version/source receipt plus hashed source archive. Write permission exists only in that preparation job. It cannot tag, merge or publish. Version preparation is not a release.

After downloading and independently verifying the resulting versioned source, add a separate native acceptance entry that reuses the existing strict validation and installer workflows with `windows_local: false`. Required installed combinations are Ubuntu 22.04/24.04 DEB and AppImage, plus Windows NSIS. Do not weaken provenance, approval/isolation tests, or evidence validators; do not add macOS. Any failure is investigated before a merge/release decision. The final public release must still be built from the exact resulting main commit and rechecked after publication.

Manual workflow impact review replaces unavailable graph tools as documented in iterations 10–12. HIGH risk applies to scoped branch writes and package provenance; no production authentication code changes are introduced here. Version helper tests and five new source contracts are the local gate. CI, prepared-source verification, and the native matrix are pending until actual results exist.

Scoped self-review: **93/100**, preparation candidate only. No approval of native acceptance or release is implied.
