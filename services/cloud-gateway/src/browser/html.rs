use super::{BrowserPage, COOKIE_NAME};
use axum::{
    http::{header, HeaderValue, StatusCode},
    response::{Html, IntoResponse, Response},
};

fn escape(value: &str) -> String {
    value
        .chars()
        .map(|c| match c {
            '&' => "&amp;".into(),
            '<' => "&lt;".into(),
            '>' => "&gt;".into(),
            '"' => "&quot;".into(),
            '\'' => "&#39;".into(),
            _ => c.to_string(),
        })
        .collect()
}
pub(crate) fn secure(mut response: Response, callback_origin: Option<&str>) -> Response {
    let callback = callback_origin.unwrap_or("");
    let policy = format!("default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self' {callback}");
    let h = response.headers_mut();
    h.insert(
        header::CONTENT_SECURITY_POLICY,
        HeaderValue::from_str(&policy).expect("validated callback origin"),
    );
    h.insert(header::X_FRAME_OPTIONS, HeaderValue::from_static("DENY"));
    h.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    h.insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
    h.insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("no-referrer"),
    );
    h.insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    response
}
pub(crate) fn page(prefix: &str, page: BrowserPage) -> Response {
    let (action, fields, title) = if page.authenticated {
        ("consent", "<button name=decision value=allow>Allow Connector access</button><button name=decision value=deny>Deny</button>", "Approve Connector access")
    } else {
        ("login", "<label>Owner password <input type=password name=password minlength=16 maxlength=1024 autocomplete=current-password required></label><button type=submit>Sign in</button>", "Sign in as Connector owner")
    };
    let html = format!("<!doctype html><html lang=en><meta charset=utf-8><title>{title}</title><h1>{title}</h1><p>Client: {}</p><p>Return address: {}</p><p>Scope: mcp. This does not approve any local workspace or command.</p><form method=post action=\"{prefix}/oauth/{action}\"><input type=hidden name=csrf value=\"{}\">{fields}</form></html>",
        escape(&page.request.client_id), escape(&page.request.redirect_uri), page.csrf.expose());
    let callback = url::Url::parse(&page.request.redirect_uri)
        .expect("registered redirect validated")
        .origin()
        .ascii_serialization();
    // Some browsers apply form-action to a 303 target. Permit only the registered origin.
    let mut response = secure(Html(html).into_response(), Some(&callback));
    // Fetch makes Origin null on non-CORS form POST under no-referrer.
    // Send only the origin (never path/query), while keeping strict Origin/CSRF checks.
    // Redirects and errors retain secure()'s no-referrer policy.
    response.headers_mut().insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("strict-origin"),
    );
    let cookie = format!(
        "{COOKIE_NAME}={}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={}",
        page.cookie.expose(),
        page.remaining_seconds
    );
    response.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_str(&cookie).expect("random URL-safe cookie"),
    );
    response
}
pub(crate) fn redirect(location: &str) -> Response {
    let mut r = secure(StatusCode::SEE_OTHER.into_response(), None);
    let Ok(location) = HeaderValue::from_str(location) else {
        return secure(StatusCode::BAD_REQUEST.into_response(), None);
    };
    r.headers_mut().insert(header::LOCATION, location);
    r.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_static(
            "__Host-ctm-browser=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0",
        ),
    );
    r
}
