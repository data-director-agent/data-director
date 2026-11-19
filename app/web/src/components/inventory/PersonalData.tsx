/**
 * Where the inventory command found possible personal data, as the researcher sees it before the
 * inventory is added and after (docs/specs/personal-data.md, #471). A finding says where, never
 * what: no value is in the inventory, so none is shown. A clean result is never shown as safe.
 *
 * Also the note that opens an inventory's view, which says what the inventory holds and what no
 * agent can see.
 */

import {
  confidenceLabel,
  findingLabel,
  findingsByPlace,
  PERSONAL_DATA_TEXT,
  personalDataState,
  type FileInventory,
  type PersonalDataFinding,
} from "@data-director/inventory";
import { createContext, useContext } from "react";

/** The findings of the inventory shown, by the file or folder they concern. */
export const FindingsContext = createContext<ReadonlyMap<string, PersonalDataFinding[]>>(new Map());

export { findingsByPlace };

/** What the inventory holds, and so what Data Director keeps and agents are shown. */
export function InventoryCallout({ editing }: { editing: boolean }) {
  return (
    <p className="callout">
      This is everything the inventory holds, and so everything Data Director keeps and agents are
      shown: file names and folders, sizes, digests, formats, the column headings of tables
      {editing ? ", anything you describe here" : ""} and where the inventory command found possible
      personal data. It holds nothing else from inside the files, so no agent can see what they say:
      whether locations are sensitive, licence terms written in a file, or names and access codes in
      files the command did not check. Files whose names suggest something to check are marked; that
      is a prompt for you, not a decision, and a file not marked may still need checking.
    </p>
  );
}

/** The section listing the findings by place, or saying that none were found or none looked for. */
export function PersonalData({ inventory }: { inventory: FileInventory }) {
  const state = personalDataState(inventory);
  const byPlace = useContext(FindingsContext);
  return (
    <section aria-labelledby="inventory-personal-data">
      <h3 id="inventory-personal-data">Possible personal data</h3>
      <p>{PERSONAL_DATA_TEXT[state]}</p>
      {byPlace.size > 0 && (
        <ul className="inventory-findings">
          {[...byPlace].map(([place, findings]) => (
            <li key={place}>
              <span className="inventory-file-name">{place}</span>
              <ul aria-label={`Possible personal data in ${place}`}>
                {findings.map((f) => (
                  <li key={`${f.finding_target}:${f.finding_column ?? ""}:${f.finding_kind}`}>
                    {findingLabel(f)} <span className="muted">({confidenceLabel(f)})</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** A badge on a file in which possible personal data was found. */
export function FindingBadge({ path }: { path: string }) {
  if (!useContext(FindingsContext).has(path)) return null;
  return (
    <>
      {" "}
      <span className="status status-warn">Possible personal data</span>
    </>
  );
}
