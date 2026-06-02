/**
 * Circex LeanMCP bridge — MCP server fronting the Python worker.
 *
 * Boots a streamable-HTTP MCP server on port 3001 and auto-discovers tools
 * from `./mcp/<service>/index.ts`. Each tool call is forwarded to the
 * long-lived Python worker at $CIRCEX_WORKER_HOST:$CIRCEX_WORKER_PORT
 * (defaults 127.0.0.1:8765) via the JSON-line TCP protocol in
 * `bridge/python_bridge.ts`.
 *
 * Run:
 *   npm run dev
 *
 * Requires the Python worker to be running:
 *   circex serve --host 127.0.0.1 --port 8765 --store data/extractions.sqlite
 *
 * MCP clients (Claude Desktop, MCP Inspector, the Anthropic Computer-Use
 * SDK) connect to `http://localhost:3001/mcp` (or whatever path LeanMCP
 * mounts the MCP transport on — check the boot log).
 */
import "reflect-metadata";
import { createHTTPServer } from "@leanmcp/core";

const PORT = Number(process.env.PORT ?? 3001);

async function main(): Promise<void> {
  const server = await createHTTPServer({
    name: "circex",
    version: "0.1.0",
    port: PORT,
    cors: true,
    logging: true,
  });

  const shutdown = (signal: string) => {
    console.error(`\n[circex-bridge] received ${signal}, shutting down…`);
    // LeanMCP's HTTP server exposes an underlying Node http server; close it.
    const httpServer = (server as { close?: (cb?: () => void) => void }).close;
    if (typeof httpServer === "function") {
      httpServer.call(server, () => process.exit(0));
      setTimeout(() => process.exit(1), 5000).unref();
    } else {
      process.exit(0);
    }
  };
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  console.error(
    `[circex-bridge] MCP server listening on http://localhost:${PORT} ` +
      `(forwarding to Python worker on ${
        process.env.CIRCEX_WORKER_HOST ?? "127.0.0.1"
      }:${process.env.CIRCEX_WORKER_PORT ?? "8765"})`,
  );
}

main().catch((err: unknown) => {
  console.error("[circex-bridge] fatal:", err);
  process.exit(1);
});
