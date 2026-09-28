use crate::{LinkError, Result};
use serde_json::Value;
use sha2::{Digest, Sha256};

/// The gateway's bounded, sorted-key JSON encoding, not a new canonicalization dialect.
pub(crate) fn digest_json(value: &Value, max: usize) -> Result<[u8;32]> {
    let mut out=Vec::with_capacity(max.min(256));
    write(value,&mut out,max,0)?;
    Ok(Sha256::digest(out).into())
}
fn write(value:&Value,out:&mut Vec<u8>,max:usize,depth:usize)->Result<()> {
    if depth>64 { return Err(LinkError::Protocol); }
    match value {
        Value::Array(rows)=> {
            extend(out,b"[",max)?;
            for (i,row) in rows.iter().enumerate() {
                if i!=0 { extend(out,b",",max)?; }
                write(row,out,max,depth+1)?;
            }
            extend(out,b"]",max)?;
        },
        Value::Object(rows)=> {
            extend(out,b"{",max)?;
            let mut keys:Vec<_>=rows.keys().collect();keys.sort_unstable();
            for (i,key) in keys.into_iter().enumerate() {
                if i!=0 {extend(out,b",",max)?;}
                extend(out,&serde_json::to_vec(key).map_err(|_|LinkError::Protocol)?,max)?;
                extend(out,b":",max)?;
                write(&rows[key],out,max,depth+1)?;
            }
            extend(out,b"}",max)?;
        },
        _=>extend(out,&serde_json::to_vec(value).map_err(|_|LinkError::Protocol)?,max)?,
    }
    Ok(())
}
fn extend(out:&mut Vec<u8>,bytes:&[u8],max:usize)->Result<()> {
    if out.len().checked_add(bytes.len()).is_none_or(|n|n>max) {return Err(LinkError::Protocol);}
    out.extend_from_slice(bytes);Ok(())
}
