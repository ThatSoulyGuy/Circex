/**
 * GcnService — the 7 Circex MCP tools.
 *
 * Each method is a thin forwarder: validate input (LeanMCP runs AJV against
 * the @SchemaConstraint-decorated input class before we see the object),
 * then call the Python worker over the persistent TCP socket. The actual
 * extraction / SQLite / FTS5 work happens Python-side; this layer only
 * shapes the MCP protocol surface.
 *
 * Tools are auto-discovered by LeanMCP from this file's exported class.
 */
import "reflect-metadata";
import { Tool } from "@leanmcp/core";

import { callPythonTool, PythonBridgeError } from "../../bridge/python_bridge.js";
import {
  ExtractPropertiesInput,
  ExtractTextInput,
  FetchGcnCircularsInput,
  FindCounterpartsInput,
  GetClassificationInput,
  GetPhotometryInput,
  GetRedshiftInput,
  SearchGcnCircularsInput,
} from "./input_schema.js";

/**
 * Map a Python-side error to an MCP-shaped error response.
 * LeanMCP serializes thrown Error objects into protocol error frames; we
 * preserve the worker's message rather than burying it.
 */
function forward(toolName: string, args: Record<string, unknown>): Promise<unknown> {
  return callPythonTool(toolName, args).catch((err: unknown) => {
    if (err instanceof PythonBridgeError) {
      throw new Error(`[circex/${toolName}] ${err.message}`);
    }
    throw err;
  });
}

export class GcnService {
  @Tool({
    description:
      "Return the full structured CircularExtraction for one circular " +
      "(event, redshift, photometry, classification, provenance, etc.). " +
      "If the circular is not yet in the extraction store, the worker " +
      "extracts on demand using its configured default extractor.",
    inputClass: ExtractPropertiesInput,
  })
  async extract_properties(input: ExtractPropertiesInput): Promise<unknown> {
    return forward("extract_properties", { circular_id: input.circular_id });
  }

  @Tool({
    description:
      "Extract structured properties from a raw circular body, without an " +
      "archive lookup. Use this for live circulars delivered over " +
      "gcn.circulars (Kafka) that are not yet archived. Pass the real " +
      "circular_id when known so re-delivered messages are served from cache " +
      "rather than re-extracted.",
    inputClass: ExtractTextInput,
  })
  async extract_text(input: ExtractTextInput): Promise<unknown> {
    const args: Record<string, unknown> = { body: input.body };
    if (input.circular_id !== undefined) args.circular_id = input.circular_id;
    if (input.subject !== undefined) args.subject = input.subject;
    if (input.event_id !== undefined) args.event_id = input.event_id;
    return forward("extract_text", args);
  }

  @Tool({
    description:
      "Get the best-known Redshift record for an event, or null if none " +
      "is recorded. Searches across all extracted circulars about the event.",
    inputClass: GetRedshiftInput,
  })
  async get_redshift(input: GetRedshiftInput): Promise<unknown> {
    return forward("get_redshift", { event: input.event });
  }

  @Tool({
    description:
      "Return all PhotometryExt rows recorded for an event across all " +
      "extracted circulars. Multi-epoch tables produce multiple rows.",
    inputClass: GetPhotometryInput,
  })
  async get_photometry(input: GetPhotometryInput): Promise<unknown[]> {
    return (await forward("get_photometry", { event: input.event })) as unknown[];
  }

  @Tool({
    description:
      "Return the canonical time-domain Classification for an event " +
      "(e.g. 'Ia', 'Ic-BL', 'kilonova', 'Tidal Disruption Event'), or null.",
    inputClass: GetClassificationInput,
  })
  async get_classification(input: GetClassificationInput): Promise<unknown> {
    return forward("get_classification", { event: input.event });
  }

  @Tool({
    description:
      "Find optical counterpart claims for a gravitational-wave or " +
      "neutrino trigger ID. Returns FollowUp records that cross-reference " +
      "the trigger.",
    inputClass: FindCounterpartsInput,
  })
  async find_counterparts(input: FindCounterpartsInput): Promise<unknown[]> {
    return (await forward("find_counterparts", {
      gw_event_id: input.gw_event_id,
    })) as unknown[];
  }

  @Tool({
    description:
      "FTS5 full-text search across circular bodies and subjects. " +
      "Returns search hits ranked by relevance, optionally constrained " +
      "to one event.",
    inputClass: SearchGcnCircularsInput,
  })
  async search_gcn_circulars(input: SearchGcnCircularsInput): Promise<unknown[]> {
    const args: Record<string, unknown> = { query: input.query };
    if (input.event !== undefined) args.event = input.event;
    if (input.limit !== undefined) args.limit = input.limit;
    return (await forward("search_gcn_circulars", args)) as unknown[];
  }

  @Tool({
    description:
      "Fetch raw archive records for a list of circular IDs. Returns the " +
      "original GCN JSON objects (subject, body, eventId, createdOn, " +
      "submitter, bibcode) — useful when a client wants the prose rather " +
      "than the structured extraction.",
    inputClass: FetchGcnCircularsInput,
  })
  async fetch_gcn_circulars(input: FetchGcnCircularsInput): Promise<unknown[]> {
    return (await forward("fetch_gcn_circulars", {
      circular_ids: input.circular_ids,
    })) as unknown[];
  }
}
