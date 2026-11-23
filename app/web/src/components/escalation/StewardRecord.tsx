/**
 * What data stewards did in the researcher's project, for the researcher (docs/specs/stewardship.md,
 * invariant 10): who opened it and when, at most once a day each, and each steward's decision on
 * a step referred to them, with its reason. A steward's messages are shown in the conversation,
 * and their proposed versions in the document's history, each with the steward's name. Nothing
 * renders until a steward has done anything.
 */

import type { ProjectStewarding } from "../../project/escalations";
import { formatDateTime } from "../../format";

const WHEN = { dateStyle: "medium", timeStyle: "short" } as const;

type Entry = { key: string; at: string; said: string };

function entries(stewarding: ProjectStewarding): Entry[] {
  const found: Entry[] = [
    ...stewarding.views.map((v, index) => ({
      key: `view-${String(index)}`,
      at: v.at,
      said: `${v.by.name} opened this project as a data steward`,
    })),
    ...stewarding.gate_decisions.map((d) => ({
      key: `gate-${d.invocation_id}`,
      at: d.at,
      said: `${d.by.name} ${d.verdict === "cleared" ? "cleared" : "refused"} a step referred to a data steward: ${d.reason}`,
    })),
  ];
  return found.sort((a, b) => b.at.localeCompare(a.at));
}

export function StewardRecord({ stewarding }: { stewarding: ProjectStewarding | undefined }) {
  const shown = stewarding ? entries(stewarding) : [];
  if (shown.length === 0) return null;
  return (
    <details className="steward-record">
      <summary>What data stewards did here</summary>
      <ul className="plain-list">
        {shown.map((e) => (
          <li key={e.key}>
            <time dateTime={e.at}>{formatDateTime(e.at, WHEN)}</time>: {e.said}
          </li>
        ))}
      </ul>
    </details>
  );
}
