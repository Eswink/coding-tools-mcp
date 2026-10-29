//! Device-only offline commands. No database credentials or remote requests.
use super::{
    enrollment::{Invitation, Proof},
    enrollment_io::{serialize, Flags, Output},
    Result, ServiceError,
};
use crate::PublicIdentity;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use zeroize::{Zeroize, Zeroizing};
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Identity {
    origin: String,
    prefix: String,
    connector: Uuid,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Key {
    pkcs8: String,
}
impl Drop for Key {
    fn drop(&mut self) {
        self.pkcs8.zeroize();
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Bundle {
    invitation: Invitation,
    key: Key,
}
pub(crate) fn run(args: Vec<String>) -> Result<()> {
    let f = Flags::parse(
        args,
        &[
            "--config",
            "--input-file",
            "--input-stdin",
            "--key-file",
            "--key-stdin",
            "--bundle-stdin",
            "--output-file",
            "--output-stdout",
        ],
    )?;
    if f.command == "generate-key" {
        if [
            "--config",
            "--input-file",
            "--input-stdin",
            "--key-file",
            "--key-stdin",
            "--bundle-stdin",
        ]
        .iter()
        .any(|s| f.has(s))
        {
            return Err(ServiceError::Arguments);
        }
        let output = Output::open(&f)?;
        let key = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new())
            .map_err(|_| ServiceError::Input)?;
        output.write(&serialize(&Key {
            pkcs8: URL_SAFE_NO_PAD.encode(key.as_ref()),
        })?)?;
    } else if f.command == "prove-enrollment" {
        // Operator-pinned identity is distinct from the received invitation.
        let expected: Identity = serde_json::from_slice(&super::enrollment_io::read_public_config(
            &f.path("--config")?,
        )?)
        .map_err(|_| ServiceError::Input)?;
        let expected = PublicIdentity::new(&expected.origin, &expected.prefix, expected.connector)
            .map_err(|_| ServiceError::Input)?;
        let (invitation, key) = if f.has("--bundle-stdin") {
            if ["--input-file", "--input-stdin", "--key-file", "--key-stdin"]
                .iter()
                .any(|s| f.has(s))
            {
                return Err(ServiceError::Arguments);
            }
            let bundle: Bundle =
                serde_json::from_slice(&f.document("--unused-file", "--bundle-stdin")?)
                    .map_err(|_| ServiceError::Input)?;
            (bundle.invitation, bundle.key)
        } else {
            let invitation: Invitation =
                serde_json::from_slice(&f.document("--input-file", "--input-stdin")?)
                    .map_err(|_| ServiceError::Input)?;
            let raw = f.document("--key-file", "--key-stdin")?;
            if raw.len() > 4096 {
                return Err(ServiceError::Input);
            }
            let key: Key = serde_json::from_slice(&raw).map_err(|_| ServiceError::Input)?;
            (invitation, key)
        };
        if key.pkcs8.len() > 4096 {
            return Err(ServiceError::Input);
        }
        let identity = invitation.identity()?;
        if identity.issuer() != expected.issuer() || identity.resource() != expected.resource() {
            return Err(ServiceError::Identity);
        }
        let bytes = Zeroizing::new(
            URL_SAFE_NO_PAD
                .decode(&key.pkcs8)
                .map_err(|_| ServiceError::Input)?,
        );
        if URL_SAFE_NO_PAD.encode(&bytes) != key.pkcs8 {
            return Err(ServiceError::Input);
        }
        let pair = Ed25519KeyPair::from_pkcs8(&bytes).map_err(|_| ServiceError::Input)?;
        let message = crate::device::enrollment_message(
            &identity,
            &invitation.token,
            pair.public_key().as_ref(),
        )
        .map_err(|_| ServiceError::Input)?;
        let proof = Proof {
            invitation,
            public_key: URL_SAFE_NO_PAD.encode(pair.public_key().as_ref()),
            signature: URL_SAFE_NO_PAD.encode(pair.sign(&message).as_ref()),
        };
        Output::open(&f)?.write(&serialize(&proof)?)?;
    } else {
        return Err(ServiceError::Arguments);
    }
    eprintln!("{}", serde_json::json!({"ok":true,"operation":f.command}));
    Ok(())
}
