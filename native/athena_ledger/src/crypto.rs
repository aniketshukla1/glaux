//! Pure crypto primitives (no PyO3) so they unit-test under `cargo test`.
//!
//! Keys and signatures cross the FFI boundary as base58 (Bitcoin alphabet,
//! matching Python's `base58`); messages cross as raw bytes. Ed25519 here is
//! RFC 8032 standard, so it interoperates with Python's `cryptography` —
//! a block signed in Rust verifies in Python and vice versa.

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use sha2::{Digest, Sha256};

pub fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    let digest = hasher.finalize();
    let mut out = String::with_capacity(64);
    for b in digest {
        out.push_str(&format!("{b:02x}"));
    }
    out
}

pub fn sign(secret_b58: &str, msg: &[u8]) -> Result<String, String> {
    let bytes = bs58::decode(secret_b58)
        .into_vec()
        .map_err(|e| format!("bad base58 secret: {e}"))?;
    let arr: [u8; 32] = bytes
        .try_into()
        .map_err(|_| "secret key must be 32 bytes".to_string())?;
    let sk = SigningKey::from_bytes(&arr);
    let sig: Signature = sk.sign(msg);
    Ok(bs58::encode(sig.to_bytes()).into_string())
}

pub fn verify(public_key_b58: &str, msg: &[u8], sig_b58: &str) -> bool {
    let inner = || -> Option<bool> {
        let pk_bytes = bs58::decode(public_key_b58).into_vec().ok()?;
        let pk_arr: [u8; 32] = pk_bytes.try_into().ok()?;
        let vk = VerifyingKey::from_bytes(&pk_arr).ok()?;
        let sig_bytes = bs58::decode(sig_b58).into_vec().ok()?;
        let sig_arr: [u8; 64] = sig_bytes.try_into().ok()?;
        let sig = Signature::from_bytes(&sig_arr);
        Some(vk.verify(msg, &sig).is_ok())
    };
    inner().unwrap_or(false)
}

/// One link in the chain, supplied by Python with the *exact* canonical bytes
/// that were hashed and signed (so Rust never has to reproduce canonical JSON).
pub struct ChainItem {
    pub content: Vec<u8>,
    pub signature_b58: String,
    pub signing_pubkey_b58: String,
    pub stored_hash: String,
    pub prev_hash: String,
}

/// Verify a whole chain natively: per block check the content hash, the
/// previous-hash linkage, and the signature. Returns `(ok, first_bad_index,
/// reason)`; `first_bad_index` is -1 when valid.
pub fn verify_chain(items: &[ChainItem], genesis_hash: &str) -> (bool, i64, String) {
    let mut expected_prev = genesis_hash.to_string();
    for (i, it) in items.iter().enumerate() {
        let h = sha256_hex(&it.content);
        if h != it.stored_hash {
            return (false, i as i64, "block hash mismatch".to_string());
        }
        if it.prev_hash != expected_prev {
            return (false, i as i64, "broken chain link".to_string());
        }
        if !verify(&it.signing_pubkey_b58, &it.content, &it.signature_b58) {
            return (false, i as i64, "invalid signature".to_string());
        }
        expected_prev = it.stored_hash.clone();
    }
    (true, -1, "ok".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn keypair(seed: u8) -> (String, String) {
        let sk = SigningKey::from_bytes(&[seed; 32]);
        let pk = sk.verifying_key();
        (
            bs58::encode(sk.to_bytes()).into_string(),
            bs58::encode(pk.to_bytes()).into_string(),
        )
    }

    #[test]
    fn sha256_is_stable_and_hex() {
        let h = sha256_hex(b"athena");
        assert_eq!(h.len(), 64);
        assert_eq!(h, sha256_hex(b"athena"));
        assert_ne!(h, sha256_hex(b"athenb"));
    }

    #[test]
    fn sign_verify_roundtrip() {
        let (sk, pk) = keypair(7);
        let sig = sign(&sk, b"hello").unwrap();
        assert!(verify(&pk, b"hello", &sig));
        assert!(!verify(&pk, b"tampered", &sig));
    }

    #[test]
    fn verify_rejects_garbage() {
        assert!(!verify("not-a-key", b"x", "not-a-sig"));
    }

    fn build_chain(n: usize) -> Vec<ChainItem> {
        let (sk, pk) = keypair(3);
        let mut items = Vec::new();
        let mut prev = "0".repeat(64);
        for i in 0..n {
            let content = format!("block-{i}").into_bytes();
            let stored_hash = sha256_hex(&content);
            let signature_b58 = sign(&sk, &content).unwrap();
            items.push(ChainItem {
                content,
                signature_b58,
                signing_pubkey_b58: pk.clone(),
                stored_hash: stored_hash.clone(),
                prev_hash: prev.clone(),
            });
            prev = stored_hash;
        }
        items
    }

    #[test]
    fn verify_chain_accepts_valid() {
        let items = build_chain(5);
        let (ok, bad, _) = verify_chain(&items, &"0".repeat(64));
        assert!(ok);
        assert_eq!(bad, -1);
    }

    #[test]
    fn verify_chain_detects_tampered_content() {
        let mut items = build_chain(5);
        items[2].content = b"tampered".to_vec(); // hash no longer matches stored_hash
        let (ok, bad, reason) = verify_chain(&items, &"0".repeat(64));
        assert!(!ok);
        assert_eq!(bad, 2);
        assert!(reason.contains("hash"));
    }

    #[test]
    fn verify_chain_detects_broken_link() {
        let mut items = build_chain(5);
        items[3].prev_hash = "deadbeef".to_string();
        let (ok, bad, _) = verify_chain(&items, &"0".repeat(64));
        assert!(!ok);
        assert_eq!(bad, 3);
    }

    #[test]
    fn verify_chain_detects_bad_signature() {
        let mut items = build_chain(5);
        let (_other_sk, _other_pk) = keypair(99);
        items[1].signature_b58 = sign(&keypair(99).0, &items[1].content).unwrap();
        let (ok, bad, reason) = verify_chain(&items, &"0".repeat(64));
        assert!(!ok);
        assert_eq!(bad, 1);
        assert!(reason.contains("signature"));
    }
}
