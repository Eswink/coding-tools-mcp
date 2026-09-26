//! Durable cloud request admission and no-replay reconciliation.
//!
//! This module never executes a tool. It records only bounded metadata and hashes,
//! and it treats the device-signed local projection plus authenticated channel as
//! prerequisites, not as a substitute for the future Agent's local execution gate.
mod canonical;
mod store;

pub use store::{
    AdmissionDecision, AdmissionDeny, AdmissionReceipt, AdmissionRequest, AdmissionStore,
    RequestClass, RequestState, MAX_ARGUMENT_BYTES, MAX_DEADLINE_SECONDS, MAX_IN_FLIGHT,
};
