-- Additive, isolated database only. No source, command, output or raw credential columns.
CREATE TABLE ctm_identity_config (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 issuer text NOT NULL, resource text NOT NULL, key_check bytea NOT NULL
);
CREATE TABLE ctm_clients (
 client_id text PRIMARY KEY, redirect_uri text NOT NULL,
 secret_hash bytea, disabled boolean NOT NULL DEFAULT false
);
CREATE TABLE ctm_families (
 id uuid PRIMARY KEY, client_id text NOT NULL REFERENCES ctm_clients(client_id),
 subject uuid NOT NULL, resource text NOT NULL, expires_at bigint NOT NULL,
 revoked boolean NOT NULL DEFAULT false
);
CREATE TABLE ctm_codes (
 code_hash bytea PRIMARY KEY, family_id uuid NOT NULL REFERENCES ctm_families(id),
 redirect_uri text NOT NULL, pkce text NOT NULL,
 expires_at bigint NOT NULL, redeemed boolean NOT NULL DEFAULT false
);
CREATE TABLE ctm_refresh_tokens (
 token_hash bytea PRIMARY KEY, family_id uuid NOT NULL REFERENCES ctm_families(id),
 consumed boolean NOT NULL DEFAULT false
);
CREATE TABLE ctm_access_tokens (
 token_hash bytea PRIMARY KEY, family_id uuid NOT NULL REFERENCES ctm_families(id), expires_at bigint NOT NULL
);
CREATE INDEX ctm_refresh_family_idx ON ctm_refresh_tokens(family_id);
CREATE INDEX ctm_access_family_idx ON ctm_access_tokens(family_id);
CREATE TABLE ctm_enrollments (
 token_hash bytea PRIMARY KEY, id uuid UNIQUE NOT NULL, connector uuid NOT NULL,
 expires_at bigint NOT NULL, consumed boolean NOT NULL DEFAULT false
);
CREATE TABLE ctm_devices (
 id uuid PRIMARY KEY, enrollment_id uuid UNIQUE NOT NULL REFERENCES ctm_enrollments(id),
 connector uuid NOT NULL, public_key bytea NOT NULL CHECK(octet_length(public_key)=32),
 revoked boolean NOT NULL DEFAULT false, epoch bigint NOT NULL DEFAULT 1 CHECK(epoch > 0)
);
