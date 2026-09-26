use super::{
    input::{self, ClientMode, GatewayConfig, Secrets},
    lifecycle, runtime, Result, ServiceError,
};
use serde_json::json;
use std::{io::IsTerminal, path::PathBuf};

const HELP: &str = "coding-tools-gateway (identity-only; not an MCP execution gateway)\n\
Commands: check-config | migrate | provision-owner | register-client | rotate-owner | serve\n\
Required: --config ABSOLUTE_JSON_PATH\n\
Except check-config: exactly one of --secrets-stdin | --secrets-file ABSOLUTE_PATH\n\
rotate-owner also requires: --expected-epoch POSITIVE_INTEGER\n\
Credentials are never accepted as argument values. Secret files are Unix owner-only;\n\
Windows requires non-terminal stdin until the native ACL adapter is available.\n\
No public signup, HTTP admin, default owner/password, automatic migration, or Agent execution.\n";
struct Args {
    command: String,
    config: PathBuf,
    secret_file: Option<PathBuf>,
    stdin: bool,
    epoch: Option<i64>,
}
fn parse(args: Vec<String>) -> Result<Args> {
    let mut it = args.into_iter();
    let command = it.next().ok_or(ServiceError::Arguments)?;
    if ![
        "check-config",
        "migrate",
        "provision-owner",
        "register-client",
        "rotate-owner",
        "serve",
    ]
    .contains(&command.as_str())
    {
        return Err(ServiceError::Arguments);
    }
    let (mut config, mut secret_file, mut stdin, mut epoch) = (None, None, false, None);
    while let Some(flag) = it.next() {
        match flag.as_str() {
            "--config" if config.is_none() => {
                config = Some(PathBuf::from(it.next().ok_or(ServiceError::Arguments)?))
            }
            "--secrets-file" if secret_file.is_none() => {
                secret_file = Some(PathBuf::from(it.next().ok_or(ServiceError::Arguments)?))
            }
            "--secrets-stdin" if !stdin => stdin = true,
            "--expected-epoch" if epoch.is_none() => {
                epoch = Some(
                    it.next()
                        .ok_or(ServiceError::Arguments)?
                        .parse::<i64>()
                        .map_err(|_| ServiceError::Arguments)?,
                )
            }
            _ => return Err(ServiceError::Arguments),
        }
    }
    let config = config.ok_or(ServiceError::Arguments)?;
    if !config.is_absolute()
        || secret_file.as_ref().is_some_and(|p| !p.is_absolute())
        || (command == "check-config" && (stdin || secret_file.is_some()))
        || (command != "check-config" && stdin == secret_file.is_some())
        || (command == "rotate-owner") != epoch.is_some()
        || epoch.is_some_and(|e| e <= 0)
    {
        return Err(ServiceError::Arguments);
    }
    Ok(Args {
        command,
        config,
        secret_file,
        stdin,
        epoch,
    })
}
/// Exact input shape prevents accidentally retaining operator passwords in serving config.
fn check_secret_use(command: &str, cfg: &GatewayConfig, secrets: &Secrets) -> Result<()> {
    let needs_password = matches!(command, "provision-owner" | "rotate-owner");
    let needs_client_secret =
        command == "register-client" && cfg.client_authentication == ClientMode::Confidential;
    if secrets.password.is_some() != needs_password
        || secrets.client_secret.is_some() != needs_client_secret
    {
        return Err(ServiceError::Input);
    }
    Ok(())
}
pub async fn run(args: Vec<String>) -> Result<()> {
    if args == ["--help"] {
        print!("{HELP}");
        return Ok(());
    }
    if args == ["--version"] {
        println!(
            "coding-tools-gateway {} identity-only",
            env!("CARGO_PKG_VERSION")
        );
        return Ok(());
    }
    let args = parse(args)?;
    let cfg = GatewayConfig::read(&args.config)?;
    if args.command == "check-config" {
        println!("{}", json!({"ok":true,"check":"configuration_only"}));
        return Ok(());
    }
    let bytes = if args.stdin {
        let stdin = std::io::stdin();
        if stdin.is_terminal() {
            return Err(ServiceError::Input);
        }
        input::read_bounded(stdin.lock())?
    } else {
        input::read_protected(args.secret_file.as_deref().ok_or(ServiceError::Arguments)?)?
    };
    let secrets = Secrets::parse(&bytes)?;
    drop(bytes);
    check_secret_use(&args.command, &cfg, &secrets)?;
    let store = lifecycle::open(&cfg, &secrets, args.command == "migrate").await?;
    match args.command.as_str() {
        "serve" => {
            drop(secrets);
            return runtime::serve(store, cfg).await;
        }
        "migrate" => {}
        _ => lifecycle::provision(&store, &cfg, secrets, &args.command, args.epoch).await?,
    }
    store.pool.close().await;
    println!("{}", json!({"ok":true,"operation":args.command}));
    Ok(())
}
