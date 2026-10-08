//! Frozen v1: typed host envelopes; guest bytes never confer lifecycle authority.
use base64::Engine;
use serde::{Deserialize, Deserializer, Serialize};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};

pub(super) const MAX_FRAME: usize = 65_536;
pub(super) const MAX_TOTAL: usize = 1_048_576;
pub(super) fn canonical_id(value: &str, v4: bool) -> bool {
    uuid::Uuid::parse_str(value).ok().is_some_and(|u| {
        !u.is_nil()
            && u.to_string() == value
            && (!v4 || (u.as_bytes()[6] >> 4 == 4 && u.as_bytes()[8] & 0xc0 == 0x80))
    })
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub(super) enum Fixture {
    Runtimes,
    LiveChild,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub(super) enum Op {
    Prepare,
    Start,
    Cancel,
    Finish,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub(super) enum Kind {
    Prepared,
    Creating,
    Running,
    Guest,
    Cleanup,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub(super) enum Quarantine {
    Written,
    Withheld,
    NotStarted,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Request {
    pub version: u32,
    pub source: String,
    pub session: String,
    pub seq: u64,
    pub op: Op,
    pub fixture: Fixture,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Event {
    pub version: u32,
    pub source: String,
    pub session: String,
    pub seq: u64,
    pub kind: Kind,
    pub vm_id: String,
    pub runtime_id: String,
    #[serde(deserialize_with = "required")]
    pub guest: Option<GuestResult>,
    #[serde(deserialize_with = "required")]
    pub cleanup: Option<Cleanup>,
    pub error: String,
}
fn required<'de, D: Deserializer<'de>, T: Deserialize<'de>>(d: D) -> Result<Option<T>, D::Error> {
    Option::<T>::deserialize(d)
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct GuestResult {
    pub cases: Vec<Case>,
    pub input_sha256: String,
    pub output_sha256: String,
    pub data_base64: String,
    pub child_alive: bool,
}
impl GuestResult {
    pub(super) fn valid_for(&self, session: &str) -> bool {
        let input = format!("ctm-synthetic:{session}");
        let output = input.to_ascii_uppercase();
        let names = ["cmd", "windows-powershell", "node", "pwsh"];
        self.input_sha256 == format!("{:x}", Sha256::digest(input.as_bytes()))
            && self.output_sha256 == format!("{:x}", Sha256::digest(output.as_bytes()))
            && base64::engine::general_purpose::STANDARD
                .decode(&self.data_base64)
                .is_ok_and(|bytes| bytes == output.as_bytes() && bytes.len() <= 1024)
            && if self.child_alive {
                self.cases.is_empty()
            } else {
                self.cases.len() == names.len()
                    && self.cases.iter().zip(names).all(|(case, name)| {
                        case.name == name
                            && case.passed
                            && case.exit_code == 23
                            && case.stderr.is_empty()
                            && case.stdout.len() <= MAX_FRAME
                    })
            }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Case {
    pub name: String,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub passed: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Cleanup {
    pub terminate_ok: bool,
    pub whole_vm_exited: bool,
    pub exit_ok: bool,
    pub close_ok: bool,
    pub guest_io_joined: bool,
    pub quarantine: Quarantine,
    pub input_sha256: String,
    pub output_sha256: String,
    pub owned_data_retained: bool,
    pub network_denial_proven: bool,
    pub workspace_integration: bool,
    pub production_admission: bool,
    pub errors: Vec<String>,
}
impl Cleanup {
    pub(super) fn retirable(
        &self,
        guest: Option<&GuestResult>,
        started: bool,
        cancelled: bool,
    ) -> bool {
        [
            self.terminate_ok,
            self.whole_vm_exited,
            self.exit_ok,
            self.close_ok,
            self.guest_io_joined,
        ] == [started; 5]
            && self.errors.is_empty()
            && !self.network_denial_proven
            && !self.workspace_integration
            && !self.production_admission
            && self.owned_data_retained
            && (self.quarantine == Quarantine::Written || self.output_sha256.is_empty())
            && if !started {
                cancelled && self.quarantine == Quarantine::NotStarted
            } else if cancelled {
                self.quarantine == Quarantine::Withheld
            } else {
                self.quarantine == Quarantine::Written
                    && guest.is_some_and(|g| {
                        !g.child_alive
                            && self.input_sha256 == g.input_sha256
                            && self.output_sha256 == g.output_sha256
                    })
            }
    }
}
pub(super) fn decode_frame(bytes: &[u8], total: &mut usize) -> Result<Event, String> {
    if bytes.len() < 4 {
        return Err("truncated frame header".into());
    }
    let n = u32::from_le_bytes(bytes[..4].try_into().unwrap()) as usize;
    *total = total.saturating_add(bytes.len());
    if n == 0 || n > MAX_FRAME || bytes.len() != n + 4 || *total > MAX_TOTAL {
        return Err("frame or aggregate bound".into());
    }
    let (mut depth, mut quoted, mut escape) = (0usize, false, false);
    for &b in &bytes[4..] {
        if quoted {
            if escape {
                escape = false;
            } else if b == b'\\' {
                escape = true;
            } else if b == b'"' {
                quoted = false;
            }
        } else if b == b'"' {
            quoted = true;
        } else if b == b'{' || b == b'[' {
            depth += 1;
            if depth > 8 {
                return Err("nesting bound".into());
            }
        } else if b == b'}' || b == b']' {
            depth = depth.saturating_sub(1);
        }
    }
    // Direct typed decoding preserves duplicate-field errors at every nested level.
    serde_json::from_slice(&bytes[4..]).map_err(|e| e.to_string())
}
pub(super) fn read_event(r: &mut impl Read, total: &mut usize) -> Result<Option<Event>, String> {
    let mut header = [0u8; 4];
    if r.read(&mut header[..1]).map_err(|e| e.to_string())? == 0 {
        return Ok(None);
    }
    r.read_exact(&mut header[1..]).map_err(|e| e.to_string())?;
    let n = u32::from_le_bytes(header) as usize;
    if n == 0 || n > MAX_FRAME || total.saturating_add(n + 4) > MAX_TOTAL {
        return Err("frame or aggregate bound".into());
    }
    let mut bytes = Vec::with_capacity(n + 4);
    bytes.extend_from_slice(&header);
    bytes.resize(n + 4, 0);
    r.read_exact(&mut bytes[4..]).map_err(|e| e.to_string())?;
    decode_frame(&bytes, total).map(Some)
}
pub(super) fn write_request(
    w: &mut impl Write,
    request: &Request,
    total: &mut usize,
) -> Result<(), String> {
    let body = serde_json::to_vec(request).map_err(|e| e.to_string())?;
    *total = total.saturating_add(body.len() + 4);
    if body.is_empty() || body.len() > MAX_FRAME || *total > MAX_TOTAL {
        return Err("request bound".into());
    }
    w.write_all(&(body.len() as u32).to_le_bytes())
        .and_then(|()| w.write_all(&body))
        .and_then(|()| w.flush())
        .map_err(|e| e.to_string())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum State {
    RegisteredNoEffects,
    BrokerPreparedNoHCS,
    CreatingMayExist,
    RunningOwnedVM,
    Terminating,
    ExitedAndIOJoined,
    QuarantineHandled,
    Retired,
}
pub(super) struct Validator {
    pub(super) source: String,
    pub(super) session: String,
    pub(super) seq: u64,
    pub(super) stage: State,
    pub(super) failed: bool,
    pub(super) started: bool,
    pub(super) creating: bool,
    pub(super) vm_id: String,
    pub(super) runtime_id: String,
    pub(super) guest: Option<GuestResult>,
    pub(super) cleanup: Option<Cleanup>,
    pub(super) trace: Vec<(u64, Kind)>,
}
impl Validator {
    pub(super) fn new(source: String, session: String) -> Self {
        Self {
            source,
            session,
            seq: 0,
            stage: State::RegisteredNoEffects,
            failed: false,
            started: false,
            creating: false,
            vm_id: String::new(),
            runtime_id: String::new(),
            guest: None,
            cleanup: None,
            trace: Vec::new(),
        }
    }
    pub(super) fn start_attempted(&mut self) {
        self.failed |= self.stage != State::BrokerPreparedNoHCS;
        self.started = true; // Set before even the first Start byte can be written.
        self.stage = State::CreatingMayExist;
    }
    pub(super) fn accept(&mut self, e: &Event) -> Result<(), String> {
        let valid = (|| {
            if self.failed
                || self.cleanup.is_some()
                || e.version != 1
                || e.source != self.source
                || e.session != self.session
                || e.seq != self.seq
                || !e.error.is_empty()
                || self.source.len() != 40
                || !self
                    .source
                    .bytes()
                    .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
                || !canonical_id(&e.session, true)
                || (e.kind == Kind::Guest) != e.guest.is_some()
                || (e.kind == Kind::Cleanup) != e.cleanup.is_some()
                || e.guest
                    .as_ref()
                    .is_some_and(|g| !g.valid_for(&self.session))
            {
                return false;
            }
            if self.vm_id.is_empty() {
                if e.kind != Kind::Prepared || !canonical_id(&e.vm_id, false) {
                    return false;
                }
            } else if e.vm_id != self.vm_id {
                return false;
            }
            if e.kind != Kind::Running && e.runtime_id != self.runtime_id {
                return false;
            }
            match e.kind {
                Kind::Prepared if self.stage == State::RegisteredNoEffects => {
                    self.vm_id = e.vm_id.clone();
                    self.stage = State::BrokerPreparedNoHCS;
                }
                Kind::Creating
                    if self.started && !self.creating && self.stage == State::CreatingMayExist =>
                {
                    self.creating = true;
                }
                Kind::Running
                    if self.creating
                        && self.stage == State::CreatingMayExist
                        && canonical_id(&e.runtime_id, false) =>
                {
                    self.runtime_id = e.runtime_id.clone();
                    self.stage = State::RunningOwnedVM;
                }
                Kind::Guest if self.stage == State::RunningOwnedVM && self.guest.is_none() => {
                    self.guest = e.guest.clone()
                }
                Kind::Cleanup => {
                    self.cleanup = e.cleanup.clone();
                    self.stage = State::Terminating;
                }
                _ => return false,
            }
            self.trace.push((e.seq, e.kind));
            self.seq += 1;
            true
        })();
        if valid {
            Ok(())
        } else {
            self.failed = true;
            Err("invalid/sticky host protocol".into())
        }
    }
    pub(super) fn finish(&mut self, host_joined: bool, helper_ok: bool, cancelled: bool) -> bool {
        let input_sha256 = format!(
            "{:x}",
            Sha256::digest(format!("ctm-synthetic:{}", self.session).as_bytes())
        );
        let valid = !self.failed
            && host_joined
            && helper_ok
            && self.cleanup.as_ref().is_some_and(|c| {
                c.input_sha256 == input_sha256
                    && c.retirable(self.guest.as_ref(), self.started, cancelled)
            });
        if valid {
            self.stage = State::ExitedAndIOJoined;
            self.stage = State::QuarantineHandled;
            self.stage = State::Retired;
        } else {
            self.failed = true;
        }
        valid
    }
}
