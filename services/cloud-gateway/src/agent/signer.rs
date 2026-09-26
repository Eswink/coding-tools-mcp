use super::{wire::SnapshotChallenge, AgentConfig, AgentError, Result};
use crate::{
    channel::{connect_message, ConnectChallenge, ConnectClaims, SignedPayload, AUTH_SECONDS},
    crypto::valid_digest,
    projection::{projection_message, ExecutionState, ProjectionClaims, ProjectionPhase},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde::Deserialize;
use uuid::Uuid;
use zeroize::{Zeroize, Zeroizing};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct KeyInput {
    pkcs8: String,
}
impl Drop for KeyInput {
    fn drop(&mut self) {
        self.pkcs8.zeroize();
    }
}
// Not public; no method accepts arbitrary bytes to sign on behalf of a peer.
pub(super) struct RecoverySigner {
    key: Ed25519KeyPair,
    cfg: AgentConfig,
}
impl RecoverySigner {
    pub(super) fn from_input(cfg: AgentConfig, input: &[u8]) -> Result<Self> {
        if input.is_empty() || input.len() > 4096 {
            return Err(AgentError::Credentials);
        }
        let raw: KeyInput = serde_json::from_slice(input).map_err(|_| AgentError::Credentials)?;
        let key_bytes = Zeroizing::new(
            URL_SAFE_NO_PAD
                .decode(&raw.pkcs8)
                .map_err(|_| AgentError::Credentials)?,
        );
        let key = Ed25519KeyPair::from_pkcs8(&key_bytes).map_err(|_| AgentError::Credentials)?;
        if key.public_key().as_ref() != cfg.key_bytes()?.as_slice() {
            return Err(AgentError::Credentials);
        }
        Ok(Self { key, cfg })
    }
    pub(super) fn connect(&self, c: ConnectChallenge, at: i64) -> Result<(Uuid, SignedPayload)> {
        let id = self.cfg.identity()?;
        if c.version != 1
            || c.issuer != id.issuer()
            || c.resource != id.resource()
            || c.connector != id.connector()
            || c.gateway_boot.is_nil()
            || c.attempt.is_nil()
            || !valid_digest(&c.nonce)
            || c.issued_at < 0
            || c.issued_at > at
            || c.expires_at <= at
            || c.expires_at.checked_sub(c.issued_at) != Some(AUTH_SECONDS)
        {
            return Err(AgentError::Protocol);
        }
        let boot = c.gateway_boot;
        let claims = ConnectClaims {
            version: 1,
            issuer: id.issuer(),
            resource: id.resource(),
            connector: id.connector(),
            device: self.cfg.device,
            device_epoch: self.cfg.device_epoch,
            gateway_boot: boot,
            attempt: c.attempt,
            nonce: c.nonce,
            issued_at: c.issued_at,
            expires_at: c.expires_at,
        };
        let payload = serde_json::to_vec(&claims).map_err(|_| AgentError::Protocol)?;
        let msg = connect_message(&payload).map_err(|_| AgentError::Protocol)?;
        Ok((boot, self.proof(payload, &msg)))
    }
    pub(super) fn snapshot(
        &self,
        c: SnapshotChallenge,
        expected_boot: Uuid,
        revision: i64,
        at: i64,
    ) -> Result<SignedPayload> {
        if c.boot != expected_boot
            || c.boot.is_nil()
            || !valid_digest(&c.nonce)
            || revision <= 0
            || at < 0
            || c.expires_at <= at
            || c.expires_at > at + 60
            || c.ceiling <= at
            || c.ceiling > c.expires_at
            || c.ceiling > at + 30
        {
            return Err(AgentError::Protocol);
        }
        let id = self.cfg.identity()?;
        // Authority is constant/local. No server-supplied grant, scope or phase is copied.
        let claims = ProjectionClaims {
            version: 1,
            issuer: id.issuer(),
            resource: id.resource(),
            connector: id.connector(),
            device: self.cfg.device,
            device_epoch: self.cfg.device_epoch,
            gateway_boot: expected_boot,
            challenge: c.nonce,
            revision,
            authority_epoch: self.cfg.authority_epoch,
            issued_at: at,
            valid_until: c.ceiling,
            phase: ProjectionPhase::RecoveryRequired,
            execution: ExecutionState::Offline,
            grant: None,
            drained_grant: None,
        };
        let payload = serde_json::to_vec(&claims).map_err(|_| AgentError::Protocol)?;
        let msg = projection_message(&payload).map_err(|_| AgentError::Protocol)?;
        Ok(self.proof(payload, &msg))
    }
    fn proof(&self, payload: Vec<u8>, message: &[u8]) -> SignedPayload {
        SignedPayload {
            payload: URL_SAFE_NO_PAD.encode(payload),
            signature: URL_SAFE_NO_PAD.encode(self.key.sign(message).as_ref()),
        }
    }
    pub(super) fn journal_record(&self, revision: i64) -> Result<Vec<u8>> {
        let binding = ring::digest::digest(&ring::digest::SHA256, &self.cfg.journal_binding()?);
        let mut body = revision.to_be_bytes().to_vec();
        body.extend_from_slice(binding.as_ref());
        let mut msg = b"coding-tools-agent-journal-v1\0".to_vec();
        msg.extend_from_slice(&body);
        body.extend_from_slice(self.key.sign(&msg).as_ref());
        Ok(body)
    }
    pub(super) fn verify_record(&self, record: &[u8], revision: i64) -> Result<()> {
        // Ed25519 signatures are deterministic. Compare with locally generated exact record.
        if record != self.journal_record(revision)? {
            return Err(AgentError::Journal);
        }
        Ok(())
    }
}
