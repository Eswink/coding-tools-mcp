//! One-time trusted selection, transactional and idempotent. Not a controller restart.
use super::{Result, ServiceError};
use crate::IdentityStore;
use uuid::Uuid;

pub(super) async fn select(store: &IdentityStore, device: Uuid) -> Result<()> {
    select_transaction(store, device)
        .await
        .map_err(|_| ServiceError::Provisioning)
}
async fn select_transaction(store: &IdentityStore, device: Uuid) -> crate::Result<()> {
    let mut tx = store.pool.begin().await?;
    sqlx::query("SET LOCAL lock_timeout='1000ms'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("SET LOCAL statement_timeout='2000ms'")
        .execute(&mut *tx)
        .await?;
    let registered: Option<Uuid> = sqlx::query_scalar(
        "SELECT id FROM ctm_devices WHERE id=$1 AND connector=$2 AND NOT revoked FOR SHARE",
    )
    .bind(device)
    .bind(store.identity().connector())
    .fetch_optional(&mut *tx)
    .await?;
    if registered.is_none() {
        return Err(crate::IdentityError::InvalidProof);
    }
    sqlx::query("INSERT INTO ctm_grant_projection(connector,gateway_boot,device) VALUES($1,$2,$3) ON CONFLICT(connector) DO NOTHING")
        .bind(store.identity().connector()).bind(Uuid::new_v4()).bind(device)
        .execute(&mut *tx).await?;
    let selected: Option<Uuid> =
        sqlx::query_scalar("SELECT device FROM ctm_grant_projection WHERE connector=$1 FOR UPDATE")
            .bind(store.identity().connector())
            .fetch_one(&mut *tx)
            .await?;
    if selected.is_some_and(|existing| existing != device) {
        return Err(crate::IdentityError::Conflict);
    }
    if selected.is_none() {
        sqlx::query("UPDATE ctm_grant_projection SET device=$1 WHERE connector=$2")
            .bind(device)
            .bind(store.identity().connector())
            .execute(&mut *tx)
            .await?;
    }
    tx.commit().await?;
    Ok(())
}
