"""OpenAI-compatible LLM providers — one adapter, the whole world of models.

Almost every modern LLM API (OpenAI, Google Gemini, xAI, Mistral, DeepSeek,
Groq, Together, Fireworks, Perplexity, Cerebras, SambaNova, DeepInfra, Novita,
Sarvam, Moonshot/Kimi, Zhipu/GLM, Alibaba Qwen, 01.AI/Yi, OpenRouter, and local
runtimes like LM Studio / vLLM / llama.cpp) exposes the same
``POST {base_url}/chat/completions`` shape. So a single
:class:`OpenAICompatibleClient` (stdlib HTTP, no SDK) plus a catalog of base
URLs covers them all. Anything else self-hosted slots in via the ``custom``
provider with a user-supplied base URL.

Native Anthropic (``AnthropicClient``) and Ollama (``OllamaClient``) keep their
own clients; everything else flows through here.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from .gateway import LLMResponse, Message


class LLMError(RuntimeError):
    """A provider request failed (HTTP error, bad key, unreachable host)."""


class OpenAICompatibleClient:
    """Talks to any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        provider: str = "openai",
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer ",
        extra_headers: Optional[dict] = None,
        timeout: float = 120.0,
        default_max_tokens: int = 1024,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_id = f"{provider}:{model}"
        self.api_key = api_key
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix
        self.extra_headers = extra_headers or {}
        self.timeout = timeout
        self._default_max_tokens = default_max_tokens

    def complete(
        self,
        messages: list[Message],
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: Optional[int] = None,
    ) -> LLMResponse:
        chat: list[dict] = []
        if system:
            chat.append({"role": "system", "content": system})
        chat.extend({"role": m.role, "content": m.content} for m in messages)

        payload: dict = {
            "model": self.model,
            "messages": chat,
            "temperature": temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
        }
        if seed is not None:
            payload["seed"] = seed

        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers[self.auth_header] = f"{self.auth_prefix}{self.api_key}"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise LLMError(f"{self.model_id}: HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            raise LLMError(f"{self.model_id}: connection error: {e.reason}")

        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            model_id=self.model_id,
            usage={
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            },
            raw=data,
        )


@dataclass
class Provider:
    id: str
    label: str
    base_url: str  # "" for custom (user supplies)
    key_env: Optional[str]  # env var holding the key; None for local/no-auth
    default_model: str
    models: list[str] = field(default_factory=list)
    docs: str = ""
    kind: str = "cloud"  # cloud | aggregator | regional | local | custom
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    extra_headers: dict = field(default_factory=dict)
    requires_key: bool = True


def _p(*args, **kwargs) -> Provider:
    return Provider(*args, **kwargs)


# Catalog. Ordered by kind for nice grouping in the UI. Base URLs are the part
# before "/chat/completions"; model lists are suggestions, not exhaustive — any
# model string the provider serves works.
_PROVIDER_LIST: list[Provider] = [
    # --- frontier / major cloud ---
    _p("openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY",
       "gpt-4o-mini", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3", "o4-mini"],
       "https://platform.openai.com/docs/api-reference"),
    _p("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
       "GEMINI_API_KEY", "gemini-2.5-flash",
       ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
       "https://ai.google.dev/gemini-api/docs/openai"),
    _p("xai", "xAI (Grok)", "https://api.x.ai/v1", "XAI_API_KEY", "grok-3-mini",
       ["grok-4", "grok-3", "grok-3-mini", "grok-2-vision-1212"], "https://docs.x.ai"),
    _p("mistral", "Mistral AI", "https://api.mistral.ai/v1", "MISTRAL_API_KEY",
       "mistral-small-latest",
       ["mistral-large-latest", "mistral-small-latest", "codestral-latest",
        "ministral-8b-latest", "magistral-medium-latest"], "https://docs.mistral.ai"),
    _p("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
       "deepseek-chat", ["deepseek-chat", "deepseek-reasoner"], "https://api-docs.deepseek.com"),
    _p("cohere", "Cohere", "https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY",
       "command-r", ["command-a-03-2025", "command-r-plus", "command-r"],
       "https://docs.cohere.com/docs/compatibility-api"),
    _p("ai21", "AI21 Labs", "https://api.ai21.com/studio/v1", "AI21_API_KEY", "jamba-mini",
       ["jamba-large", "jamba-mini"], "https://docs.ai21.com"),

    # --- aggregator / router ---
    _p("openrouter", "OpenRouter (300+ models)", "https://openrouter.ai/api/v1",
       "OPENROUTER_API_KEY", "openai/gpt-4o-mini",
       ["anthropic/claude-3.7-sonnet", "openai/gpt-4o", "google/gemini-2.5-pro",
        "meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat", "qwen/qwen-2.5-72b-instruct"],
       "https://openrouter.ai/docs", kind="aggregator"),
    _p("huggingface", "Hugging Face (any model)", "https://router.huggingface.co/v1",
       "HF_TOKEN", "meta-llama/Llama-3.3-70B-Instruct",
       ["meta-llama/Llama-3.3-70B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3-0324",
        "mistralai/Mistral-7B-Instruct-v0.3", "google/gemma-2-27b-it"],
       "https://huggingface.co/docs/inference-providers", kind="aggregator"),

    # --- fast inference / model hosts ---
    _p("groq", "Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
       "llama-3.3-70b-versatile",
       ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b",
        "qwen-2.5-32b", "mixtral-8x7b-32768"], "https://console.groq.com/docs", kind="host"),
    _p("together", "Together AI", "https://api.together.xyz/v1", "TOGETHER_API_KEY",
       "meta-llama/Llama-3.3-70B-Instruct-Turbo",
       ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen2.5-72B-Instruct-Turbo", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
       "https://docs.together.ai", kind="host"),
    _p("fireworks", "Fireworks AI", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY",
       "accounts/fireworks/models/llama-v3p3-70b-instruct",
       ["accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/deepseek-v3", "accounts/fireworks/models/qwen2p5-72b-instruct"],
       "https://docs.fireworks.ai", kind="host"),
    _p("perplexity", "Perplexity", "https://api.perplexity.ai", "PERPLEXITY_API_KEY", "sonar",
       ["sonar", "sonar-pro", "sonar-reasoning", "sonar-reasoning-pro"],
       "https://docs.perplexity.ai", kind="host"),
    _p("cerebras", "Cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "llama-3.3-70b",
       ["llama-3.3-70b", "llama3.1-8b", "qwen-3-32b"], "https://inference-docs.cerebras.ai", kind="host"),
    _p("sambanova", "SambaNova", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY",
       "Meta-Llama-3.3-70B-Instruct",
       ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-R1", "Qwen2.5-72B-Instruct"],
       "https://docs.sambanova.ai", kind="host"),
    _p("deepinfra", "DeepInfra", "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY",
       "meta-llama/Llama-3.3-70B-Instruct",
       ["meta-llama/Llama-3.3-70B-Instruct", "deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
       "https://deepinfra.com/docs", kind="host"),
    _p("novita", "Novita AI", "https://api.novita.ai/v3/openai", "NOVITA_API_KEY",
       "meta-llama/llama-3.3-70b-instruct",
       ["meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-v3", "qwen/qwen-2.5-72b-instruct"],
       "https://novita.ai/docs", kind="host"),
    _p("hyperbolic", "Hyperbolic", "https://api.hyperbolic.xyz/v1", "HYPERBOLIC_API_KEY",
       "meta-llama/Llama-3.3-70B-Instruct",
       ["meta-llama/Llama-3.3-70B-Instruct", "deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
       "https://docs.hyperbolic.xyz", kind="host"),
    _p("nebius", "Nebius AI Studio", "https://api.studio.nebius.ai/v1", "NEBIUS_API_KEY",
       "meta-llama/Llama-3.3-70B-Instruct",
       ["meta-llama/Llama-3.3-70B-Instruct", "deepseek-ai/DeepSeek-V3"],
       "https://docs.nebius.com/studio", kind="host"),
    _p("nvidia", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
       "meta/llama-3.3-70b-instruct",
       ["meta/llama-3.3-70b-instruct", "deepseek-ai/deepseek-r1",
        "nvidia/llama-3.1-nemotron-70b-instruct", "qwen/qwen2.5-72b-instruct"],
       "https://docs.api.nvidia.com", kind="host"),
    _p("nous", "Nous Research Portal", "https://inference-api.nousresearch.com/v1", "NOUS_API_KEY",
       "Hermes-3-Llama-3.1-70B",
       ["Hermes-4-405B", "Hermes-4-70B", "Hermes-3-Llama-3.1-70B", "DeepHermes-3-Llama-3-8B-Preview"],
       "https://portal.nousresearch.com", kind="host"),

    # --- regional / international ---
    _p("sarvam", "Sarvam AI (India)", "https://api.sarvam.ai/v1", "SARVAM_API_KEY", "sarvam-m",
       ["sarvam-m", "sarvam-30b", "sarvam-105b"], "https://docs.sarvam.ai", kind="regional"),
    _p("moonshot", "Moonshot AI (Kimi)", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY",
       "kimi-k2-0711-preview", ["kimi-k2-0711-preview", "moonshot-v1-128k", "kimi-latest"],
       "https://platform.moonshot.ai/docs", kind="regional"),
    _p("zhipu", "Zhipu AI (GLM)", "https://open.bigmodel.cn/api/paas/v4", "ZHIPUAI_API_KEY",
       "glm-4-flash", ["glm-4.6", "glm-4-plus", "glm-4-flash", "glm-4-air"],
       "https://docs.bigmodel.cn", kind="regional"),
    _p("dashscope", "Alibaba Qwen (DashScope)",
       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", "qwen-plus",
       ["qwen-max", "qwen-plus", "qwen-turbo", "qwen2.5-72b-instruct"],
       "https://www.alibabacloud.com/help/en/model-studio", kind="regional"),
    _p("yi", "01.AI (Yi)", "https://api.lingyiwanwu.com/v1", "YI_API_KEY", "yi-lightning",
       ["yi-lightning", "yi-large"], "https://platform.lingyiwanwu.com", kind="regional"),
    _p("baichuan", "Baichuan", "https://api.baichuan-ai.com/v1", "BAICHUAN_API_KEY",
       "Baichuan4-Turbo", ["Baichuan4-Turbo", "Baichuan4"], "https://platform.baichuan-ai.com",
       kind="regional"),

    # --- local / self-hosted (no key) ---
    _p("lmstudio", "LM Studio (local)", "http://localhost:1234/v1", None, "local-model",
       ["local-model"], "https://lmstudio.ai/docs", kind="local", requires_key=False),
    _p("vllm", "vLLM (local)", "http://localhost:8000/v1", None, "", [],
       "https://docs.vllm.ai", kind="local", requires_key=False),
    _p("llamacpp", "llama.cpp server (local)", "http://localhost:8080/v1", None, "", [],
       "https://github.com/ggml-org/llama.cpp", kind="local", requires_key=False),

    # --- catch-all ---
    _p("custom", "Custom (any OpenAI-compatible)", "", None, "", [],
       "Point at any endpoint exposing /chat/completions (Azure OpenAI, a proxy, a self-host).",
       kind="custom", requires_key=False),
]

PROVIDERS: dict[str, Provider] = {p.id: p for p in _PROVIDER_LIST}


def provider_catalog() -> list[dict]:
    """Serializable catalog for the UI — includes whether each key is set in the
    environment (the key value itself is never exposed)."""
    return [
        {
            "id": p.id,
            "label": p.label,
            "kind": p.kind,
            "base_url": p.base_url,
            "key_env": p.key_env,
            "key_present": bool(p.key_env and os.environ.get(p.key_env)),
            "requires_key": p.requires_key,
            "default_model": p.default_model,
            "models": list(p.models),
            "docs": p.docs,
        }
        for p in PROVIDERS.values()
    ]


def key_available(provider_id: str, explicit_key: Optional[str] = None) -> bool:
    p = PROVIDERS[provider_id]
    if not p.requires_key:
        return True
    return bool(explicit_key or (p.key_env and os.environ.get(p.key_env)))


# --- Hugging Face: run any downloaded model -------------------------------
# Athena orchestrates; the model is served by a runtime that speaks the OpenAI
# API. These are the ways to take any model off the HF Hub and point Athena at
# it — a hosted router (no install) or a local server you run yourself. The
# ``{repo}`` placeholder is the HF repo id (e.g. "Qwen/Qwen2.5-7B-Instruct").
HF_RUNTIMES: list[dict] = [
    {
        "id": "hf-router", "label": "Hugging Face Inference (hosted)", "provider": "huggingface",
        "base_url": "https://router.huggingface.co/v1", "command": "", "local": False,
        "note": "No install. Needs an HF token; routes any model across inference providers.",
    },
    {
        "id": "vllm", "label": "vLLM (local · GPU)", "provider": "vllm",
        "base_url": "http://localhost:8000/v1", "command": "pip install vllm && vllm serve {repo}",
        "local": True, "note": "High-throughput GPU serving. OpenAI API on :8000.",
    },
    {
        "id": "ollama", "label": "Ollama (local · CPU/GPU)", "provider": "ollama",
        "base_url": "", "command": "ollama run hf.co/{repo}", "model": "hf.co/{repo}",
        "local": True, "note": "For GGUF repos — runs anywhere, no GPU required.",
    },
    {
        "id": "llamacpp", "label": "llama.cpp (local)", "provider": "llamacpp",
        "base_url": "http://localhost:8080/v1", "command": "llama-server -hf {repo}",
        "local": True, "note": "Pulls a GGUF straight from the Hub. OpenAI API on :8080.",
    },
    {
        "id": "lmstudio", "label": "LM Studio (local · GUI)", "provider": "lmstudio",
        "base_url": "http://localhost:1234/v1",
        "command": "In LM Studio: search & download {repo}, then start the Local Server",
        "local": True, "note": "Easiest no-terminal path. OpenAI API on :1234.",
    },
    {
        "id": "tgi", "label": "Text Generation Inference (Docker)", "provider": "custom",
        "base_url": "http://localhost:8080/v1",
        "command": "docker run --gpus all -p 8080:80 ghcr.io/huggingface/text-generation-inference --model-id {repo}",
        "local": True, "note": "HF's official server. Messages API on :8080.",
    },
    {
        "id": "transformers", "label": "transformers serve (local)", "provider": "custom",
        "base_url": "http://localhost:8000/v1",
        "command": 'pip install "transformers[serving]" && transformers serve',
        "local": True, "note": "Then set the model to {repo}. OpenAI API on :8000.",
    },
]


def hf_runtimes() -> list[dict]:
    return [dict(r) for r in HF_RUNTIMES]


def make_client(
    provider_id: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 120.0,
) -> OpenAICompatibleClient:
    p = PROVIDERS.get(provider_id)
    if p is None:
        raise KeyError(f"unknown provider {provider_id!r}")
    burl = base_url or p.base_url
    if not burl:
        raise ValueError(f"provider {provider_id!r} requires a base_url")
    key = api_key or (os.environ.get(p.key_env) if p.key_env else None)
    return OpenAICompatibleClient(
        base_url=burl,
        model=model or p.default_model,
        api_key=key,
        provider=provider_id,
        auth_header=p.auth_header,
        auth_prefix=p.auth_prefix,
        extra_headers=p.extra_headers,
        timeout=timeout,
    )
