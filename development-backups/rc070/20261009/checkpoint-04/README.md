# RC 0.7.0 source checkpoint 04

Two immutable source families are archived independently. `.source` suffixes preserve original UTF8 bytes as inert backup artifacts. Restore filenames by removing only this suffix and use each family's source manifest for original Git modes. This backup commit does not modify any active RC source or qualify release/installation.

## NEW28 source-only

Start with a full public clone at D6 `c60f9667fa8431e27fabbc497c19b4abfef5b965`. Apply `new28-source-only/source.patch` with `git apply --check` then `git apply --index`; or overlay the exact28 source files and stage them. Verify `git write-tree` is `2ed198deef3b6386df377798a6bdf03a24dfd21d` with1867 source entries and every SOURCE-TREE identity. Do not first apply the old18 patch: this is a complete D6-based28-path delta. Necessary488 were loaded, not executed at this freeze; all five actual installed slots/nativeCI remain NOT_RUN. Native privileged issuer and lost22 implementation remain absent/BLOCKED. Historical component passes are not current qualification.

## Windows foundation33 alternative

Start independently at D6 and restore the exact73 `.source` files from checkpoint-01/windows-recovered73 using that family's source modes. Stage them and verify baseline partial tree `d4bd2d9813176afd83270ba39971d3204e350105` with1913 entries. **Do not apply checkpoint-02 Stage11** on this route. Apply this family's source.patch with `git apply --check` then `git apply --index`, or overlay its33 files. Verify partial physical tree `295ee8a8efd6c131dad098e8c7b628f7482e732a` with1943 entries and all partial SOURCE-TREE identities. This is newly authored source, not recovery of the historical40 missing originals. Six output Rust and four transfer Go paths remain absent; actual boot producer is missing. Types/tests/positive native execution/production VM/GuestIO/output issuer and release/install gates remain BLOCKED or NOT_RUN. Do not merge this alternative with frozen Stage11 and borrow either tree identity.

Both source overlays and both patches were independently reconstructed through private native Git indices and matched these exact trees before backup. This is source integrity checking, not runtime testing. Raw reports, native index files, raw commit bytes, TLS material, credentials, runtime pins, environment/config files and active work snapshots are excluded. Earlier checkpoints stay immutable. PR98 cancellation and Issue86 snapshot pause remain unchanged.

## Current known NEW28 v1 blocker

**NEW28 v1 is SOURCE_ONLY / ORDERING_BLOCKED.** Root and the author identified that its content route performs parent admission before full current-source admission, violating the required current-fullsource-first contract. The original28 source bytes, D6 patch and tree remain archived unchanged. A new immutable v2 addresses only this finite ordering problem; it is not included here and has no executed488/nativeCI/five-install qualification. Loaded488 at v1 freeze is an inventory observation, not a pass and not removal of this known blocker.
