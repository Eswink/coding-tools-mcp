//! Bounded pending-authorization round trips. These wire types are NOT grants.
use crate::{
    canonical::digest_json, execution::PeerBinding, grant::LOCAL_SCOPES, ProtocolError, Result,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;
pub const APPROVAL_CAPACITY: usize = 2;
pub const MAX_APPROVAL_BYTES: usize = 4096;
pub const MAX_APPROVAL_SECONDS: i64 = 8;

#[derive(Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Debug)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalMethod {
    Status,
    Request,
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalBinding {
    pub request_id: Uuid,
    pub peer: PeerBinding,
    pub conversation: String,
    pub method: ApprovalMethod,
    pub arguments_hash: [u8; 32],
    pub deadline: i64,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalRequest {
    pub binding: ApprovalBinding,
    pub arguments: Value,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalReply {
    pub binding: ApprovalBinding,
    pub result: Value,
}
impl ApprovalRequest {
    pub fn new(
        peer: PeerBinding,
        conversation: String,
        method: ApprovalMethod,
        arguments: Value,
        request_id: Uuid,
        deadline: i64,
    ) -> Result<Self> {
        let hash = digest_json(&arguments, MAX_APPROVAL_BYTES)?;
        let value = Self {
            binding: ApprovalBinding {
                request_id,
                peer,
                conversation,
                method,
                arguments_hash: hash,
                deadline,
            },
            arguments,
        };
        value.validate_at(&value.binding.peer, deadline - MAX_APPROVAL_SECONDS)?;
        Ok(value)
    }
    pub fn validate_at(&self, peer: &PeerBinding, now: i64) -> Result<()> {
        self.binding.validate_at(peer, now)?;
        validate_arguments(self.binding.method, &self.arguments)?;
        if digest_json(&self.arguments, MAX_APPROVAL_BYTES)? != self.binding.arguments_hash {
            return Err(ProtocolError::InvalidProof);
        }
        Ok(())
    }
}
impl ApprovalBinding {
    pub fn validate_at(&self, peer: &PeerBinding, now: i64) -> Result<()> {
        self.peer.validate()?;
        if &self.peer != peer
            || self.request_id.is_nil()
            || !crate::crypto::valid_digest(&self.conversation)
            || now < 0
            || self.deadline <= now
            || self
                .deadline
                .checked_sub(now)
                .is_none_or(|n| n > MAX_APPROVAL_SECONDS)
        {
            return Err(ProtocolError::InvalidProof);
        }
        Ok(())
    }
}
impl ApprovalReply {
    pub fn validate_for(&self, binding: &ApprovalBinding, now: i64) -> Result<()> {
        self.binding.validate_at(&binding.peer, now)?;
        if &self.binding != binding || !self.result.is_object() || !self.result["ok"].is_boolean() {
            return Err(ProtocolError::InvalidProof);
        }
        digest_json(&self.result, MAX_APPROVAL_BYTES)?;
        Ok(())
    }
}
pub fn validate_arguments(method: ApprovalMethod, args: &Value) -> Result<()> {
    let obj = args.as_object().ok_or(ProtocolError::InvalidRequest)?;
    if method == ApprovalMethod::Status {
        if !obj.is_empty() {
            return Err(ProtocolError::InvalidRequest);
        }
    } else {
        if obj.keys().any(|k| k != "scopes") {
            return Err(ProtocolError::InvalidRequest);
        }
        if let Some(v) = obj.get("scopes") {
            let scopes = v
                .as_array()
                .filter(|a| !a.is_empty() && a.len() <= LOCAL_SCOPES.len())
                .ok_or(ProtocolError::InvalidRequest)?;
            if scopes
                .iter()
                .any(|v| v.as_str().is_none_or(|s| !LOCAL_SCOPES.contains(&s)))
                || scopes
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<std::collections::BTreeSet<_>>()
                    .len()
                    != scopes.len()
            {
                return Err(ProtocolError::InvalidRequest);
            }
        }
    }
    Ok(())
}
macro_rules! redacted_debug {
    ($($t:ty),+) => {$(
        impl std::fmt::Debug for $t {
            fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {
                f.write_str(concat!(stringify!($t),"([REDACTED])"))
            }
        }
    )+}
}
redacted_debug!(ApprovalBinding, ApprovalRequest, ApprovalReply);
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn peer() -> PeerBinding {
        PeerBinding {
            connector: Uuid::new_v4(),
            device: Uuid::new_v4(),
            device_epoch: 1,
            gateway_boot: Uuid::new_v4(),
            channel_session: Uuid::new_v4(),
            channel_generation: 1,
        }
    }
    fn request() -> ApprovalRequest {
        use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
        ApprovalRequest::new(
            peer(),
            URL_SAFE_NO_PAD.encode([4; 32]),
            ApprovalMethod::Request,
            json!({"scopes":["files.read"]}),
            Uuid::new_v4(),
            108,
        )
        .unwrap()
    }
    #[test]
    fn shape_rejects_native_authority_fields_and_conditional_commands() {
        for args in [
            json!({"approve":true}),
            json!({"scopes":["files.read"],"workspace":"/"}),
            json!({"scopes":["files.read","files.read"]}),
            json!({"scopes":["admin"]}),
            json!({"scopes":[]}),
        ] {
            assert!(validate_arguments(ApprovalMethod::Request, &args).is_err());
        }
        assert!(
            validate_arguments(ApprovalMethod::Status, &json!({"scopes":["files.read"]})).is_err()
        );
    }
    #[test]
    fn strict_binding_covers_peer_deadline_method_and_canonical_arguments() {
        let r = request();
        r.validate_at(&r.binding.peer, 100).unwrap();
        assert!(r.validate_at(&r.binding.peer, 108).is_err());
        assert!(r.validate_at(&r.binding.peer, 99).is_err());
        assert!(r.validate_at(&peer(), 100).is_err());
        let mut changed = r.clone();
        changed.arguments = json!({"scopes":["exec.run"]});
        assert!(changed.validate_at(&r.binding.peer, 100).is_err());
    }
    #[test]
    fn reply_is_request_exact_and_never_an_execution_credential() {
        let r = request();
        let reply = ApprovalReply {
            binding: r.binding.clone(),
            result: json!({"ok":true,"authorization":{"status":"pending"}}),
        };
        reply.validate_for(&r.binding, 100).unwrap();
        let mut wrong = r.binding.clone();
        wrong.request_id = Uuid::new_v4();
        assert!(reply.validate_for(&wrong, 100).is_err());
        assert!(!format!("{reply:?}").contains(&r.binding.conversation));
    }
    #[test]
    fn unknown_wire_fields_and_oversized_results_are_rejected() {
        let r = request();
        let mut value = serde_json::to_value(&r).unwrap();
        value["binding"]["grant_id"] = json!(Uuid::new_v4());
        assert!(serde_json::from_value::<ApprovalRequest>(value).is_err());
        let reply = ApprovalReply {
            binding: r.binding.clone(),
            result: json!({"ok":true,"text":"x".repeat(MAX_APPROVAL_BYTES)}),
        };
        assert!(reply.validate_for(&r.binding, 100).is_err());
    }
}
