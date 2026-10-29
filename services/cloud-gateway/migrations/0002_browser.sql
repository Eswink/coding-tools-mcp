-- Browser state only; independent of local chat grants and Agent presence.
CREATE TABLE ctm_owner (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 subject uuid NOT NULL UNIQUE, password_phc text NOT NULL,
 epoch bigint NOT NULL DEFAULT 1 CHECK(epoch > 0),
 failures integer NOT NULL DEFAULT 0 CHECK(failures >= 0),
 locked_until bigint NOT NULL DEFAULT 0
);
CREATE TABLE ctm_browser_flows (
 session_hash bytea PRIMARY KEY CHECK(octet_length(session_hash)=32),
 csrf_hash bytea NOT NULL CHECK(octet_length(csrf_hash)=32),
 request_cipher bytea NOT NULL,
 owner_epoch bigint NOT NULL CHECK(owner_epoch > 0),
 authenticated boolean NOT NULL DEFAULT false,
 expires_at bigint NOT NULL
);
CREATE INDEX ctm_browser_expiry_idx ON ctm_browser_flows(expires_at);
