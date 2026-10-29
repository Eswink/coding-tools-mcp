use super::{BrowserAuth, BrowserError, BrowserRequest, Result};
use ring::{
    aead,
    rand::{SecureRandom, SystemRandom},
};
use zeroize::Zeroizing;

impl BrowserAuth {
    fn encryption_key(&self) -> Result<aead::LessSafeKey> {
        let bytes = Zeroizing::new(self.store.key.digest("browser-aead-key-v1", b"AES-256-GCM"));
        aead::UnboundKey::new(&aead::AES_256_GCM, &bytes)
            .map(aead::LessSafeKey::new)
            .map_err(|_| BrowserError::InvalidConfig)
    }
    fn aad(&self) -> Vec<u8> {
        format!(
            "ctm/browser/v1\n{}\n{}",
            self.store.identity.issuer(),
            self.store.identity.resource()
        )
        .into_bytes()
    }
    pub(crate) fn seal(&self, request: &BrowserRequest) -> Result<Vec<u8>> {
        let mut nonce = [0; 12];
        SystemRandom::new()
            .fill(&mut nonce)
            .map_err(|_| BrowserError::StoreUnavailable)?;
        let mut bytes =
            Zeroizing::new(serde_json::to_vec(request).map_err(|_| BrowserError::Rejected)?);
        self.encryption_key()?
            .seal_in_place_append_tag(
                aead::Nonce::assume_unique_for_key(nonce),
                aead::Aad::from(self.aad()),
                &mut *bytes,
            )
            .map_err(|_| BrowserError::StoreUnavailable)?;
        let mut sealed = nonce.to_vec();
        sealed.extend_from_slice(&bytes);
        Ok(sealed)
    }
    pub(crate) fn unseal(&self, bytes: &[u8]) -> Result<BrowserRequest> {
        if !(28..=8192).contains(&bytes.len()) {
            return Err(BrowserError::Rejected);
        }
        let nonce: [u8; 12] = bytes[..12].try_into().map_err(|_| BrowserError::Rejected)?;
        let mut body = Zeroizing::new(bytes[12..].to_vec());
        let plaintext = self
            .encryption_key()?
            .open_in_place(
                aead::Nonce::assume_unique_for_key(nonce),
                aead::Aad::from(self.aad()),
                &mut body,
            )
            .map_err(|_| BrowserError::Rejected)?;
        serde_json::from_slice(plaintext).map_err(|_| BrowserError::Rejected)
    }
}
