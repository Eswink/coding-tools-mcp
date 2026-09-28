-- Durable request metadata only. No tool payloads, command output, bearer tokens or raw Host sessions.
CREATE TABLE ctm_request_ledger (
    request_id uuid PRIMARY KEY,
    connector uuid NOT NULL,
    conversation_hash bytea NOT NULL CHECK (octet_length(conversation_hash) = 32),
    scope text NOT NULL CHECK (octet_length(scope) BETWEEN 1 AND 64),
    tool_name text NOT NULL CHECK (octet_length(tool_name) BETWEEN 1 AND 128),
    arguments_hash bytea NOT NULL CHECK (octet_length(arguments_hash) = 32),
    request_class text NOT NULL CHECK (request_class IN ('read_only','mutating')),
    deadline bigint NOT NULL,
    state text NOT NULL CHECK (state IN ('not_admitted','admitted','running','completed','outcome_unknown','cancelled')),
    deny_reason text CHECK (deny_reason IS NULL OR deny_reason IN ('authorization','scope','recovery','offline','backpressure','deadline')),
    device uuid,
    device_epoch bigint,
    gateway_boot uuid,
    channel_session uuid,
    channel_generation bigint,
    grant_id uuid,
    grant_revision bigint,
    authority_epoch bigint,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    result_hash bytea CHECK (result_hash IS NULL OR octet_length(result_hash) = 32),
    result_ok boolean
);
CREATE INDEX ctm_request_ledger_active_idx
    ON ctm_request_ledger(connector, state, updated_at)
    WHERE state IN ('admitted','running','outcome_unknown');
CREATE INDEX ctm_request_ledger_terminal_idx
    ON ctm_request_ledger(connector, updated_at)
    WHERE state IN ('not_admitted','completed','cancelled');
