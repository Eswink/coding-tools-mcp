//! Uninhabited reservation, NOT an actual VM/IO close proof or an issuer.
//! Future real native producer must be separately specified and verified.
pub(super) enum ClosedVmAndIoOwner {}
pub(super) struct OwnedOutputPublication {
    _closed: ClosedVmAndIoOwner,
    _data: super::gate::OutputDataPlan,
}
// No constructor, Clone, Deserialize, public fields or drop-triggered effects.
// No current code can construct this type or use diagnostics to publish output.
