//! Authenticated request routing, never cloud execution or local authorization.
mod broker;
mod wire;
pub use broker::DispatchError;
pub(crate) use broker::{now, Broker, Delivery, Registration, CAPACITY};
pub use wire::{
    ExecutionBinding, ExecutionReply, ExecutionRequest, PeerBinding, EXECUTION_VERSION,
    MAX_EXECUTION_ARGUMENTS, MAX_EXECUTION_RESULT,
};
#[cfg(test)]
mod tests;
