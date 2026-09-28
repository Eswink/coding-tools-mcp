use super::{
    client, config::AgentConfig, journal::RevisionJournal, signer::RecoverySigner, AgentError,
    Result,
};
use std::{
    io::{IsTerminal, Read},
    path::PathBuf,
};
use tokio::sync::watch;
use zeroize::Zeroizing;
const HELP:&str="coding-tools-agent (recovery-only control client; no local executor)\nCommands: check-config | init-state | run\n--config ABSOLUTE_JSON_PATH\ninit-state/run also require exactly one: --key-stdin | --key-file ABSOLUTE_PATH\nPrivate keys are never command-line values. Windows key-file is refused until ACL verification.\nWSS and certificate/name verification are mandatory. No grant/scopes or generic signing arguments.\n";
struct Args {
    command: String,
    config: PathBuf,
    key_file: Option<PathBuf>,
    stdin: bool,
}
fn parse(args: Vec<String>) -> Result<Args> {
    let mut it = args.into_iter();
    let command = it.next().ok_or(AgentError::Arguments)?;
    if !["run", "init-state", "check-config"].contains(&command.as_str()) {
        return Err(AgentError::Arguments);
    }
    let (mut config, mut file, mut stdin) = (None, None, false);
    while let Some(s) = it.next() {
        match s.as_str() {
            "--config" if config.is_none() => {
                config = Some(PathBuf::from(it.next().ok_or(AgentError::Arguments)?))
            }
            "--key-file" if file.is_none() => {
                file = Some(PathBuf::from(it.next().ok_or(AgentError::Arguments)?))
            }
            "--key-stdin" if !stdin => stdin = true,
            _ => return Err(AgentError::Arguments),
        }
    }
    let config = config.ok_or(AgentError::Arguments)?;
    if !config.is_absolute()
        || file.as_ref().is_some_and(|p| !p.is_absolute())
        || (command == "check-config" && (stdin || file.is_some()))
        || (command != "check-config" && (stdin == file.is_some()))
    {
        return Err(AgentError::Arguments);
    }
    Ok(Args {
        command,
        config,
        key_file: file,
        stdin,
    })
}
pub async fn run(args: Vec<String>) -> Result<()> {
    if args == ["--help"] {
        print!("{HELP}");
        return Ok(());
    }
    if args == ["--version"] {
        println!(
            "coding-tools-agent {} recovery-only",
            env!("CARGO_PKG_VERSION")
        );
        return Ok(());
    }
    let args = parse(args)?;
    let cfg = AgentConfig::read(&args.config)?;
    if args.command == "check-config" {
        println!(
            "{}",
            serde_json::json!({"ok":true,"check":"agent_config_only"})
        );
        return Ok(());
    }
    let bytes = if args.stdin {
        let stdin = std::io::stdin();
        if stdin.is_terminal() {
            return Err(AgentError::Credentials);
        }
        let mut b = Zeroizing::new(Vec::new());
        stdin
            .lock()
            .take(4097)
            .read_to_end(&mut b)
            .map_err(|_| AgentError::Credentials)?;
        b
    } else {
        crate::service::read_protected(args.key_file.as_deref().ok_or(AgentError::Arguments)?)
            .map_err(|_| AgentError::Credentials)?
    };
    let signer = RecoverySigner::from_input(cfg.clone(), &bytes)?;
    drop(bytes);
    let mut journal =
        RevisionJournal::open(&cfg.revision_file, &signer, args.command == "init-state")?;
    if args.command == "init-state" {
        println!(
            "{}",
            serde_json::json!({"ok":true,"operation":"init_state"})
        );
        return Ok(());
    }
    let (stop, rx) = watch::channel(false);
    #[cfg(unix)]
    let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .map_err(|_| AgentError::Configuration)?;
    let task = tokio::spawn(async move {
        #[cfg(unix)]
        tokio::select! {_ = tokio::signal::ctrl_c()=>{},_ = term.recv()=>{}}
        #[cfg(not(unix))]
        {
            let _ = tokio::signal::ctrl_c().await;
        }
        let _ = stop.send(true);
    });
    let result = client::drive(&cfg, &signer, &mut journal, rx).await;
    task.abort();
    if result.is_ok() {
        println!("{}", serde_json::json!({"event":"agent_stopped"}));
    }
    result
}
