//! Explicit managed MCP control-plane service. No local execution implementation is present.
use super::{
    input::{self, GatewayConfig, Secrets},
    lifecycle, mcp_runtime, Result, ServiceError,
};
use std::{io::IsTerminal, path::PathBuf};

pub async fn run_mcp(args: Vec<String>) -> Result<()> {
    if args == ["--help"] {
        println!("coding-tools-mcp-gateway: explicit cloud identity + Agent control + MCP control plane\nCommand: serve\n--config ABSOLUTE_JSON_PATH, exactly one --secrets-stdin or --secrets-file ABSOLUTE_PATH\nRequires an already selected enrolled device. No local filesystem/shell execution is performed by this binary.");
        return Ok(());
    }
    if args == ["--version"] {
        println!(
            "coding-tools-mcp-gateway {} control-plane",
            env!("CARGO_PKG_VERSION")
        );
        return Ok(());
    }
    let mut it = args.into_iter();
    if it.next().as_deref() != Some("serve") {
        return Err(ServiceError::Arguments);
    }
    let (mut cfg_path, mut secrets_path, mut stdin) = (None, None, false);
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--config" if cfg_path.is_none() => {
                cfg_path = Some(PathBuf::from(it.next().ok_or(ServiceError::Arguments)?))
            }
            "--secrets-file" if secrets_path.is_none() => {
                secrets_path = Some(PathBuf::from(it.next().ok_or(ServiceError::Arguments)?))
            }
            "--secrets-stdin" if !stdin => stdin = true,
            _ => return Err(ServiceError::Arguments),
        }
    }
    let path = cfg_path.ok_or(ServiceError::Arguments)?;
    if !path.is_absolute()
        || stdin == secrets_path.is_some()
        || secrets_path.as_ref().is_some_and(|p| !p.is_absolute())
    {
        return Err(ServiceError::Arguments);
    }
    let cfg = GatewayConfig::read(&path)?;
    let bytes = if stdin {
        let s = std::io::stdin();
        if s.is_terminal() {
            return Err(ServiceError::Input);
        }
        input::read_bounded(s.lock())?
    } else {
        input::read_protected(secrets_path.as_deref().ok_or(ServiceError::Arguments)?)?
    };
    let secrets = Secrets::parse(&bytes)?;
    drop(bytes);
    if secrets.password.is_some() || secrets.client_secret.is_some() {
        return Err(ServiceError::Input);
    }
    let store = lifecycle::open(&cfg, &secrets, false).await?;
    drop(secrets);
    lifecycle::ready(&store, &cfg).await?;
    let device: Option<uuid::Uuid> =
        sqlx::query_scalar("SELECT device FROM ctm_grant_projection WHERE connector=$1")
            .bind(cfg.connector)
            .fetch_optional(&store.pool)
            .await
            .map_err(|_| ServiceError::NotReady)?
            .flatten();
    store
        .registered_device(device.ok_or(ServiceError::NotReady)?)
        .await
        .map_err(|_| ServiceError::NotReady)?;
    mcp_runtime::serve(store, cfg).await
}
