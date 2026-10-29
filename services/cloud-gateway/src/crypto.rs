use crate::{IdentityError, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{
    digest, hmac,
    rand::{SecureRandom, SystemRandom},
};
use zeroize::Zeroizing;

/// Intentionally redacted Debug; serialization requires explicit expose().
#[derive(Clone)]
pub struct Secret(Zeroizing<String>);
impl Secret {
    pub fn new(value: String) -> Self {
        Self(Zeroizing::new(value))
    }
    pub fn expose(&self) -> &str {
        &self.0
    }
    pub fn random() -> Result<Self> {
        let mut bytes = [0u8; 32];
        SystemRandom::new()
            .fill(&mut bytes)
            .map_err(|_| IdentityError::StoreUnavailable)?;
        Ok(Self::new(URL_SAFE_NO_PAD.encode(bytes)))
    }
}
impl std::fmt::Debug for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Secret([REDACTED])")
    }
}
#[derive(Clone)]
pub struct SecretKey(Zeroizing<[u8; 32]>);
impl SecretKey {
    pub fn new(bytes: [u8; 32]) -> Result<Self> {
        if bytes == [0; 32] {
            return Err(IdentityError::InvalidConfig);
        }
        Ok(Self(Zeroizing::new(bytes)))
    }
    pub fn digest(&self, domain: &str, value: &[u8]) -> Vec<u8> {
        let key = hmac::Key::new(hmac::HMAC_SHA256, self.0.as_ref());
        let mut ctx = hmac::Context::with_key(&key);
        ctx.update(&(domain.len() as u64).to_be_bytes());
        ctx.update(domain.as_bytes());
        ctx.update(value);
        ctx.sign().as_ref().to_vec()
    }
    pub fn matches(&self, domain: &str, value: &[u8], expected: &[u8]) -> bool {
        let key = hmac::Key::new(hmac::HMAC_SHA256, self.0.as_ref());
        let mut data = (domain.len() as u64).to_be_bytes().to_vec();
        data.extend_from_slice(domain.as_bytes());
        data.extend_from_slice(value);
        hmac::verify(&key, &data, expected).is_ok()
    }
}
impl std::fmt::Debug for SecretKey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("SecretKey([REDACTED])")
    }
}
pub fn pkce_challenge(verifier: &str) -> Result<String> {
    if !(43..=128).contains(&verifier.len())
        || !verifier
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-._~".contains(&b))
    {
        return Err(IdentityError::InvalidRequest);
    }
    Ok(URL_SAFE_NO_PAD.encode(digest::digest(&digest::SHA256, verifier.as_bytes()).as_ref()))
}
pub(crate) fn valid_digest(value: &str) -> bool {
    value.len() == 43 && URL_SAFE_NO_PAD.decode(value).is_ok_and(|v| v.len() == 32)
}
