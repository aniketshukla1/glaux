//! The ledger: signed, hash-chained, tamper-evident blocks — all native.
//!
//! `append` canonicalizes the block content, signs it (Ed25519), and SHA-256
//! hashes it; `verify` walks the chain checking index, content hash, prev-hash
//! linkage, and signature for every block. Persistence is append-only JSONL.
//! Rotation-aware key-validity checks live in the Python layer (cheap registry
//! lookups); everything cryptographic is here.

use std::fs::File;
use std::io::{BufRead, BufReader, ErrorKind, Write};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::canonical::canonical_bytes;
use crate::crypto;

pub fn genesis_hash() -> String {
    "0".repeat(64)
}

/// Microseconds since the epoch.
///
/// Deliberately an integer: block hashes are computed over the canonical JSON,
/// so any float in the hashed content makes integrity depend on f64 text
/// round-tripping exactly. It does not always. A timestamp written as
/// 1785528166.6964545 could be read back as 1785528166.6964543 — one ULP apart,
/// same instant — and the chain then reported CHAIN INVALID on a ledger nobody
/// had touched. Integers have exactly one representation, so this cannot recur.
fn now_unix_us() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_micros() as i64)
        .unwrap_or(0)
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Block {
    pub index: u64,
    pub timestamp_us: i64,
    pub agent_id: String,
    pub signing_pubkey: String,
    pub action_type: String,
    pub payload: Value,
    pub prev_hash: String,
    pub signature: String,
    pub hash: String,
}

impl Block {
    /// The signed/hashed portion (everything except `signature` and `hash`).
    fn content_value(&self) -> Value {
        let mut m = Map::new();
        m.insert("index".into(), json!(self.index));
        m.insert("timestamp_us".into(), json!(self.timestamp_us));
        m.insert("agent_id".into(), json!(self.agent_id));
        m.insert("signing_pubkey".into(), json!(self.signing_pubkey));
        m.insert("action_type".into(), json!(self.action_type));
        m.insert("payload".into(), self.payload.clone());
        m.insert("prev_hash".into(), json!(self.prev_hash));
        Value::Object(m)
    }

    pub fn content_bytes(&self) -> Vec<u8> {
        canonical_bytes(&self.content_value())
    }
}

#[derive(Default)]
pub struct Ledger {
    pub blocks: Vec<Block>,
}

impl Ledger {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> usize {
        self.blocks.len()
    }

    pub fn is_empty(&self) -> bool {
        self.blocks.is_empty()
    }

    pub fn head_hash(&self) -> String {
        self.blocks
            .last()
            .map(|b| b.hash.clone())
            .unwrap_or_else(genesis_hash)
    }

    pub fn append(
        &mut self,
        agent_id: String,
        signing_pubkey: String,
        secret_b58: &str,
        action_type: String,
        payload: Value,
        timestamp_us: Option<i64>,
    ) -> Result<Block, String> {
        let mut block = Block {
            index: self.blocks.len() as u64,
            timestamp_us: timestamp_us.unwrap_or_else(now_unix_us),
            agent_id,
            signing_pubkey,
            action_type,
            payload,
            prev_hash: self.head_hash(),
            signature: String::new(),
            hash: String::new(),
        };
        let content = block.content_bytes();
        block.signature = crypto::sign(secret_b58, &content)?;
        block.hash = crypto::sha256_hex(&content);
        self.blocks.push(block.clone());
        Ok(block)
    }

    /// Returns `(ok, first_bad_index, reason)`; index is -1 when valid.
    pub fn verify(&self) -> (bool, i64, String) {
        let mut expected_prev = genesis_hash();
        for (i, b) in self.blocks.iter().enumerate() {
            if b.index != i as u64 {
                return (false, i as i64, "block index mismatch".into());
            }
            let content = b.content_bytes();
            if crypto::sha256_hex(&content) != b.hash {
                return (false, i as i64, "block hash mismatch".into());
            }
            if b.prev_hash != expected_prev {
                return (false, i as i64, "broken chain link".into());
            }
            if !crypto::verify(&b.signing_pubkey, &content, &b.signature) {
                return (false, i as i64, "invalid signature".into());
            }
            expected_prev = b.hash.clone();
        }
        (true, -1, "ok".into())
    }

    pub fn save(&self, path: &str) -> std::io::Result<()> {
        let mut f = File::create(path)?;
        for b in &self.blocks {
            let line = serde_json::to_string(b)
                .map_err(|e| std::io::Error::new(ErrorKind::Other, e))?;
            f.write_all(line.as_bytes())?;
            f.write_all(b"\n")?;
        }
        f.sync_all()?;
        Ok(())
    }

    pub fn load(path: &str) -> std::io::Result<Self> {
        let mut ledger = Ledger::new();
        let file = match File::open(path) {
            Ok(f) => f,
            Err(e) if e.kind() == ErrorKind::NotFound => return Ok(ledger),
            Err(e) => return Err(e),
        };
        for line in BufReader::new(file).lines() {
            let line = line?;
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            let block: Block = serde_json::from_str(trimmed)
                .map_err(|e| std::io::Error::new(ErrorKind::InvalidData, e))?;
            ledger.blocks.push(block);
        }
        Ok(ledger)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::SigningKey;

    fn keys(seed: u8) -> (String, String) {
        let sk = SigningKey::from_bytes(&[seed; 32]);
        (
            bs58::encode(sk.to_bytes()).into_string(),
            bs58::encode(sk.verifying_key().to_bytes()).into_string(),
        )
    }

    fn ledger_with(n: usize) -> Ledger {
        let (sk, pk) = keys(5);
        let mut l = Ledger::new();
        for i in 0..n {
            l.append(
                "agent".into(),
                pk.clone(),
                &sk,
                "THINK".into(),
                json!({ "i": i }),
                Some(i as i64),
            )
            .unwrap();
        }
        l
    }

    #[test]
    fn hashed_content_holds_no_floats() {
        // Regression: block hashes are computed over the canonical JSON, so a float
        // anywhere in the hashed content makes integrity depend on f64 text
        // round-tripping exactly — which it did not, producing CHAIN INVALID on
        // untouched ledgers. Nothing in the signed content may serialize as a float.
        let l = ledger_with(3);
        for b in &l.blocks {
            let v = b.content_value();
            fn assert_no_float(v: &Value, path: &str) {
                match v {
                    Value::Number(n) => assert!(
                        !n.is_f64(),
                        "float in hashed content at {path}: {n}"
                    ),
                    Value::Object(m) => {
                        for (k, sub) in m {
                            assert_no_float(sub, &format!("{path}.{k}"));
                        }
                    }
                    Value::Array(a) => {
                        for (i, sub) in a.iter().enumerate() {
                            assert_no_float(sub, &format!("{path}[{i}]"));
                        }
                    }
                    _ => {}
                }
            }
            assert_no_float(&v, "content");
        }
    }

    #[test]
    fn survives_a_json_round_trip() {
        // Save/load must reproduce byte-identical canonical content, or the chain
        // fails to verify on a ledger nobody touched.
        let l = ledger_with(4);
        for b in &l.blocks {
            let text = serde_json::to_string(b).unwrap();
            let back: Block = serde_json::from_str(&text).unwrap();
            assert_eq!(b.content_bytes(), back.content_bytes());
            assert_eq!(b.timestamp_us, back.timestamp_us);
        }
    }

    #[test]
    fn append_and_verify() {
        let l = ledger_with(3);
        let (ok, bad, _) = l.verify();
        assert!(ok);
        assert_eq!(bad, -1);
        assert_eq!(l.blocks[0].prev_hash, genesis_hash());
        assert_eq!(l.blocks[1].prev_hash, l.blocks[0].hash);
    }

    #[test]
    fn detect_payload_tamper() {
        let mut l = ledger_with(3);
        l.blocks[1].payload = json!({ "i": 999999 });
        let (ok, bad, reason) = l.verify();
        assert!(!ok);
        assert_eq!(bad, 1);
        assert!(reason.contains("hash"));
    }

    #[test]
    fn detect_bad_signature() {
        let mut l = ledger_with(3);
        let (other_sk, _) = keys(99);
        l.blocks[1].signature = crypto::sign(&other_sk, &l.blocks[1].content_bytes()).unwrap();
        let (ok, bad, reason) = l.verify();
        assert!(!ok);
        assert_eq!(bad, 1);
        assert!(reason.contains("signature"));
    }

    #[test]
    fn detect_broken_link() {
        let (sk, _pk) = keys(5);
        let mut l = ledger_with(3);
        // make block 2 internally consistent but pointing at the wrong parent
        l.blocks[2].prev_hash = "f".repeat(64);
        let content = l.blocks[2].content_bytes();
        l.blocks[2].hash = crypto::sha256_hex(&content);
        l.blocks[2].signature = crypto::sign(&sk, &content).unwrap();
        let (ok, bad, reason) = l.verify();
        assert!(!ok);
        assert_eq!(bad, 2);
        assert!(reason.contains("link"));
    }

    #[test]
    fn save_load_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ledger.jsonl");
        let path = path.to_str().unwrap();
        let l = ledger_with(4);
        l.save(path).unwrap();
        let reloaded = Ledger::load(path).unwrap();
        assert_eq!(reloaded.len(), 4);
        assert!(reloaded.verify().0);
    }
}
