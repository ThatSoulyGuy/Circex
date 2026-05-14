"""JSON line protocol for the Circex worker.

Request:  {"tool": "<name>", "arguments": {...}, "id": "<opaque>"}
Response: {"ok": true,  "result": <json>,  "id": "<echoed>"}
       or {"ok": false, "error":  "<msg>", "id": "<echoed>"}

Each message is a single JSON object on its own line, terminated by \\n.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REQUEST_VERSION = "1.0"


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    arguments: dict[str, Any]
    id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ToolRequest:
        if "tool" not in payload:
            raise ValueError("missing 'tool' field")
        args = payload.get("arguments") or {}
        if not isinstance(args, dict):
            raise ValueError("'arguments' must be an object")
        return cls(tool=str(payload["tool"]), arguments=args, id=payload.get("id"))


@dataclass(frozen=True)
class ToolResponse:
    ok: bool
    result: Any = None
    error: str | None = None
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            out["result"] = self.result
        else:
            out["error"] = self.error
        if self.id is not None:
            out["id"] = self.id
        return out
