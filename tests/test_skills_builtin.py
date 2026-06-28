"""The real built-in skill suite."""

import hashlib

import pytest

from agents.skills import (
    base64_transform,
    csv_preview,
    diff_text,
    extract_entities,
    format_json,
    hash_text,
    regex_extract,
    text_stats,
)


def test_format_json_pretty_and_minify():
    assert format_json('{"b":1,"a":2}', indent=0) == '{"b":1,"a":2}'
    assert "\n" in format_json('{"a":1}', indent=2)
    with pytest.raises(Exception):
        format_json("{not json}")


def test_csv_preview():
    out = csv_preview("name,age\nAda,36\nGrace,45\n", limit=1)
    assert out["columns"] == ["name", "age"]
    assert out["row_count"] == 2
    assert out["rows"] == [{"name": "Ada", "age": "36"}]


def test_regex_extract_groups():
    out = regex_extract(r"(\w+)@(\w+)", "a@x and b@y", flags="i")
    assert out["count"] == 2
    assert out["matches"][0] == ["a", "x"]


def test_text_stats():
    s = text_stats("The cat sat. The cat ran.")
    assert s["words"] == 6
    assert s["sentences"] == 2
    assert s["unique_words"] == 4
    assert s["top_words"][0] == {"word": "the", "count": 2}


def test_hash_text_matches_hashlib():
    assert hash_text("hi") == hashlib.sha256(b"hi").hexdigest()
    assert hash_text("hi", "md5") == hashlib.md5(b"hi").hexdigest()
    with pytest.raises(ValueError):
        hash_text("hi", "crc32")


def test_base64_roundtrip():
    enc = base64_transform("héllo", "encode")
    assert base64_transform(enc, "decode") == "héllo"


def test_diff_text():
    d = diff_text("a\nb\nc", "a\nB\nc")
    assert "-b" in d and "+B" in d
    assert diff_text("same", "same") == "(identical)"


def test_extract_entities():
    out = extract_entities("mail me at a@b.com or see https://x.io — 42 items, $3.50")
    assert "a@b.com" in out["emails"]
    assert "https://x.io" in out["urls"]
    assert "42" in out["numbers"]
