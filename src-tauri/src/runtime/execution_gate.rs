use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionAvailability {
    Online,
    Offline,
}

impl ExecutionAvailability {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Online => "online",
            Self::Offline => "offline",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExecutionGateSnapshot {
    pub availability: ExecutionAvailability,
    pub in_flight: usize,
}

/// Admission fence for remote workspace execution.
///
/// The mutex is held only while deciding admission or changing availability.
/// Tool execution never runs while this lock is held.
#[derive(Debug)]
pub struct WorkspaceExecutionGate {
    state: Mutex<GateState>,
}

#[derive(Debug)]
struct GateState {
    availability: ExecutionAvailability,
    in_flight: usize,
}

impl Default for WorkspaceExecutionGate {
    fn default() -> Self {
        Self {
            state: Mutex::new(GateState {
                availability: ExecutionAvailability::Online,
                in_flight: 0,
            }),
        }
    }
}

impl WorkspaceExecutionGate {
    pub fn shared() -> Arc<Self> {
        Arc::new(Self::default())
    }

    pub fn snapshot(&self) -> ExecutionGateSnapshot {
        let state = self.state.lock().expect("workspace execution gate");
        ExecutionGateSnapshot {
            availability: state.availability,
            in_flight: state.in_flight,
        }
    }

    /// Linearization point for new remote execution.
    ///
    /// A permit acquired before pause commits may finish. Once pause returns,
    /// subsequent admissions fail until resume.
    pub fn try_admit(self: &Arc<Self>) -> Result<ExecutionPermit, &'static str> {
        let mut state = self.state.lock().map_err(|_| "WORKSPACE_EXECUTION_UNAVAILABLE")?;
        if state.availability == ExecutionAvailability::Offline {
            return Err("WORKSPACE_OFFLINE");
        }
        state.in_flight = state.in_flight.saturating_add(1);
        Ok(ExecutionPermit { gate: self.clone() })
    }

    pub fn pause(&self) -> Result<ExecutionGateSnapshot, &'static str> {
        let mut state = self.state.lock().map_err(|_| "WORKSPACE_EXECUTION_UNAVAILABLE")?;
        state.availability = ExecutionAvailability::Offline;
        Ok(ExecutionGateSnapshot {
            availability: state.availability,
            in_flight: state.in_flight,
        })
    }

    pub fn resume(&self) -> Result<ExecutionGateSnapshot, &'static str> {
        let mut state = self.state.lock().map_err(|_| "WORKSPACE_EXECUTION_UNAVAILABLE")?;
        state.availability = ExecutionAvailability::Online;
        Ok(ExecutionGateSnapshot {
            availability: state.availability,
            in_flight: state.in_flight,
        })
    }
}

pub struct ExecutionPermit {
    gate: Arc<WorkspaceExecutionGate>,
}

impl Drop for ExecutionPermit {
    fn drop(&mut self) {
        if let Ok(mut state) = self.gate.state.lock() {
            state.in_flight = state.in_flight.saturating_sub(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pause_blocks_new_admission_without_revoking_existing_permit() {
        let gate = WorkspaceExecutionGate::shared();
        let permit = gate.try_admit().expect("initial admission");
        assert_eq!(gate.snapshot().in_flight, 1);

        let paused = gate.pause().expect("pause");
        assert_eq!(paused.availability, ExecutionAvailability::Offline);
        assert_eq!(paused.in_flight, 1);
        assert_eq!(gate.try_admit().err(), Some("WORKSPACE_OFFLINE"));

        drop(permit);
        assert_eq!(gate.snapshot().in_flight, 0);
        assert_eq!(gate.snapshot().availability, ExecutionAvailability::Offline);
    }

    #[test]
    fn resume_reopens_admission() {
        let gate = WorkspaceExecutionGate::shared();
        gate.pause().expect("pause");
        gate.resume().expect("resume");
        let permit = gate.try_admit().expect("admission after resume");
        assert_eq!(gate.snapshot().availability, ExecutionAvailability::Online);
        assert_eq!(gate.snapshot().in_flight, 1);
        drop(permit);
        assert_eq!(gate.snapshot().in_flight, 0);
    }

    #[test]
    fn concurrent_pause_has_a_single_admission_boundary() {
        let gate = WorkspaceExecutionGate::shared();
        let first = gate.try_admit().expect("first admission");
        let clone = gate.clone();
        let paused = std::thread::spawn(move || clone.pause().expect("pause"))
            .join()
            .expect("pause thread");
        assert_eq!(paused.in_flight, 1);
        assert!(gate.try_admit().is_err());
        drop(first);
        assert_eq!(gate.snapshot().in_flight, 0);
    }
}
