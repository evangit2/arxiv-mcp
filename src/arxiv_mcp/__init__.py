"""arxiv-mcp: fast no-key arXiv search + extraction over the public export.arxiv.org API."""
from .server import main, mcp

__all__ = ["main", "mcp"]
__version__ = "0.1.0"
