"""Built-in web/browser tools — parsing and error handling (no real network).

We monkeypatch the single HTTP chokepoint (`agents.web._http_get`) so these
tests are deterministic and offline; the live-network behaviour is exercised
manually.
"""

import urllib.error

import pytest

from agents import default_browser_client
from agents.web import web_fetch, web_search


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
