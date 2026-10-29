-- Preserve existing bounded metadata/hashes, never tool arguments or output.
-- Forgetting an already-dispatched request would allow the same ID to execute
-- again after cleanup. Retention is an intentional safety fence, not a queue.
ALTER TABLE ctm_request_ledger
    ADD COLUMN dispatch_claimed boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT ctm_dispatch_claimed_state CHECK (
        NOT dispatch_claimed OR state IN ('running','completed','outcome_unknown')
    );

-- Retain fences even if an older cleanup implementation is invoked. Explicit
-- database-owner destructive restore/TRUNCATE is outside this protection.
CREATE FUNCTION ctm_preserve_dispatch_tombstone() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.dispatch_claimed THEN RETURN NULL; END IF;
        RETURN OLD;
    END IF;
    IF OLD.dispatch_claimed AND (
        NOT NEW.dispatch_claimed OR
        ROW(NEW.request_id, NEW.connector, NEW.conversation_hash, NEW.scope,
            NEW.tool_name, NEW.arguments_hash, NEW.request_class, NEW.deadline,
            NEW.device, NEW.device_epoch, NEW.gateway_boot, NEW.channel_session,
            NEW.channel_generation, NEW.grant_id, NEW.grant_revision,
            NEW.authority_epoch, NEW.created_at)
        IS DISTINCT FROM
        ROW(OLD.request_id, OLD.connector, OLD.conversation_hash, OLD.scope,
            OLD.tool_name, OLD.arguments_hash, OLD.request_class, OLD.deadline,
            OLD.device, OLD.device_epoch, OLD.gateway_boot, OLD.channel_session,
            OLD.channel_generation, OLD.grant_id, OLD.grant_revision,
            OLD.authority_epoch, OLD.created_at)
    ) THEN
        RAISE EXCEPTION 'dispatch identity is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ctm_dispatch_tombstone_guard
BEFORE UPDATE OR DELETE ON ctm_request_ledger
FOR EACH ROW EXECUTE FUNCTION ctm_preserve_dispatch_tombstone();
