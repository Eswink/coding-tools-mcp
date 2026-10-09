//! Exact data binding; no grant/Claim/root/native-resource constructor.
use super::{chunks::ImmutableChunks, path};
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct RunBinding {
    pub host: String,
    pub profile: String,
    pub caller: String,
    pub source: String,
    pub session: String,
    pub operation: String,
    pub input_relative: String,
    pub output_parent: String,
    pub output_leaf: String,
}
pub(crate) fn leaf(text: &str) -> bool { path::component(text) }
fn uuid(text: &str) -> bool {
    uuid::Uuid::parse_str(text).is_ok_and(|id| !id.is_nil() && id.to_string() == text)
}
fn label(text: &str, limit: usize) -> bool {
    !text.is_empty() && text.len() <= limit && !text.chars().any(char::is_control)
}
impl RunBinding {
    pub(crate) fn valid(&self) -> bool {
        uuid(&self.host) && uuid(&self.session) && uuid(&self.operation)
            && label(&self.profile, 128) && label(&self.caller, 256)
            && self.source.len() == 40
            && self.source.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
            && path::components(&self.input_relative).is_ok()
            && path::components(&self.output_parent).is_ok() && leaf(&self.output_leaf)
    }
}
pub(crate) struct InputTransfer {
    binding: RunBinding,
    bytes: ImmutableChunks,
    size: usize,
    digest: [u8; 32],
    cleared: bool,
}
impl InputTransfer {
    pub(super) fn new(binding: RunBinding, bytes: ImmutableChunks) -> Result<Self, &'static str> {
        if !binding.valid() { return Err("WINDOWS_INPUT_TRANSFER_BINDING_REJECTED"); }
        let size = bytes.size();
        let digest = bytes.digest()?;
        Ok(Self { binding, bytes, size, digest, cleared: false })
    }
    pub(crate) fn matches(&self, binding: &RunBinding) -> bool {
        !self.cleared && binding.valid() && &self.binding == binding
            && self.bytes.size() == self.size && self.bytes.digest() == Ok(self.digest)
    }
    pub(crate) fn clear_after_checked_close(&mut self) {
        self.bytes.clear_after_checked_close(); self.cleared = true;
    }
}
