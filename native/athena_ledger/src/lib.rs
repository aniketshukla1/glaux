//! athena_ledger — native ledger kernel for Athena.
//!
//! Owns the entire tamper-evident action log: canonicalization, Ed25519 signing,
//! SHA-256 hashing, chain verification, and JSONL persistence. The Python side
//! is a thin ergonomic wrapper (`src/core/ledger.py`) that calls `append` /
//! `verify` and layers on rotation-aware key-validity checks via the registry.
//!
//! Pure logic lives in [`crypto`], [`canonical`], and [`ledger`] (all testable
//! with plain `cargo test`); the PyO3 surface is feature-gated behind `python`.

pub mod canonical;
pub mod crypto;
pub mod ledger;

#[cfg(feature = "python")]
mod py;
