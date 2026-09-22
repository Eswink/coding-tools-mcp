-- A single bounded control-session row. Presence is NOT workspace authority.
-- Intentionally no FK/cascade to durable authority: restoring that table must
-- not depend on ephemeral presence. Every operation locks/checks projection,
-- selected device and gateway boot; activation always invalidates presence.
CREATE TABLE ctm_agent_channel (
    connector uuid PRIMARY KEY,
    gateway_boot uuid NOT NULL,
    generation bigint NOT NULL DEFAULT 0 CHECK (generation >= 0),
    session uuid,
    device uuid,
    device_epoch bigint,
    connected boolean NOT NULL DEFAULT false,
    last_seq bigint NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    lease_until bigint NOT NULL DEFAULT 0,
    absolute_until bigint NOT NULL DEFAULT 0
);
