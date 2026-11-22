/**
 * The facts one person kept from their public ORCID record in a project (docs/specs/projects.md,
 * invariant 27): what agents in the project are given, in ORCID's words, and when it was read.
 */

import { formatDateTime } from "../../format";
import { RECORD_ITEMS, RECORD_SECTIONS, type ResearcherRecord } from "../../project/researcher";
import { ITEM_LABELS, SECTION_LABELS, itemsOf, sectionText } from "./researcherFacts";

export function KeptFacts({ record }: { record: ResearcherRecord }) {
  const sections = RECORD_SECTIONS.filter((s) => sectionText(record, s) !== "");
  return (
    <>
      <dl className="researcher-facts">
        {sections.map((section) => (
          <div key={section}>
            <dt>{SECTION_LABELS[section]}</dt>
            <dd>{sectionText(record, section)}</dd>
          </div>
        ))}
        {RECORD_ITEMS.map((section) => {
          const items = itemsOf(record, section);
          if (items.length === 0) return null;
          return (
            <div key={section}>
              <dt>{ITEM_LABELS[section]}</dt>
              <dd>
                <ul className="plain-list">
                  {items.map(([code, text]) => (
                    <li key={code}>{text}</li>
                  ))}
                </ul>
              </dd>
            </div>
          );
        })}
      </dl>
      <p className="hint">
        Read from ORCID on{" "}
        <time dateTime={record.record_retrieved_at}>{formatDateTime(record.record_retrieved_at)}</time>.
      </p>
    </>
  );
}
