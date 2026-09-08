#[path = "系统密钥v6.rs"]
mod key_store;
#[path = "配置加密v6.rs"]
mod encrypted_config;
#[path = "配置文件v6.rs"]
mod secure_file;
#[path = "配置锁v2.rs"]
mod config_lock;
mod migrate;
mod model;
mod store;

pub use model::AppData;
pub use store::DataStore;

#[cfg(test)]
#[path = "迁移可见性回归v4.rs"]
mod migration_visibility_tests;
