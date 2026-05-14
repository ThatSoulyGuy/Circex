/**
 * TCP-socket client to the long-lived Circex Python worker.
 *
 * Replaces the predecessor's per-call subprocess model. The worker is started
 * separately with `circex serve --worker` and listens on a configurable
 * localhost port (default 8765).
 *
 * Set CIRCEX_LEGACY_PY_BRIDGE=1 to fall back to the predecessor's subprocess
 * behavior (one `python py_bridge.py` spawn per call) for debugging.
 */

import { connect, type Socket } from 'node:net';

const DEFAULT_HOST = process.env.CIRCEX_WORKER_HOST ?? '127.0.0.1';
const DEFAULT_PORT = Number(process.env.CIRCEX_WORKER_PORT ?? 8765);
const REQUEST_TIMEOUT_MS = Number(process.env.CIRCEX_WORKER_TIMEOUT_MS ?? 30000);

export class PythonBridgeError extends Error {}
export class PythonBridgeLaunchError extends PythonBridgeError {}
export class PythonBridgeParseError extends PythonBridgeError {}

interface ToolRequest {
  tool: string;
  arguments: Record<string, unknown>;
  id?: string;
}

interface ToolResponseOk {
  ok: true;
  result: unknown;
  id?: string;
}

interface ToolResponseErr {
  ok: false;
  error: string;
  id?: string;
}

type ToolResponse = ToolResponseOk | ToolResponseErr;

let _requestCounter = 0;

function _nextRequestId(): string {
  _requestCounter += 1;
  return `req-${Date.now()}-${_requestCounter}`;
}

/**
 * Send one JSON-line request and read the next JSON-line response.
 * Opens a fresh connection per call for simplicity; if call rate matters,
 * replace with a pool.
 */
export async function callPythonTool(
  tool: string,
  args: Record<string, unknown>,
  opts: { host?: string; port?: number } = {},
): Promise<unknown> {
  if (process.env.CIRCEX_LEGACY_PY_BRIDGE === '1') {
    return _callViaSubprocess(tool, args);
  }
  return _callViaSocket(tool, args, {
    host: opts.host ?? DEFAULT_HOST,
    port: opts.port ?? DEFAULT_PORT,
  });
}

function _callViaSocket(
  tool: string,
  args: Record<string, unknown>,
  opts: { host: string; port: number },
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let socket: Socket | undefined;
    const buffer: Buffer[] = [];
    const timer = setTimeout(() => {
      socket?.destroy();
      reject(new PythonBridgeError(`worker timeout after ${REQUEST_TIMEOUT_MS} ms`));
    }, REQUEST_TIMEOUT_MS);

    const onError = (err: Error) => {
      clearTimeout(timer);
      socket?.destroy();
      if ((err as NodeJS.ErrnoException).code === 'ECONNREFUSED') {
        reject(
          new PythonBridgeLaunchError(
            `Cannot reach Circex worker at ${opts.host}:${opts.port}. ` +
              `Did you start it with \`circex serve\`?`,
          ),
        );
        return;
      }
      reject(new PythonBridgeError(err.message));
    };

    socket = connect({ host: opts.host, port: opts.port });
    socket.setEncoding('utf-8');
    socket.on('error', onError);
    socket.on('data', (chunk) => {
      buffer.push(Buffer.from(chunk));
      const combined = Buffer.concat(buffer).toString('utf-8');
      const nlIdx = combined.indexOf('\n');
      if (nlIdx === -1) return;
      const line = combined.slice(0, nlIdx);
      clearTimeout(timer);
      socket?.end();
      let parsed: ToolResponse;
      try {
        parsed = JSON.parse(line) as ToolResponse;
      } catch (err) {
        reject(new PythonBridgeParseError(`bad JSON from worker: ${(err as Error).message}`));
        return;
      }
      if (!parsed.ok) {
        reject(new PythonBridgeError(parsed.error ?? 'worker reported error'));
        return;
      }
      resolve(parsed.result);
    });

    const request: ToolRequest = {
      tool,
      arguments: args,
      id: _nextRequestId(),
    };
    socket.write(`${JSON.stringify(request)}\n`);
  });
}

async function _callViaSubprocess(
  _tool: string,
  _args: Record<string, unknown>,
): Promise<unknown> {
  throw new PythonBridgeLaunchError(
    'CIRCEX_LEGACY_PY_BRIDGE=1 is set but subprocess fallback not yet ported. ' +
      'Copy py_bridge.py from references/GCNMCP/leanmcp_bridge/ if you need it.',
  );
}
