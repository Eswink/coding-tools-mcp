use super::{chunks::ImmutableChunks, transfer::InputTransfer, transfer_tests::binding};
#[test]
fn checked_close_consumes_data_only_transfer() {
    let binding = binding(); let mut data = ImmutableChunks::new(); data.seal();
    let mut transfer = InputTransfer::new(binding.clone(), data).unwrap();
    assert!(transfer.matches(&binding)); transfer.clear_after_checked_close();
    assert!(!transfer.matches(&binding)); transfer.clear_after_checked_close();
    assert!(!transfer.matches(&binding));
}
