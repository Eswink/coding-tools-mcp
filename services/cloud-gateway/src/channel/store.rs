use super::protocol::*;
use crate::{
    device::EnrolledDevice,
    projection::{ConversationBinding, ProjectionDecision, ProjectionStore},
    store::now,
    IdentityError, IdentityStore, Result,
};
use serde_json::{json, Value};
use sqlx::{postgres::PgRow, Postgres, Row, Transaction};
use std::{
    sync::Arc,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::sync::Mutex;
use uuid::Uuid;

/// Must not be deserialized or constructed from peer-supplied session fields.
#[derive(Clone)]
pub struct ChannelSession {
    device: Uuid,
    epoch: i64,
    boot: Uuid,
    session: Uuid,
    generation: i64,
}
impl std::fmt::Debug for ChannelSession {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("ChannelSession([REDACTED])")
    }
}
pub struct PendingConnection {
    challenge: ConnectChallenge,
    deadline: Instant,
}
impl PendingConnection {
    pub fn challenge(&self) -> &ConnectChallenge {
        &self.challenge
    }
}
#[derive(Clone)]
pub struct ChannelController {
    identity: IdentityStore,
    projection: ProjectionStore,
    boot: Uuid,
    // Serialize the session check + existing projection API without holding SQL locks
    // across a nested transaction. Never hold this guard over a socket send/receive.
    serial: Arc<Mutex<()>>,
}
impl ChannelController {
    /// Once per lifecycle, never per upgrade. Device binding is a separate trusted
    /// operator operation and is NOT installed or changed by this constructor.
    pub async fn activate(identity: IdentityStore) -> Result<Self> {
        let projection = ProjectionStore::activate(identity.clone()).await?;
        let expected_boot = projection.active_boot_id();
        let mut tx = bounded_tx(&identity).await?;
        let boot: Uuid = sqlx::query_scalar(
            "SELECT gateway_boot FROM ctm_grant_projection WHERE connector=$1 FOR UPDATE",
        )
        .bind(identity.identity.connector())
        .fetch_one(&mut *tx)
        .await?;
        if boot != expected_boot {
            return Err(IdentityError::InvalidProof);
        }
        sqlx::query("INSERT INTO ctm_agent_channel(connector,gateway_boot) VALUES($1,$2) ON CONFLICT(connector) DO UPDATE SET gateway_boot=$2,session=NULL,connected=false,last_seq=0,lease_until=0,absolute_until=0")
            .bind(identity.identity.connector()).bind(boot).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(Self {
            identity,
            projection,
            boot,
            serial: Arc::new(Mutex::new(())),
        })
    }
    pub fn identity(&self) -> &crate::PublicIdentity {
        self.identity.identity()
    }
    pub fn pending(&self) -> Result<PendingConnection> {
        let at = i64::try_from(
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|_| IdentityError::InvalidProof)?
                .as_secs(),
        )
        .map_err(|_| IdentityError::InvalidProof)?;
        Ok(PendingConnection {
            challenge: ConnectChallenge::fresh(self.identity(), self.boot, at)?,
            deadline: Instant::now() + Duration::from_secs(AUTH_SECONDS as u64),
        })
    }
    pub async fn authenticate(
        &self,
        pending: PendingConnection,
        proof: &SignedPayload,
    ) -> Result<ChannelSession> {
        let _guard = self.serial.lock().await;
        if Instant::now() >= pending.deadline || pending.challenge.gateway_boot != self.boot {
            return Err(IdentityError::InvalidProof);
        }
        let (payload, signature) = proof.decode(4096)?;
        let untrusted: ConnectClaims =
            serde_json::from_slice(&payload).map_err(|_| IdentityError::InvalidProof)?;
        let mut tx = bounded_tx(&self.identity).await?;
        let device = self.lock_device(untrusted.device, &mut tx).await?;
        self.lock_projection(device.id, &mut tx).await?;
        let row = self.lock_channel(&mut tx).await?;
        let at = now(&mut tx).await?;
        verify_connect(
            self.identity(),
            &device,
            &pending.challenge,
            &payload,
            &signature,
            at,
        )?;
        if Instant::now() >= pending.deadline {
            return Err(IdentityError::InvalidProof);
        }
        let generation = row
            .get::<i64, _>("generation")
            .checked_add(1)
            .ok_or(IdentityError::InvalidProof)?;
        let session = Uuid::new_v4();
        sqlx::query("UPDATE ctm_agent_channel SET session=$1,device=$2,device_epoch=$3,generation=$4,connected=true,last_seq=0,lease_until=$5,absolute_until=$6 WHERE connector=$7")
            .bind(session).bind(device.id).bind(device.epoch).bind(generation)
            .bind(at+LEASE_SECONDS).bind(at+MAX_AGE_SECONDS).bind(self.identity.identity.connector()).execute(&mut *tx).await?;
        self.fence_projection(&mut tx).await?;
        tx.commit().await?;
        Ok(ChannelSession {
            device: device.id,
            epoch: device.epoch,
            boot: self.boot,
            session,
            generation,
        })
    }
    /// Control-only messages. No business dispatch, signed execution ticket or replay.
    pub async fn control(
        &self,
        session: &ChannelSession,
        message: ControlMessage,
    ) -> Result<Value> {
        let _guard = self.serial.lock().await;
        let seq = message.sequence();
        let mut tx = bounded_tx(&self.identity).await?;
        let registered = self.lock_device(session.device, &mut tx).await?;
        self.lock_projection(session.device, &mut tx).await?;
        let row = self.lock_channel(&mut tx).await?;
        let at = now(&mut tx).await?;
        self.check_session(session, &registered, &row, at)?;
        if seq <= 0 || row.get::<i64, _>("last_seq").checked_add(1) != Some(seq) {
            return Err(IdentityError::InvalidProof);
        }
        let lease = if matches!(&message, ControlMessage::Heartbeat { .. }) {
            (at + LEASE_SECONDS).min(row.get("absolute_until"))
        } else {
            row.get("lease_until")
        };
        sqlx::query("UPDATE ctm_agent_channel SET last_seq=$1,lease_until=$2 WHERE connector=$3")
            .bind(seq)
            .bind(lease)
            .bind(self.identity.identity.connector())
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        match message {
            ControlMessage::Heartbeat { .. } => Ok(json!({"type":"heartbeat_ack","seq":seq})),
            ControlMessage::ProjectionChallenge { .. } => {
                let c = self.projection.challenge(session.device).await?;
                Ok(
                    json!({"type":"projection_challenge","seq":seq,"gateway_boot":c.gateway_boot,
                    "nonce":c.nonce.expose(),"expires_at":c.expires_at,"snapshot_valid_until":lease.min(c.expires_at)}),
                )
            }
            ControlMessage::Projection { proof, .. } => {
                let (payload, sig) = proof.decode(8192)?;
                let snapshot: crate::projection::ProjectionClaims =
                    serde_json::from_slice(&payload).map_err(|_| IdentityError::InvalidProof)?;
                // The existing projection transaction rechecks signed expiry after its
                // lock waits. Binding that expiry to this session's locked lease also
                // prevents a proof committing after the authenticated link expired.
                if snapshot.valid_until > lease {
                    return Err(IdentityError::InvalidProof);
                }
                self.projection
                    .apply(session.device, &payload, &sig)
                    .await?;
                Ok(json!({"type":"projection_ack","seq":seq}))
            }
        }
    }
    /// Periodic expiry/revocation check; DOES NOT renew any lease.
    pub async fn validate(&self, session: &ChannelSession) -> Result<()> {
        let _guard = self.serial.lock().await;
        let mut tx = bounded_tx(&self.identity).await?;
        let device = self.lock_device(session.device, &mut tx).await?;
        self.lock_projection(session.device, &mut tx).await?;
        let row = self.lock_channel(&mut tx).await?;
        self.check_session(session, &device, &row, now(&mut tx).await?)?;
        tx.commit().await?;
        Ok(())
    }
    /// Compare exact session/generation before cleanup; an old socket cannot close a new one.
    /// No device lock is needed: cleanup only removes presence, never issues authority.
    pub async fn disconnect(&self, session: &ChannelSession) -> Result<()> {
        let _guard = self.serial.lock().await;
        let mut tx = bounded_tx(&self.identity).await?;
        self.lock_projection(session.device, &mut tx).await?;
        let row = self.lock_channel(&mut tx).await?;
        if self.matches(session, &row) {
            sqlx::query(
                "UPDATE ctm_agent_channel SET connected=false,lease_until=0 WHERE connector=$1",
            )
            .bind(self.identity.identity.connector())
            .execute(&mut *tx)
            .await?;
            self.fence_projection(&mut tx).await?;
        }
        tx.commit().await?;
        Ok(())
    }
    /// Internal caller must pass freshly authenticated conversation binding. This filter
    /// cannot replace the future Agent's local grant/gate and durable mutation ledger.
    pub async fn assess(
        &self,
        binding: &ConversationBinding,
        scope: &str,
    ) -> Result<ProjectionDecision> {
        let _guard = self.serial.lock().await;
        let decision = self.projection.assess(binding, scope).await?;
        if decision != ProjectionDecision::Eligible {
            return Ok(decision);
        }
        let row=sqlx::query("SELECT connected,lease_until,absolute_until,gateway_boot FROM ctm_agent_channel WHERE connector=$1")
            .bind(self.identity.identity.connector()).fetch_one(&self.identity.pool).await?;
        let at: i64 =
            sqlx::query_scalar("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
                .fetch_one(&self.identity.pool)
                .await?;
        if row.get::<Uuid, _>("gateway_boot") != self.boot
            || !row.get::<bool, _>("connected")
            || at >= row.get::<i64, _>("lease_until")
            || at >= row.get::<i64, _>("absolute_until")
        {
            return Ok(ProjectionDecision::WorkspaceOffline);
        }
        Ok(decision)
    }
    async fn lock_device(
        &self,
        id: Uuid,
        tx: &mut Transaction<'_, Postgres>,
    ) -> Result<EnrolledDevice> {
        let r=sqlx::query("SELECT id,connector,public_key,epoch FROM ctm_devices WHERE id=$1 AND connector=$2 AND NOT revoked FOR SHARE")
            .bind(id).bind(self.identity.identity.connector()).fetch_optional(&mut **tx).await?.ok_or(IdentityError::InvalidProof)?;
        Ok(EnrolledDevice {
            id: r.get("id"),
            connector: r.get("connector"),
            public_key: r.get("public_key"),
            epoch: r.get("epoch"),
        })
    }
    async fn lock_projection(&self, id: Uuid, tx: &mut Transaction<'_, Postgres>) -> Result<()> {
        let r = sqlx::query(
            "SELECT gateway_boot,device FROM ctm_grant_projection WHERE connector=$1 FOR UPDATE",
        )
        .bind(self.identity.identity.connector())
        .fetch_one(&mut **tx)
        .await?;
        if r.get::<Uuid, _>("gateway_boot") != self.boot
            || r.get::<Option<Uuid>, _>("device") != Some(id)
        {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
    async fn lock_channel(&self, tx: &mut Transaction<'_, Postgres>) -> Result<PgRow> {
        let r = sqlx::query("SELECT * FROM ctm_agent_channel WHERE connector=$1 FOR UPDATE")
            .bind(self.identity.identity.connector())
            .fetch_one(&mut **tx)
            .await?;
        if r.get::<Uuid, _>("gateway_boot") != self.boot {
            return Err(IdentityError::InvalidProof);
        }
        Ok(r)
    }
    fn matches(&self, s: &ChannelSession, r: &PgRow) -> bool {
        s.boot == self.boot
            && r.get::<Uuid, _>("gateway_boot") == s.boot
            && r.get::<Option<Uuid>, _>("session") == Some(s.session)
            && r.get::<Option<Uuid>, _>("device") == Some(s.device)
            && r.get::<i64, _>("generation") == s.generation
    }
    fn check_session(
        &self,
        s: &ChannelSession,
        d: &EnrolledDevice,
        r: &PgRow,
        at: i64,
    ) -> Result<()> {
        if !self.matches(s, r)
            || d.epoch != s.epoch
            || r.get::<Option<i64>, _>("device_epoch") != Some(d.epoch)
            || !r.get::<bool, _>("connected")
            || at >= r.get::<i64, _>("lease_until")
            || at >= r.get::<i64, _>("absolute_until")
        {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
    async fn fence_projection(&self, tx: &mut Transaction<'_, Postgres>) -> Result<()> {
        sqlx::query("UPDATE ctm_grant_projection SET reconciled=false,challenge_hash=NULL,challenge_until=0 WHERE connector=$1 AND gateway_boot=$2")
            .bind(self.identity.identity.connector()).bind(self.boot).execute(&mut **tx).await?;
        Ok(())
    }
}
async fn bounded_tx(store: &IdentityStore) -> Result<Transaction<'_, Postgres>> {
    let mut tx = store.pool.begin().await?;
    sqlx::query("SET LOCAL lock_timeout='1000ms'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("SET LOCAL statement_timeout='2000ms'")
        .execute(&mut *tx)
        .await?;
    Ok(tx)
}
