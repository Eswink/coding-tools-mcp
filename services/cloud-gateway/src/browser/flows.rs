use super::{
    BrowserAuth, BrowserError, BrowserPage, BrowserRequest, Result, FLOW_SECONDS, MAX_FLOWS,
};
use crate::{crypto::valid_digest, store::now, AuthorizationRequest, Secret};
use sqlx::{postgres::PgRow, Postgres, Row, Transaction};
use uuid::Uuid;

impl BrowserAuth {
    async fn validate_request(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        r: &BrowserRequest,
    ) -> Result<()> {
        if r.resource != self.store.identity.resource()
            || !valid_digest(&r.code_challenge)
            || r.state.is_empty()
            || r.state.len() > 1024
            || r.state.chars().any(char::is_control)
            || r.client_id.len() > 128
            || r.redirect_uri.len() > 2048
        {
            return Err(BrowserError::Rejected);
        }
        let redirect: Option<String> = sqlx::query_scalar(
            "SELECT redirect_uri FROM ctm_clients WHERE client_id=$1 AND NOT disabled FOR SHARE",
        )
        .bind(&r.client_id)
        .fetch_optional(&mut **tx)
        .await?;
        if redirect.as_deref() != Some(r.redirect_uri.as_str()) {
            return Err(BrowserError::Rejected);
        }
        Ok(())
    }
    /// Creates only an expiring login transaction, never OAuth/local execution authority.
    pub async fn begin(&self, request: BrowserRequest) -> Result<BrowserPage> {
        let mut tx = self.store.pool.begin().await?;
        let epoch: i64 =
            sqlx::query_scalar("SELECT epoch FROM ctm_owner WHERE singleton FOR UPDATE")
                .fetch_optional(&mut *tx)
                .await?
                .ok_or(BrowserError::InvalidConfig)?;
        self.validate_request(&mut tx, &request).await?;
        let current = now(&mut tx).await?;
        sqlx::query("DELETE FROM ctm_browser_flows WHERE expires_at <= $1")
            .bind(current)
            .execute(&mut *tx)
            .await?;
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_browser_flows")
            .fetch_one(&mut *tx)
            .await?;
        if count >= MAX_FLOWS {
            return Err(BrowserError::RateLimited);
        }
        let cookie = Secret::random()?;
        let csrf = Secret::random()?;
        sqlx::query("INSERT INTO ctm_browser_flows(session_hash,csrf_hash,request_cipher,owner_epoch,expires_at) VALUES($1,$2,$3,$4,$5)")
            .bind(self.store.key.digest("browser-session-v1",cookie.expose().as_bytes()))
            .bind(self.store.key.digest("browser-csrf-v1",csrf.expose().as_bytes()))
            .bind(self.seal(&request)?).bind(epoch).bind(current+FLOW_SECONDS).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(BrowserPage {
            cookie,
            csrf,
            authenticated: false,
            remaining_seconds: FLOW_SECONDS,
            request,
        })
    }
    async fn locked_flow(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        cookie: &str,
        csrf: &str,
        authenticated: bool,
    ) -> Result<(PgRow, PgRow, i64)> {
        if !valid_digest(cookie) || !valid_digest(csrf) {
            return Err(BrowserError::Rejected);
        }
        // All browser operations/rotation share this lock order: owner -> flow -> client.
        let owner = sqlx::query("SELECT subject,password_phc,epoch,failures,locked_until FROM ctm_owner WHERE singleton FOR UPDATE")
            .fetch_optional(&mut **tx).await?.ok_or(BrowserError::Rejected)?;
        let flow = sqlx::query("SELECT csrf_hash,request_cipher,owner_epoch,authenticated,expires_at FROM ctm_browser_flows WHERE session_hash=$1 FOR UPDATE")
            .bind(self.store.key.digest("browser-session-v1",cookie.as_bytes()))
            .fetch_optional(&mut **tx).await?.ok_or(BrowserError::Rejected)?;
        let current = now(tx).await?;
        if flow.get::<i64, _>("expires_at") <= current
            || flow.get::<i64, _>("owner_epoch") != owner.get::<i64, _>("epoch")
            || flow.get::<bool, _>("authenticated") != authenticated
            || !self.store.key.matches(
                "browser-csrf-v1",
                csrf.as_bytes(),
                &flow.get::<Vec<u8>, _>("csrf_hash"),
            )
        {
            return Err(BrowserError::Rejected);
        }
        Ok((owner, flow, current))
    }
    pub async fn login(&self, cookie: &str, csrf: &str, password: Secret) -> Result<BrowserPage> {
        let mut tx = self.store.pool.begin().await?;
        let (owner, _, current) = self.locked_flow(&mut tx, cookie, csrf, false).await?;
        if owner.get::<i64, _>("locked_until") > current {
            return Err(BrowserError::RateLimited);
        }
        let epoch = owner.get::<i64, _>("epoch");
        let phc = owner.get::<String, _>("password_phc");
        tx.rollback().await?;
        // Do not hold database locks across expensive credential work.
        let matched = self.check_password(password, phc).await?;
        let mut tx = self.store.pool.begin().await?;
        let (owner, flow, current) = self.locked_flow(&mut tx, cookie, csrf, false).await?;
        if owner.get::<i64, _>("epoch") != epoch {
            return Err(BrowserError::Rejected);
        }
        if owner.get::<i64, _>("locked_until") > current {
            return Err(BrowserError::RateLimited);
        }
        if !matched {
            let failures = if owner.get::<i64, _>("locked_until") > 0 {
                1
            } else {
                owner.get::<i32, _>("failures") + 1
            };
            let until = if failures >= 5 { current + 60 } else { 0 };
            sqlx::query("UPDATE ctm_owner SET failures=$1,locked_until=$2 WHERE singleton")
                .bind(failures)
                .bind(until)
                .execute(&mut *tx)
                .await?;
            tx.commit().await?;
            return Err(BrowserError::LoginRejected);
        }
        let request = self.unseal(&flow.get::<Vec<u8>, _>("request_cipher"))?;
        self.validate_request(&mut tx, &request).await?;
        let current = now(&mut tx).await?;
        if current >= flow.get::<i64, _>("expires_at") {
            return Err(BrowserError::Rejected);
        }
        let new_cookie = Secret::random()?;
        let new_csrf = Secret::random()?;
        sqlx::query("UPDATE ctm_browser_flows SET session_hash=$1,csrf_hash=$2,authenticated=true WHERE session_hash=$3")
            .bind(self.store.key.digest("browser-session-v1",new_cookie.expose().as_bytes()))
            .bind(self.store.key.digest("browser-csrf-v1",new_csrf.expose().as_bytes()))
            .bind(self.store.key.digest("browser-session-v1",cookie.as_bytes())).execute(&mut *tx).await?;
        sqlx::query("UPDATE ctm_owner SET failures=0,locked_until=0 WHERE singleton")
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(BrowserPage {
            cookie: new_cookie,
            csrf: new_csrf,
            authenticated: true,
            remaining_seconds: flow.get::<i64, _>("expires_at") - current,
            request,
        })
    }
    /// Atomically consume browser consent AND issue the authorization code. No local grant.
    /// The returned URI contains a one-time code: never log it or format it via Debug.
    pub async fn decide(&self, cookie: &str, csrf: &str, allow: bool) -> Result<Secret> {
        let mut tx = self.store.pool.begin().await?;
        let (owner, flow, _) = self.locked_flow(&mut tx, cookie, csrf, true).await?;
        let request = self.unseal(&flow.get::<Vec<u8>, _>("request_cipher"))?;
        self.validate_request(&mut tx, &request).await?;
        if now(&mut tx).await? >= flow.get::<i64, _>("expires_at") {
            return Err(BrowserError::Rejected);
        }
        let mut redirect =
            url::Url::parse(&request.redirect_uri).map_err(|_| BrowserError::Rejected)?;
        if allow {
            let req = AuthorizationRequest {
                client_id: &request.client_id,
                redirect_uri: &request.redirect_uri,
                resource: &request.resource,
                code_challenge: &request.code_challenge,
                code_challenge_method: "S256",
            };
            let code = self
                .store
                .issue_consent_tx(
                    owner.get::<Uuid, _>("subject"),
                    req,
                    &mut tx,
                    Some(flow.get("expires_at")),
                )
                .await?;
            redirect
                .query_pairs_mut()
                .append_pair("code", code.expose());
        } else {
            redirect
                .query_pairs_mut()
                .append_pair("error", "access_denied");
        }
        redirect
            .query_pairs_mut()
            .append_pair("state", &request.state)
            .append_pair("iss", &self.store.identity.issuer());
        sqlx::query("DELETE FROM ctm_browser_flows WHERE session_hash=$1")
            .bind(
                self.store
                    .key
                    .digest("browser-session-v1", cookie.as_bytes()),
            )
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(Secret::new(redirect.into()))
    }
}
