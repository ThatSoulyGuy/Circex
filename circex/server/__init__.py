"""Long-lived Python worker + MCP tool implementations.

The TS LeanMCP bridge talks to this worker over a TCP socket (cross-platform).
Each tool reads from the ExtractionStore first; cache miss falls back to
on-the-fly extraction with the configured default extractor.
"""

from circex.server.protocol import REQUEST_VERSION, ToolRequest, ToolResponse
from circex.server.registry import TOOLS, ToolHandler, tool
from circex.server.store import ExtractionStore
from circex.server.worker import serve

__all__ = [
    "ExtractionStore",
    "REQUEST_VERSION",
    "TOOLS",
    "ToolHandler",
    "ToolRequest",
    "ToolResponse",
    "serve",
    "tool",
]
