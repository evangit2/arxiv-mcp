"""arxiv-mcp server: search + extract arXiv papers, no API keys.

Backend: public export.arxiv.org API (no key, ~1 req / 3s politeness)
         + ar5iv HTML for full-text extraction (no key).
Stdlib networking only (urllib) so the server stays lean.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

try:
    from fastmcp import FastMCP
except ImportError:  # mcp 1.x SDK layout
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("arxiv")

API_BASE = "https://export.arxiv.org/api/query"
ABS_BASE = "https://arxiv.org/abs/"
PDF_BASE = "https://arxiv.org/pdf/"
AR5IV_BASE = "https://ar5iv.org/html/"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
USER_AGENT = "arxiv-mcp/0.1.0 (https://github.com/evangit2/arxiv-mcp; mailto:evangit2@users.noreply.github.com)"

_last_call_ts = 0.0


def _polite_wait(min_interval: float = 3.0) -> None:
    global _last_call_ts
    dt = time.time() - _last_call_ts
    if dt < min_interval:
        time.sleep(min_interval - dt)
    _last_call_ts = time.time()


def _http_get(url: str, timeout: int = 30) -> bytes:
    _polite_wait()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def _parse_entry(entry: ET.Element) -> dict:
    raw_id = _text(entry.find("a:id", ATOM_NS))
    arxiv_id = raw_id.split("/abs/")[-1].split("v")[0] if "/abs/" in raw_id else raw_id
    versioned = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
    authors = [
        _text(a.find("a:name", ATOM_NS)) for a in entry.findall("a:author", ATOM_NS)
    ]
    cats = [c.get("term", "") for c in entry.findall("a:category", ATOM_NS)]
    links = {l.get("rel", ""): l.get("href", "") for l in entry.findall("a:link", ATOM_NS)}
    return {
        "id": arxiv_id,
        "versioned_id": versioned,
        "title": _text(entry.find("a:title", ATOM_NS)),
        "authors": authors,
        "published": _text(entry.find("a:published", ATOM_NS))[:10],
        "updated": _text(entry.find("a:updated", ATOM_NS))[:10],
        "summary": _text(entry.find("a:summary", ATOM_NS)),
        "categories": cats,
        "abs_url": f"{ABS_BASE}{arxiv_id}",
        "pdf_url": f"{PDF_BASE}{arxiv_id}",
        "html_url": f"{AR5IV_BASE}{versioned}",
        "alternate_link": links.get("alternate", ""),
    }


def _query_api(params: dict) -> list[dict]:
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    try:
        data = _http_get(url)
    except Exception as e:
        raise RuntimeError(f"arXiv API request failed: {e}")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise RuntimeError(f"arXiv API returned unparsable XML: {e}")
    return [_parse_entry(e) for e in root.findall("a:entry", ATOM_NS)]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = True
        elif tag in ("p", "br", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = False
        elif tag in ("p", "h1", "h2", "h3", "h4", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            s = data.strip()
            if s:
                self.parts.append(s + " ")

    def get_text(self) -> str:
        text = "".join(self.parts)
        return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def _strip_html(html_bytes: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            html = html_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        html = html_bytes.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


@mcp.tool()
def search_papers(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    search_field: str = "all",
) -> list[dict]:
    """Search arXiv papers. No API key needed.

    Args:
        query: keywords, e.g. "quantum error correction".
            For author/category/ID searches use search_field instead.
        max_results: 1-50 papers to return.
        sort_by: "relevance", "lastUpdatedDate" or "submittedDate".
        sort_order: "ascending" or "descending".
        search_field: "all" | "title" | "author" | "abstract" | "category" | "id".
            "category" expects e.g. "cs.AI"; "id" expects an arXiv ID.
    """
    max_results = max(1, min(int(max_results), 50))
    if sort_by not in ("relevance", "lastUpdatedDate", "submittedDate"):
        sort_by = "relevance"
    if sort_order not in ("ascending", "descending"):
        sort_order = "descending"
    prefix = {
        "all": "all",
        "title": "ti",
        "author": "au",
        "abstract": "abs",
        "category": "cat",
        "id": "id",
    }.get(search_field, "all")
    if search_field == "id":
        params = {"id_list": query.strip(), "max_results": max_results}
    else:
        params = {
            "search_query": f"{prefix}:{query.strip()}",
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
    return _query_api(params)


@mcp.tool()
def get_paper(arxiv_id: str) -> dict:
    """Get full metadata + abstract for one arXiv ID (e.g. "1706.03762"). No API key needed."""
    arxiv_id = arxiv_id.strip()
    papers = _query_api({"id_list": arxiv_id, "max_results": 1})
    if not papers:
        raise ValueError(f"No paper found for ID {arxiv_id!r}")
    return papers[0]


@mcp.tool()
def extract_paper(arxiv_id: str, max_chars: int = 20000) -> dict:
    """Extract readable full text of a paper. No API key needed.

    Returns the abstract (from the API) plus body text scraped from the
    ar5iv HTML rendering, truncated to max_chars. Falls back to the
    abstract alone when no HTML rendering exists yet.
    """
    arxiv_id = arxiv_id.strip().split("/")[-1]
    meta = get_paper(arxiv_id)
    max_chars = max(1000, min(int(max_chars), 200000))
    full_text = ""
    source_used = "abstract-only"
    for url in (meta["html_url"], f"{AR5IV_BASE}{meta['id']}"):
        try:
            full_text = _strip_html(_http_get(url))
            # ar5iv error pages are short; real papers are long
            if len(full_text) > 2000:
                source_used = url
                break
        except Exception:
            continue
    else:
        full_text = ""
    truncated = len(full_text) > max_chars
    return {
        "id": meta["id"],
        "title": meta["title"],
        "authors": meta["authors"],
        "published": meta["published"],
        "categories": meta["categories"],
        "abstract": meta["summary"],
        "abs_url": meta["abs_url"],
        "pdf_url": meta["pdf_url"],
        "text_source": source_used,
        "text_length": len(full_text),
        "truncated": truncated,
        "text": full_text[:max_chars],
    }


DATASETS_SERVER = "https://datasets-server.huggingface.co/filter"
CORPUS_DATASET = "secemp9/arxiv-complete"


@mcp.tool()
def corpus_lookup(paper_id: str) -> dict:
    """Look up one paper in the secemp9/arxiv-complete HF snapshot. No key needed.

    Uses the free Hugging Face datasets-server filter API (metadata config
    only) — no 16 TB download. Returns the corpus metadata row for the paper
    (title, abstract, licence, categories, version dates) plus pointers to
    where its files live in the snapshot.
    """
    pid = paper_id.strip()
    params = {
        "dataset": CORPUS_DATASET,
        "config": "metadata",
        "split": "train",
        "where": f"\"paper_id\"='{pid}'",
        "offset": 0,
        "length": 5,
    }
    url = DATASETS_SERVER + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            import json

            payload = json.loads(resp.read().decode("utf-8"))
        rows = payload.get("rows", [])
        if not rows:
            raise ValueError("empty")
        row = rows[0].get("row", rows[0])
        return {
            "paper_id": row.get("paper_id", pid),
            "title": row.get("title", ""),
            "abstract": row.get("abstract", ""),
            "categories": row.get("categories", ""),
            "primary_category": row.get("primary_category", ""),
            "license": row.get("license"),
            "doi": row.get("doi"),
            "journal_ref": row.get("journal_ref"),
            "n_versions": row.get("n_versions"),
            "first_version_date": row.get("first_version_date"),
            "latest_version_date": row.get("latest_version_date"),
            "abs_url": row.get("arxiv_abs_url", f"{ABS_BASE}{pid}"),
            "pdf_url": f"{PDF_BASE}{pid}",
            "corpus": CORPUS_DATASET,
            "corpus_source": "datasets-server",
        }
    except Exception as e:
        # datasets-server can 500 during outages; fall back to live arXiv
        # metadata plus deterministic snapshot pointers (no 16 TB download).
        meta = get_paper(pid)
        return {
            "paper_id": meta["id"],
            "title": meta["title"],
            "abstract": meta["summary"],
            "categories": " ".join(meta["categories"]),
            "primary_category": meta["categories"][0] if meta["categories"] else "",
            "license": None,
            "doi": None,
            "journal_ref": None,
            "n_versions": None,
            "first_version_date": None,
            "latest_version_date": None,
            "abs_url": meta["abs_url"],
            "pdf_url": meta["pdf_url"],
            "corpus": CORPUS_DATASET,
            "corpus_source": f"live-fallback (datasets-server error: {e})",
        }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
