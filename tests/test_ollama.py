"""Ollama backend client (mocked HTTP — no live server needed)."""

from __future__ import annotations

import json
import urllib.request

import pytest

from llm import Message
from llm.ollama import OllamaClient, ollama_status


class _FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_complete_parses_text_and_usage(monkeypatch):
    canned = {
        "message": {"role": "assistant", "content": "the answer is 42"},
        "prompt_eval_count": 25,
        "eval_count": 7,
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _FakeResp(canned))

    client = OllamaClient(model="llama3.2")
    resp = client.complete([Message("user", "what is the answer")], system="be terse", temperature=0.0)
    assert resp.text == "the answer is 42"
    assert resp.model_id == "ollama:llama3.2"
    assert resp.usage == {"input_tokens": 25, "output_tokens": 7}


def test_complete_sends_system_and_messages(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp({"message": {"content": "ok"}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    OllamaClient(model="m").complete([Message("user", "hi")], system="sys", max_tokens=64, seed=3)

    body = captured["body"]
    assert body["model"] == "m"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}
    assert body["options"]["num_predict"] == 64
    assert body["options"]["seed"] == 3
    assert body["stream"] is False


def test_status_unreachable_is_graceful(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    status = ollama_status("http://localhost:11434")
    assert status["reachable"] is False
    assert status["models"] == []


def test_status_reachable_lists_models(monkeypatch):
    payload = {"models": [{"name": "llama3.2"}, {"name": "qwen2.5"}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _FakeResp(payload))
    status = ollama_status()
    assert status["reachable"] is True
    assert status["models"] == ["llama3.2", "qwen2.5"]
