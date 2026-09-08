//! Authenticated encryption envelope. A whole snapshot is protected, including
//! proxy credentials and unknown extension fields, not only known Secret maps.
use std::path::Path;

use base64::{engine::general_purpose::STANDARD, Engine};
use ring::{aead, rand::{SecureRandom, SystemRandom}};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use zeroize::Zeroizing;

use crate::error::{AppError, AppResult};
use super::key_store::KeyStore;

pub(super) const MAX_PLAINTEXT: usize = 32 * 1024 * 1024;
pub(super) const MAX_DOCUMENT: u64 = 48 * 1024 * 1024;
const FORMAT: &str = "coding-tools-mcp.encrypted";
const ALGORITHM: &str = "AES-256-GCM";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Envelope {
    // Older guarded readers must reject, not deserialize an empty AppData.
    schema_version: u32,
    format: String,
    storage_version: u32,
    algorithm: String,
    pub(super) key_id: String,
    nonce: String,
    ciphertext: String,
}

fn invalid() -> AppError {
    AppError::Message("加密配置格式无效、认证失败或版本不支持；原文件已保留，禁止重置或明文降级。".into())
}

pub(super) fn parse_envelope(raw: &str) -> AppResult<Option<Envelope>> {
    if raw.len() as u64 > MAX_DOCUMENT { return Err(invalid()); }
    let value: serde_json::Value = serde_json::from_str(raw).map_err(|_| invalid())?;
    if value.get("format").is_none() && value.get("storage_version").is_none() {
        return Ok(None);
    }
    let envelope: Envelope = serde_json::from_str(raw).map_err(|_| invalid())?;
    if envelope.schema_version != 2 || envelope.storage_version != 1
        || envelope.format != FORMAT || envelope.algorithm != ALGORITHM
        || envelope.key_id.len() != 64
        || !envelope.key_id.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()) {
        return Err(invalid());
    }
    Ok(Some(envelope))
}

pub(super) fn key_id_for_path(path: &Path) -> AppResult<String> {
    // Creation is serialized by DataStore's cross-process configuration lock.
    let parent = path.parent().ok_or_else(invalid)?.canonicalize()?;
    let canonical = parent.join(path.file_name().ok_or_else(invalid)?);
    Ok(format!("{:x}", Sha256::digest(canonical.to_string_lossy().as_bytes())))
}

fn aad(id: &str) -> String {
    format!("{FORMAT}|2|1|{ALGORITHM}|{id}")
}

fn load_key(keys: &dyn KeyStore, id: &str) -> AppResult<Zeroizing<Vec<u8>>> {
    let key = keys.get(id)?.ok_or_else(|| AppError::Message(
        "配置加密密钥不存在；请使用原系统账户及其凭据备份恢复。未生成替代密钥，原文件已保留。".into()
    ))?;
    if key.len() != 32 { return Err(invalid()); }
    Ok(key)
}

fn cipher(key: &[u8]) -> AppResult<aead::LessSafeKey> {
    aead::UnboundKey::new(&aead::AES_256_GCM, key)
        .map(aead::LessSafeKey::new).map_err(|_| invalid())
}

pub(super) fn seal(
    plaintext: &str, id: &str, allow_create: bool, keys: &dyn KeyStore,
) -> AppResult<String> {
    if plaintext.len() > MAX_PLAINTEXT { return Err(invalid()); }
    if id.len() != 64 || !id.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()) {
        return Err(invalid());
    }
    let key = match keys.get(id)? {
        Some(key) => key,
        None if allow_create => {
            let mut key = Zeroizing::new(vec![0_u8; 32]);
            SystemRandom::new().fill(&mut key).map_err(|_| invalid())?;
            keys.set(id, &key)?;
            // A successful set alone is insufficient: confirm the backend persisted it.
            let saved = load_key(keys, id)?;
            if *saved != *key { return Err(invalid()); }
            key
        }
        None => return Err(AppError::Message("配置加密密钥丢失，拒绝覆盖已有密文；原文件已保留。".into())),
    };
    let cipher = cipher(&key)?;
    let mut nonce_bytes = [0_u8; aead::NONCE_LEN];
    // Independent CSPRNG nonces avoid reusing a persisted counter after restore.
    SystemRandom::new().fill(&mut nonce_bytes).map_err(|_| invalid())?;
    let nonce = aead::Nonce::assume_unique_for_key(nonce_bytes);
    let mut ciphertext = Zeroizing::new(plaintext.as_bytes().to_vec());
    cipher.seal_in_place_append_tag(nonce, aead::Aad::from(aad(id)), &mut *ciphertext)
        .map_err(|_| invalid())?;
    let envelope = Envelope {
        schema_version: 2, format: FORMAT.into(), storage_version: 1,
        algorithm: ALGORITHM.into(), key_id: id.into(), nonce: STANDARD.encode(nonce_bytes),
        ciphertext: STANDARD.encode(&*ciphertext),
    };
    serde_json::to_string_pretty(&envelope).map_err(|_| invalid())
}

pub(super) fn open(envelope: &Envelope, keys: &dyn KeyStore) -> AppResult<Zeroizing<String>> {
    let key = load_key(keys, &envelope.key_id)?;
    let nonce = STANDARD.decode(&envelope.nonce).map_err(|_| invalid())?;
    let nonce = aead::Nonce::try_assume_unique_for_key(&nonce).map_err(|_| invalid())?;
    let mut ciphertext = Zeroizing::new(STANDARD.decode(&envelope.ciphertext).map_err(|_| invalid())?);
    if ciphertext.len() > MAX_PLAINTEXT + aead::MAX_TAG_LEN { return Err(invalid()); }
    let cipher = cipher(&key)?;
    let plaintext = cipher.open_in_place(nonce, aead::Aad::from(aad(&envelope.key_id)), &mut ciphertext)
        .map_err(|_| invalid())?;
    String::from_utf8(plaintext.to_vec()).map(Zeroizing::new).map_err(|_| invalid())
}

#[cfg(test)]
#[path = "配置加密回归v6.rs"]
mod tests;
