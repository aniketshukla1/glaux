"""Run a model straight from a local file on disk.

For builders and fine-tuners: point Athena at a weights file
(``.gguf`` / ``.safetensors`` / ``.bin`` / ``.pt``) or a model directory and it
launches the right local inference server — llama.cpp for GGUF, vLLM for
Hugging Face weights — waits for it to come up, and runs the whole swarm on it
over the OpenAI API. Athena owns the server process lifecycle (start / status /
stop), so all the user provides is a path.

The model itself runs in that server; Athena talks to it with the same
:class:`~llm.providers.OpenAICompatibleClient` as every other backend.
"""

from __future__ import annotations

import collections
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Optional


class LocalModelError(RuntimeError):
    """Couldn't launch a local model server (bad path, no runtime, timeout)."""


GGUF_EXT = ".gguf"
HF_WEIGHT_EXTS = (".safetensors", ".bin", ".pt", ".pth")


def detect_format(path: Path) -> str:
    if path.is_dir():
        return "hf-dir"
    suffix = path.suffix.lower()
    if suffix == GGUF_EXT:
        return "gguf"
    if suffix in HF_WEIGHT_EXTS:
        return "hf-weights"
    return "unknown"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def plan_runtime(path: Path) -> dict:
    """Decide which runtime serves ``path``, whether it's installed, and — if
    not — how to get it. Returns a plan dict; ``cmd`` is a ``port -> argv``
    builder present only when a runtime is available."""
    fmt = detect_format(path)

    if fmt == "gguf":
        if find_spec("llama_cpp"):
            return {
                "format": fmt, "runtime": "llama-cpp-python", "available": True, "model": path.stem,
                "cmd": lambda port: [
                    sys.executable, "-m", "llama_cpp.server",
                    "--model", str(path), "--host", "127.0.0.1", "--port", str(port),
                ],
            }
        if shutil.which("llama-server"):
            return {
                "format": fmt, "runtime": "llama.cpp", "available": True, "model": path.stem,
                "cmd": lambda port: [
                    "llama-server", "-m", str(path), "--host", "127.0.0.1", "--port", str(port),
                ],
            }
        return {
            "format": fmt, "runtime": "llama.cpp", "available": False, "model": path.stem,
            "install": "pip install 'llama-cpp-python[server]'  — or install the llama.cpp `llama-server` binary",
        }

    if fmt in ("hf-dir", "hf-weights"):
        model_dir = path if path.is_dir() else path.parent
        if shutil.which("vllm"):
            return {
                "format": fmt, "runtime": "vllm", "available": True, "model": str(model_dir),
                "cmd": lambda port: ["vllm", "serve", str(model_dir), "--host", "127.0.0.1", "--port", str(port)],
            }
        if find_spec("vllm"):
            return {
                "format": fmt, "runtime": "vllm", "available": True, "model": str(model_dir),
                "cmd": lambda port: [
                    sys.executable, "-m", "vllm.entrypoints.openai.api_server",
                    "--model", str(model_dir), "--host", "127.0.0.1", "--port", str(port),
                ],
            }
        return {
            "format": fmt, "runtime": "vllm", "available": False, "model": str(model_dir),
            "install": "pip install vllm  — a GPU is strongly recommended for .safetensors/.bin/.pt weights",
        }

    return {
        "format": "unknown", "runtime": None, "available": False,
        "error": "unrecognized model — expected a .gguf / .safetensors / .bin / .pt file, or a model directory",
    }


class LocalModelManager:
    """Owns a single local-model server subprocess and its lifecycle."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._logs: collections.deque = collections.deque(maxlen=80)
        self._lock = threading.Lock()
        self.info: Optional[dict] = None

    # -- introspection --
    def plan(self, path_str: str) -> dict:
        p = Path(path_str).expanduser()
        if not p.exists():
            return {"error": f"path not found: {p}"}
        plan = plan_runtime(p)
        plan.pop("cmd", None)  # not serializable / not needed by the UI
        return {**plan, "path": str(p)}

    def status(self) -> dict:
        running = self._proc is not None and self._proc.poll() is None
        if self.info and self._proc is not None and self._proc.poll() is not None and self.info.get("status") == "running":
            self.info = {**self.info, "status": "exited"}
        return {"running": running, **(self.info or {"status": "idle"})}

    # -- lifecycle --
    def launch(
        self,
        path_str: str,
        *,
        port: Optional[int] = None,
        ready_timeout: float = 180.0,
        plan_fn: Optional[Callable[[Path], dict]] = None,
    ) -> dict:
        p = Path(path_str).expanduser()
        if not p.exists():
            raise LocalModelError(f"path not found: {p}")
        plan = (plan_fn or plan_runtime)(p)
        if plan.get("error"):
            raise LocalModelError(plan["error"])
        if not plan.get("available"):
            raise LocalModelError(
                f"no runtime installed to serve {plan.get('format')} — {plan.get('install', '')}"
            )

        port = port or _free_port()
        base_url = f"http://127.0.0.1:{port}/v1"
        cmd = plan["cmd"](port)

        with self._lock:
            self._stop_locked()
            self._logs.clear()
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )
            self._reader = threading.Thread(target=self._read_logs, args=(self._proc,), daemon=True)
            self._reader.start()
            self.info = {
                "status": "loading", "path": str(p), "runtime": plan["runtime"], "format": plan["format"],
                "model": plan["model"], "port": port, "base_url": base_url, "command": " ".join(cmd),
            }

        try:
            self._wait_ready(base_url, ready_timeout)
        except LocalModelError:
            self.stop()
            raise
        self.info = {**self.info, "status": "running"}
        return self.status()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        if self.info:
            self.info = {**self.info, "status": "stopped"}

    # -- internals --
    def _read_logs(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                self._logs.append(line.rstrip())
        except Exception:  # noqa: BLE001
            pass

    def _tail(self, n: int = 12) -> str:
        return "\n".join(list(self._logs)[-n:])

    def _wait_ready(self, base_url: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        url = base_url.rstrip("/") + "/models"
        while time.monotonic() < deadline:
            if self._proc is None or self._proc.poll() is not None:
                code = self._proc.returncode if self._proc else "?"
                raise LocalModelError(f"the model server exited (code {code}):\n{self._tail()}")
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status == 200:
                        return
            except Exception:  # noqa: BLE001 - not up yet
                pass
            time.sleep(0.5)
        raise LocalModelError(f"timed out after {timeout:.0f}s waiting for the model server:\n{self._tail()}")
