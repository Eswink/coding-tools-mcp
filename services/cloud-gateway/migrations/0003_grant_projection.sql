-- Minimal local-authority projection only. Not a command queue or execution ledger.
CREATE TABLE ctm_grant_projection (
 connector uuid PRIMARY KEY,
 device uuid REFERENCES ctm_devices(id),
 gateway_boot uuid NOT NULL,
 revision bigint NOT NULL DEFAULT 0 CHECK(revision >= 0),
 revoked_through_epoch bigint NOT NULL DEFAULT 0 CHECK(revoked_through_epoch >= 0),
 state_text text CHECK(octet_length(state_text) <= 4096),
 snapshot_until bigint NOT NULL DEFAULT 0,
 snapshot_device_epoch bigint NOT NULL DEFAULT 0 CHECK(snapshot_device_epoch >= 0),
 last_digest bytea CHECK(last_digest IS NULL OR octet_length(last_digest) = 32),
 reconciled boolean NOT NULL DEFAULT false,
 challenge_hash bytea CHECK(challenge_hash IS NULL OR octet_length(challenge_hash) = 32),
 challenge_until bigint NOT NULL DEFAULT 0
);
