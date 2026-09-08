use serde_json::{json, Value};

pub fn input_schema(name: &str) -> Option<Value> {
    Some(match name {
        "start_exec_task" => json!({
            "type": "object", "additionalProperties": false,
            "required": ["cmd", "request_id"],
            "properties": {
                "cmd": {"type": "string", "minLength": 1, "maxLength": 4000},
                "request_id": {"type": "string", "minLength": 1, "maxLength": 128,
                    "description": "Create one key per logical command; reuse EXACTLY the same key and command after a lost response. Deduplication lasts one hour after completion within this service instance."},
                "workdir": {"type": "string", "default": "."},
                "timeout_ms": {"type": "integer", "minimum": 1, "maximum": 600000, "default": 600000,
                    "description": "Process execution budget, NOT HTTP response wait. Does not remove the existing 10-minute policy limit."},
                "confirm": {"type": "boolean", "default": false},
                "filesystem_scope": {"type": "string", "enum": ["workspace"], "default": "workspace"},
                "reason": {"type": "string", "default": ""}
            }
        }),
        "get_exec_task" => json!({
            "type": "object", "additionalProperties": false, "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
                "stdout_cursor": {"type": "integer", "minimum": 0, "default": 0},
                "stderr_cursor": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 16384, "default": 4096,
                    "description": "Byte budget per stream. Follow each stream's next_cursor; dropped_bytes reports an expired ring-buffer prefix."}
            }
        }),
        "list_exec_tasks" => json!({
            "type": "object", "additionalProperties": false,
            "properties": {"request_id": {"type": "string", "minLength": 1, "maxLength": 128,
                "description": "Find an accepted command when the initial job_id response was lost."}}
        }),
        "cancel_exec_task" => json!({
            "type": "object", "additionalProperties": false, "required": ["job_id"],
            "properties": {"job_id": {"type": "string", "minLength": 1}}
        }),
        _ => return None,
    })
}
