use super::{
    input::{ClientMode, GatewayConfig, Secrets},
    Result, ServiceError,
};
use crate::{browser::BrowserAuth, IdentityError, IdentityStore, Lifetimes};
use sqlx::{
    postgres::{PgConnectOptions, PgPoolOptions},
    ConnectOptions, PgPool, Row,
};
use std::{str::FromStr, time::Duration};

pub(crate) async fn open(
    cfg: &GatewayConfig,
    secrets: &Secrets,
    migrate: bool,
) -> Result<IdentityStore> {
    let options = PgConnectOptions::from_str(secrets.database_url.expose())
        .map_err(|_| ServiceError::Input)?
        .disable_statement_logging();
    let pool = PgPoolOptions::new()
        .max_connections(8)
        .acquire_timeout(Duration::from_secs(3))
        .after_connect(|c, _| {
            Box::pin(async move {
                sqlx::query("SET statement_timeout='3000ms'")
                    .execute(&mut *c)
                    .await?;
                sqlx::query("SET lock_timeout='2000ms'")
                    .execute(&mut *c)
                    .await?;
                sqlx::query("SET idle_in_transaction_session_timeout='5000ms'")
                    .execute(&mut *c)
                    .await?;
                Ok(())
            })
        })
        .connect_with(options)
        .await
        .map_err(|_| ServiceError::Store)?;
    if migrate {
        IdentityStore::migrate(&pool).await.map_err(map_identity)?;
    } else {
        // Validate the exact embedded migration ledger without changing any schema.
        check_migrations(&pool).await?;
        let exists: bool =
            sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM ctm_identity_config WHERE singleton)")
                .fetch_one(&pool)
                .await
                .map_err(|_| ServiceError::NotReady)?;
        if !exists {
            return Err(ServiceError::NotReady);
        }
    }
    IdentityStore::open(
        pool,
        cfg.identity()?,
        secrets.identity_key.clone(),
        Lifetimes::default(),
    )
    .await
    .map_err(map_identity)
}
fn map_identity(err: IdentityError) -> ServiceError {
    match err {
        IdentityError::IdentityMismatch => ServiceError::Identity,
        _ => ServiceError::Store,
    }
}
async fn check_migrations(pool: &PgPool) -> Result<()> {
    let rows =
        sqlx::query("SELECT version,checksum,success FROM _sqlx_migrations ORDER BY version")
            .fetch_all(pool)
            .await
            .map_err(|_| ServiceError::NotReady)?;
    let migrator = sqlx::migrate!("./migrations");
    if rows.len() != migrator.iter().count() {
        return Err(ServiceError::NotReady);
    }
    for (r, m) in rows.iter().zip(migrator.iter()) {
        if r.get::<i64, _>("version") != m.version
            || !r.get::<bool, _>("success")
            || r.get::<Vec<u8>, _>("checksum").as_slice() != m.checksum.as_ref()
        {
            return Err(ServiceError::NotReady);
        }
    }
    Ok(())
}
pub(crate) async fn ready(store: &IdentityStore, cfg: &GatewayConfig) -> Result<()> {
    let owner: Option<uuid::Uuid> =
        sqlx::query_scalar("SELECT subject FROM ctm_owner WHERE singleton")
            .fetch_optional(&store.pool)
            .await
            .map_err(|_| ServiceError::Store)?;
    if owner != Some(cfg.owner_subject) {
        return Err(ServiceError::NotReady);
    }
    let row = sqlx::query("SELECT redirect_uri, secret_hash IS NOT NULL AS confidential, disabled FROM ctm_clients WHERE client_id=$1")
        .bind(&cfg.client_id).fetch_optional(&store.pool).await.map_err(|_| ServiceError::Store)?
        .ok_or(ServiceError::NotReady)?;
    if row.get::<String, _>("redirect_uri") != cfg.redirect_uri
        || row.get::<bool, _>("disabled")
        || row.get::<bool, _>("confidential")
            != (cfg.client_authentication == ClientMode::Confidential)
    {
        return Err(ServiceError::NotReady);
    }
    Ok(())
}
pub(crate) async fn provision(
    store: &IdentityStore,
    cfg: &GatewayConfig,
    mut secrets: Secrets,
    command: &str,
    epoch: Option<i64>,
) -> Result<()> {
    match command {
        "provision-owner" => {
            let password = secrets.password.take().ok_or(ServiceError::Input)?;
            BrowserAuth::new(store.clone())
                .provision_owner(cfg.owner_subject, password)
                .await
                .map_err(|_| ServiceError::Provisioning)
        }
        "rotate-owner" => {
            let owner: Option<uuid::Uuid> =
                sqlx::query_scalar("SELECT subject FROM ctm_owner WHERE singleton")
                    .fetch_optional(&store.pool)
                    .await
                    .map_err(|_| ServiceError::Store)?;
            if owner != Some(cfg.owner_subject) {
                return Err(ServiceError::Identity);
            }
            BrowserAuth::new(store.clone())
                .rotate_owner_password(
                    epoch.ok_or(ServiceError::Arguments)?,
                    secrets.password.take().ok_or(ServiceError::Input)?,
                )
                .await
                .map_err(|_| ServiceError::Provisioning)
        }
        "register-client" => store
            .register_client(
                &cfg.client_id,
                &cfg.redirect_uri,
                secrets.client_secret.as_ref(),
            )
            .await
            .map_err(|_| ServiceError::Provisioning),
        _ => Err(ServiceError::Arguments),
    }
}
