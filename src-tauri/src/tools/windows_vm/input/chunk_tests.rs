use super::chunks::{ImmutableChunks, CHUNK, MAXIMUM};
#[test]
fn sealed_chunks_keep_original_and_detached_owners_independent() {
    let mut original = ImmutableChunks::new();
    original.append(b"original immutable canary").unwrap(); original.seal();
    let digest = original.digest().unwrap();
    let detached = original.detached(&|| false).unwrap();
    original.clear_after_checked_close();
    assert!(original.digest().is_err());
    assert_eq!(detached.digest().unwrap(), digest);
    assert_eq!(detached.size(), 25);
}
#[test]
fn chunk_cap_and_cancel_do_not_publish_partial_copy() {
    let mut bytes = ImmutableChunks::new();
    assert!(bytes.append(&[]).is_err());
    assert!(bytes.append(&vec![0; CHUNK + 1]).is_err());
    for _ in 0..MAXIMUM/CHUNK { bytes.append(&vec![7; CHUNK]).unwrap(); }
    assert!(bytes.append(&[1]).is_err());
    assert!(bytes.digest().is_err()); bytes.seal();
    assert!(bytes.append(&[1]).is_err());
    assert!(bytes.detached(&|| true).is_err());
    let copied = bytes.detached(&|| false).unwrap();
    assert_eq!(copied.size(), MAXIMUM);
    assert_eq!(copied.digest(), bytes.digest());
}
