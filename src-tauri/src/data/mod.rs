#[path = "配置锁v2.rs"]
mod config_lock;
mod migrate;
mod model;
mod store;

pub use model::AppData;
pub use store::DataStore;
