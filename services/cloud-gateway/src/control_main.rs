//! Explicit opt-in gateway binary. Default identity-only executable is separate.
#[tokio::main]
async fn main() {
    let args: Result<Vec<_>, _> = std::env::args_os()
        .skip(1)
        .map(|x| x.into_string())
        .collect();
    let result = match args {
        Ok(args) => coding_tools_cloud_gateway::service::run_control(args).await,
        Err(_) => Err(coding_tools_cloud_gateway::service::ServiceError::Arguments),
    };
    if let Err(e) = result {
        eprintln!("{}", serde_json::json!({"ok":false,"error":e.to_string()}));
        std::process::exit(1);
    }
}
