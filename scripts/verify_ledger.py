#!/usr/bin/env python3
"""Independently verify an exported Glaux ledger.

    python scripts/verify_ledger.py <glaux-ledger.jsonl>

Re-checks every block's Ed25519 signature and the SHA-256 hash chain using the
open `glaux_ledger` verifier — no running server, and no trust in the Glaux
app required. This is the point of the signed ledger: a proof anyone can check.

Exit code 0 = valid, 1 = tampered/invalid, 2 = usage error.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from core.ledger import Ledger  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verify_ledger.py <ledger.jsonl>", file=sys.stderr)
        return 2
    try:
        led = Ledger.load(argv[1])
    except Exception as e:  # noqa: BLE001
        print(f"could not read ledger: {e}", file=sys.stderr)
        return 1

    v = led.verify()
    n = len(led)
    if v.valid:
        head = led.head_hash if n else "0" * 64
        print(f"✓ VALID  —  {n} signed blocks, head {head[:16]}…")
        return 0
    print(f"✗ INVALID at block {v.first_bad_index}: {v.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
