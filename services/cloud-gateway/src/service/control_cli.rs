//! Trusted local command only. No remote enrollment, approval, or arbitrary device routing.
use super::{
    input::{self, GatewayConfig, Secrets},
    lifecycle, runtime, Result, ServiceError,
};
use std::{io::IsTerminal, path::PathBuf};
use uuid::Uuid;

pub async fn run_control(args: Vec<String>) -> Result<()> {
    if args == ["--help"] {
        println!("coding-tools-control-gateway: explicit opt-in identity and Agent control service\nCommands: serve | select-device\n--config ABSOLUTE_JSON_PATH, exactly one --secrets-stdin or --secrets-file ABSOLUTE_PATH\nselect-device additionally requires --device UUID. Existing different device cannot be replaced.\nNo MCP business dispatch, no public admin/approval/enrollment endpoint.");
        return Ok(());
    }
    if args == ["--version"] {
        println!(
            "coding-tools-control-gateway {} control-only",
            env!("CARGO_PKG_VERSION")
        );
        return Ok(());
    }
    let mut it = args.into_iter();
    let command = it.next().ok_or(ServiceError::Arguments)?;
    if !["serve", "select-device"].contains(&command.as_str()) {
        return Err(ServiceError::Arguments);
    }
    let (mut cfg_path, mut secrets_path, mut stdin, mut device) = (None, None, false, None);
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--config" if cfg_path.is_none() => {
                cfg_path = Some(PathBuf::from(it.next().ok_or(ServiceError::Arguments)?))
            }
            "--secrets-file" if secrets_path.is_none() => {
                secrets_path = Some(PathBuf::from(it.next().ok_or(ServiceError::Arguments)?))
            }
            "--secrets-stdin" if !stdin => stdin = true,
            "--device" if device.is_none() => {
                device = Some(
                    it.next()
                        .ok_or(ServiceError::Arguments)?
                        .parse::<Uuid>()
                        .map_err(|_| ServiceError::Arguments)?,
                )
            }
            _ => return Err(ServiceError::Arguments),
        }
    }
    let path = cfg_path.ok_or(ServiceError::Arguments)?;
    if !path.is_absolute()
        || stdin == secrets_path.is_some()
        || secrets_path.as_ref().is_some_and(|p| !p.is_absolute())
        || (command == "select-device") != device.is_some()
        || device.is_some_and(|d| d.is_nil())
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
    if let Some(device) = device {
        super::control_selection::select(&store, device).await?;
        store.pool.close().await;
        println!(
            "{}",
            serde_json::json!({"ok":true,"operation":"select_device"})
        );
        Ok(())
    } else {
        let device: Option<Uuid> =
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
        runtime::serve_managed(store, cfg, true).await
    }
}
