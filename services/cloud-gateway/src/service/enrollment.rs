//! Trusted local operator commands; no HTTP management route and no local grant.
use super::{
    enrollment_io::{serialize, Flags, Output},
    input::{GatewayConfig, Secrets},
    lifecycle, Result, ServiceError,
};
use crate::{device::enrollment_message, PublicIdentity};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use zeroize::Zeroize;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Invitation {
    pub version: u32,
    pub origin: String,
    pub prefix: String,
    pub connector: Uuid,
    pub token: String,
}
impl Drop for Invitation {
    fn drop(&mut self) {
        self.token.zeroize();
    }
}
impl Invitation {
    pub fn identity(&self) -> Result<PublicIdentity> {
        if self.version != 1 {
            return Err(ServiceError::Input);
        }
        let id = PublicIdentity::new(&self.origin, &self.prefix, self.connector)
            .map_err(|_| ServiceError::Input)?;
        if !crate::crypto::valid_digest(&self.token) {
            return Err(ServiceError::Input);
        }
        Ok(id)
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Proof {
    pub invitation: Invitation,
    pub public_key: String,
    pub signature: String,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Credentials {
    database_url: String,
    identity_key: String,
}
impl Drop for Credentials {
    fn drop(&mut self) {
        self.database_url.zeroize();
        self.identity_key.zeroize();
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Bundle {
    secrets: Credentials,
    proof: Proof,
}
#[derive(Serialize)]
struct Connection {
    version: u32,
    origin: String,
    prefix: String,
    connector: Uuid,
    device: Uuid,
    device_epoch: i64,
    authority_epoch: i64,
    public_key: String,
    run_seconds: u64,
}
pub(crate) async fn run(args: Vec<String>) -> Result<()> {
    let f = Flags::parse(
        args,
        &[
            "--config",
            "--secrets-file",
            "--secrets-stdin",
            "--input-file",
            "--input-stdin",
            "--output-file",
            "--output-stdout",
            "--device",
            "--bundle-stdin",
        ],
    )?;
    if !["invite-device", "redeem-device", "revoke-device"].contains(&f.command.as_str()) {
        return Err(ServiceError::Arguments);
    }
    let redeem = f.command == "redeem-device";
    let revoke = f.command == "revoke-device";
    if (f.has("--input-file") || f.has("--input-stdin") || f.has("--bundle-stdin")) != redeem
        || f.has("--device") != revoke
        || (revoke && (f.has("--output-file") || f.has("--output-stdout")))
    {
        return Err(ServiceError::Arguments);
    }
    let cfg = GatewayConfig::read(&f.path("--config")?)?;
    validate_native_identity(&cfg.identity()?)?;
    let (secrets, proof): (Secrets, Option<Proof>) = if f.has("--bundle-stdin") {
        if [
            "--secrets-file",
            "--secrets-stdin",
            "--input-file",
            "--input-stdin",
        ]
        .iter()
        .any(|s| f.has(s))
        {
            return Err(ServiceError::Arguments);
        }
        let bundle: Bundle =
            serde_json::from_slice(&f.document("--unused-file", "--bundle-stdin")?)
                .map_err(|_| ServiceError::Input)?;
        (
            Secrets::parse(&serialize(&bundle.secrets)?)?,
            Some(bundle.proof),
        )
    } else {
        let secrets = Secrets::parse(&f.document("--secrets-file", "--secrets-stdin")?)?;
        let proof = if redeem {
            Some(
                serde_json::from_slice(&f.document("--input-file", "--input-stdin")?)
                    .map_err(|_| ServiceError::Input)?,
            )
        } else {
            None
        };
        (secrets, proof)
    };
    if secrets.password.is_some() || secrets.client_secret.is_some() {
        return Err(ServiceError::Input);
    }
    let identity = cfg.identity()?;
    let parsed = if let Some(p) = proof.as_ref() {
        let other = p.invitation.identity()?;
        if other.issuer() != identity.issuer() || other.resource() != identity.resource() {
            return Err(ServiceError::Identity);
        }
        let public = decode(&p.public_key, 32)?;
        let signature = decode(&p.signature, 64)?;
        // Verify shape and configured domain before opening a database connection.
        let message = enrollment_message(&identity, &p.invitation.token, &public)
            .map_err(|_| ServiceError::Input)?;
        ring::signature::UnparsedPublicKey::new(&ring::signature::ED25519, &public)
            .verify(&message, &signature)
            .map_err(|_| ServiceError::Provisioning)?;
        Some((public, signature))
    } else {
        None
    };
    let device = if revoke {
        let id = f
            .value("--device")?
            .parse::<Uuid>()
            .map_err(|_| ServiceError::Arguments)?;
        if id.is_nil() {
            return Err(ServiceError::Arguments);
        }
        Some(id)
    } else {
        None
    };
    // Reserve a create-new destination before any invitation is issued or consumed.
    let output = if revoke {
        None
    } else {
        Some(Output::open(&f)?)
    };
    let store = lifecycle::open(&cfg, &secrets, false).await?;
    drop(secrets);
    lifecycle::ready(&store, &cfg).await?;
    let bytes = if let Some(device) = device {
        store
            .registered_device(device)
            .await
            .map_err(|_| ServiceError::Provisioning)?;
        store
            .revoke_device(device)
            .await
            .map_err(|_| ServiceError::Provisioning)?;
        None
    } else if let (Some(p), Some((public, signature))) = (proof.as_ref(), parsed) {
        let d = store
            .redeem_device_invitation(&p.invitation.token, &public, &signature)
            .await
            .map_err(|_| ServiceError::Provisioning)?;
        Some(serialize(&Connection {
            version: 1,
            origin: cfg.origin,
            prefix: cfg.prefix,
            connector: d.connector,
            device: d.id,
            device_epoch: d.epoch,
            authority_epoch: 1,
            public_key: URL_SAFE_NO_PAD.encode(public),
            run_seconds: 3600,
        })?)
    } else {
        let invite = store
            .create_device_invitation()
            .await
            .map_err(|_| ServiceError::Provisioning)?;
        Some(serialize(&Invitation {
            version: 1,
            origin: cfg.origin,
            prefix: cfg.prefix,
            connector: cfg.connector,
            token: invite.token.expose().to_owned(),
        })?)
    };
    store.pool.close().await;
    if let (Some(output), Some(bytes)) = (output, bytes) {
        output.write(&bytes)?;
    }
    eprintln!("{}", serde_json::json!({"ok":true,"operation":f.command}));
    Ok(())
}
pub(super) fn decode(value: &str, length: usize) -> Result<Vec<u8>> {
    let bytes = URL_SAFE_NO_PAD
        .decode(value)
        .map_err(|_| ServiceError::Input)?;
    if bytes.len() != length || URL_SAFE_NO_PAD.encode(&bytes) != value {
        return Err(ServiceError::Input);
    }
    Ok(bytes)
}

// Native ConnectionConfig has a narrower public identity grammar than legacy gateway
// configuration. Reject before issuing/consuming an invitation, never emit an unimportable profile.
fn validate_native_identity(identity: &PublicIdentity) -> Result<()> {
    let route = identity
        .prefix()
        .strip_prefix('/')
        .ok_or(ServiceError::Configuration)?;
    if identity.origin().len() > 512
        || !identity.origin().is_ascii()
        || route.starts_with('-')
        || route.ends_with('-')
    {
        return Err(ServiceError::Configuration);
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bootstrap_identity_is_compatible_with_native_profile_grammar() {
        let valid = PublicIdentity::new(
            "https://gateway.example.invalid",
            "/coding-tools",
            Uuid::from_u128(1),
        )
        .unwrap();
        assert!(validate_native_identity(&valid).is_ok());
        for prefix in ["/-coding-tools", "/coding-tools-"] {
            let id = PublicIdentity::new(
                "https://gateway.example.invalid",
                prefix,
                Uuid::from_u128(1),
            )
            .unwrap();
            assert!(validate_native_identity(&id).is_err());
        }
    }
}
