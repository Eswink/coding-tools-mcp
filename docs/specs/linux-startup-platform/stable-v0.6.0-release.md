# Stable v0.6.0 release record

Status: **RELEASED / LATEST VERIFIED**

## Release identity

- Release tag: `v0.6.0`
- GitHub release ID: `389313566`
- Accepted candidate: `0.6.0-rc.4`
- Accepted product source: `afcaae34e700e468b08eb97187ef9b12a0be1388`
- Promotion mode: `metadata-only-exact-accepted-bytes`
- Stable publish workflow run: `34996754993` — passed
- Stable promotion receipt artifact: `10407333161`
- Receipt artifact digest: `sha256:a048b80e5cb6d7f96d43f9fa771e011c6161768498c89a5db0e02ba5073b22db`
- Published as GitHub Latest: verified
- Anonymous public downloads: verified and re-hashed

## Published product bytes

The stable release deliberately reuses the exact product bytes that passed the Round 17 automated and real-operator gates. No rebuild or product re-versioning was performed during Stable promotion.

- Ubuntu DEB: `MCP_0.6.0-rc.4_amd64.deb`
  - SHA-256: `4b9fb575897f70cef8f1271675f4dc14485db02f5339dee450d8b0e61178031f`
- Ubuntu AppImage: `MCP_0.6.0-rc.4_amd64.AppImage`
  - SHA-256: `b7a6dcf79dd096a184a4ac5f572450d8b7f8a08c7fcf2b7a9ff43f82981041d0`
- Windows NSIS: `MCP_0.6.0-rc.4_x64-setup.exe`
  - SHA-256: `a7fae3fcb16e653fa0ac27843b7ab63619b74bb089871e9217d88d75be60897c`

Because preserving exact accepted bytes is the controlling release invariant, the installers retain the embedded/package version and filenames `0.6.0-rc.4` while the GitHub Stable/Latest release tag is `v0.6.0`. The release notes and provenance files disclose this explicitly.

## Provenance

- Linux accepted run: `34976767756`
- Linux package artifact digest: `sha256:c6d18965a7872b45644d98f1a74fe8486e4309f4752693ec1d747d56f638f232`
- Windows accepted run: `34976767781`
- Windows package artifact digest: `sha256:7ec0ab609b88feedd171f504f4263a725ac28d936b1c693c296e0935401ceb87`
- Real affected Ubuntu 24.04 operator gate: passed for both exact DEB and AppImage bytes

The release also publishes `SHA256SUMS_v0.6.0.txt`, `Release-scope_v0.6.0.json`, `Verification_v0.6.0.md`, `Linux-source_v0.6.0.json`, and `Windows-source_v0.6.0.json`.

## Release-control incident

The first release-control workflow run `34996605476` failed before artifact download or release creation because `rc_version_gate.py` was invoked from the wrong working directory and could not find `package.json`. No release or product bytes were published by that failed attempt. The corrected workflow run `34996754993` fixed only promotion plumbing, then completed all provenance checks, exact-byte checks, draft verification, Stable/Latest publication, and anonymous public-download verification successfully.

## Security and future-version boundary

The published bytes preserve the accepted fail-closed behavior: no plaintext fallback, no raw master-key file, no replacement key for existing ciphertext, no silent secure-storage downgrade, and no background MCP/Actions/tunnel/chat-approval startup before secure configuration is Ready.

`v0.5.0` remains immutable. Any future product-byte change is outside the accepted RC4 evidence and must use `0.6.0-rc.5` or a later version with the required automated and real-operator validation before another Stable promotion.
