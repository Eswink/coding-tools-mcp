//! Exact ledger claim/result transitions for the live channel, without payload persistence.
use super::*;
use crate::execution::{ExecutionBinding, ExecutionReply, ExecutionRequest, PeerBinding};

fn binding(row: &PgRow, conversation: &str) -> Result<ExecutionBinding> {
    let bytes: Vec<u8> = row.get("arguments_hash");
    Ok(ExecutionBinding {
        request_id: row.get("request_id"),
        peer: PeerBinding {
            connector: row.get("connector"),
            device: row
                .get::<Option<Uuid>, _>("device")
                .ok_or(IdentityError::InvalidProof)?,
            device_epoch: row
                .get::<Option<i64>, _>("device_epoch")
                .ok_or(IdentityError::InvalidProof)?,
            gateway_boot: row
                .get::<Option<Uuid>, _>("gateway_boot")
                .ok_or(IdentityError::InvalidProof)?,
            channel_session: row
                .get::<Option<Uuid>, _>("channel_session")
                .ok_or(IdentityError::InvalidProof)?,
            channel_generation: row
                .get::<Option<i64>, _>("channel_generation")
                .ok_or(IdentityError::InvalidProof)?,
        },
        grant_id: row
            .get::<Option<Uuid>, _>("grant_id")
            .ok_or(IdentityError::InvalidProof)?,
        grant_revision: row
            .get::<Option<i64>, _>("grant_revision")
            .ok_or(IdentityError::InvalidProof)?,
        authority_epoch: row
            .get::<Option<i64>, _>("authority_epoch")
            .ok_or(IdentityError::InvalidProof)?,
        conversation: conversation.into(),
        scope: row.get("scope"),
        tool: row.get("tool_name"),
        arguments_hash: bytes.try_into().map_err(|_| IdentityError::InvalidProof)?,
        deadline: row.get("deadline"),
    })
}
impl AdmissionStore {
    pub(crate) async fn claim_dispatch(
        &self,
        input: AdmissionRequest<'_>,
        peer: &PeerBinding,
    ) -> Result<ExecutionRequest> {
        let fingerprint = self.fingerprint(&input)?;
        let mut tx = bounded_tx(&self.identity).await?;
        let row = lock_request(&mut tx, input.request_id)
            .await?
            .ok_or(IdentityError::InvalidRequest)?;
        self.verify_same(&row, &input, &fingerprint)?;
        if RequestState::parse(row.get("state"))? != RequestState::Admitted {
            return Err(IdentityError::Conflict);
        }
        if self.recheck_locked(&mut tx, &row).await?.is_some() {
            return Err(IdentityError::InvalidProof);
        }
        // Locks were acquired above. Recheck time after all lock waits.
        if self.recheck_locked(&mut tx, &row).await?.is_some() {
            return Err(IdentityError::InvalidProof);
        }
        let at = now(&mut tx).await?;
        let request = ExecutionRequest {
            binding: binding(&row, input.conversation.as_str())?,
            arguments: input.arguments.clone(),
        };
        request.validate_at(peer, at)?;
        sqlx::query(
            "UPDATE ctm_request_ledger SET state='running',dispatch_claimed=true,updated_at=$2 WHERE request_id=$1",
        )
        .bind(input.request_id)
        .bind(at)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        Ok(request)
    }
    pub(crate) async fn complete_dispatch(
        &self,
        reply: &ExecutionReply,
        result_hash: [u8; 32],
    ) -> Result<()> {
        let mut tx = bounded_tx(&self.identity).await?;
        let row = lock_request(&mut tx, reply.binding.request_id)
            .await?
            .ok_or(IdentityError::InvalidRequest)?;
        let conv = self.identity.key.digest(
            "request-conversation-v1",
            reply.binding.conversation.as_bytes(),
        );
        if row.get::<Uuid, _>("connector") != self.identity.identity.connector()
            || row.get::<Vec<u8>, _>("conversation_hash") != conv
            || binding(&row, &reply.binding.conversation)? != reply.binding
            || RequestState::parse(row.get("state"))? != RequestState::Running
        {
            return Err(IdentityError::InvalidProof);
        }
        if self.recheck_locked(&mut tx, &row).await?.is_some() {
            return Err(IdentityError::InvalidProof);
        }
        if self.recheck_locked(&mut tx, &row).await?.is_some() {
            return Err(IdentityError::InvalidProof);
        }
        // The database clock must be sampled after every authority/channel lock.
        let at = now(&mut tx).await?;
        if reply.validate_for(&reply.binding, at)? != result_hash {
            return Err(IdentityError::InvalidProof);
        }
        let ok = reply.result["ok"]
            .as_bool()
            .ok_or(IdentityError::InvalidProof)?;
        sqlx::query("UPDATE ctm_request_ledger SET state='completed',result_hash=$2,result_ok=$3,updated_at=$4 WHERE request_id=$1")
            .bind(reply.binding.request_id).bind(result_hash.as_slice()).bind(ok).bind(at).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(())
    }
    /// Reuse the original deadline only after every other request field matches.
    /// Recomputing now+TTL on retries would turn a legitimate retry into a conflict.
    pub async fn original_deadline(&self, input: &AdmissionRequest<'_>) -> Result<Option<i64>> {
        let fingerprint = self.fingerprint(input)?;
        let mut tx = bounded_tx(&self.identity).await?;
        let Some(row) = lock_request(&mut tx, input.request_id).await? else {
            return Ok(None);
        };
        let deadline = row.get("deadline");
        let original = AdmissionRequest {
            deadline,
            request_id: input.request_id,
            conversation: input.conversation,
            scope: input.scope,
            tool_name: input.tool_name,
            arguments: input.arguments,
            class: input.class,
        };
        self.verify_same(&row, &original, &fingerprint)?;
        tx.commit().await?;
        Ok(Some(deadline))
    }
}
