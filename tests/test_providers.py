"""OpenAI-compatible provider client + the provider catalog.

Exercises the generic client end to end against a stub server that speaks the
OpenAI /chat/completions shape, plus the catalog/factory logic.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from llm import Message  # noqa: E402
from llm.providers import (  # noqa: E402
    PROVIDERS,
    LLMError,
    OpenAICompatibleClient,
    hf_runtimes,
    key_available,
    make_client,
    provider_catalog,
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        auth = self.headers.get("Authorization")
        if not auth:  # mimic a provider rejecting an unauthenticated call
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"missing api key"}}')
            return
        last_user = next((m["content"] for m in reversed(body["messages"]) if m["role"] == "user"), "")
        out = {
            "model": body["model"],
            "choices": [{"message": {"role": "assistant", "content": f"echo:{body['model']}:{last_user}"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }
        payload = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def stub_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    finally:
        srv.shutdown()


def test_openai_compatible_client_roundtrip(stub_server):
    c = OpenAICompatibleClient(base_url=stub_server, model="gpt-test", api_key="sk-x", provider="stub")
    res = c.complete([Message(role="user", content="hello")], system="be terse")
    assert res.text == "echo:gpt-test:hello"
    assert res.model_id == "stub:gpt-test"
    # OpenAI usage fields mapped onto Athena's input/output token names
    assert res.usage == {"input_tokens": 11, "output_tokens": 7}


def test_missing_key_surfaces_as_llm_error(stub_server):
    c = OpenAICompatibleClient(base_url=stub_server, model="m", api_key=None, provider="stub")
    with pytest.raises(LLMError) as e:
        c.complete([Message(role="user", content="x")])
    assert "401" in str(e.value)


def test_catalog_is_comprehensive():
    cat = {p["id"] for p in provider_catalog()}
    # a broad sample across categories must be present
    for pid in ["openai", "gemini", "xai", "mistral", "deepseek", "cohere", "openrouter",
                "huggingface", "groq", "together", "fireworks", "perplexity", "cerebras",
                "sambanova", "deepinfra", "novita", "nvidia", "nous", "sarvam", "moonshot",
                "zhipu", "dashscope", "yi", "lmstudio", "vllm", "custom"]:
        assert pid in cat, pid
    assert len(cat) >= 30


def test_catalog_entries_well_formed():
    for p in provider_catalog():
        assert p["id"] and p["label"] and "kind" in p
        # every non-custom, non-local provider has a real https base url
        if p["id"] not in ("custom", "vllm", "llamacpp", "lmstudio"):
            assert p["base_url"].startswith("https://"), p["id"]
            assert p["key_env"], p["id"]
        assert "key_present" in p  # never leaks the key value, just presence


def test_key_present_reflects_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert {p["id"]: p["key_present"] for p in provider_catalog()}["deepseek"] is False
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-abc")
    assert {p["id"]: p["key_present"] for p in provider_catalog()}["deepseek"] is True


def test_make_client_resolves_preset_and_env_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    c = make_client("deepseek")
    assert isinstance(c, OpenAICompatibleClient)
    assert c.base_url == "https://api.deepseek.com/v1"
    assert c.model == PROVIDERS["deepseek"].default_model
    assert c.api_key == "sk-from-env"
    assert c.model_id.startswith("deepseek:")


def test_make_client_explicit_key_overrides_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    c = make_client("openai", model="gpt-4o", api_key="explicit")
    assert c.api_key == "explicit" and c.model == "gpt-4o"


def test_custom_requires_base_url():
    with pytest.raises(ValueError):
        make_client("custom", model="m")
    c = make_client("custom", model="m", base_url="https://my.host/v1", api_key="k")
    assert c.base_url == "https://my.host/v1"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        make_client("nope")


def test_key_available_logic(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert key_available("groq") is False
    assert key_available("groq", "explicit") is True
    assert key_available("lmstudio") is True  # local, no key needed
    assert key_available("custom") is True


def test_huggingface_provider(monkeypatch):
    assert "huggingface" in PROVIDERS
    monkeypatch.setenv("HF_TOKEN", "hf_xyz")
    c = make_client("huggingface", model="Qwen/Qwen2.5-7B-Instruct")
    assert c.base_url == "https://router.huggingface.co/v1"
    assert c.api_key == "hf_xyz"
    assert c.model == "Qwen/Qwen2.5-7B-Instruct"


def test_hf_runtimes_cover_hosted_and_local():
    runtimes = hf_runtimes()
    ids = {r["id"] for r in runtimes}
    # a hosted (no-install) path plus the common local servers
    assert {"hf-router", "vllm", "ollama", "llamacpp", "lmstudio"} <= ids
    by_id = {r["id"]: r for r in runtimes}
    assert by_id["hf-router"]["local"] is False
    assert by_id["vllm"]["local"] is True
    # local runtimes carry a serve command templated on the repo id
    assert "{repo}" in by_id["vllm"]["command"]
    # each runtime maps to a backend Athena can actually switch to
    backends = set(PROVIDERS) | {"ollama"}
    for r in runtimes:
        assert r["provider"] in backends, r["id"]
