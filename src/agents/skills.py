"""Built-in skills: a suite of genuinely useful, deterministic tools the swarm
can call directly — JSON and CSV handling, regex extraction, text statistics,
hashing, encoding, diffing and entity extraction.

Pure standard library, no third-party deps. These replace the original toy
demo tools (string-reverse / uppercase) with capabilities that do real work.
"""

from __future__ import annotations

import base64 as _b64
import csv as _csv
import difflib
import hashlib
import io
import json as _json
import re
from collections import Counter
from typing import Any


def format_json(text: str, indent: int = 2) -> str:
    """Validate and pretty-print a JSON string (indent=0 minifies)."""
    obj = _json.loads(text)
    if int(indent) <= 0:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    return _json.dumps(obj, indent=int(indent), ensure_ascii=False)


def csv_preview(text: str, limit: int = 10) -> dict:
    """Parse CSV text into columns, a row count and the first rows as records."""
    rows = list(_csv.reader(io.StringIO(text)))
    if not rows:
        return {"columns": [], "row_count": 0, "rows": []}
    header = [h.strip() for h in rows[0]]
    body = rows[1:]
    records = [dict(zip(header, r)) for r in body[: max(1, int(limit))]]
    return {"columns": header, "row_count": len(body), "rows": records}


def regex_extract(pattern: str, text: str, flags: str = "") -> dict:
    """Find all matches of a regex in text. Groups are returned when present."""
    fl = 0
    if "i" in flags:
        fl |= re.IGNORECASE
    if "m" in flags:
        fl |= re.MULTILINE
    if "s" in flags:
        fl |= re.DOTALL
    rx = re.compile(pattern, fl)
    out: list[Any] = []
    for m in rx.finditer(text):
        out.append(list(m.groups()) if m.groups() else m.group(0))
        if len(out) >= 200:
            break
    return {"count": len(out), "matches": out}


def text_stats(text: str) -> dict:
    """Word / sentence / character counts, unique words, reading time, top words."""
    words = re.findall(r"\b\w+\b", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    lowered = [w.lower() for w in words]
    common = Counter(lowered).most_common(5)
    return {
        "characters": len(text),
        "words": len(words),
        "sentences": len(sentences),
        "unique_words": len(set(lowered)),
        "avg_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0,
        "reading_time_min": round(len(words) / 200, 1),
        "top_words": [{"word": w, "count": c} for w, c in common],
    }


def hash_text(text: str, algo: str = "sha256") -> str:
    """Cryptographic hash of text (sha256 / sha1 / sha512 / md5)."""
    algo = str(algo).lower()
    if algo not in {"sha256", "sha1", "sha512", "md5"}:
        raise ValueError(f"unsupported algorithm {algo!r} (use sha256, sha1, sha512 or md5)")
    return hashlib.new(algo, text.encode("utf-8")).hexdigest()


def base64_transform(text: str, mode: str = "encode") -> str:
    """Base64 encode or decode text."""
    if str(mode).lower() == "decode":
        return _b64.b64decode(text.encode("utf-8")).decode("utf-8", "replace")
    return _b64.b64encode(text.encode("utf-8")).decode("ascii")


def diff_text(a: str, b: str) -> str:
    """A unified diff between two texts."""
    diff = difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=2)
    return "\n".join(diff) or "(identical)"


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://[^\s)>\"']+")
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def extract_entities(text: str) -> dict:
    """Pull emails, URLs and numbers out of free text."""
    return {
        "emails": list(dict.fromkeys(_EMAIL.findall(text)))[:100],
        "urls": list(dict.fromkeys(_URL.findall(text)))[:100],
        "numbers": _NUM.findall(text)[:100],
    }


def register_skills(client) -> None:
    """Register the real skill suite onto a LocalMCPClient."""
    client.register("format_json", "Validate and pretty-print a JSON string (indent=0 to minify).", format_json,
                    {"text": "JSON string", "indent": "integer (default 2; 0 = minify)"})
    client.register("csv_preview", "Parse CSV text into columns, row count and the first rows as records.", csv_preview,
                    {"text": "CSV text", "limit": "integer rows (default 10)"})
    client.register("regex_extract", "Find all matches of a regex in text (capture groups returned when present).", regex_extract,
                    {"pattern": "regular expression", "text": "string", "flags": "any of i,m,s"})
    client.register("text_stats", "Word/sentence/character counts, unique words, reading time and the most frequent words.", text_stats,
                    {"text": "string"})
    client.register("hash_text", "Cryptographic hash of text (sha256/sha1/sha512/md5).", hash_text,
                    {"text": "string", "algo": "sha256 | sha1 | sha512 | md5"})
    client.register("base64_transform", "Base64 encode or decode text.", base64_transform,
                    {"text": "string", "mode": "encode | decode"})
    client.register("diff_text", "Compute a unified diff between two texts.", diff_text,
                    {"a": "original text", "b": "new text"})
    client.register("extract_entities", "Extract emails, URLs and numbers from text.", extract_entities,
                    {"text": "string"})
