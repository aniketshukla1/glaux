"""Built-in web / browser tools.

Gives agents real read-access to the live web — run a search, or fetch and clean
a page — exposed as in-process MCP tools, so the very same ``call_mcp`` action an
agent already emits reaches them. Results are structured and capped, and every
call reports the source URL(s) so the UI can render them as citations.

Pure standard library (``urllib`` + ``html.parser``): no third-party deps. When
the network is unavailable the tool surfaces a clear error observation rather
than crashing the agent loop.
"""

from __future__ import annotations

import contextvars
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .mcp import LocalMCPClient

# Per-task source capture. run_task starts a bucket before the swarm runs; the
# web tools record every page they read / surface into it (it propagates into
# the worker thread the swarm runs in via contextvars). The result then carries
# real citations — sources are never fabricated, only what was actually visited.
_sources: contextvars.ContextVar = contextvars.ContextVar("athena_web_sources", default=None)


def begin_source_capture() -> list:
    """Start a fresh source bucket for the current logical task; returns it."""
    bucket: list = []
    _sources.set(bucket)
    return bucket


def collected_sources() -> list:
    bucket = _sources.get()
    return list(bucket) if bucket else []


def _record_source(url: str, title: str = "") -> None:
    bucket = _sources.get()
    if bucket is None or not url:
        return
    for s in bucket:
        if s["url"] == url:
            if title and not s.get("title"):
                s["title"] = title
            return
    if len(bucket) < 50:
        bucket.append({"url": url, "title": title or ""})

USER_AGENT = "Mozilla/5.0 (compatible; AthenaAgent/1.0; +https://athena.local)"
_MAX_BYTES = 2_000_000   # don't read unbounded pages into memory
_MAX_TEXT = 12_000       # cap the readable text handed back to the model
_TIMEOUT = 15.0


class _TextExtractor(HTMLParser):
    """Flatten HTML to readable text + the document <title>, dropping script/
    style/nav noise. Block-level tags become line breaks so the text reads."""

    _SKIP = {"script", "style", "noscript", "template", "svg", "iframe"}
    _BLOCK = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr", "section", "article", "header", "footer", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._parts: list[str] = []
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        t = data.strip()
        if t:
            self._parts.append(t + " ")

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _http_get(url: str, timeout: float = _TIMEOUT) -> tuple[str, str, str]:
    """GET a URL, returning (final_url, content_type, decoded_body)."""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - http(s) only, enforced above
        ctype = resp.headers.get("Content-Type", "") or ""
        raw = resp.read(_MAX_BYTES)
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    if m:
        charset = m.group(1)
    return resp.geturl() if hasattr(resp, "geturl") else url, ctype, raw.decode(charset, errors="replace")


def web_fetch(url: str) -> dict:
    """Fetch a web page and return its readable text and title.

    Raises on network/HTTP failure so the agent sees a clear error observation
    (LocalMCPClient turns the exception into ``{ok: False, error}``)."""
    if not url or not str(url).strip():
        raise ValueError("web_fetch needs a url")
    try:
        final_url, ctype, body = _http_get(str(url).strip())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {e.reason} fetching {url}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach {url}: {e.reason}")

    looks_html = "html" in ctype.lower() or body.lstrip()[:1] == "<"
    if looks_html:
        p = _TextExtractor()
        try:
            p.feed(body)
        except Exception:  # noqa: BLE001 - malformed HTML: keep whatever we parsed
            pass
        title = html.unescape(p.title).strip()
        text = p.text()
    else:
        title = ""
        text = body.strip()

    _record_source(final_url, title)
    truncated = len(text) > _MAX_TEXT
    return {
        "url": final_url,
        "title": title,
        "text": text[:_MAX_TEXT],
        "truncated": truncated,
        "chars": min(len(text), _MAX_TEXT),
    }


def _ddg_unwrap(href: str) -> str:
    """DuckDuckGo HTML results wrap the real link in a /l/?uddg= redirect."""
    if "uddg=" in href:
        query = urllib.parse.urlparse(("https:" + href) if href.startswith("//") else href).query
        params = urllib.parse.parse_qs(query)
        if params.get("uddg"):
            return params["uddg"][0]
    if href.startswith("//"):
        return "https:" + href
    return href


def web_search(query: str, limit: int = 5) -> dict:
    """Search the web (DuckDuckGo) and return result titles, URLs and snippets."""
    if not query or not str(query).strip():
        raise ValueError("web_search needs a query")
    limit = max(1, min(int(limit or 5), 10))
    # The lite endpoint returns clean, server-rendered HTML (no JS challenge).
    url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": str(query).strip()})
    try:
        _final, _ctype, body = _http_get(url)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(f"search failed: {reason}")

    results: list[dict] = []
    for m in re.finditer(r"<a\b([^>]*\bclass=['\"]result-link['\"][^>]*)>(.*?)</a>", body, re.S):
        href_m = re.search(r"""href=['"]([^'"]+)['"]""", m.group(1))
        if not href_m:
            continue
        link = _ddg_unwrap(href_m.group(1))
        title = _strip_tags(html.unescape(m.group(2)))
        if link and title:
            results.append({"title": title, "url": link})
        if len(results) >= limit:
            break

    snippets = [_strip_tags(html.unescape(s)) for s in re.findall(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", body, re.S)]
    for i, r in enumerate(results):
        if i < len(snippets):
            r["snippet"] = snippets[i][:300]

    if not results:
        return {"query": query, "results": [], "note": "no results — search may be rate-limited or blocked"}
    for r in results:
        _record_source(r["url"], r["title"])
    return {"query": query, "results": results}


def default_browser_client() -> LocalMCPClient:
    """A LocalMCPClient exposing Athena's built-in web tools (server 'athena-web')."""
    c = LocalMCPClient(server_name="athena-web")
    c.register(
        "web_search",
        "Search the live web (DuckDuckGo) for a query. Returns a list of result titles, URLs and snippets.",
        web_search,
        {"query": "string", "limit": "integer 1-10 (default 5)"},
    )
    c.register(
        "web_fetch",
        "Fetch a web page by URL and return its readable text and title. Use after web_search to read a chosen result.",
        web_fetch,
        {"url": "string (http(s) URL)"},
    )
    return c
