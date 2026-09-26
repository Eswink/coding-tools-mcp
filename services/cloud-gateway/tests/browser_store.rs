mod browser_support;
#[allow(dead_code)]
mod common;
use browser_support::*;
use coding_tools_cloud_gateway::{
    browser::{BrowserAuth, BrowserError, MAX_FLOWS},
    IdentityStore, Lifetimes, Secret, SecretKey,
};
use sqlx::Row;

#[tokio::test]
async fn provisioning_is_explicit_and_never_overwrites_an_owner() {
    let (f, a) = setup().await;
    assert!(a
        .provision_owner(OWNER, Secret::new(PASSWORD.into()))
        .await
        .is_err());
    assert!(a
        .provision_owner(uuid::Uuid::nil(), Secret::new(PASSWORD.into()))
        .await
        .is_err());
    let row = sqlx::query("SELECT password_phc,epoch FROM ctm_owner")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    let hash: String = row.get("password_phc");
    assert!(hash.starts_with("$argon2id$v=19$m=19456,t=2,p=1$"));
    assert!(!hash.contains(PASSWORD));
    assert_eq!(row.get::<i64, _>("epoch"), 1);
}
#[tokio::test]
async fn begin_and_login_do_not_grant_oauth_or_device_authority() {
    let (f, a) = setup().await;
    let p = a.begin(request()).await.unwrap();
    assert!(!p.authenticated);
    assert_eq!(codes(&f).await, 0);
    let before: i64 = sqlx::query_scalar("SELECT expires_at FROM ctm_browser_flows")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    let q = a
        .login(
            p.cookie.expose(),
            p.csrf.expose(),
            Secret::new(PASSWORD.into()),
        )
        .await
        .unwrap();
    assert!(q.authenticated);
    assert!(q.cookie.expose() != p.cookie.expose());
    assert!(q.csrf.expose() != p.csrf.expose());
    let after: i64 = sqlx::query_scalar("SELECT expires_at FROM ctm_browser_flows")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(before, after);
    assert_eq!(codes(&f).await, 0);
    let devices: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_devices")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(devices, 0);
    assert!(matches!(
        a.login(
            p.cookie.expose(),
            p.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
        .await,
        Err(BrowserError::Rejected)
    ));
}
#[tokio::test]
async fn csrf_wrong_cookie_and_unauthenticated_consent_fail_before_password_work() {
    let (f, a) = setup().await;
    let p = a.begin(request()).await.unwrap();
    let fake = Secret::random().unwrap();
    assert!(matches!(
        a.login(
            p.cookie.expose(),
            fake.expose(),
            Secret::new(PASSWORD.into())
        )
        .await,
        Err(BrowserError::Rejected)
    ));
    assert!(matches!(
        a.login(fake.expose(), p.csrf.expose(), Secret::new(PASSWORD.into()))
            .await,
        Err(BrowserError::Rejected)
    ));
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    let failures: i32 = sqlx::query_scalar("SELECT failures FROM ctm_owner")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(failures, 0);
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn allow_exchanges_pkce_and_refreshes_with_no_agent() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    let location = a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .unwrap();
    let u = url::Url::parse(location.expose()).unwrap();
    assert!(u
        .query_pairs()
        .any(|(k, v)| k == "state" && v == request().state));
    assert!(u
        .query_pairs()
        .any(|(k, v)| k == "iss" && v == common::identity().issuer()));
    let pair = f
        .store
        .exchange_code(
            common::public(),
            &code(&location),
            &"a".repeat(43),
            REDIRECT,
            &common::identity().resource(),
        )
        .await
        .unwrap();
    let principal = f
        .store
        .authenticate_access(pair.access_token.expose())
        .await
        .unwrap();
    assert_eq!(principal.subject, OWNER);
    let next = f
        .store
        .refresh(
            common::public(),
            pair.refresh_token.expose(),
            &common::identity().resource(),
        )
        .await
        .unwrap();
    assert!(f
        .store
        .authenticate_access(next.access_token.expose())
        .await
        .is_ok());
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert_eq!(codes(&f).await, 1);
}
#[tokio::test]
async fn deny_is_one_time_and_preserves_state_without_code_or_family() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    let u = url::Url::parse(
        a.decide(p.cookie.expose(), p.csrf.expose(), false)
            .await
            .unwrap()
            .expose(),
    )
    .unwrap();
    assert!(u
        .query_pairs()
        .any(|(k, v)| k == "error" && v == "access_denied"));
    assert!(!u.query_pairs().any(|(k, _)| k == "code"));
    assert!(u
        .query_pairs()
        .any(|(k, v)| k == "state" && v == request().state));
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert_eq!(codes(&f).await, 0);
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_families")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(n, 0);
}
#[tokio::test]
async fn concurrent_allow_issues_at_most_one_code() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    let (x, y) = tokio::join!(
        a.decide(p.cookie.expose(), p.csrf.expose(), true),
        a.decide(p.cookie.expose(), p.csrf.expose(), true)
    );
    assert_eq!(usize::from(x.is_ok()) + usize::from(y.is_ok()), 1);
    assert_eq!(codes(&f).await, 1);
}
#[tokio::test]
async fn another_browser_cannot_confirm_this_browser_flow() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    let q = logged_in(&a).await;
    assert!(a
        .decide(p.cookie.expose(), q.csrf.expose(), true)
        .await
        .is_err());
    assert!(a
        .decide(q.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn expired_login_and_consent_cannot_issue_authority() {
    let (f, a) = setup().await;
    let p = a.begin(request()).await.unwrap();
    sqlx::query("UPDATE ctm_browser_flows SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(a
        .login(
            p.cookie.expose(),
            p.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
        .await
        .is_err());
    let p = logged_in(&a).await;
    sqlx::query("UPDATE ctm_browser_flows SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn disabled_or_reconfigured_client_is_rechecked_before_consent() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    sqlx::query("UPDATE ctm_clients SET disabled=true")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    sqlx::query(
        "UPDATE ctm_clients SET disabled=false,redirect_uri='https://different.example.invalid/cb'",
    )
    .execute(&f.pool)
    .await
    .unwrap();
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn encrypted_request_tampering_fails_closed() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    let cipher: Vec<u8> = sqlx::query_scalar("SELECT request_cipher FROM ctm_browser_flows")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert!(!cipher
        .windows(request().state.len())
        .any(|w| w == request().state.as_bytes()));
    let mut bad = cipher;
    bad[15] ^= 1;
    sqlx::query("UPDATE ctm_browser_flows SET request_cipher=$1")
        .bind(bad)
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn restart_preserves_a_browser_flow_and_csrf_binding() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    drop(a);
    let s = IdentityStore::open(
        f.pool.clone(),
        common::identity(),
        SecretKey::new([7; 32]).unwrap(),
        Lifetimes::default(),
    )
    .await
    .unwrap();
    let reopened = BrowserAuth::new(s);
    assert!(reopened
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_ok());
    assert_eq!(codes(&f).await, 1);
}
#[tokio::test]
async fn password_rotation_revokes_browser_and_oauth_authority_atomically() {
    let (f, a) = setup().await;
    let pair = f.tokens(OWNER).await;
    let p = logged_in(&a).await;
    let q = a.begin(request()).await.unwrap();
    assert!(a
        .rotate_owner_password(1, Secret::new("too-short".into()))
        .await
        .is_err());
    a.rotate_owner_password(1, Secret::new("rotated-owner-password-canary".into()))
        .await
        .unwrap();
    assert!(a
        .decide(p.cookie.expose(), p.csrf.expose(), true)
        .await
        .is_err());
    assert!(a
        .login(
            q.cookie.expose(),
            q.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
        .await
        .is_err());
    assert!(f
        .store
        .authenticate_access(pair.access_token.expose())
        .await
        .is_err());
    assert!(a
        .rotate_owner_password(1, Secret::new(PASSWORD.into()))
        .await
        .is_err());
}
#[tokio::test]
async fn failure_cooldown_cannot_be_reset_by_new_preauth_requests() {
    let (f, a) = setup().await;
    let p = a.begin(request()).await.unwrap();
    for _ in 0..5 {
        assert!(matches!(
            a.login(
                p.cookie.expose(),
                p.csrf.expose(),
                Secret::new("incorrect-password-canary".into())
            )
            .await,
            Err(BrowserError::LoginRejected)
        ));
    }
    let q = a.begin(request()).await.unwrap();
    assert!(matches!(
        a.login(
            q.cookie.expose(),
            q.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
        .await,
        Err(BrowserError::RateLimited)
    ));
    let reopened = BrowserAuth::new(f.store.clone());
    assert!(matches!(
        reopened
            .login(
                q.cookie.expose(),
                q.csrf.expose(),
                Secret::new(PASSWORD.into())
            )
            .await,
        Err(BrowserError::RateLimited)
    ));
    sqlx::query("UPDATE ctm_owner SET locked_until=1")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(reopened
        .login(
            q.cookie.expose(),
            q.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
        .await
        .is_ok());
}
#[tokio::test]
async fn active_browser_transactions_are_bounded_and_expired_rows_are_reclaimed() {
    let (f, a) = setup().await;
    for _ in 0..MAX_FLOWS {
        a.begin(request()).await.unwrap();
    }
    assert!(matches!(
        a.begin(request()).await,
        Err(BrowserError::RateLimited)
    ));
    sqlx::query("UPDATE ctm_browser_flows SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(a.begin(request()).await.is_ok());
}
#[tokio::test]
async fn client_lock_wait_does_not_extend_browser_consent_expiry() {
    let (f, a) = setup().await;
    let p = logged_in(&a).await;
    sqlx::query("UPDATE ctm_browser_flows SET expires_at=floor(extract(epoch FROM clock_timestamp()))::bigint+1").execute(&f.pool).await.unwrap();
    let mut lock = f.pool.begin().await.unwrap();
    sqlx::query("SELECT client_id FROM ctm_clients FOR UPDATE")
        .fetch_one(&mut *lock)
        .await
        .unwrap();
    let pending =
        tokio::spawn(async move { a.decide(p.cookie.expose(), p.csrf.expose(), true).await });
    tokio::time::sleep(std::time::Duration::from_millis(1300)).await;
    lock.commit().await.unwrap();
    assert!(
        matches!(pending.await.unwrap(), Err(BrowserError::Rejected)),
        "expired consent must not become a code after waiting on client lock"
    );
    assert_eq!(codes(&f).await, 0);
}

#[tokio::test]
async fn unbounded_or_invalid_stored_password_parameters_are_not_executed() {
    let (f, a) = setup().await;
    let p = a.begin(request()).await.unwrap();
    sqlx::query("UPDATE ctm_owner SET password_phc=replace(password_phc,'m=19456','m=4294967295')")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(matches!(
        a.login(
            p.cookie.expose(),
            p.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
        .await,
        Err(BrowserError::InvalidConfig)
    ));
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn concurrent_login_rotates_the_preauth_transaction_only_once() {
    let (f, a) = setup().await;
    let p = a.begin(request()).await.unwrap();
    let (x, y) = tokio::join!(
        a.login(
            p.cookie.expose(),
            p.csrf.expose(),
            Secret::new(PASSWORD.into())
        ),
        a.login(
            p.cookie.expose(),
            p.csrf.expose(),
            Secret::new(PASSWORD.into())
        )
    );
    assert_eq!(usize::from(x.is_ok()) + usize::from(y.is_ok()), 1);
    assert_eq!(codes(&f).await, 0);
}
