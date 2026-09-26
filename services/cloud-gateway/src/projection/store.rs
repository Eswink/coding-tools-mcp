use super::claims::{transition, ProjectedState};
use super::{verify_snapshot, ExecutionState, ProjectionDecision, ProjectionPhase};
use crate::{
    device::EnrolledDevice, store::now, IdentityError, IdentityStore, OAuthPrincipal, Result,
    Secret,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use sqlx::{postgres::PgRow, Postgres, Row, Transaction};
use uuid::Uuid;

#[derive(Clone)]
pub struct ConversationBinding(String);
impl ConversationBinding {
    /// Transfer this opaque digest only to the authenticated local approval path.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}
impl std::fmt::Debug for ConversationBinding {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("ConversationBinding([REDACTED])")
    }
}
pub struct ProjectionChallenge {
    pub gateway_boot: Uuid,
    pub nonce: Secret,
    pub expires_at: i64,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApplyOutcome {
    Applied,
    Duplicate,
}
#[derive(Clone)]
pub struct ProjectionStore {
    identity: IdentityStore,
    boot: Uuid,
}
impl ProjectionStore {
    /// Internal lifecycle fence; a channel must not adopt another controller's boot.
    pub(crate) fn active_boot_id(&self) -> Uuid {
        self.boot
    }
    /// Trusted lifecycle operation: fence all old handles and require new proof.
    /// Call once per single active controller boot; use Clone for request handling.
    pub async fn activate(identity: IdentityStore) -> Result<Self> {
        let boot = Uuid::new_v4();
        let mut tx = bounded_tx(&identity).await?;
        sqlx::query("INSERT INTO ctm_grant_projection(connector,gateway_boot) VALUES($1,$2) ON CONFLICT(connector) DO UPDATE SET gateway_boot=$2,reconciled=false,challenge_hash=NULL,challenge_until=0")
            .bind(identity.identity.connector()).bind(boot).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(Self { identity, boot })
    }
    /// Trusted operator API; not device self-registration or an HTTP endpoint.
    pub async fn bind_device(&self, id: Uuid) -> Result<()> {
        let mut tx = bounded_tx(&self.identity).await?;
        let _registered = lock_device(&self.identity, id, &mut tx).await?;
        let row = self.lock_row(&mut tx, true).await?;
        self.check_boot(&row)?;
        match row.try_get::<Option<Uuid>, _>("device")? {
            Some(existing) if existing != id => return Err(IdentityError::Conflict),
            Some(_) => {}
            None => {
                sqlx::query("UPDATE ctm_grant_projection SET device=$1 WHERE connector=$2")
                    .bind(id)
                    .bind(self.identity.identity.connector())
                    .execute(&mut *tx)
                    .await?;
            }
        }
        tx.commit().await?;
        Ok(())
    }
    /// Requires a freshly validated OAuth principal and Host-provided session.
    /// NEVER accept the Host session from model tool arguments.
    pub fn conversation_binding(
        &self,
        principal: &OAuthPrincipal,
        host_session: &str,
    ) -> Result<ConversationBinding> {
        if principal.resource != self.identity.identity.resource()
            || principal.subject.is_nil()
            || principal.client_id.is_empty()
            || principal.client_id.len() > 128
            || host_session.is_empty()
            || host_session.len() > 1024
            || host_session.chars().any(char::is_control)
        {
            return Err(IdentityError::InvalidRequest);
        }
        let bytes = serde_json::to_vec(&(
            self.identity.identity.issuer(),
            self.identity.identity.resource(),
            self.identity.identity.connector(),
            principal.subject,
            &principal.client_id,
            host_session,
        ))
        .map_err(|_| IdentityError::InvalidRequest)?;
        Ok(ConversationBinding(
            URL_SAFE_NO_PAD.encode(
                self.identity
                    .key
                    .digest("cloud-conversation-binding-v1", &bytes),
            ),
        ))
    }
    /// Future authenticated channel only. Starting reconciliation fences cached admission.
    pub async fn challenge(&self, id: Uuid) -> Result<ProjectionChallenge> {
        let nonce = Secret::random()?;
        let mut tx = bounded_tx(&self.identity).await?;
        let _registered = lock_device(&self.identity, id, &mut tx).await?;
        let row = self.lock_row(&mut tx, true).await?;
        self.check_device_and_boot(&row, id)?;
        let expiry = now(&mut tx)
            .await?
            .checked_add(60)
            .ok_or(IdentityError::InvalidProof)?;
        sqlx::query("UPDATE ctm_grant_projection SET challenge_hash=$1,challenge_until=$2,reconciled=false WHERE connector=$3")
            .bind(self.identity.key.digest("projection-challenge-v1", nonce.expose().as_bytes()))
            .bind(expiry).bind(self.identity.identity.connector()).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(ProjectionChallenge {
            gateway_boot: self.boot,
            nonce,
            expires_at: expiry,
        })
    }
    pub async fn apply(
        &self,
        device: Uuid,
        payload: &[u8],
        signature: &[u8],
    ) -> Result<ApplyOutcome> {
        // Bound work before opening a database transaction. Signature is checked against
        // the locked registry, not a public key carried inside an untrusted payload.
        if payload.is_empty() || payload.len() > 8192 || signature.len() != 64 {
            return Err(IdentityError::InvalidProof);
        }
        let mut tx = bounded_tx(&self.identity).await?;
        let registered = lock_device(&self.identity, device, &mut tx).await?;
        let row = self.lock_row(&mut tx, true).await?;
        self.check_device_and_boot(&row, device)?;
        let c = verify_snapshot(
            &self.identity.identity,
            &registered,
            payload,
            signature,
            now(&mut tx).await?,
        )?
        .0;
        if c.gateway_boot != self.boot {
            return Err(IdentityError::InvalidProof);
        }
        let digest = self.identity.key.digest("projection-payload-v1", payload);
        let old_revision: i64 = row.try_get("revision")?;
        if c.revision == old_revision
            && row.try_get::<bool, _>("reconciled")?
            && row.try_get::<Option<Vec<u8>>, _>("last_digest")?.as_deref()
                == Some(digest.as_slice())
        {
            // No update and no renewed freshness on a duplicate retry.
            tx.commit().await?;
            return Ok(ApplyOutcome::Duplicate);
        }
        let expected: Option<Vec<u8>> = row.try_get("challenge_hash")?;
        if c.revision <= old_revision
            || now(&mut tx).await? >= row.try_get::<i64, _>("challenge_until")?
            || expected.as_ref().is_none_or(|hash| {
                !self
                    .identity
                    .key
                    .matches("projection-challenge-v1", c.challenge.as_bytes(), hash)
            })
        {
            return Err(IdentityError::InvalidProof);
        }
        let old = read_state(&row)?;
        let floor = transition(old.as_ref(), &c, row.try_get("revoked_through_epoch")?)?;
        let state = serde_json::to_string(&c.state()).map_err(|_| IdentityError::InvalidProof)?;
        // Lock waits and state validation are not allowed to make an expired proof valid.
        let at = now(&mut tx).await?;
        c.validate_time(at)?;
        if at >= row.try_get::<i64, _>("challenge_until")? {
            return Err(IdentityError::InvalidProof);
        }
        sqlx::query("UPDATE ctm_grant_projection SET revision=$1,revoked_through_epoch=$2,state_text=$3,snapshot_until=$4,last_digest=$5,snapshot_device_epoch=$7,reconciled=true,challenge_hash=NULL,challenge_until=0 WHERE connector=$6")
            .bind(c.revision).bind(floor).bind(state).bind(c.valid_until).bind(digest)
            .bind(self.identity.identity.connector()).bind(registered.epoch).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(ApplyOutcome::Applied)
    }
    /// No raw state is returned, and no pending authorization is allocated.
    /// A future public adapter must reauthenticate its OAuth token on every call.
    pub async fn assess(
        &self,
        binding: &ConversationBinding,
        scope: &str,
    ) -> Result<ProjectionDecision> {
        use ProjectionDecision::*;
        let mut tx = bounded_tx(&self.identity).await?;
        let selected: Option<Uuid> =
            sqlx::query_scalar("SELECT device FROM ctm_grant_projection WHERE connector=$1")
                .bind(self.identity.identity.connector())
                .fetch_optional(&mut *tx)
                .await?
                .flatten();
        let Some(id) = selected else {
            return Ok(AuthorizationUnavailable);
        };
        let device = match lock_device(&self.identity, id, &mut tx).await {
            Ok(d) => d,
            Err(IdentityError::InvalidProof) => return Ok(AuthorizationUnavailable),
            Err(e) => return Err(e),
        };
        let row = self.lock_row(&mut tx, false).await?;
        if row.try_get::<Option<Uuid>, _>("device")? != Some(device.id)
            || row.try_get::<i64, _>("snapshot_device_epoch")? != device.epoch
        {
            return Ok(AuthorizationUnavailable);
        }
        let Some(state) = read_state(&row)? else {
            return Ok(AuthorizationUnavailable);
        };
        let Some(grant) = state.grant.as_ref() else {
            return Ok(AuthorizationUnavailable);
        };
        let at = now(&mut tx).await?;
        if grant.conversation != binding.0
            || grant.expires_at <= at
            || grant.issued_at > at
            || state.authority_epoch <= row.try_get::<i64, _>("revoked_through_epoch")?
        {
            return Ok(AuthorizationUnavailable);
        }
        if !grant.scopes.iter().any(|s| s == scope) {
            return Ok(ScopeDenied);
        }
        if row.try_get::<Uuid, _>("gateway_boot")? != self.boot
            || !row.try_get::<bool, _>("reconciled")?
            || matches!(
                state.phase,
                ProjectionPhase::Draining | ProjectionPhase::RecoveryRequired
            )
        {
            return Ok(RecoveryRequired);
        }
        if state.phase != ProjectionPhase::Active {
            return Ok(AuthorizationUnavailable);
        }
        if row.try_get::<i64, _>("snapshot_until")? <= at
            || state.execution == ExecutionState::Offline
        {
            return Ok(WorkspaceOffline);
        }
        Ok(Eligible)
    }
    async fn lock_row(&self, tx: &mut Transaction<'_, Postgres>, exclusive: bool) -> Result<PgRow> {
        let query = if exclusive {
            "SELECT * FROM ctm_grant_projection WHERE connector=$1 FOR UPDATE"
        } else {
            "SELECT * FROM ctm_grant_projection WHERE connector=$1 FOR SHARE"
        };
        sqlx::query(query)
            .bind(self.identity.identity.connector())
            .fetch_optional(&mut **tx)
            .await?
            .ok_or(IdentityError::InvalidProof)
    }
    fn check_boot(&self, row: &PgRow) -> Result<()> {
        if row.try_get::<Uuid, _>("gateway_boot")? != self.boot {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
    fn check_device_and_boot(&self, row: &PgRow, id: Uuid) -> Result<()> {
        self.check_boot(row)?;
        if row.try_get::<Option<Uuid>, _>("device")? != Some(id) {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
}
async fn bounded_tx(store: &IdentityStore) -> Result<Transaction<'_, Postgres>> {
    let mut tx = store.pool.begin().await?;
    sqlx::query("SET LOCAL lock_timeout='2000ms'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("SET LOCAL statement_timeout='3000ms'")
        .execute(&mut *tx)
        .await?;
    Ok(tx)
}
async fn lock_device(
    store: &IdentityStore,
    id: Uuid,
    tx: &mut Transaction<'_, Postgres>,
) -> Result<EnrolledDevice> {
    let r = sqlx::query("SELECT id,connector,public_key,epoch FROM ctm_devices WHERE id=$1 AND connector=$2 AND NOT revoked FOR SHARE")
        .bind(id).bind(store.identity.connector()).fetch_optional(&mut **tx).await?
        .ok_or(IdentityError::InvalidProof)?;
    Ok(EnrolledDevice {
        id: r.try_get("id")?,
        connector: r.try_get("connector")?,
        public_key: r.try_get("public_key")?,
        epoch: r.try_get("epoch")?,
    })
}
fn read_state(row: &PgRow) -> Result<Option<ProjectedState>> {
    let text: Option<String> = row.try_get("state_text")?;
    text.map(|s| {
        let state: ProjectedState =
            serde_json::from_str(&s).map_err(|_| IdentityError::StoreUnavailable)?;
        state
            .validate_shape()
            .map_err(|_| IdentityError::StoreUnavailable)?;
        Ok(state)
    })
    .transpose()
}
