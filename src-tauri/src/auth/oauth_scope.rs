//! OAuth scopes are a bounded set; offline access is consent, not a business JWT scope.
pub(super) fn normalize(scope: &str, refresh_enabled: bool) -> Result<String, ()> {
    if scope.len()>128 || scope.chars().any(|c|c.is_control()) { return Err(()); }
    let mut mcp=false; let mut offline=false;
    for item in scope.split(' ').filter(|s|!s.is_empty()) {
        match item { "mcp"=>mcp=true, "offline_access" if refresh_enabled=>offline=true, _=>return Err(()) }
    }
    if scope.is_empty(){mcp=true;}
    if !mcp {return Err(())}
    Ok(if offline {"mcp offline_access"} else {"mcp"}.into())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn normalizes_order_and_duplicates_without_widening() {
        assert_eq!(normalize("offline_access mcp mcp",true).unwrap(),"mcp offline_access");
        assert_eq!(normalize("",true).unwrap(),"mcp");
        for s in ["admin","openid mcp","offline_access","mcp\n", " "]{assert!(normalize(s,true).is_err(),"{s}");}
        assert!(normalize("mcp offline_access",false).is_err());
    }
}
