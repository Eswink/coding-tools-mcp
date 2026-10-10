//! Checked retirement is explicit. Unknown/panic transfers whole owned assets.
pub(super) struct Retained<T> {
    owned: Option<Box<T>>,
    uncertain: fn(Box<T>),
}
impl<T> Retained<T> {
    pub fn new(owned: T, uncertain: fn(Box<T>)) -> Self {
        Self {
            owned: Some(Box::new(owned)),
            uncertain,
        }
    }
    pub fn get(&self) -> &T {
        self.owned.as_deref().expect("retained native assets")
    }
    pub fn get_mut(&mut self) -> &mut T {
        self.owned.as_deref_mut().expect("retained native assets")
    }
    /// Call only after actual checked closure/retirement succeeds.
    pub fn retire_known(mut self) {
        drop(self.owned.take());
    }
}
impl<T> Drop for Retained<T> {
    fn drop(&mut self) {
        if let Some(owned) = self.owned.take() {
            (self.uncertain)(owned);
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    struct Assets {
        drops: Arc<AtomicUsize>,
        bytes: Vec<u8>,
    }
    impl Drop for Assets {
        fn drop(&mut self) {
            self.drops.fetch_add(1, Ordering::SeqCst);
        }
    }
    fn hold(owned: Box<Assets>) {
        let _ = Box::leak(owned);
    }
    #[test]
    fn checked_retirement_releases_the_actual_noncloneable_assets_once() {
        let drops = Arc::new(AtomicUsize::new(0));
        let owner = Retained::new(
            Assets {
                drops: drops.clone(),
                bytes: vec![7; 1024],
            },
            hold,
        );
        assert_eq!(owner.get().bytes.len(), 1024);
        owner.retire_known();
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }
    #[test]
    fn unknown_retirement_keeps_whole_assets_without_running_destructors() {
        let drops = Arc::new(AtomicUsize::new(0));
        let owner = Retained::new(
            Assets {
                drops: drops.clone(),
                bytes: vec![7; 1024],
            },
            hold,
        );
        let weak = Arc::downgrade(&drops);
        drop(owner);
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        drop(drops);
        assert!(weak.upgrade().is_some());
    }
    #[test]
    fn actual_unwind_transfers_assets_instead_of_releasing_permission_state() {
        let drops = Arc::new(AtomicUsize::new(0));
        let count = drops.clone();
        let result = std::panic::catch_unwind(move || {
            let owner = Retained::new(
                Assets {
                    drops: count,
                    bytes: vec![7; 1024],
                },
                hold,
            );
            assert_eq!(owner.get().bytes.len(), 1024);
            panic!("controlled owner panic");
        });
        assert!(result.is_err());
        assert_eq!(drops.load(Ordering::SeqCst), 0);
    }
}
