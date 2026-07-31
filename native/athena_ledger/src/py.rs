//! PyO3 bindings: `import athena_ledger`.
//!
//! Exposes the `Ledger` class (the whole ledger lives in Rust) plus the
//! low-level primitives (`sha256_hex`, `sign`, `verify`, `verify_chain`).
//! Blocks cross the boundary as JSON strings (Python `json.loads`), keeping the
//! binding dependency-free.

use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use serde_json::{json, Value};

use crate::crypto;
use crate::ledger::Ledger as RustLedger;

#[pyfunction]
fn sha256_hex(data: &[u8]) -> String {
    crypto::sha256_hex(data)
}

#[pyfunction]
fn sign(secret_b58: &str, msg: &[u8]) -> PyResult<String> {
    crypto::sign(secret_b58, msg).map_err(PyValueError::new_err)
}

#[pyfunction]
fn verify(public_key_b58: &str, msg: &[u8], sig_b58: &str) -> bool {
    crypto::verify(public_key_b58, msg, sig_b58)
}

/// Batched chain verification over caller-supplied canonical content bytes.
/// `items`: list of (content_bytes, signature_b58, signing_pubkey_b58,
/// stored_hash, prev_hash). Returns (ok, first_bad_index, reason).
#[pyfunction]
fn verify_chain(
    items: Vec<(Vec<u8>, String, String, String, String)>,
    genesis_hash: &str,
) -> (bool, i64, String) {
    let chain: Vec<crypto::ChainItem> = items
        .into_iter()
        .map(
            |(content, signature_b58, signing_pubkey_b58, stored_hash, prev_hash)| {
                crypto::ChainItem {
                    content,
                    signature_b58,
                    signing_pubkey_b58,
                    stored_hash,
                    prev_hash,
                }
            },
        )
        .collect();
    crypto::verify_chain(&chain, genesis_hash)
}

#[pyclass(name = "Ledger")]
pub struct PyLedger {
    inner: RustLedger,
}

#[pymethods]
impl PyLedger {
    #[new]
    fn new() -> Self {
        Self { inner: RustLedger::new() }
    }

    /// Sign and append a block. `payload_json` is a JSON string. Returns the new
    /// block as a JSON string.
    #[pyo3(signature = (agent_id, signing_pubkey, signing_secret_b58, action_type, payload_json, timestamp=None))]
    fn append(
        &mut self,
        agent_id: String,
        signing_pubkey: String,
        signing_secret_b58: &str,
        action_type: String,
        payload_json: &str,
        timestamp: Option<f64>,
    ) -> PyResult<String> {
        let payload: Value = serde_json::from_str(payload_json)
            .map_err(|e| PyValueError::new_err(format!("invalid payload JSON: {e}")))?;
        let block = self
            .inner
            .append(
                agent_id,
                signing_pubkey,
                signing_secret_b58,
                action_type,
                payload,
                timestamp.map(|s| (s * 1_000_000.0).round() as i64),
            )
            .map_err(PyValueError::new_err)?;
        serde_json::to_string(&block).map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Verify the whole chain natively. Returns (ok, first_bad_index, reason).
    fn verify(&self) -> (bool, i64, String) {
        self.inner.verify()
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }

    fn head_hash(&self) -> String {
        self.inner.head_hash()
    }

    /// Full block (incl. payload) as a JSON string.
    fn block(&self, index: usize) -> PyResult<String> {
        let block = self
            .inner
            .blocks
            .get(index)
            .ok_or_else(|| PyValueError::new_err("block index out of range"))?;
        serde_json::to_string(block).map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Lightweight per-block metadata (no payload) as a JSON list string — used
    /// for the registry validity check and the UI's chain auditor.
    fn blocks_meta(&self) -> PyResult<String> {
        let meta: Vec<Value> = self
            .inner
            .blocks
            .iter()
            .map(|b| {
                json!({
                    "index": b.index,
                    "timestamp_us": b.timestamp_us,
                    "agent_id": b.agent_id,
                    "signing_pubkey": b.signing_pubkey,
                    "action_type": b.action_type,
                    "hash": b.hash,
                    "prev_hash": b.prev_hash,
                })
            })
            .collect();
        serde_json::to_string(&meta).map_err(|e| PyValueError::new_err(e.to_string()))
    }

    fn save(&self, path: &str) -> PyResult<()> {
        self.inner.save(path).map_err(|e| PyIOError::new_err(e.to_string()))
    }

    #[staticmethod]
    fn load(path: &str) -> PyResult<Self> {
        RustLedger::load(path)
            .map(|inner| Self { inner })
            .map_err(|e| PyIOError::new_err(e.to_string()))
    }
}

#[pymodule]
fn athena_ledger(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sha256_hex, m)?)?;
    m.add_function(wrap_pyfunction!(sign, m)?)?;
    m.add_function(wrap_pyfunction!(verify, m)?)?;
    m.add_function(wrap_pyfunction!(verify_chain, m)?)?;
    m.add_class::<PyLedger>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
