use crate::{IdentityError, PublicIdentity, Result, SecretKey};
use sqlx::{PgPool, Postgres, Row, Transaction};
use std::sync::Arc;

#[derive(Debug, Clone, Copy)]
pub struct Lifetimes {
    pub access_seconds: i64,
    pub family_seconds: i64,
    pub code_seconds: i64,
}
impl Default for Lifetimes {
    fn default() -> Self {
        Self {
            access_seconds: 3600,
            family_seconds: 30 * 86400,
            code_seconds: 300,
        }
    }
}
impl Lifetimes {
    fn validate(self) -> Result<Self> {
        if !(60..=28800).contains(&self.access_seconds)
            || !(3600..=90 * 86400).contains(&self.family_seconds)
            || !(30..=600).contains(&self.code_seconds)
            || self.access_seconds > self.family_seconds
        {
            return Err(IdentityError::InvalidConfig);
        }
        Ok(self)
    }
}
#[derive(Clone)]
pub struct IdentityStore {
    pub(crate) pool: PgPool,
    pub(crate) key: Arc<SecretKey>,
    pub(crate) identity: PublicIdentity,
    pub(crate) ttl: Lifetimes,
}
impl IdentityStore {
    /// Caller supplies an isolated, least-privileged production pool or a disposable test pool.
    /// Migrations are explicit; this function does not alter schema or reset identity.
    pub async fn open(
        pool: PgPool,
        identity: PublicIdentity,
        key: SecretKey,
        ttl: Lifetimes,
    ) -> Result<Self> {
        let ttl = ttl.validate()?;
        let check = key.digest("store-binding-v1", b"coding-tools-cloud-identity");
        let mut tx = pool.begin().await?;
        sqlx::query("INSERT INTO ctm_identity_config(singleton,issuer,resource,key_check) VALUES(true,$1,$2,$3) ON CONFLICT DO NOTHING")
            .bind(identity.issuer()).bind(identity.resource()).bind(&check).execute(&mut *tx).await?;
        let row = sqlx::query(
            "SELECT issuer,resource,key_check FROM ctm_identity_config WHERE singleton FOR SHARE",
        )
        .fetch_one(&mut *tx)
        .await?;
        if row.get::<String, _>("issuer") != identity.issuer()
            || row.get::<String, _>("resource") != identity.resource()
            || row.get::<Vec<u8>, _>("key_check") != check
        {
            return Err(IdentityError::IdentityMismatch);
        }
        tx.commit().await?;
        Ok(Self {
            pool,
            key: Arc::new(key),
            identity,
            ttl,
        })
    }
    pub fn identity(&self) -> &PublicIdentity {
        &self.identity
    }
    pub async fn migrate(pool: &PgPool) -> Result<()> {
        sqlx::migrate!("./migrations")
            .run(pool)
            .await
            .map_err(|_| IdentityError::StoreUnavailable)
    }
}
pub(crate) async fn now(tx: &mut Transaction<'_, Postgres>) -> Result<i64> {
    Ok(
        sqlx::query_scalar("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
            .fetch_one(&mut **tx)
            .await?,
    )
}
