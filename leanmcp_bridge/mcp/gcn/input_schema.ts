/**
 * Input dataclasses for the 7 Circex MCP tools.
 *
 * The shapes mirror `circex/server/tools.py` exactly. LeanMCP turns each
 * decorated class into a JSON Schema and an AJV validator at startup; the
 * already-validated argument object is then passed to the service method,
 * which forwards it to the long-lived Python worker over TCP.
 */
import "reflect-metadata";
import { Optional, SchemaConstraint } from "@leanmcp/core";

export class ExtractPropertiesInput {
  @SchemaConstraint({
    description: "Integer GCN circular ID, e.g. 21509.",
    minimum: 1,
  })
  circular_id!: number;
}

export class GetRedshiftInput {
  @SchemaConstraint({
    description:
      "Event identifier (e.g. 'GRB 230307A', 'AT2017gfo', 'GW170817'). " +
      "Matched against extracted `event.event_name` in the store.",
    minLength: 1,
  })
  event!: string;
}

export class GetPhotometryInput {
  @SchemaConstraint({
    description: "Event identifier (see GetRedshiftInput.event).",
    minLength: 1,
  })
  event!: string;
}

export class GetClassificationInput {
  @SchemaConstraint({
    description: "Event identifier (see GetRedshiftInput.event).",
    minLength: 1,
  })
  event!: string;
}

export class FindCounterpartsInput {
  @SchemaConstraint({
    description:
      "Gravitational-wave or neutrino trigger ID, e.g. 'GW170817' or 'IC230925A'. " +
      "Returns optical FollowUp records that reference this trigger.",
    minLength: 1,
  })
  gw_event_id!: string;
}

export class SearchGcnCircularsInput {
  @SchemaConstraint({
    description: "FTS5 query string against the circulars body + subject index.",
    minLength: 1,
  })
  query!: string;

  @Optional()
  @SchemaConstraint({
    description:
      "Optional event ID to constrain the search to circulars about one event.",
    minLength: 1,
  })
  event?: string;

  @Optional()
  @SchemaConstraint({
    description: "Max rows to return.",
    minimum: 1,
    maximum: 100,
    default: 10,
  })
  limit?: number;
}

export class FetchGcnCircularsInput {
  @SchemaConstraint({
    description:
      "List of integer circular IDs to fetch raw archive records for. " +
      "Returns the original JSON objects (subject, body, eventId, ...). " +
      "Recommended cap is ~100 IDs per call.",
    type: "array",
  })
  circular_ids!: number[];
}
