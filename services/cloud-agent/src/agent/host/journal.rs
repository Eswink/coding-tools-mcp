//! Signed append-only local dispatch claims and reserved projection revisions.
//! No payloads or results; ordinary cleanup never removes a claimed identity.
use super::super::{signer::RecoverySigner, AgentError};
use crate::execution::ExecutionRequest;
use ring::digest::{digest, SHA256};
use std::{
    collections::HashMap,
    fs::{File, OpenOptions},
    io::{Read, Write},
    path::Path,
};
use uuid::Uuid;

const HEADER: usize = 104;
const BODY: usize = 104;
const RECORD: usize = BODY + 64;
const MAX_RECORDS: u64 = 100_000;
const MAX_OPERATIONS: usize = 32_768;
const RESERVATION: i64 = 1024;
const RESERVE: u8 = 1;
const CLAIM: u8 = 2;
const COMPLETE: u8 = 3;

pub(super) struct HostJournal {
    file: File,
    chain: [u8; 32],
    records: u64,
    high: i64,
    next: i64,
    operations: HashMap<Uuid, ([u8; 32], bool)>,
    poisoned: bool,
}
impl HostJournal {
    pub fn open(
        path: &Path,
        signer: &RecoverySigner,
        initialize: bool,
    ) -> Result<Self, AgentError> {
        let err = || AgentError::Journal;
        if !path.is_absolute() {
            return Err(err());
        }
        let parent = path.parent().ok_or_else(err)?;
        if parent.canonicalize().map_err(|_| err())? != parent {
            return Err(err());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            let meta = parent.metadata().map_err(|_| err())?;
            // SAFETY: geteuid has no inputs or writable user memory.
            if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o022 != 0 {
                return Err(err());
            }
        }
        let mut options = OpenOptions::new();
        options.read(true).write(true);
        if initialize {
            options.create_new(true);
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options
                .mode(0o600)
                .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC);
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::OpenOptionsExt;
            options.custom_flags(0x0020_0000); // FILE_FLAG_OPEN_REPARSE_POINT
        }
        let mut file = options.open(path).map_err(|_| err())?;
        file.try_lock().map_err(|_| err())?;
        let meta = file.metadata().map_err(|_| err())?;
        if !meta.is_file()
            || meta.file_type().is_symlink()
            || meta.len() > HEADER as u64 + MAX_RECORDS * RECORD as u64
        {
            return Err(err());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if meta.mode() & 0o077 != 0
                || meta.nlink() != 1
                || meta.uid() != unsafe { libc::geteuid() }
            {
                return Err(err());
            }
        }
        let mut header = b"CTMHST01".to_vec();
        header.extend_from_slice(&signer.host_binding()?);
        header.extend_from_slice(&signer.host_record_signature(&header));
        if initialize {
            file.write_all(&header)
                .and_then(|_| file.sync_all())
                .map_err(|_| err())?;
            #[cfg(unix)]
            File::open(parent)
                .and_then(|f| f.sync_all())
                .map_err(|_| err())?;
        }
        use std::io::{Seek, SeekFrom};
        file.seek(SeekFrom::Start(0)).map_err(|_| err())?;
        let mut data = Vec::new();
        Read::by_ref(&mut file)
            .take((HEADER as u64 + MAX_RECORDS * RECORD as u64) + 1)
            .read_to_end(&mut data)
            .map_err(|_| err())?;
        if data.len() < HEADER
            || data[..HEADER] != header
            || !(data.len() - HEADER).is_multiple_of(RECORD)
            || data.len() as u64 > HEADER as u64 + MAX_RECORDS * RECORD as u64
        {
            return Err(err());
        }
        let mut journal = Self {
            file,
            chain: hash(&header),
            records: 0,
            high: 0,
            next: 1,
            operations: HashMap::new(),
            poisoned: false,
        };
        for bytes in data[HEADER..].as_chunks::<RECORD>().0 {
            if bytes[BODY..] != signer.host_record_signature(&bytes[..BODY]) {
                return Err(err());
            }
            journal.apply(&bytes[..BODY])?;
            journal.chain = hash(bytes);
        }
        // Skip the entire previously reserved block after every process attachment.
        journal.next = journal.high.checked_add(1).ok_or_else(err)?;
        Ok(journal)
    }
    fn apply(&mut self, body: &[u8]) -> Result<(), AgentError> {
        if body.len() != BODY {
            return Err(AgentError::Journal);
        }
        let count = u64::from_be_bytes(body[..8].try_into().map_err(|_| AgentError::Journal)?);
        let kind = body[8];
        let id = Uuid::from_bytes(body[16..32].try_into().map_err(|_| AgentError::Journal)?);
        let fp: [u8; 32] = body[32..64].try_into().map_err(|_| AgentError::Journal)?;
        let value = i64::from_be_bytes(body[64..72].try_into().map_err(|_| AgentError::Journal)?);
        if count != self.records.checked_add(1).ok_or(AgentError::Journal)?
            || count > MAX_RECORDS
            || body[9..16] != [0; 7]
            || body[72..104] != self.chain
        {
            return Err(AgentError::Journal);
        }
        match kind {
            RESERVE
                if id.is_nil()
                    && fp == [0; 32]
                    && self.high.checked_add(RESERVATION) == Some(value) =>
            {
                self.high = value;
            }
            CLAIM
                if !id.is_nil()
                    && value == 0
                    && self.operations.len() < MAX_OPERATIONS
                    && !self.operations.contains_key(&id) =>
            {
                self.operations.insert(id, (fp, false));
            }
            COMPLETE
                if !id.is_nil() && value == 0 && self.operations.get(&id) == Some(&(fp, false)) =>
            {
                self.operations.insert(id, (fp, true));
            }
            _ => return Err(AgentError::Journal),
        }
        self.records = count;
        Ok(())
    }
    fn append(
        &mut self,
        signer: &RecoverySigner,
        kind: u8,
        id: Uuid,
        fp: [u8; 32],
        value: i64,
    ) -> Result<(), AgentError> {
        if self.poisoned || self.records >= MAX_RECORDS {
            return Err(AgentError::Journal);
        }
        let mut body = Vec::with_capacity(BODY);
        body.extend_from_slice(&(self.records + 1).to_be_bytes());
        body.push(kind);
        body.extend_from_slice(&[0; 7]);
        body.extend_from_slice(id.as_bytes());
        body.extend_from_slice(&fp);
        body.extend_from_slice(&value.to_be_bytes());
        body.extend_from_slice(&self.chain);
        let mut record = body.clone();
        record.extend_from_slice(&signer.host_record_signature(&body));
        if self
            .file
            .write_all(&record)
            .and_then(|_| self.file.sync_all())
            .is_err()
        {
            self.poisoned = true;
            return Err(AgentError::Journal);
        }
        if self.apply(&body).is_err() {
            self.poisoned = true;
            return Err(AgentError::Journal);
        }
        self.chain = hash(&record);
        Ok(())
    }
    pub fn revision(&mut self, signer: &RecoverySigner) -> Result<i64, AgentError> {
        if self.poisoned {
            return Err(AgentError::Journal);
        }
        if self.next > self.high {
            let high = self
                .high
                .checked_add(RESERVATION)
                .ok_or(AgentError::Journal)?;
            self.append(signer, RESERVE, Uuid::nil(), [0; 32], high)?;
        }
        let n = self.next;
        self.next = self.next.checked_add(1).ok_or(AgentError::Journal)?;
        Ok(n)
    }
    pub fn claim(
        &mut self,
        signer: &RecoverySigner,
        request: &ExecutionRequest,
    ) -> Result<(), AgentError> {
        let fp = request_fingerprint(request)?;
        if self.poisoned {
            return Err(AgentError::Journal);
        }
        if self.operations.contains_key(&request.binding.request_id) {
            return Err(AgentError::Duplicate);
        }
        if self.operations.len() >= MAX_OPERATIONS {
            return Err(AgentError::Capacity);
        }
        self.append(signer, CLAIM, request.binding.request_id, fp, 0)
    }
    pub fn complete(
        &mut self,
        signer: &RecoverySigner,
        request: &ExecutionRequest,
    ) -> Result<(), AgentError> {
        let fp = request_fingerprint(request)?;
        if self.operations.get(&request.binding.request_id) != Some(&(fp, false)) {
            return Err(AgentError::Journal);
        }
        self.append(signer, COMPLETE, request.binding.request_id, fp, 0)
    }
}
fn hash(data: &[u8]) -> [u8; 32] {
    let mut out = [0; 32];
    out.copy_from_slice(digest(&SHA256, data).as_ref());
    out
}
fn request_fingerprint(request: &ExecutionRequest) -> Result<[u8; 32], AgentError> {
    let data = serde_json::to_vec(&request.binding).map_err(|_| AgentError::Protocol)?;
    Ok(hash(&data))
}
