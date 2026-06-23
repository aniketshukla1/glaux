"""Built-in web/browser tools — parsing and error handling (no real network).

We monkeypatch the single HTTP chokepoint (`agents.web._http_get`) so these
tests are deterministic and offline; the live-network behaviour is exercised
manually.
"""

import urllib.error

import pytest

from agents import default_browser_client
from agents.web import (
    begin_source_capture,
    collected_sources,
    configure_search,
    resolve_provider,
    web_fetch,
    web_search,
)


@pytest.fixture(autouse=True)
def _reset_search(monkeypatch):
    # Each test starts with no pinned provider and no env keys.
    for v in ("ATHENA_SEARCH_PROVIDER", "ATHENA_BRAVE_API_KEY", "ATHENA_TAVILY_API_KEY", "ATHENA_SERPER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    configure_search("", {})
    yield
    configure_search("", {})


_PAGE = """
<html><head><title>  Ada Lovelace  </title><style>.x{color:red}</style></head>
<body>
  <script>var noise = 1;</script>
  <h1>Notes</h1>
  <p>First paragraph about analytical engines.</p>
  <p>Second &amp; final paragraph.</p>
</body></html>
"""

_LITE = """
<html><body><table>
<tr><td>1.&nbsp;</td><td>
  <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FEdDSA&rut=ab" class='result-link'>EdDSA - Wikipedia</a>
</td></tr>
<tr><td></td><td class='result-snippet'>Ed25519 is an EdDSA signature scheme.</td></tr>
<tr><td>2.&nbsp;</td><td>
  <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fsig&rut=cd" class='result-link'>Signatures &amp; You</a>
</td></tr>
<tr><td></td><td class='result-snippet'>A practical guide.</td></tr>
</table></body></html>
"""


def test_web_fetch_extracts_title_and_text(monkeypatch):
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("https://x.test/", "text/html", _PAGE))
    out = web_fetch("x.test")
    assert out["title"] == "Ada Lovelace"
    assert "analytical engines" in out["text"]
    assert "Second & final paragraph." in out["text"]
    assert "noise" not in out["text"] and "color:red" not in out["text"]  # script/style dropped
    assert out["url"] == "https://x.test/"
    assert out["truncated"] is False


def test_web_fetch_truncates_long_pages(monkeypatch):
    big = "<html><body>" + ("word " * 20000) + "</body></html>"
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("https://x.test/", "text/html", big))
    out = web_fetch("https://x.test/")
    assert out["truncated"] is True
    assert out["chars"] <= 12_000


def test_web_fetch_network_error_surfaces_as_exception(monkeypatch):
    def boom(url, timeout=15.0):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr("agents.web._http_get", boom)
    with pytest.raises(RuntimeError) as ei:
        web_fetch("https://nope.invalid/")
    assert "could not reach" in str(ei.value)


def test_web_search_parses_lite_results(monkeypatch):
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("u", "text/html", _LITE))
    out = web_search("ed25519", limit=5)
    res = out["results"]
    assert len(res) == 2
    assert res[0]["title"] == "EdDSA - Wikipedia"
    assert res[0]["url"] == "https://en.wikipedia.org/wiki/EdDSA"  # uddg redirect unwrapped
    assert res[0]["snippet"].startswith("Ed25519 is an EdDSA")
    assert res[1]["title"] == "Signatures & You"
    assert res[1]["url"] == "https://example.org/sig"


def test_web_search_limit_respected(monkeypatch):
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("u", "text/html", _LITE))
    assert len(web_search("ed25519", limit=1)["results"]) == 1


def test_browser_client_registers_tools_and_wraps_errors(monkeypatch):
    client = default_browser_client()
    names = {t.name for t in client.list_tools()}
    assert {"web_search", "web_fetch"} <= names

    # call_tool wraps a successful return…
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("https://x.test/", "text/html", _PAGE))
    ok = client.call_tool("web_fetch", {"url": "x.test"})
    assert ok["ok"] is True and ok["result"]["title"] == "Ada Lovelace"

    # …and turns a raised error into an observation rather than crashing.
    def boom(url, timeout=15.0):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("agents.web._http_get", boom)
    bad = client.call_tool("web_fetch", {"url": "x.test"})
    assert bad["ok"] is False and "could not reach" in bad["error"]


def test_source_capture_records_fetched_and_searched(monkeypatch):
    begin_source_capture()
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("https://x.test/", "text/html", _PAGE))
    web_fetch("x.test")
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("u", "text/html", _LITE))
    web_search("ed25519", limit=5)
    urls = [s["url"] for s in collected_sources()]
    assert "https://x.test/" in urls
    assert "https://en.wikipedia.org/wiki/EdDSA" in urls
    # the fetched page carried its title through
    fetched = next(s for s in collected_sources() if s["url"] == "https://x.test/")
    assert fetched["title"] == "Ada Lovelace"


def test_source_capture_dedupes_and_is_noop_without_session(monkeypatch):
    # No capture started → recording is a harmless no-op (no crash, nothing kept).
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("https://x.test/", "text/html", _PAGE))
    web_fetch("x.test")  # outside any capture
    begin_source_capture()
    web_fetch("x.test")
    web_fetch("x.test")  # same url twice → deduped
    assert [s["url"] for s in collected_sources()] == ["https://x.test/"]


# --- pluggable search providers ------------------------------------------

_BRAVE = {"web": {"results": [
    {"title": "Ed25519 <strong>signature</strong>", "url": "https://a.test/1", "description": "fast <b>EdDSA</b>"},
    {"title": "More", "url": "https://a.test/2", "description": "second"},
]}}
_TAVILY = {"results": [
    {"title": "Tavily One", "url": "https://t.test/1", "content": "answer-style content"},
]}
_SERPER = {"organic": [
    {"title": "Serper One", "url": "https://s.test/1", "snippet": "google snippet"},
]}


def test_resolve_provider_defaults_to_duckduckgo():
    assert resolve_provider() == ("duckduckgo", "")


def test_resolve_provider_auto_picks_keyed_provider():
    configure_search("", {"tavily": "tvly-x"})
    assert resolve_provider() == ("tavily", "tvly-x")
    configure_search("", {"brave": "bk", "tavily": "tvly-x"})  # brave wins by preference order
    assert resolve_provider() == ("brave", "bk")


def test_resolve_provider_env_key(monkeypatch):
    monkeypatch.setenv("ATHENA_SERPER_API_KEY", "sk-env")
    assert resolve_provider() == ("serper", "sk-env")


def test_pinned_provider_without_key_falls_back():
    configure_search("brave", {})  # pinned but no key
    assert resolve_provider() == ("duckduckgo", "")


def test_web_search_uses_brave_when_configured(monkeypatch):
    configure_search("brave", {"brave": "bk"})
    monkeypatch.setattr("agents.web._http_json", lambda *a, **k: _BRAVE)
    out = web_search("ed25519", limit=5)
    assert out["provider"] == "brave"
    assert out["results"][0]["title"] == "Ed25519 signature"  # html stripped
    assert out["results"][0]["url"] == "https://a.test/1"
    assert out["results"][0]["snippet"] == "fast EdDSA"


def test_web_search_tavily_and_serper(monkeypatch):
    configure_search("tavily", {"tavily": "tk"})
    monkeypatch.setattr("agents.web._http_json", lambda *a, **k: _TAVILY)
    assert web_search("q")["results"][0]["url"] == "https://t.test/1"

    configure_search("serper", {"serper": "sk"})
    monkeypatch.setattr("agents.web._http_json", lambda *a, **k: _SERPER)
    assert web_search("q")["results"][0]["snippet"] == "google snippet"


def test_web_search_falls_back_to_ddg_on_provider_error(monkeypatch):
    configure_search("brave", {"brave": "bk"})

    def boom(*a, **k):
        raise urllib.error.URLError("brave down")

    monkeypatch.setattr("agents.web._http_json", boom)
    monkeypatch.setattr("agents.web._http_get", lambda url, timeout=15.0: ("u", "text/html", _LITE))
    out = web_search("ed25519")
    assert out["provider"] == "brave→duckduckgo"
    assert any(r["url"] == "https://en.wikipedia.org/wiki/EdDSA" for r in out["results"])
