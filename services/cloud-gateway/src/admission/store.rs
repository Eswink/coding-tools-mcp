use super::canonical::digest_json;
use crate::{
    grant::LOCAL_SCOPES,
    projection::{ConversationBinding, ExecutionState, LocalLease, ProjectionPhase},
    IdentityError, IdentityStore, Result,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{postgres::PgRow, Postgres, Row, Transaction};
use uuid::Uuid;

pub const MAX_ARGUMENT_BYTES: usize = 65_536;
pub const MAX_DEADLINE_SECONDS: i64 = 300;
pub const MAX_IN_FLIGHT: i64 = 32;
const MAX_TOOL_NAME: usize = 128;
const MAX_SCOPE: usize = 64;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RequestClass {
    ReadOnly,
    Mutating,
}
impl RequestClass {
    fn as_str(self) -> &'static str {
        match self {
            Self::ReadOnly => "read_only",
            Self::Mutating => "mutating",
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RequestState {
    NotAdmitted,
    Admitted,
    Running,
    Completed,
    OutcomeUnknown,
    Cancelled,
}
impl RequestState {
    fn parse(value: &str) -> Result<Self> {
        Ok(match value {
            "not_admitted" => Self::NotAdmitted,
            "admitted" => Self::Admitted,
            "running" => Self::Running,
            "completed" => Self::Completed,
            "outcome_unknown" => Self::OutcomeUnknown,
            "cancelled" => Self::Cancelled,
            _ => return Err(IdentityError::StoreUnavailable),
        })
    }
    fn as_str(self) -> &'static str {
        match self {
            Self::NotAdmitted => "not_admitted",
            Self::Admitted => "admitted",
            Self::Running => "running",
            Self::Completed => "completed",
            Self::OutcomeUnknown => "outcome_unknown",
            Self::Cancelled => "cancelled",
        }
    }
    fn terminal(self) -> bool {
        matches!(self, Self::NotAdmitted | Self::Completed | Self::Cancelled)
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdmissionDeny {
    Authorization,
    Scope,
    Recovery,
    Offline,
    Backpressure,
    Deadline,
}
impl AdmissionDeny {
    fn as_str(self) -> &'static str {
        match self {
            Self::Authorization => "authorization",
            Self::Scope => "scope",
            Self::Recovery => "recovery",
            Self::Offline => "offline",
            Self::Backpressure => "backpressure",
            Self::Deadline => "deadline",
        }
    }
    fn parse(value: &str) -> Result<Self> {
        Ok(match value {
            "authorization" => Self::Authorization,
            "scope" => Self::Scope,
            "recovery" => Self::Recovery,
            "offline" => Self::Offline,
            "backpressure" => Self::Backpressure,
            "deadline" => Self::Deadline,
            _ => return Err(IdentityError::StoreUnavailable),
        })
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdmissionDecision {
    Admitted,
    Existing,
    ReconcileRequired,
    Denied(AdmissionDeny),
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdmissionReceipt {
    pub request_id: Uuid,
    pub state: RequestState,
    pub decision: AdmissionDecision,
    pub result_ok: Option<bool>,
}
pub struct AdmissionRequest<'a> {
    pub request_id: Uuid,
    pub conversation: &'a ConversationBinding,
    pub scope: &'a str,
    pub tool_name: &'a str,
    pub arguments: &'a Value,
    pub class: RequestClass,
    pub deadline: i64,
}
impl std::fmt::Debug for AdmissionRequest<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("AdmissionRequest")
            .field("request_id", &self.request_id)
            .field("scope", &self.scope)
            .field("tool_name", &self.tool_name)
            .field("class", &self.class)
            .field("deadline", &self.deadline)
            .field("conversation", &"[REDACTED]")
            .field("arguments", &"[REDACTED]")
            .finish()
    }
}
#[derive(Clone)]
pub struct AdmissionStore {
    identity: IdentityStore,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectedState {
    phase: ProjectionPhase,
    execution: ExecutionState,
    authority_epoch: i64,
    grant: Option<LocalLease>,
}
#[derive(Clone)]
struct Fence {
    device: Uuid,
    device_epoch: i64,
    gateway_boot: Uuid,
    channel_session: Uuid,
    channel_generation: i64,
    grant_id: Uuid,
    grant_revision: i64,
    authority_epoch: i64,
}
struct Fingerprint {
    conversation_hash: Vec<u8>,
    arguments_hash: [u8; 32],
}
struct EvalContext<'a> {
    device: &'a PgRow,
    projection: &'a PgRow,
    channel: &'a PgRow,
    state: &'a ProjectedState,
    at: i64,
}
struct InsertDisposition<'a> {
    state: RequestState,
    deny: Option<AdmissionDeny>,
    fence: Option<&'a Fence>,
    at: i64,
}
impl AdmissionStore {
    pub fn new(identity: IdentityStore) -> Self {
        Self { identity }
    }

    /// Atomically checks the current device-owned grant/channel fence and creates one
    /// durable metadata row. No tool payload or output is stored, and no execution starts.
    pub async fn admit(&self, request: AdmissionRequest<'_>) -> Result<AdmissionReceipt> {
        let fingerprint = self.fingerprint(&request)?;
        let mut tx = bounded_tx(&self.identity).await?;
        let at = now(&mut tx).await?;
        self.validate_request(&request, at)?;
        // Serialize retries for one external request ID before the existence check.
        // This is a transaction-scoped lock only; it carries no execution authority.
        sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
            .bind(request.request_id.to_string())
            .execute(&mut *tx)
            .await?;
        if let Some(existing) = lock_request(&mut tx, request.request_id).await? {
            self.verify_same(&existing, &request, &fingerprint)?;
            let receipt = receipt(&existing, true)?;
            tx.commit().await?;
            return Ok(receipt);
        }

        let decision = self
            .current_fence(&mut tx, &request, &fingerprint, at)
            .await?;
        let (state, deny, fence) = match decision {
            Ok(fence) => {
                let active: i64 = sqlx::query_scalar(
                    "SELECT count(*) FROM ctm_request_ledger WHERE connector=$1 AND state IN ('admitted','running')",
                )
                .bind(self.identity.identity.connector())
                .fetch_one(&mut *tx)
                .await?;
                if active >= MAX_IN_FLIGHT {
                    (
                        RequestState::NotAdmitted,
                        Some(AdmissionDeny::Backpressure),
                        None,
                    )
                } else {
                    (RequestState::Admitted, None, Some(fence))
                }
            }
            Err(deny) => (RequestState::NotAdmitted, Some(deny), None),
        };
        insert_request(
            &mut tx,
            &self.identity,
            &request,
            &fingerprint,
            InsertDisposition {
                state,
                deny,
                fence: fence.as_ref(),
                at,
            },
        )
        .await?;
        tx.commit().await?;
        Ok(AdmissionReceipt {
            request_id: request.request_id,
            state,
            decision: deny.map_or(AdmissionDecision::Admitted, AdmissionDecision::Denied),
            result_ok: None,
        })
    }

    /// Marks a request as dispatched only after rechecking the exact generation and
    /// local grant. The future Agent still has to recheck its authoritative local gate.
    pub async fn begin_execution(&self, request_id: Uuid) -> Result<AdmissionReceipt> {
        let mut tx = bounded_tx(&self.identity).await?;
        let at = now(&mut tx).await?;
        let row = lock_request(&mut tx, request_id)
            .await?
            .ok_or(IdentityError::InvalidRequest)?;
        let state = RequestState::parse(row.get("state"))?;
        if state != RequestState::Admitted {
            let r = receipt(&row, true)?;
            tx.commit().await?;
            return Ok(r);
        }
        if row.get::<i64, _>("deadline") <= at {
            set_denied(&mut tx, request_id, AdmissionDeny::Deadline, at).await?;
            tx.commit().await?;
            return Ok(AdmissionReceipt {
                request_id,
                state: RequestState::NotAdmitted,
                decision: AdmissionDecision::Denied(AdmissionDeny::Deadline),
                result_ok: None,
            });
        }
        let deny = self.recheck_locked(&mut tx, &row, at).await?;
        if let Some(deny) = deny {
            set_denied(&mut tx, request_id, deny, at).await?;
            tx.commit().await?;
            return Ok(AdmissionReceipt {
                request_id,
                state: RequestState::NotAdmitted,
                decision: AdmissionDecision::Denied(deny),
                result_ok: None,
            });
        }
        sqlx::query(
            "UPDATE ctm_request_ledger SET state='running',updated_at=$2 WHERE request_id=$1",
        )
        .bind(request_id)
        .bind(at)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        Ok(AdmissionReceipt {
            request_id,
            state: RequestState::Running,
            decision: AdmissionDecision::Existing,
            result_ok: None,
        })
    }

    pub async fn complete(
        &self,
        request_id: Uuid,
        result_hash: [u8; 32],
        ok: bool,
    ) -> Result<AdmissionReceipt> {
        let mut tx = bounded_tx(&self.identity).await?;
        let at = now(&mut tx).await?;
        let row = lock_request(&mut tx, request_id)
            .await?
            .ok_or(IdentityError::InvalidRequest)?;
        let state = RequestState::parse(row.get("state"))?;
        if state == RequestState::Completed {
            let existing: Option<Vec<u8>> = row.get("result_hash");
            if existing.as_deref() != Some(result_hash.as_slice())
                || row.get::<Option<bool>, _>("result_ok") != Some(ok)
            {
                return Err(IdentityError::Conflict);
            }
            let r = receipt(&row, true)?;
            tx.commit().await?;
            return Ok(r);
        }
        if state != RequestState::Running {
            return Err(IdentityError::Conflict);
        }
        sqlx::query("UPDATE ctm_request_ledger SET state='completed',result_hash=$2,result_ok=$3,updated_at=$4 WHERE request_id=$1")
            .bind(request_id).bind(result_hash.as_slice()).bind(ok).bind(at).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(AdmissionReceipt {
            request_id,
            state: RequestState::Completed,
            decision: AdmissionDecision::Existing,
            result_ok: Some(ok),
        })
    }

    /// Use when dispatch/result certainty is lost. This state is never auto-replayed.
    pub async fn mark_outcome_unknown(&self, request_id: Uuid) -> Result<AdmissionReceipt> {
        self.transition_uncertain(request_id, false).await
    }

    /// Cancellation before dispatch is terminal; once running, outcome becomes unknown.
    pub async fn cancel(&self, request_id: Uuid) -> Result<AdmissionReceipt> {
        self.transition_uncertain(request_id, true).await
    }

    async fn transition_uncertain(
        &self,
        request_id: Uuid,
        cancel: bool,
    ) -> Result<AdmissionReceipt> {
        let mut tx = bounded_tx(&self.identity).await?;
        let at = now(&mut tx).await?;
        let row = lock_request(&mut tx, request_id)
            .await?
            .ok_or(IdentityError::InvalidRequest)?;
        let current = RequestState::parse(row.get("state"))?;
        let next = match (cancel, current) {
            (_, RequestState::OutcomeUnknown) => RequestState::OutcomeUnknown,
            (_, s) if s.terminal() => s,
            (true, RequestState::Admitted) => RequestState::Cancelled,
            (true, RequestState::Running)
            | (false, RequestState::Admitted | RequestState::Running) => {
                RequestState::OutcomeUnknown
            }
            _ => return Err(IdentityError::Conflict),
        };
        if next != current {
            sqlx::query("UPDATE ctm_request_ledger SET state=$2,updated_at=$3 WHERE request_id=$1")
                .bind(request_id)
                .bind(next.as_str())
                .bind(at)
                .execute(&mut *tx)
                .await?;
        }
        tx.commit().await?;
        Ok(AdmissionReceipt {
            request_id,
            state: next,
            decision: decision_for_state(next, None),
            result_ok: row.get("result_ok"),
        })
    }

    /// Fence uncertain work from an old controller boot. No row is resubmitted.
    pub async fn fence_other_boots(&self, current_boot: Uuid) -> Result<u64> {
        if current_boot.is_nil() {
            return Err(IdentityError::InvalidRequest);
        }
        let mut tx = bounded_tx(&self.identity).await?;
        let at = now(&mut tx).await?;
        let result = sqlx::query("UPDATE ctm_request_ledger SET state='outcome_unknown',updated_at=$2 WHERE connector=$1 AND state IN ('admitted','running') AND gateway_boot IS DISTINCT FROM $3")
            .bind(self.identity.identity.connector()).bind(at).bind(current_boot).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(result.rows_affected())
    }

    pub async fn get(&self, request_id: Uuid) -> Result<Option<AdmissionReceipt>> {
        if request_id.is_nil() {
            return Err(IdentityError::InvalidRequest);
        }
        let row =
            sqlx::query("SELECT * FROM ctm_request_ledger WHERE request_id=$1 AND connector=$2")
                .bind(request_id)
                .bind(self.identity.identity.connector())
                .fetch_optional(&self.identity.pool)
                .await?;
        row.as_ref().map(|r| receipt(r, true)).transpose()
    }

    /// Bounded cleanup removes only known-terminal metadata. Unknown/running work is retained.
    pub async fn purge_terminal_before(&self, cutoff: i64, limit: i64) -> Result<u64> {
        if cutoff <= 0 || !(1..=1000).contains(&limit) {
            return Err(IdentityError::InvalidRequest);
        }
        let result = sqlx::query("WITH doomed AS (SELECT request_id FROM ctm_request_ledger WHERE connector=$1 AND updated_at<$2 AND state IN ('not_admitted','completed','cancelled') ORDER BY updated_at LIMIT $3) DELETE FROM ctm_request_ledger l USING doomed d WHERE l.request_id=d.request_id")
            .bind(self.identity.identity.connector()).bind(cutoff).bind(limit).execute(&self.identity.pool).await?;
        Ok(result.rows_affected())
    }

    fn fingerprint(&self, request: &AdmissionRequest<'_>) -> Result<Fingerprint> {
        Ok(Fingerprint {
            conversation_hash: self.identity.key.digest(
                "request-conversation-v1",
                request.conversation.as_str().as_bytes(),
            ),
            arguments_hash: digest_json(request.arguments, MAX_ARGUMENT_BYTES)?,
        })
    }
    fn validate_request(&self, request: &AdmissionRequest<'_>, at: i64) -> Result<()> {
        if request.request_id.is_nil()
            || request.scope.is_empty()
            || request.scope.len() > MAX_SCOPE
            || !LOCAL_SCOPES.contains(&request.scope)
            || !valid_tool(request.tool_name)
            || request.deadline <= at
            || request
                .deadline
                .checked_sub(at)
                .is_none_or(|n| n > MAX_DEADLINE_SECONDS)
        {
            return Err(IdentityError::InvalidRequest);
        }
        Ok(())
    }
    fn verify_same(
        &self,
        row: &PgRow,
        request: &AdmissionRequest<'_>,
        f: &Fingerprint,
    ) -> Result<()> {
        if row.get::<Uuid, _>("connector") != self.identity.identity.connector()
            || row.get::<Vec<u8>, _>("conversation_hash") != f.conversation_hash
            || row.get::<String, _>("scope") != request.scope
            || row.get::<String, _>("tool_name") != request.tool_name
            || row.get::<Vec<u8>, _>("arguments_hash") != f.arguments_hash
            || row.get::<String, _>("request_class") != request.class.as_str()
            || row.get::<i64, _>("deadline") != request.deadline
        {
            return Err(IdentityError::Conflict);
        }
        Ok(())
    }
    async fn current_fence(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        request: &AdmissionRequest<'_>,
        fingerprint: &Fingerprint,
        at: i64,
    ) -> Result<std::result::Result<Fence, AdmissionDeny>> {
        let selected: Option<Uuid> =
            sqlx::query_scalar("SELECT device FROM ctm_grant_projection WHERE connector=$1")
                .bind(self.identity.identity.connector())
                .fetch_optional(&mut **tx)
                .await?
                .flatten();
        let Some(device_id) = selected else {
            return Ok(Err(AdmissionDeny::Authorization));
        };
        let device = match lock_device(&self.identity, device_id, tx).await {
            Ok(row) => row,
            Err(IdentityError::InvalidProof) => return Ok(Err(AdmissionDeny::Authorization)),
            Err(error) => return Err(error),
        };
        let projection = lock_projection(&self.identity, tx).await?;
        let channel = lock_channel(&self.identity, tx).await?;
        evaluate(
            &self.identity,
            request,
            fingerprint,
            &device,
            &projection,
            &channel,
            at,
        )
    }
    async fn recheck_locked(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        request: &PgRow,
        at: i64,
    ) -> Result<Option<AdmissionDeny>> {
        let Some(device_id) = request.get::<Option<Uuid>, _>("device") else {
            return Ok(Some(AdmissionDeny::Authorization));
        };
        let device = match lock_device(&self.identity, device_id, tx).await {
            Ok(row) => row,
            Err(IdentityError::InvalidProof) => return Ok(Some(AdmissionDeny::Authorization)),
            Err(error) => return Err(error),
        };
        let projection = lock_projection(&self.identity, tx).await?;
        let channel = lock_channel(&self.identity, tx).await?;
        let state = parse_state(&projection)?;
        let Some(grant) = state.grant.as_ref() else {
            return Ok(Some(AdmissionDeny::Authorization));
        };
        let conv = request.get::<Vec<u8>, _>("conversation_hash");
        let actual_conv = self
            .identity
            .key
            .digest("request-conversation-v1", grant.conversation.as_bytes());
        if conv != actual_conv
            || request.get::<Option<Uuid>, _>("grant_id") != Some(grant.id)
            || request.get::<Option<i64>, _>("authority_epoch") != Some(state.authority_epoch)
            || projection.get::<i64, _>("revision")
                < request
                    .get::<Option<i64>, _>("grant_revision")
                    .unwrap_or(i64::MAX)
            || request.get::<Option<Uuid>, _>("device") != Some(device.get("id"))
            || request.get::<Option<i64>, _>("device_epoch") != Some(device.get("epoch"))
            || request.get::<Option<Uuid>, _>("gateway_boot") != Some(channel.get("gateway_boot"))
            || request.get::<Option<Uuid>, _>("channel_session") != channel.get("session")
            || request.get::<Option<i64>, _>("channel_generation")
                != Some(channel.get("generation"))
        {
            return Ok(Some(AdmissionDeny::Recovery));
        }
        Ok(evaluate_state(
            &self.identity,
            &conv,
            request.get::<String, _>("scope").as_str(),
            &EvalContext {
                device: &device,
                projection: &projection,
                channel: &channel,
                state: &state,
                at,
            },
        )
        .err())
    }
}

fn valid_tool(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= MAX_TOOL_NAME
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.'))
}
fn parse_state(row: &PgRow) -> Result<ProjectedState> {
    let text: Option<String> = row.get("state_text");
    let state: ProjectedState =
        serde_json::from_str(text.as_deref().ok_or(IdentityError::InvalidProof)?)
            .map_err(|_| IdentityError::StoreUnavailable)?;
    if state.authority_epoch <= 0
        || (state.phase != ProjectionPhase::Active && state.execution != ExecutionState::Offline)
        || (state.phase == ProjectionPhase::Free && state.grant.is_some())
        || (matches!(
            state.phase,
            ProjectionPhase::Active | ProjectionPhase::Draining
        ) && state.grant.is_none())
    {
        return Err(IdentityError::StoreUnavailable);
    }
    if let Some(grant) = &state.grant {
        if grant.id.is_nil()
            || grant.conversation.len() != 43
            || grant.issued_at < 0
            || grant.expires_at <= grant.issued_at
            || grant.scopes.is_empty()
            || grant.scopes.len() > LOCAL_SCOPES.len()
            || grant
                .scopes
                .iter()
                .any(|s| !LOCAL_SCOPES.contains(&s.as_str()))
        {
            return Err(IdentityError::StoreUnavailable);
        }
    }
    Ok(state)
}
fn evaluate(
    identity: &IdentityStore,
    request: &AdmissionRequest<'_>,
    fingerprint: &Fingerprint,
    device: &PgRow,
    projection: &PgRow,
    channel: &PgRow,
    at: i64,
) -> Result<std::result::Result<Fence, AdmissionDeny>> {
    let state = parse_state(projection)?;
    match evaluate_state(
        identity,
        &fingerprint.conversation_hash,
        request.scope,
        &EvalContext {
            device,
            projection,
            channel,
            state: &state,
            at,
        },
    ) {
        Ok(()) => Ok(Ok(Fence {
            device: device.get("id"),
            device_epoch: device.get("epoch"),
            gateway_boot: channel.get("gateway_boot"),
            channel_session: channel
                .get::<Option<Uuid>, _>("session")
                .ok_or(IdentityError::InvalidProof)?,
            channel_generation: channel.get("generation"),
            grant_id: state.grant.as_ref().ok_or(IdentityError::InvalidProof)?.id,
            grant_revision: projection.get("revision"),
            authority_epoch: state.authority_epoch,
        })),
        Err(deny) => Ok(Err(deny)),
    }
}
fn evaluate_state(
    identity: &IdentityStore,
    conversation_hash: &[u8],
    scope: &str,
    ctx: &EvalContext<'_>,
) -> std::result::Result<(), AdmissionDeny> {
    let device = ctx.device;
    let projection = ctx.projection;
    let channel = ctx.channel;
    let state = ctx.state;
    let at = ctx.at;
    if device.get::<Uuid, _>("connector") != identity.identity.connector()
        || projection.get::<Option<Uuid>, _>("device") != Some(device.get("id"))
        || projection.get::<i64, _>("snapshot_device_epoch") != device.get::<i64, _>("epoch")
    {
        return Err(AdmissionDeny::Authorization);
    }
    let Some(grant) = state.grant.as_ref() else {
        return Err(AdmissionDeny::Authorization);
    };
    let expected = identity
        .key
        .digest("request-conversation-v1", grant.conversation.as_bytes());
    if expected.as_slice() != conversation_hash
        || grant.expires_at <= at
        || grant.issued_at > at
        || state.authority_epoch <= projection.get::<i64, _>("revoked_through_epoch")
    {
        return Err(AdmissionDeny::Authorization);
    }
    if !grant.scopes.iter().any(|s| s == scope) {
        return Err(AdmissionDeny::Scope);
    }
    if !projection.get::<bool, _>("reconciled")
        || matches!(
            state.phase,
            ProjectionPhase::Draining | ProjectionPhase::RecoveryRequired
        )
        || projection.get::<Uuid, _>("gateway_boot") != channel.get::<Uuid, _>("gateway_boot")
    {
        return Err(AdmissionDeny::Recovery);
    }
    if state.phase != ProjectionPhase::Active {
        return Err(AdmissionDeny::Authorization);
    }
    if !channel.get::<bool, _>("connected")
        || channel.get::<Option<Uuid>, _>("device") != Some(device.get("id"))
        || channel.get::<Option<i64>, _>("device_epoch") != Some(device.get("epoch"))
        || channel.get::<Option<Uuid>, _>("session").is_none()
        || channel.get::<i64, _>("generation") <= 0
        || at >= channel.get::<i64, _>("lease_until")
        || at >= channel.get::<i64, _>("absolute_until")
        || projection.get::<i64, _>("snapshot_until") <= at
        || state.execution == ExecutionState::Offline
    {
        return Err(AdmissionDeny::Offline);
    }
    Ok(())
}
async fn insert_request(
    tx: &mut Transaction<'_, Postgres>,
    identity: &IdentityStore,
    request: &AdmissionRequest<'_>,
    fingerprint: &Fingerprint,
    disposition: InsertDisposition<'_>,
) -> Result<()> {
    let state = disposition.state;
    let deny = disposition.deny;
    let fence = disposition.fence;
    let at = disposition.at;
    sqlx::query("INSERT INTO ctm_request_ledger(request_id,connector,conversation_hash,scope,tool_name,arguments_hash,request_class,deadline,state,deny_reason,device,device_epoch,gateway_boot,channel_session,channel_generation,grant_id,grant_revision,authority_epoch,created_at,updated_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$19)")
        .bind(request.request_id).bind(identity.identity.connector()).bind(fingerprint.conversation_hash.as_slice())
        .bind(request.scope).bind(request.tool_name).bind(fingerprint.arguments_hash.as_slice()).bind(request.class.as_str()).bind(request.deadline)
        .bind(state.as_str()).bind(deny.map(AdmissionDeny::as_str)).bind(fence.map(|f|f.device)).bind(fence.map(|f|f.device_epoch))
        .bind(fence.map(|f|f.gateway_boot)).bind(fence.map(|f|f.channel_session)).bind(fence.map(|f|f.channel_generation)).bind(fence.map(|f|f.grant_id))
        .bind(fence.map(|f|f.grant_revision)).bind(fence.map(|f|f.authority_epoch)).bind(at).execute(&mut **tx).await?;
    Ok(())
}
async fn set_denied(
    tx: &mut Transaction<'_, Postgres>,
    id: Uuid,
    deny: AdmissionDeny,
    at: i64,
) -> Result<()> {
    sqlx::query("UPDATE ctm_request_ledger SET state='not_admitted',deny_reason=$2,updated_at=$3 WHERE request_id=$1")
        .bind(id).bind(deny.as_str()).bind(at).execute(&mut **tx).await?;
    Ok(())
}
async fn lock_request(tx: &mut Transaction<'_, Postgres>, id: Uuid) -> Result<Option<PgRow>> {
    if id.is_nil() {
        return Err(IdentityError::InvalidRequest);
    }
    Ok(
        sqlx::query("SELECT * FROM ctm_request_ledger WHERE request_id=$1 FOR UPDATE")
            .bind(id)
            .fetch_optional(&mut **tx)
            .await?,
    )
}
async fn lock_device(
    identity: &IdentityStore,
    id: Uuid,
    tx: &mut Transaction<'_, Postgres>,
) -> Result<PgRow> {
    sqlx::query("SELECT id,connector,epoch FROM ctm_devices WHERE id=$1 AND connector=$2 AND NOT revoked FOR SHARE")
        .bind(id).bind(identity.identity.connector()).fetch_optional(&mut **tx).await?.ok_or(IdentityError::InvalidProof)
}
async fn lock_projection(
    identity: &IdentityStore,
    tx: &mut Transaction<'_, Postgres>,
) -> Result<PgRow> {
    sqlx::query("SELECT * FROM ctm_grant_projection WHERE connector=$1 FOR SHARE")
        .bind(identity.identity.connector())
        .fetch_one(&mut **tx)
        .await
        .map_err(Into::into)
}
async fn lock_channel(
    identity: &IdentityStore,
    tx: &mut Transaction<'_, Postgres>,
) -> Result<PgRow> {
    sqlx::query("SELECT * FROM ctm_agent_channel WHERE connector=$1 FOR UPDATE")
        .bind(identity.identity.connector())
        .fetch_one(&mut **tx)
        .await
        .map_err(Into::into)
}
async fn bounded_tx(identity: &IdentityStore) -> Result<Transaction<'_, Postgres>> {
    let mut tx = identity.pool.begin().await?;
    sqlx::query("SET LOCAL lock_timeout='2000ms'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("SET LOCAL statement_timeout='3000ms'")
        .execute(&mut *tx)
        .await?;
    Ok(tx)
}
async fn now(tx: &mut Transaction<'_, Postgres>) -> Result<i64> {
    Ok(
        sqlx::query_scalar("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
            .fetch_one(&mut **tx)
            .await?,
    )
}
fn receipt(row: &PgRow, duplicate: bool) -> Result<AdmissionReceipt> {
    let state = RequestState::parse(row.get("state"))?;
    let deny = row
        .get::<Option<String>, _>("deny_reason")
        .as_deref()
        .map(AdmissionDeny::parse)
        .transpose()?;
    Ok(AdmissionReceipt {
        request_id: row.get("request_id"),
        state,
        decision: if duplicate {
            decision_for_state(state, deny)
        } else {
            AdmissionDecision::Existing
        },
        result_ok: row.get("result_ok"),
    })
}
fn decision_for_state(state: RequestState, deny: Option<AdmissionDeny>) -> AdmissionDecision {
    match state {
        RequestState::NotAdmitted => {
            AdmissionDecision::Denied(deny.unwrap_or(AdmissionDeny::Authorization))
        }
        RequestState::Admitted => AdmissionDecision::Existing,
        RequestState::Running | RequestState::OutcomeUnknown => {
            AdmissionDecision::ReconcileRequired
        }
        RequestState::Completed | RequestState::Cancelled => AdmissionDecision::Existing,
    }
}
