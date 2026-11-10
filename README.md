# arxiv-mcp

MCP server for fast arXiv search + full-text extraction. **No API keys.**

Backend is the public `export.arxiv.org` API plus the ar5iv HTML rendering — stdlib networking only (`urllib`), so the server stays lean.

## Tools

| Tool | What it does |
|---|---|
| `search_papers(query, max_results, sort_by, sort_order, search_field)` | Keyword / title / author / category / ID search |
| `get_paper(arxiv_id)` | Full metadata + abstract for one ID |
| `extract_paper(arxiv_id, max_chars)` | Abstract + readable body text via ar5iv HTML (falls back to abstract) |
| `corpus_lookup(paper_id)` | Metadata row from the `secemp9/arxiv-complete` HF snapshot via the free datasets-server API (no 16 TB download) |

## Quick start

```bash
pip install arxiv-mcp
arxiv-mcp   # stdio MCP server
```

From source:

```bash
pip install -e .
python -m arxiv_mcp.server
```

## Client config

Claude Desktop / Hermes (`~/.hermes/config.yaml` style):

```json
{
  "mcpServers": {
    "arxiv": {
      "command": "arxiv-mcp",
      "args": []
    }
  }
}
```

```yaml
mcp_servers:
  arxiv:
    command: "arxiv-mcp"
```

From source without install:

```yaml
mcp_servers:
  arxiv:
    command: "python"
    args: ["-m", "arxiv_mcp.server"]
```

## Examples

- `search_papers("quantum error correction", max_results=5, sort_by="submittedDate")`
- `search_papers("cs.AI", search_field="category", max_results=5)`
- `get_paper("1706.03762")` (Attention Is All You Need)
- `extract_paper("1706.03762")`

## Notes

- No keys, no auth. Please respect arXiv's politeness limit (~1 req / 3s); the server throttles itself.
- Full text comes from ar5iv when a rendering exists; very new papers may return abstract-only.
- This project is not affiliated with arXiv or Hugging Face. The 16 TB `secemp9/arxiv-complete` HF snapshot is a separate bulk corpus — this server targets quick live lookup instead of bulk download.

## License

MIT
