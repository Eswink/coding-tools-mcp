use super::{chunks::ImmutableChunks, transfer::{RunBinding, InputTransfer}};
pub(super) fn binding() -> RunBinding {
    RunBinding { host: uuid::Uuid::new_v4().to_string(), profile: "data-only".into(),
        caller: "conversation-data-only".into(), source: "1".repeat(40),
        session: uuid::Uuid::new_v4().to_string(), operation: uuid::Uuid::new_v4().to_string(),
        input_relative: "input.txt".into(), output_parent: "results".into(), output_leaf: "new.txt".into() }
}
#[test]
fn exact_transfer_binding_rejects_each_field_mismatch() {
    let original = binding(); let mut bytes = ImmutableChunks::new();
    bytes.append(b"data canary").unwrap(); bytes.seal();
    let transfer = InputTransfer::new(original.clone(), bytes).unwrap();
    assert!(transfer.matches(&original));
    let mut variants = Vec::new();
    let mut changed = original.clone(); changed.host = uuid::Uuid::new_v4().to_string(); variants.push(changed);
    let mut changed = original.clone(); changed.profile.push('x'); variants.push(changed);
    let mut changed = original.clone(); changed.caller.push('x'); variants.push(changed);
    let mut changed = original.clone(); changed.source = "2".repeat(40); variants.push(changed);
    let mut changed = original.clone(); changed.session = uuid::Uuid::new_v4().to_string(); variants.push(changed);
    let mut changed = original.clone(); changed.operation = uuid::Uuid::new_v4().to_string(); variants.push(changed);
    let mut changed = original.clone(); changed.input_relative = "other.txt".into(); variants.push(changed);
    let mut changed = original.clone(); changed.output_parent = "other".into(); variants.push(changed);
    let mut changed = original.clone(); changed.output_leaf = "other.txt".into(); variants.push(changed);
    for changed in variants { assert!(changed.valid()); assert!(!transfer.matches(&changed)); }
}
#[test]
fn invalid_wire_names_and_nil_binding_never_make_native_authority() {
    for text in ["../escape", "C:\\external", "a:stream", "NUL.txt", "a/../b"] {
        let mut data = binding(); data.input_relative = text.into(); assert!(!data.valid());
    }
    let mut data = binding(); data.host = uuid::Uuid::nil().to_string(); assert!(!data.valid());
    let mut data = binding(); data.source = "F".repeat(40); assert!(!data.valid());
}
