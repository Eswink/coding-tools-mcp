//! Separate native outbound control client; no secrets are printed on any error.
#[tokio::main]
async fn main() {
    let args: Result<Vec<_>, _> = std::env::args_os()
        .skip(1)
        .map(|x| x.into_string())
        .collect();
    let result = match args {
        Ok(args) => coding_tools_cloud_gateway::agent::run(args).await,
        Err(_) => Err(coding_tools_cloud_gateway::agent::AgentError::Arguments),
    };
    if let Err(e) = result {
        eprintln!("{}", serde_json::json!({"ok":false,"error":e.to_string()}));
        std::process::exit(1);
    }
}
