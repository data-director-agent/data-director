/** A record's citations as numbered links to the evidence; one with no matching item is flagged. */

import type { GroundingRef } from "../../../run/types";
import { evidenceAnchor, evidenceKey } from "../EvidencePanel";
import type { Context } from "./context";

export function RestsOn({ refs, ctx }: { refs: GroundingRef[]; ctx: Context }) {
  return (
    <ul className="rests-on">
      {refs.map((ref) => {
        const found = ctx.evidence.get(evidenceKey(ref));
        return (
          <li key={evidenceKey(ref)}>
            {found ? (
              <a href={`#${evidenceAnchor(ctx.idPrefix, found.index)}`}>
                [{found.index + 1}] {found.name}
              </a>
            ) : (
              <>
                <span className="status status-danger">Not in the evidence</span>{" "}
                <code>{ref.source_id}</code>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
