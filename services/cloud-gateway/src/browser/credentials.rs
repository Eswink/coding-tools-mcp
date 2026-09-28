use super::{BrowserAuth, BrowserError, Result};
use crate::Secret;
use argon2::{
    password_hash::SaltString, Algorithm, Argon2, Params, PasswordHash, PasswordHasher,
    PasswordVerifier, Version,
};
use ring::rand::{SecureRandom, SystemRandom};
use uuid::Uuid;

const MEMORY: u32 = 19_456;
const ITERATIONS: u32 = 2;
fn hasher() -> Argon2<'static> {
    Argon2::new(
        Algorithm::Argon2id,
        Version::V0x13,
        Params::new(MEMORY, ITERATIONS, 1, Some(32)).expect("fixed Argon2 parameters"),
    )
}
fn valid_password(password: &Secret) -> bool {
    (16..=1024).contains(&password.expose().len())
        && !password.expose().chars().any(char::is_control)
}
impl BrowserAuth {
    async fn hash_password(&self, password: Secret) -> Result<String> {
        if !valid_password(&password) {
            return Err(BrowserError::InvalidConfig);
        }
        let permit = self
            .password_work
            .clone()
            .try_acquire_owned()
            .map_err(|_| BrowserError::RateLimited)?;
        tokio::task::spawn_blocking(move || {
            // The permit lives in the blocking task even if the HTTP caller is cancelled.
            let _permit = permit;
            let mut salt = [0u8; 16];
            SystemRandom::new()
                .fill(&mut salt)
                .map_err(|_| BrowserError::StoreUnavailable)?;
            let salt = SaltString::encode_b64(&salt).map_err(|_| BrowserError::InvalidConfig)?;
            hasher()
                .hash_password(password.expose().as_bytes(), &salt)
                .map(|h| h.to_string())
                .map_err(|_| BrowserError::InvalidConfig)
        })
        .await
        .map_err(|_| BrowserError::StoreUnavailable)?
    }
    pub(crate) async fn check_password(&self, password: Secret, phc: String) -> Result<bool> {
        if !valid_password(&password) {
            return Ok(false);
        }
        let permit = self
            .password_work
            .clone()
            .try_acquire_owned()
            .map_err(|_| BrowserError::RateLimited)?;
        tokio::task::spawn_blocking(move || {
            let _permit = permit;
            let hash = PasswordHash::new(&phc).map_err(|_| BrowserError::InvalidConfig)?;
            if hash.algorithm.as_str() != "argon2id"
                || hash.version != Some(19)
                || hash.params.get_decimal("m") != Some(MEMORY)
                || hash.params.get_decimal("t") != Some(ITERATIONS)
                || hash.params.get_decimal("p") != Some(1)
                || hash.hash.as_ref().is_none_or(|h| h.len() != 32)
            {
                return Err(BrowserError::InvalidConfig);
            }
            Ok(hasher()
                .verify_password(password.expose().as_bytes(), &hash)
                .is_ok())
        })
        .await
        .map_err(|_| BrowserError::StoreUnavailable)?
    }
    /// Trusted provisioning API; never exposed by any HTTP route. No default owner/password.
    pub async fn provision_owner(&self, subject: Uuid, password: Secret) -> Result<()> {
        if subject.is_nil() {
            return Err(BrowserError::InvalidConfig);
        }
        let hash = self.hash_password(password).await?;
        let n = sqlx::query("INSERT INTO ctm_owner(singleton,subject,password_phc) VALUES(true,$1,$2) ON CONFLICT DO NOTHING")
            .bind(subject).bind(hash).execute(&self.store.pool).await?.rows_affected();
        if n != 1 {
            return Err(BrowserError::Rejected);
        }
        Ok(())
    }
    /// Explicit operator action: compare-and-swap epoch, revoke browser and OAuth sessions.
    pub async fn rotate_owner_password(&self, expected_epoch: i64, password: Secret) -> Result<()> {
        if expected_epoch <= 0 {
            return Err(BrowserError::Rejected);
        }
        let hash = self.hash_password(password).await?;
        let mut tx = self.store.pool.begin().await?;
        let subject: Option<Uuid> = sqlx::query_scalar("UPDATE ctm_owner SET password_phc=$1,epoch=epoch+1,failures=0,locked_until=0 WHERE singleton AND epoch=$2 RETURNING subject")
            .bind(hash).bind(expected_epoch).fetch_optional(&mut *tx).await?;
        let subject = subject.ok_or(BrowserError::Rejected)?;
        sqlx::query("DELETE FROM ctm_browser_flows")
            .execute(&mut *tx)
            .await?;
        sqlx::query("UPDATE ctm_families SET revoked=true WHERE subject=$1")
            .bind(subject)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(())
    }
}
