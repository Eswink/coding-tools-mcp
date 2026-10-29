use crate::{
    config::validate_client,
    crypto::{pkce_challenge, valid_digest},
    store::now,
    IdentityError, IdentityStore, Result, Secret,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use sqlx::{Postgres, Row, Transaction};
use uuid::Uuid;

pub struct ClientCredential<'a> {
    pub client_id: &'a str,
    pub secret: Option<&'a str>,
}
/// Only the authenticated owner-consent controller may construct and submit this request.
/// This type is NOT accepted by any HTTP handler in this increment.
pub struct AuthorizationRequest<'a> {
    pub client_id: &'a str,
    pub redirect_uri: &'a str,
    pub resource: &'a str,
    pub code_challenge: &'a str,
    pub code_challenge_method: &'a str,
}
pub struct TokenPair {
    pub access_token: Secret,
    pub refresh_token: Secret,
    pub expires_in: i64,
}
impl std::fmt::Debug for TokenPair {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TokenPair")
            .field("credentials", &"[REDACTED]")
            .field("expires_in", &self.expires_in)
            .finish()
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OAuthPrincipal {
    pub subject: Uuid,
    pub client_id: String,
    pub resource: String,
}

impl IdentityStore {
    /// Trusted administrative provisioning; never exposed as unauthenticated client registration.
    /// A duplicate ID is rejected, not silently reconfigured.
    pub async fn register_client(
        &self,
        id: &str,
        redirect: &str,
        secret: Option<&Secret>,
    ) -> Result<()> {
        validate_client(id, redirect)?;
        if secret.is_some_and(|s| s.expose().len() < 32 || s.expose().len() > 512) {
            return Err(IdentityError::InvalidConfig);
        }
        let hash = secret.map(|s| self.key.digest("client-secret-v1", s.expose().as_bytes()));
        let n=sqlx::query("INSERT INTO ctm_clients(client_id,redirect_uri,secret_hash) VALUES($1,$2,$3) ON CONFLICT DO NOTHING")
            .bind(id).bind(redirect).bind(hash).execute(&self.pool).await?.rows_affected();
        if n != 1 {
            return Err(IdentityError::Conflict);
        }
        Ok(())
    }
    /// Requires prior authenticated owner consent. OAuth identity is not local workspace approval.
    /// Deliberately no HTTP route exists for this method until the consent controller is audited.
    pub async fn issue_after_owner_consent(
        &self,
        owner: Uuid,
        req: AuthorizationRequest<'_>,
    ) -> Result<Secret> {
        let mut tx = self.pool.begin().await?;
        let code = self.issue_consent_tx(owner, req, &mut tx, None).await?;
        tx.commit().await?;
        Ok(code)
    }
    /// Shares the caller's transaction with one-time browser consent consumption.
    pub(crate) async fn issue_consent_tx(
        &self,
        owner: Uuid,
        req: AuthorizationRequest<'_>,
        tx: &mut Transaction<'_, Postgres>,
        consent_deadline: Option<i64>,
    ) -> Result<Secret> {
        if owner.is_nil()
            || req.resource != self.identity.resource()
            || req.code_challenge_method != "S256"
            || !valid_digest(req.code_challenge)
        {
            return Err(IdentityError::InvalidRequest);
        }
        let redirect: Option<String> = sqlx::query_scalar(
            "SELECT redirect_uri FROM ctm_clients WHERE client_id=$1 AND NOT disabled FOR SHARE",
        )
        .bind(req.client_id)
        .fetch_optional(&mut **tx)
        .await?;
        if redirect.as_deref() != Some(req.redirect_uri) {
            return Err(IdentityError::InvalidClient);
        }
        let current = now(tx).await?;
        if consent_deadline.is_some_and(|deadline| current >= deadline) {
            return Err(IdentityError::InvalidGrant);
        }
        let family = Uuid::new_v4();
        let code = Secret::random()?;
        sqlx::query("INSERT INTO ctm_families(id,client_id,subject,resource,expires_at) VALUES($1,$2,$3,$4,$5)")
            .bind(family).bind(req.client_id).bind(owner).bind(req.resource).bind(current+self.ttl.family_seconds)
            .execute(&mut **tx).await?;
        sqlx::query("INSERT INTO ctm_codes(code_hash,family_id,redirect_uri,pkce,expires_at) VALUES($1,$2,$3,$4,$5)")
            .bind(self.key.digest("code-v1",code.expose().as_bytes())).bind(family).bind(req.redirect_uri)
            .bind(req.code_challenge).bind(current+self.ttl.code_seconds).execute(&mut **tx).await?;
        Ok(code)
    }
    async fn check_client(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        client: &ClientCredential<'_>,
    ) -> Result<()> {
        if client.client_id.is_empty()
            || client.client_id.len() > 128
            || client.secret.is_some_and(|s| s.len() > 512)
        {
            return Err(IdentityError::InvalidClient);
        }
        let row = sqlx::query(
            "SELECT secret_hash FROM ctm_clients WHERE client_id=$1 AND NOT disabled FOR SHARE",
        )
        .bind(client.client_id)
        .fetch_optional(&mut **tx)
        .await?
        .ok_or(IdentityError::InvalidClient)?;
        let expected: Option<Vec<u8>> = row.get("secret_hash");
        match (expected, client.secret) {
            (None, None) => Ok(()),
            (Some(hash), Some(secret))
                if self
                    .key
                    .matches("client-secret-v1", secret.as_bytes(), &hash) =>
            {
                Ok(())
            }
            _ => Err(IdentityError::InvalidClient),
        }
    }
    pub async fn exchange_code(
        &self,
        client: ClientCredential<'_>,
        code: &str,
        verifier: &str,
        redirect: &str,
        resource: &str,
    ) -> Result<TokenPair> {
        let mut tx = self.pool.begin().await?;
        self.check_client(&mut tx, &client).await?;
        if resource != self.identity.resource() || !valid_digest(code) {
            return Err(IdentityError::InvalidGrant);
        }
        let challenge = pkce_challenge(verifier).map_err(|_| IdentityError::InvalidGrant)?;
        let row=sqlx::query("SELECT c.*, f.client_id, f.expires_at AS family_expiry, f.revoked FROM ctm_codes c JOIN ctm_families f ON f.id=c.family_id WHERE code_hash=$1 FOR UPDATE OF f,c")
            .bind(self.key.digest("code-v1",code.as_bytes())).fetch_optional(&mut *tx).await?.ok_or(IdentityError::InvalidGrant)?;
        let current = now(&mut tx).await?;
        if row.get::<String, _>("client_id") != client.client_id
            || row.get::<String, _>("redirect_uri") != redirect
            || row.get::<String, _>("pkce") != challenge
            || row.get::<bool, _>("revoked")
            || current >= row.get::<i64, _>("expires_at")
            || current >= row.get::<i64, _>("family_expiry")
        {
            return Err(IdentityError::InvalidGrant);
        }
        let family: Uuid = row.get("family_id");
        if row.get::<bool, _>("redeemed") {
            self.revoke_tx(&mut tx, family).await?;
            tx.commit().await?;
            return Err(IdentityError::InvalidGrant);
        }
        sqlx::query("UPDATE ctm_codes SET redeemed=true WHERE code_hash=$1")
            .bind(self.key.digest("code-v1", code.as_bytes()))
            .execute(&mut *tx)
            .await?;
        let pair = self
            .mint(&mut tx, family, current, row.get("family_expiry"))
            .await?;
        tx.commit().await?;
        Ok(pair)
    }
    pub async fn refresh(
        &self,
        client: ClientCredential<'_>,
        refresh_token: &str,
        resource: &str,
    ) -> Result<TokenPair> {
        let mut tx = self.pool.begin().await?;
        self.check_client(&mut tx, &client).await?;
        if resource != self.identity.resource() || !valid_digest(refresh_token) {
            return Err(IdentityError::InvalidGrant);
        }
        let hash = self.key.digest("refresh-v1", refresh_token.as_bytes());
        // Lock the family first; a refresh row snapshot joined before waiting can be stale.
        let family: Option<Uuid> =
            sqlx::query_scalar("SELECT family_id FROM ctm_refresh_tokens WHERE token_hash=$1")
                .bind(&hash)
                .fetch_optional(&mut *tx)
                .await?;
        let family = family.ok_or(IdentityError::InvalidGrant)?;
        let row = sqlx::query(
            "SELECT client_id,resource,expires_at,revoked FROM ctm_families WHERE id=$1 FOR UPDATE",
        )
        .bind(family)
        .fetch_one(&mut *tx)
        .await?;
        let current = now(&mut tx).await?;
        if row.get::<String, _>("client_id") != client.client_id
            || row.get::<String, _>("resource") != resource
            || row.get::<bool, _>("revoked")
            || current >= row.get::<i64, _>("expires_at")
        {
            return Err(IdentityError::InvalidGrant);
        }
        let used: bool =
            sqlx::query_scalar("SELECT consumed FROM ctm_refresh_tokens WHERE token_hash=$1")
                .bind(&hash)
                .fetch_one(&mut *tx)
                .await?;
        if used {
            self.revoke_tx(&mut tx, family).await?;
            tx.commit().await?;
            return Err(IdentityError::InvalidGrant);
        }
        sqlx::query("UPDATE ctm_refresh_tokens SET consumed=true WHERE token_hash=$1")
            .bind(hash)
            .execute(&mut *tx)
            .await?;
        let pair = self
            .mint(&mut tx, family, current, row.get("expires_at"))
            .await?;
        tx.commit().await?;
        Ok(pair)
    }
    async fn mint(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        family: Uuid,
        current: i64,
        family_expiry: i64,
    ) -> Result<TokenPair> {
        let access_token = Secret::random()?;
        let refresh_token = Secret::random()?;
        let expiry = (current + self.ttl.access_seconds).min(family_expiry);
        sqlx::query(
            "INSERT INTO ctm_access_tokens(token_hash,family_id,expires_at) VALUES($1,$2,$3)",
        )
        .bind(
            self.key
                .digest("access-v1", access_token.expose().as_bytes()),
        )
        .bind(family)
        .bind(expiry)
        .execute(&mut **tx)
        .await?;
        sqlx::query("INSERT INTO ctm_refresh_tokens(token_hash,family_id) VALUES($1,$2)")
            .bind(
                self.key
                    .digest("refresh-v1", refresh_token.expose().as_bytes()),
            )
            .bind(family)
            .execute(&mut **tx)
            .await?;
        Ok(TokenPair {
            access_token,
            refresh_token,
            expires_in: expiry - current,
        })
    }
    async fn revoke_tx(&self, tx: &mut Transaction<'_, Postgres>, family: Uuid) -> Result<()> {
        sqlx::query("UPDATE ctm_families SET revoked=true WHERE id=$1")
            .bind(family)
            .execute(&mut **tx)
            .await?;
        Ok(())
    }
    pub async fn authenticate_access(&self, token: &str) -> Result<OAuthPrincipal> {
        if !valid_digest(token) {
            return Err(IdentityError::InvalidToken);
        }
        let row=sqlx::query("SELECT f.subject,f.client_id,f.resource FROM ctm_access_tokens a JOIN ctm_families f ON f.id=a.family_id JOIN ctm_clients c ON c.client_id=f.client_id WHERE a.token_hash=$1 AND NOT f.revoked AND NOT c.disabled AND a.expires_at > floor(extract(epoch FROM clock_timestamp()))::bigint AND f.expires_at > floor(extract(epoch FROM clock_timestamp()))::bigint")
            .bind(self.key.digest("access-v1",token.as_bytes())).fetch_optional(&self.pool).await?.ok_or(IdentityError::InvalidToken)?;
        if row.get::<String, _>("resource") != self.identity.resource() {
            return Err(IdentityError::InvalidToken);
        }
        Ok(OAuthPrincipal {
            subject: row.get("subject"),
            client_id: row.get("client_id"),
            resource: row.get("resource"),
        })
    }
    /// Trusted operator revocation. Client-bound token revocation HTTP flow is a later increment.
    pub async fn revoke_owner_sessions(&self, owner: Uuid) -> Result<()> {
        sqlx::query("UPDATE ctm_families SET revoked=true WHERE subject=$1")
            .bind(owner)
            .execute(&self.pool)
            .await?;
        Ok(())
    }
    pub fn conversation_binding(
        &self,
        principal: &OAuthPrincipal,
        session: &str,
    ) -> Result<String> {
        if principal.resource != self.identity.resource()
            || session.is_empty()
            || session.len() > 256
            || session.chars().any(char::is_control)
        {
            return Err(IdentityError::InvalidRequest);
        }
        let bytes = serde_json::to_vec(&(
            self.identity.issuer(),
            &principal.resource,
            principal.subject,
            &principal.client_id,
            session,
        ))
        .map_err(|_| IdentityError::InvalidRequest)?;
        Ok(URL_SAFE_NO_PAD.encode(self.key.digest("conversation-v1", &bytes)))
    }
}
