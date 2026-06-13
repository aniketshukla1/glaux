"""Local model file support — format detection, runtime planning, and the
managed server lifecycle (exercised against a stub OpenAI server)."""

from __future__ import annotations

import pathlib
import sys

import pytest

from llm import Message  # noqa: E402
from llm.localmodel import LocalModelError, LocalModelManager, detect_format, plan_runtime  # noqa: E402
from llm.providers import OpenAICompatibleClient  # noqa: E402

FAKE_SERVER = pathlib.Path(__file__).parent / "fixtures" / "fake_openai_server.py"


# --- format detection ----------------------------------------------------


def test_detect_format(tmp_path):
    assert detect_format(tmp_path / "model.gguf") == "gguf"
    assert detect_format(tmp_path / "model.safetensors") == "hf-weights"
    assert detect_format(tmp_path / "model.bin") == "hf-weights"
    assert detect_format(tmp_path / "model.pt") == "hf-weights"
    assert detect_format(tmp_path) == "hf-dir"  # a directory
    assert detect_format(tmp_path / "notes.txt") == "unknown"


# --- runtime planning ----------------------------------------------------


def test_plan_gguf_without_runtime(tmp_path):
    gguf = tmp_path / "tiny.gguf"
    gguf.write_bytes(b"\x00")
    plan = plan_runtime(gguf)
    assert plan["format"] == "gguf"
    # neither llama_cpp nor llama-server is installed in the test env
    if not plan["available"]:
        assert "llama" in plan["install"].lower()
        assert plan["model"] == "tiny"


def test_plan_safetensors_points_at_vllm(tmp_path):
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"\x00")
    plan = plan_runtime(weights)
    assert plan["format"] == "hf-weights" and plan["runtime"] == "vllm"
    if not plan["available"]:
        assert "vllm" in plan["install"].lower()


def test_plan_unknown(tmp_path):
    plan = plan_runtime(tmp_path / "weights.zip")
    assert plan["format"] == "unknown" and plan.get("error")


# --- manager lifecycle (with a stub runtime) -----------------------------


def _fake_plan(path):
    """A plan whose 'runtime' is the stub OpenAI server — exercises launch ->
    readiness -> serve -> stop without a real model runtime."""
    return {
        "format": "gguf", "runtime": "stub", "available": True, "model": path.stem,
        "cmd": lambda port: [sys.executable, str(FAKE_SERVER), "--port", str(port)],
    }


def test_launch_serve_and_stop(tmp_path):
    gguf = tmp_path / "mymodel.gguf"
    gguf.write_bytes(b"\x00")
    mgr = LocalModelManager()
    status = mgr.launch(str(gguf), plan_fn=_fake_plan, ready_timeout=20)
    try:
        assert status["running"] is True
        assert status["status"] == "running"
        assert status["model"] == "mymodel"
        assert status["base_url"].startswith("http://127.0.0.1:")
        # the swarm can actually talk to it through the standard client
        client = OpenAICompatibleClient(base_url=status["base_url"], model="local", provider="local")
        res = client.complete([Message(role="user", content="ping")])
        assert res.text == "local-echo:ping"
    finally:
        mgr.stop()
    assert mgr.status()["running"] is False


def test_launch_missing_path():
    mgr = LocalModelManager()
    with pytest.raises(LocalModelError) as e:
        mgr.launch("/no/such/model.gguf")
    assert "not found" in str(e.value)


def test_launch_no_runtime_reports_install(tmp_path):
    gguf = tmp_path / "x.gguf"
    gguf.write_bytes(b"\x00")
    mgr = LocalModelManager()
    plan = plan_runtime(gguf)
    if plan["available"]:
        pytest.skip("a gguf runtime is actually installed here")
    with pytest.raises(LocalModelError) as e:
        mgr.launch(str(gguf))
    assert "no runtime" in str(e.value).lower()
