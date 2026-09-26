//! No credential-bearing defaults, argument echoing or request/SQL logging.
#[tokio::main]
async fn main() {
    let args: Result<Vec<_>, _> = std::env::args_os()
        .skip(1)
        .map(|a| a.into_string())
        .collect();
    let result = match args {
        Ok(args) => coding_tools_cloud_gateway::service::run(args).await,
        Err(_) => Err(coding_tools_cloud_gateway::service::ServiceError::Arguments),
    };
    if let Err(error) = result {
        eprintln!(
            "{}",
            serde_json::json!({"ok":false,"error":error.to_string()})
        );
        std::process::exit(1);
    }
}
