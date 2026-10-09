//! Output bytes are DATA. Reader EOF/consumption confer no native IO retirement,
//! handle ownership, workspace writeback, publication or authorization proof.
use crate::tools::windows_vm::input::owned_run::RunBinding;
use sha2::{Digest, Sha256};
use std::io::Read;
use std::sync::{atomic::{AtomicBool, Ordering}, Arc, Mutex};

const OUTPUT_CHUNK: usize = 32_768;
const OUTPUT_MAXIMUM: usize = 1_048_576;
const OUTPUT_HEADER: usize = 72;
const OUTPUT_FRAMED_MAXIMUM: usize = OUTPUT_MAXIMUM + 33 * OUTPUT_HEADER;

/// Stop-only shared DATA cancellation. No reset API or native close capability.
#[derive(Clone, Default)]
pub(crate) struct OutputDataCancellation(Arc<AtomicBool>);
impl OutputDataCancellation {
    pub(crate) fn cancel_output_data(&self) { self.0.store(true, Ordering::Release); }
}

struct OutputDataState {
    binding: RunBinding,
    data: Vec<u8>,
    total: usize,
    digest: [u8; 32],
    cancellation: OutputDataCancellation,
    consumed: bool,
}

/// Every clone shares all private state, including terminal failed attempts.
#[derive(Clone)]
pub(crate) struct OutputDataTransfer(Arc<Mutex<OutputDataState>>);
impl OutputDataTransfer {
    pub(crate) fn take_output_data(&self, binding: &RunBinding) -> Result<Vec<u8>, &'static str> {
        let mut state = self.0.lock().map_err(|_| "WINDOWS_OUTPUT_DATA_POISONED")?;
        if state.consumed { return Err("WINDOWS_OUTPUT_DATA_ALREADY_CONSUMED"); }
        // Terminal before checking even a foreign/cancelled/invalid attempt.
        state.consumed = true;
        if state.cancellation.0.load(Ordering::Acquire) || !binding.valid()
            || &state.binding != binding || state.data.len() != state.total
            || state.total > OUTPUT_MAXIMUM
            || <[u8; 32]>::from(Sha256::digest(&state.data)) != state.digest
        { return Err("WINDOWS_OUTPUT_DATA_TAKE_REJECTED"); }
        let detached = state.data.clone();
        if state.cancellation.0.load(Ordering::Acquire) {
            return Err("WINDOWS_OUTPUT_DATA_CANCELLED");
        }
        Ok(detached)
    }
}

fn output_binding_digest(binding: &RunBinding) -> Result<[u8; 32], &'static str> {
    if !binding.valid() { return Err("WINDOWS_OUTPUT_DATA_BINDING_REJECTED"); }
    let mut hash = Sha256::new();
    hash.update(b"CTM-DATA-BINDING-1");
    for field in [&binding.host, &binding.profile, &binding.caller, &binding.source,
        &binding.session, &binding.operation, &binding.input_relative,
        &binding.output_parent, &binding.output_leaf]
    {
        // The unchanged validator bounds each UTF8 byte length below u32::MAX.
        hash.update((field.len() as u32).to_le_bytes());
        hash.update(field.as_bytes());
    }
    Ok(hash.finalize().into())
}

fn read_output_exact<R: Read>(reader: &mut R, bytes: &mut [u8],
    cancellation: &OutputDataCancellation) -> Result<(), &'static str>
{
    let mut position = 0;
    while position < bytes.len() {
        if cancellation.0.load(Ordering::Acquire) { return Err("WINDOWS_OUTPUT_DATA_CANCELLED"); }
        // A synchronous blocking Read cannot be interrupted by a DATA token.
        let count = reader.read(&mut bytes[position..]).map_err(|_| "WINDOWS_OUTPUT_DATA_READ_FAILED")?;
        if cancellation.0.load(Ordering::Acquire) { return Err("WINDOWS_OUTPUT_DATA_CANCELLED"); }
        if count == 0 || count > bytes.len() - position {
            return Err("WINDOWS_OUTPUT_DATA_TRUNCATED");
        }
        position += count;
    }
    Ok(())
}

fn finish_output_eof<R: Read>(reader: &mut R,
    cancellation: &OutputDataCancellation) -> Result<(), &'static str>
{
    if cancellation.0.load(Ordering::Acquire) { return Err("WINDOWS_OUTPUT_DATA_CANCELLED"); }
    let mut extra = [0u8; 1];
    let count = reader.read(&mut extra).map_err(|_| "WINDOWS_OUTPUT_DATA_EOF_FAILED")?;
    if cancellation.0.load(Ordering::Acquire) { return Err("WINDOWS_OUTPUT_DATA_CANCELLED"); }
    if count != 0 { return Err("WINDOWS_OUTPUT_DATA_TRAILING_BYTES"); }
    Ok(())
}

pub(crate) fn receive_output_data<R: Read>(binding: RunBinding, total: u64,
    digest: [u8; 32], reader: &mut R, cancellation: OutputDataCancellation)
    -> Result<OutputDataTransfer, &'static str>
{
    if total > OUTPUT_MAXIMUM as u64 || cancellation.0.load(Ordering::Acquire) {
        return Err("WINDOWS_OUTPUT_DATA_MANIFEST_REJECTED");
    }
    let binding_hash = output_binding_digest(&binding)?;
    let total = total as usize;
    let mut data = Vec::with_capacity(total);
    let mut sequence = 0u32;
    let mut framed = 0usize;
    loop {
        let mut header = [0u8; OUTPUT_HEADER];
        read_output_exact(reader, &mut header, &cancellation)?;
        if &header[..8] != b"CTMWIO02" || header[8] != 2 || header[9] > 1
            || header[10..12] != [0, 0] || header[36..40] != [0, 0, 0, 0]
            || header[40..72] != binding_hash
        { return Err("WINDOWS_OUTPUT_DATA_HEADER_REJECTED"); }
        let observed_sequence = u32::from_le_bytes([header[12], header[13], header[14], header[15]]);
        let offset = u64::from_le_bytes([header[16],header[17],header[18],header[19],header[20],header[21],header[22],header[23]]);
        let observed_total = u64::from_le_bytes([header[24],header[25],header[26],header[27],header[28],header[29],header[30],header[31]]);
        let count = u32::from_le_bytes([header[32],header[33],header[34],header[35]]) as usize;
        if count > OUTPUT_CHUNK || sequence > 32 || observed_sequence != sequence
            || offset != data.len() as u64 || observed_total != total as u64
            || framed + OUTPUT_HEADER + count > OUTPUT_FRAMED_MAXIMUM
        { return Err("WINDOWS_OUTPUT_DATA_SEQUENCE_OR_BOUND_REJECTED"); }
        framed += OUTPUT_HEADER + count;
        if header[9] == 1 {
            if count != 0 || data.len() != total || <[u8; 32]>::from(Sha256::digest(&data)) != digest {
                return Err("WINDOWS_OUTPUT_DATA_FINAL_HASH_REJECTED");
            }
            finish_output_eof(reader, &cancellation)?;
            if cancellation.0.load(Ordering::Acquire) { return Err("WINDOWS_OUTPUT_DATA_CANCELLED"); }
            return Ok(OutputDataTransfer(Arc::new(Mutex::new(OutputDataState {
                binding, data, total, digest, cancellation, consumed: false,
            }))));
        }
        if count == 0 || sequence == 32 || data.len() + count > total {
            return Err("WINDOWS_OUTPUT_DATA_BODY_BOUND_REJECTED");
        }
        let old = data.len();
        data.resize(old + count, 0);
        read_output_exact(reader, &mut data[old..], &cancellation)?;
        sequence += 1;
    }
}

#[cfg(test)]
#[path = "data_tests.rs"]
mod data_tests;
