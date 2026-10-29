# 需求文档：device-enrollment-bootstrap
## 功能概述
Complete #39 shipped device enrollment bootstrap, using existing crypto/DB APIs and four existing binaries. Synthetic tests only; no production credentials, HTTP administration or local authority changes.
## 需求列表
### FR-1 Trusted operator enrollment
Gateway invite-device and redeem-device commands reuse create_device_invitation and redeem_device_invitation. Inputs are bounded and protected; invitations expire in five minutes and are consumed once after valid proof. Redemption does not select a device or mint grants. Revoke-device explicitly revokes only the named enrolled device and remains separate from local approval.
### FR-2 Device-local key and proof
Agent generate-key creates a new Ed25519 PKCS8 key on the device. Agent prove-enrollment signs the exact configured issuer/resource-derived connector, invitation token and public key. No private key is sent to gateway. Existing key files cannot be overwritten.
### FR-3 Protected documents and configuration
Credential documents use protected files or explicit nonterminal streams. Fixed diagnostics never echo passwords, private keys, enrollment tokens or arbitrary arguments. Output files are create-new, owner-only and symlink/hardlink/unsafe-parent rejected; Windows fails closed for unverified files and supports explicit nonterminal streams. Redemption outputs existing native ConnectionConfig version1 without granting approval; runtime AgentConfig can be constructed using local revision path and CA configuration.
### FR-4 Executable verification
From empty key/config, shipped commands generate/sign/redeem/select and connect actual WSS with disposable PostgreSQL. Wrong proof preserves invitation; different-key race has one winner; expiry/replay/restart/revoke remain fail closed. Existing OAuth/channel/projection and portable Windows/Ubuntu regressions remain required.
## 非功能需求
NFR-1 Inputs at most16KiB, key inputs4KiB; strict JSON unknown/duplicate fields rejected; no new dependencies or HTTP routes.
NFR-2 No public HTTP/MCP administration route is added; cloud/tool inputs cannot become an administrative CLI document or expand local authority. No secret appears in diagnostics. Native output config uses existing exact identity shape.
## 验收标准
- [ ] FR-1 operator commands are explicit, single-use, domain-bound and never select/approve implicitly
- [ ] FR-2 device creates and retains private key; gateway receives proof/public key only
- [ ] FR-3 protected output no-overwrite and nonterminal stream contracts pass
- [ ] FR-4 actual process/PG/WSS and portable regression evidence is exact-source
## 范围边界
Physical workstation/VPS/ChatGPT observations deferred. No deployment, persistent real access, package version or authority changes. Rollback reverts additive CLI commands, retaining all issued device/authority records and revocations.

## 依赖关系
Existing device.rs, service input/lifecycle, native config and shared Agent transport. WHEN an enrollment command runs, it SHALL preserve all local authority and fail closed for malformed or replayed proof.
