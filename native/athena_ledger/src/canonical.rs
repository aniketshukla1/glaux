//! Canonical byte serialization for signing and hashing.
//!
//! `serde_json::Value` stores object keys in a `BTreeMap` (default features,
//! no `preserve_order`), so `to_vec` emits keys sorted and whitespace-free —
//! equivalent to Python's `json.dumps(sort_keys=True, separators=(",", ":"),
//! ensure_ascii=False)`. Because the ledger now signs *and* verifies entirely
//! in Rust, this is the single source of truth for canonical bytes; there is no
//! cross-language canonicalization to keep in sync.

use serde_json::Value;

pub fn canonical_bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).expect("serializing a serde_json::Value cannot fail")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn keys_are_sorted_and_compact() {
        let v = json!({"b": 1, "a": 2, "nested": {"z": 1, "y": 2}});
        assert_eq!(
            canonical_bytes(&v),
            br#"{"a":2,"b":1,"nested":{"y":2,"z":1}}"#.to_vec()
        );
    }

    #[test]
    fn non_ascii_is_not_escaped() {
        let v = json!({"name": "café"});
        assert_eq!(canonical_bytes(&v), r#"{"name":"café"}"#.as_bytes().to_vec());
    }
}
