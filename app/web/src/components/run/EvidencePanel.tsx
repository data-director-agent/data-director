/**
 * The evidence a run rests on, and what the harness's checks said about it (checklist item 4).
 *
 * A failed check is shown with a word and a mark, never colour alone, and its summary is shown
 * as the harness wrote it. The grounding check is a consistency check, not proof of retrieval
 * (ADR-0016). Each item has an anchor the result's "rests on" links point to.
 */

import "./EvidencePanel.css";

import { fieldName } from "../../manifest/wording";
import type { CheckReport, Checks, EvidenceItem } from "../../run/types";

export function evidenceKey(item: { source_id: string; content_hash?: string | null }): string {
  return `${item.source_id}|${item.content_hash ?? ""}`;
}

export function evidenceAnchor(idPrefix: string, index: number): string {
  return `${idPrefix}-evidence-${index + 1}`;
}

/** Shown in a record's own line, so not repeated among its other facts. */
const SHOWN = new Set(["name", "description", "title"]);

function CheckLine({ name, report }: { name: string; report: CheckReport | null }) {
  if (report === null) {
    return (
      <li>
        <span className="status status-undeclared">No report</span> {name}
      </li>
    );
  }
  return (
    <li>
      <span className={`status status-${report.passed ? "ok" : "danger"}`}>
        <span aria-hidden="true">{report.passed ? "✓ " : "✗ "}</span>
        {report.passed ? "Passed" : "Failed"}
      </span>{" "}
      {name} <span className="check-summary">{report.summary}</span>
    </li>
  );
}

function facts(content: Record<string, unknown>): [string, string][] {
  return Object.entries(content)
    .filter(([key, value]) => !SHOWN.has(key) && value !== null && value !== "")
    .filter(([, value]) => !(Array.isArray(value) && value.length === 0))
    .map(([key, value]) => [
      fieldName(key),
      Array.isArray(value) ? value.join(", ") : typeof value === "object" ? JSON.stringify(value) : String(value),
    ]);
}

export function EvidencePanel({
  evidence,
  checks,
  idPrefix,
}: {
  evidence: EvidenceItem[];
  checks: Checks;
  idPrefix: string;
}) {
  const headingId = `${idPrefix}-evidence-heading`;
  return (
    <section className="evidence" aria-labelledby={headingId}>
      <h4 id={headingId}>Evidence ({evidence.length})</h4>
      <ul className="checks">
        <CheckLine name="Grounding check" report={checks.grounding} />
        <CheckLine name="Source check" report={checks.sources} />
      </ul>
      {evidence.length === 0 ? (
        <p className="muted">This run cites no records.</p>
      ) : (
        <ol className="evidence-list">
          {evidence.map((item, i) => {
            const content = item.content ?? {};
            const name = typeof content.name === "string" ? content.name : item.source_id;
            const description =
              typeof content.description === "string" ? content.description : null;
            return (
              <li key={evidenceKey(item)} id={evidenceAnchor(idPrefix, i)} tabIndex={-1}>
                <p className="evidence-name">
                  <span className="evidence-number">[{i + 1}]</span>{" "}
                  {item.source_uri ? <a href={item.source_uri}>{name}</a> : name}
                </p>
                <p className="evidence-meta">
                  <code>{item.source_id}</code>
                  {item.snapshot_ref && <> · from {item.snapshot_ref}</>}
                  {item.retrieved_at && <> · retrieved {item.retrieved_at}</>}
                </p>
                <dl className="evidence-facts">
                  {facts(content).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
                {description && (
                  <details>
                    <summary>Record description</summary>
                    <p>{description}</p>
                  </details>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
