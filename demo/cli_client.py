"""Standalone Circex demo CLI.

Connects to a running Circex worker (`circex serve`) on localhost:8765 and
invokes Circex tools via the JSON-line protocol. Optionally hands the tools to
Claude via the Anthropic SDK so the user can ask natural-language questions
about a circular.

Usage (worker must be running):
    python demo/cli_client.py --question "what's the redshift of GRB 240101A?"

Or interactively:
    python demo/cli_client.py

This deliberately bypasses the TS LeanMCP bridge to keep the demo self-
contained. SkyPortal-style integrations would talk to the TS bridge instead,
which then forwards to this same worker — the worker is the source of truth.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import Any


def call_tool(
    host: str, port: int, tool: str, arguments: dict[str, Any], request_id: str | None = None
) -> Any:
    """One-shot blocking request to the Circex worker. Returns the result or raises."""
    with socket.create_connection((host, port), timeout=10) as sock:
        request = {"tool": tool, "arguments": arguments}
        if request_id:
            request["id"] = request_id
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
    line = b"".join(chunks).split(b"\n", 1)[0].decode("utf-8")
    response = json.loads(line)
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "unknown worker error")
    return response.get("result")


def _ask_claude(question: str, host: str, port: int) -> None:
    """Optional path: let Claude orchestrate the Circex tools to answer a question."""
    try:
        import anthropic
    except ImportError:
        print("anthropic SDK not installed; pip install -e . to get it", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic()
    tool_defs = [
        {
            "name": "get_redshift",
            "description": "Look up the redshift for a named event.",
            "input_schema": {
                "type": "object",
                "properties": {"event": {"type": "string"}},
                "required": ["event"],
            },
        },
        {
            "name": "get_photometry",
            "description": "Return all photometry rows for a named event.",
            "input_schema": {
                "type": "object",
                "properties": {"event": {"type": "string"}},
                "required": ["event"],
            },
        },
        {
            "name": "get_classification",
            "description": "Return the canonical classification for a named event.",
            "input_schema": {
                "type": "object",
                "properties": {"event": {"type": "string"}},
                "required": ["event"],
            },
        },
    ]

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    for _step in range(5):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=tool_defs,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results: list[dict[str, Any]] = []
            assistant_content = response.content
            for block in assistant_content:
                if getattr(block, "type", None) == "tool_use":
                    result = call_tool(host, port, block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})
            continue

        text_parts = [
            getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
        ]
        print("\n".join(p for p in text_parts if p))
        return

    print("(reached max tool-call steps; giving up)", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Circex demo CLI client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--tool", help="One-shot tool call (e.g., 'get_redshift'). Bypasses Claude."
    )
    parser.add_argument(
        "--args", help="JSON arguments for --tool (e.g., '{\"event\":\"GRB X\"}')."
    )
    parser.add_argument(
        "--question",
        help="Natural-language question for Claude to answer using Circex tools.",
    )
    parsed = parser.parse_args(argv)

    if parsed.tool:
        arguments = json.loads(parsed.args) if parsed.args else {}
        result = call_tool(parsed.host, parsed.port, parsed.tool, arguments)
        print(json.dumps(result, indent=2))
        return 0

    if parsed.question:
        _ask_claude(parsed.question, parsed.host, parsed.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
