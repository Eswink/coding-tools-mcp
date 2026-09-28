use crate::{IdentityError, Result};
use ring::digest::{digest, SHA256};
use serde_json::Value;

pub(crate) fn digest_json(value: &Value, max: usize) -> Result<[u8; 32]> {
    let mut out = Vec::with_capacity(256);
    write(value, &mut out, max)?;
    let d = digest(&SHA256, &out);
    let mut result = [0; 32];
    result.copy_from_slice(d.as_ref());
    Ok(result)
}

fn write(value: &Value, out: &mut Vec<u8>, max: usize) -> Result<()> {
    match value {
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
            let encoded = serde_json::to_vec(value).map_err(|_| IdentityError::InvalidRequest)?;
            extend(out, &encoded, max)?;
        }
        Value::Array(values) => {
            push(out, b'[', max)?;
            for (index, value) in values.iter().enumerate() {
                if index != 0 {
                    push(out, b',', max)?;
                }
                write(value, out, max)?;
            }
            push(out, b']', max)?;
        }
        Value::Object(values) => {
            push(out, b'{', max)?;
            let mut keys: Vec<&String> = values.keys().collect();
            keys.sort_unstable();
            for (index, key) in keys.into_iter().enumerate() {
                if index != 0 {
                    push(out, b',', max)?;
                }
                let encoded = serde_json::to_vec(key).map_err(|_| IdentityError::InvalidRequest)?;
                extend(out, &encoded, max)?;
                push(out, b':', max)?;
                write(&values[key], out, max)?;
            }
            push(out, b'}', max)?;
        }
    }
    Ok(())
}
fn push(out: &mut Vec<u8>, byte: u8, max: usize) -> Result<()> {
    if out.len() >= max {
        return Err(IdentityError::InvalidRequest);
    }
    out.push(byte);
    Ok(())
}
fn extend(out: &mut Vec<u8>, bytes: &[u8], max: usize) -> Result<()> {
    if out.len().checked_add(bytes.len()).is_none_or(|n| n > max) {
        return Err(IdentityError::InvalidRequest);
    }
    out.extend_from_slice(bytes);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn object_order_does_not_change_digest() {
        let a = json!({"b":2,"a":{"z":1,"y":[3,2,1]}});
        let b = json!({"a":{"y":[3,2,1],"z":1},"b":2});
        assert_eq!(
            digest_json(&a, 1024).unwrap(),
            digest_json(&b, 1024).unwrap()
        );
    }
    #[test]
    fn changed_value_changes_digest() {
        assert_ne!(
            digest_json(&json!({"x":1}), 1024).unwrap(),
            digest_json(&json!({"x":2}), 1024).unwrap()
        );
    }
    #[test]
    fn bounded_encoding_rejects_large_values() {
        assert!(digest_json(&json!({"x":"a".repeat(100)}), 16).is_err());
    }
}
