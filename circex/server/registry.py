"""Tool registry: decorator-based registration + dispatch.

Tool handlers are sync callables for now (the underlying extractors are sync).
Each handler takes the context dict + arguments dict and returns a JSON-
serializable result.

Importing `circex.server.tools` registers the 7 built-in tools as a side-effect.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Type aliases for handler signatures.
ToolHandler = Callable[["ToolContext", dict[str, Any]], Any]


class ToolContext:
    """Shared state passed to every tool. Constructed once by the worker."""

    def __init__(
        self,
        store: Any,  # circex.server.store.ExtractionStore
        default_extractor: Any | None = None,  # Extractor protocol
        db_path: str | None = None,
    ) -> None:
        self.store = store
        self.default_extractor = default_extractor
        self.db_path = db_path


TOOLS: dict[str, ToolHandler] = {}


def tool(name: str) -> Callable[[ToolHandler], ToolHandler]:
    """Register a tool by name."""

    def decorator(handler: ToolHandler) -> ToolHandler:
        if name in TOOLS:
            raise ValueError(f"tool {name!r} already registered")
        TOOLS[name] = handler
        return handler

    return decorator


def dispatch(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> Any:
    """Look up and invoke a registered tool. Raises KeyError if unknown."""
    handler = TOOLS.get(name)
    if handler is None:
        raise KeyError(f"unknown tool: {name!r}")
    return handler(ctx, arguments)
