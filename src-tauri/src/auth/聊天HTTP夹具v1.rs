//! Synthetic HTTP host fixture, not evidence of real ChatGPT/mTLS interoperability.
use serde_json::{json, Value};
pub(crate) const KEY: &str = "test-only-chat-auth-signing-key-no-production-credential";
pub(crate) const ORIGIN: &str = "https://chat-test.example";
pub(crate) fn token() -> String { super::principal::issue(ORIGIN,KEY,"test-client",3600).unwrap() }
pub(crate) fn approve(profile: &str, workspace: &std::path::Path, session: &str) {
    let p = super::principal::verify(&token(),KEY,ORIGIN).unwrap();
    let req = super::chat::RemoteRequest::verified(profile,&workspace.display().to_string(),p,&json!({"openai/session":session}),KEY);
    let v = req.service.request(&req,&json!({"scopes":super::chat::SCOPES}));
    if v["authorization"]["status"] == "active" { return; }
    req.service.decide(profile,v["authorization"]["id"].as_str().unwrap(),true,
        &super::chat::SCOPES.iter().map(|s| (*s).into()).collect::<Vec<_>>()).unwrap();
}
pub(crate) fn client() -> reqwest::Client {
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(reqwest::header::AUTHORIZATION,format!("Bearer {}",token()).parse().unwrap());
    reqwest::Client::builder().default_headers(headers).timeout(std::time::Duration::from_secs(10)).no_proxy().build().unwrap()
}
pub(crate) fn request(name: &str, args: Value, session: &str) -> Value {
    json!({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args,"_meta":{"openai/session":session}}})
}
