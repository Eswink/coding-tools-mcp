use super::{signer::RecoverySigner, AgentError, Result};
use std::{
    fs::{File, OpenOptions},
    io::{Read, Write},
    path::Path,
};
const RECORD: usize = 104;
const MAX_RECORDS: usize = 32768;
pub(super) struct RevisionJournal {
    file: File,
    revision: i64,
}
impl RevisionJournal {
    pub(super) fn open(path: &Path, signer: &RecoverySigner, initialize: bool) -> Result<Self> {
        if !path.is_absolute() {
            return Err(AgentError::Journal);
        }
        let parent = path.parent().ok_or(AgentError::Journal)?;
        if !parent.is_dir() {
            return Err(AgentError::Journal);
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            // SAFETY: geteuid takes no arguments and touches no caller memory.
            let uid = unsafe { libc::geteuid() };
            let meta = parent.metadata().map_err(|_| AgentError::Journal)?;
            if meta.uid() != uid
                || meta.mode() & 0o022 != 0
                || parent.canonicalize().map_err(|_| AgentError::Journal)? != parent
            {
                return Err(AgentError::Journal);
            }
        }
        if !initialize {
            let m = std::fs::symlink_metadata(path).map_err(|_| AgentError::Journal)?;
            if !m.is_file() || m.file_type().is_symlink() {
                return Err(AgentError::Journal);
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
        let mut file = options.open(path).map_err(|_| AgentError::Journal)?;
        file.try_lock().map_err(|_| AgentError::Journal)?;
        let meta = file.metadata().map_err(|_| AgentError::Journal)?;
        if !meta.is_file() || meta.len() as usize > RECORD * MAX_RECORDS {
            return Err(AgentError::Journal);
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if meta.mode() & 0o077 != 0 || meta.nlink() != 1 {
                return Err(AgentError::Journal);
            }
            // SAFETY: geteuid has no unsafe input.
            if meta.uid() != unsafe { libc::geteuid() } {
                return Err(AgentError::Journal);
            }
        }
        if initialize {
            file.write_all(&signer.journal_record(0)?)
                .map_err(|_| AgentError::Journal)?;
            file.sync_all().map_err(|_| AgentError::Journal)?;
            #[cfg(unix)]
            File::open(parent)
                .and_then(|f| f.sync_all())
                .map_err(|_| AgentError::Journal)?;
            return Ok(Self { file, revision: 0 });
        }
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take((RECORD * MAX_RECORDS + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| AgentError::Journal)?;
        if bytes.is_empty() || bytes.len() % RECORD != 0 || bytes.len() > RECORD * MAX_RECORDS {
            return Err(AgentError::Journal);
        }
        for (n, record) in bytes.as_chunks::<RECORD>().0.iter().enumerate() {
            signer.verify_record(record, n as i64)?;
        }
        Ok(Self {
            file,
            revision: (bytes.len() / RECORD - 1) as i64,
        })
    }
    pub(super) fn next(&mut self, signer: &RecoverySigner) -> Result<i64> {
        let revision = self.revision.checked_add(1).ok_or(AgentError::Journal)?;
        if revision as usize >= MAX_RECORDS {
            return Err(AgentError::Journal);
        }
        self.file
            .write_all(&signer.journal_record(revision)?)
            .map_err(|_| AgentError::Journal)?;
        self.file.sync_all().map_err(|_| AgentError::Journal)?;
        self.revision = revision;
        Ok(revision)
    }
}
