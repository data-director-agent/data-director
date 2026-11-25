/**
 * The approved metadata record converted to another standard
 * (`/api/projects/{id}/conversions`, docs/specs/metadata-standards.md, invariant 9): converting
 * it, the conversions kept, and where each one is downloaded. A conversion is a package derived
 * from the approved record, never a document; the server refuses one that would leave a field
 * the target requires empty, and says what to add.
 */

import type {
  ConversionRefusedProblem,
  ConvertedRecord,
  ConvertedRecords,
  MissingField,
} from "../api/generated/responses";
import { json } from "../http";

export type { ConvertedRecord, MissingField } from "../api/generated/responses";

/** The conversion was refused: the target requires each field in `missing`. */
export class ConversionRefused extends Error {
  readonly missing: MissingField[];

  constructor(problem: ConversionRefusedProblem) {
    super(problem.detail);
    this.name = "ConversionRefused";
    this.missing = problem.missing;
  }
}

function conversionsPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/conversions`;
}

/** Where the converted record with `digest` is downloaded, in its own media type. */
export function conversionUrl(projectId: string, digest: string): string {
  return `${conversionsPath(projectId)}/${encodeURIComponent(digest)}`;
}

/** The project's converted records, newest first. */
export async function conversions(
  projectId: string,
  signal?: AbortSignal,
): Promise<ConvertedRecord[]> {
  const response = await fetch(
    conversionsPath(projectId),
    signal ? { signal } : {},
  );
  return (await json<ConvertedRecords>(response)).conversions;
}

/** Convert the approved record to the standard `conformsTo` names; raises `ConversionRefused`. */
export async function convertRecord(
  projectId: string,
  conformsTo: string,
): Promise<ConvertedRecord> {
  const response = await fetch(conversionsPath(projectId), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ conforms_to: conformsTo }),
  });
  return json<ConvertedRecord>(response, (status, problem) => {
    const refused = problem as ConversionRefusedProblem | null;
    return status === 409 && refused?.missing
      ? new ConversionRefused(refused)
      : null;
  });
}
