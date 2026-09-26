//! Authenticated native-device control link. No local executor or public approval API.
//! WebSocket presence, projected eligibility and local execution authority are separate.
mod protocol;
mod store;
mod transport;
pub use protocol::{
    connect_message, verify_connect, ConnectChallenge, ConnectClaims, ControlMessage,
    SignedPayload, AUTH_SECONDS, LEASE_SECONDS, MAX_AGE_SECONDS, MAX_MESSAGE, SUBPROTOCOL,
};
pub use store::{ChannelController, ChannelSession, PendingConnection};
pub use transport::{agent_channel_routes, managed_agent_channel_routes, ChannelShutdown};
