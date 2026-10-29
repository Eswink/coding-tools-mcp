# Explicit operator/device enrollment

These are local commands, not HTTP administration endpoints. They do not approve a conversation, select a workspace, create OAuth authority or enable execution. Use only an operator-reviewed identity/configuration and protected document channels. No deployment or production credential action is implied by installing this software.

## Preconditions

Run existing `coding-tools-gateway migrate`, `provision-owner`, and `register-client` with the reviewed gateway configuration and protected service secrets. Existing commands never take secret values as arguments. Configure a supported database and protected service account separately.

## Device-local key

On the device, `coding-tools-agent generate-key --output-file /absolute/private/key.json` creates a new owner-only PKCS8 JSON document. The parent directory must already exist, be owned by the current user and not writable by another user. Existing destinations, symlinks and unsafe parents are refused. No parent directories or existing keys are repaired or overwritten.

The private key stays on that device. Do not upload or send it to the gateway. Import the key into the native desktop only through the existing local protected configuration interface.

## Invitation, proof and redemption

1. Gateway operator: `coding-tools-gateway invite-device --config /absolute/gateway.json --secrets-file /absolute/service-secrets.json --output-file /absolute/private/invitation.json`
2. Transfer that five-minute, single-use invitation to the intended device through an authorized protected channel. Invitations are credentials, not log material.
3. Independently pin the reviewed gateway identity on the device as a public JSON document with exactly `origin`, `prefix`, `connector`. Do not automatically trust identity values in a received invitation.
4. Device: `coding-tools-agent prove-enrollment --config /absolute/pinned-identity.json --input-file /absolute/private/invitation.json --key-file /absolute/private/key.json --output-file /absolute/private/proof.json`
5. Transfer only the proof document back to the gateway operator. It contains the invitation token, public key and domain-separated signature, never the private key.
6. Gateway: `coding-tools-gateway redeem-device --config /absolute/gateway.json --secrets-file /absolute/service-secrets.json --input-file /absolute/private/proof.json --output-file /absolute/private/connection.json`
7. The result is the existing version1 native `ConnectionConfig`, with top-level `device`, `device_epoch`, `public_key`, immutable gateway identity and initial `authority_epoch`. This is configuration only. Transfer the public configuration to the intended device for local import; keep its private key local.
8. Select explicitly: `coding-tools-control-gateway select-device --config /absolute/gateway.json --secrets-file /absolute/service-secrets.json --device DEVICE_UUID`. Existing different selections cannot be overwritten. Existing desktop workspace selection and native conversation approval remain separate required actions.

The legacy recovery-only Agent CLI additionally needs its local `revision_file`, optional reviewed `ca_der_file`, and bounded `run_seconds`. Build that AgentConfig from the public connection identity, removing the native `version` field and adding those device-local paths. This recovery client cannot execute tools or manufacture a local grant.

## Portable nonterminal stream mode

Every output document may instead use explicit `--output-stdout`; it refuses an interactive terminal. Treat stdout as a credential document channel, capture it directly into protected memory/storage, and do not tee it into CI or terminal logs. Diagnostic stderr contains fixed operation/error labels only. `--secrets-stdin`, `--key-stdin` and `--input-stdin` each require a nonterminal stream; two stdin consumers are refused.

On Windows, credential file read/write is deliberately rejected until native ACL validation is available. The supported portable flow uses pipes and the existing local encrypted desktop import:

- Generate key with `generate-key --output-stdout`; hold the result in device-local protected memory
- Generate invitation with `invite-device --config PUBLIC_GATEWAY_CONFIG --secrets-stdin --output-stdout`
- Prove with `prove-enrollment --config PUBLIC_PINNED_IDENTITY --bundle-stdin --output-stdout`. The bounded JSON input shape is `{"invitation": INVITATION_DOCUMENT, "key": {"pkcs8": DEVICE_LOCAL_KEY}}`
- Redeem with `redeem-device --config PUBLIC_GATEWAY_CONFIG --bundle-stdin --output-stdout`. The bounded JSON input shape is `{"secrets": {"database_url": OPERATOR_DSN, "identity_key": OPERATOR_KEY}, "proof": PROOF_DOCUMENT}`

Only the proof moves between device and operator; the device key is never part of the gateway bundle. Public config-file integrity on Windows remains the local operator's responsibility, matching existing GatewayConfig behavior. Stream support is not a claim of Windows credential-file ACL enforcement or Windows process sandbox acceptance.

## Revocation, failure and rollback

`coding-tools-gateway revoke-device --config PUBLIC_GATEWAY_CONFIG --secrets-stdin --device DEVICE_UUID` revokes the enrolled device. Revocation fences its authentication and does not transfer exclusive workspace ownership or confirm local drain.

A failed output can leave an issued/consumed record or an empty create-new output file. Never automatically replay redemption or truncate/recreate output. Inspect the local outcome; explicitly revoke an unusable enrollment and issue a new invitation when necessary. Invalid proof is checked before consumption. Expired and consumed invitations cannot be revived. Database restart preserves consumption and revocation.

Rollback removes only these additive CLI paths. Preserve all device records, durable authority, migrations, revocations and no-replay journals. No reset, token revival or automatic owner replacement.

## Automated evidence

`cargo test --manifest-path services/cloud-gateway/Cargo.toml --test enrollment_contracts` covers portable command and protected-output contracts. `run_enrollment_process.py --pg-bin PG_BIN --bin-dir BIN_DIR` executes actual shipped commands against disposable PostgreSQL. `run_agent_process.py` now bootstraps via those commands, retaining its real TLS/WebSocket/restart/revocation assertions. Physical workstations, VPS and real ChatGPT require their separate deferred observations.
