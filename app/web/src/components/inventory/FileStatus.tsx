/** What the inventory says about how sure it is of one file: its format, and what to check in it. */

import {
  type FileHint,
  HINT_LABELS,
  identificationLabel,
  type InventoryFile,
} from "@data-director/inventory";

/** How the file's format was identified, or that it is in doubt. */
export function FormatStatus({ file }: { file: InventoryFile }) {
  const ids = file.file_pronom_ids ?? [];
  if (file.file_identified_by === "none" || ids.length > 1) {
    return (
      <span className="status status-warn">
        {ids.length > 1 ? `Could be any of ${ids.length} formats` : identificationLabel("none")}
      </span>
    );
  }
  if (file.file_identified_by === "researcher") {
    return <span className="status status-ok">Format chosen by you</span>;
  }
  return <span className="muted">({identificationLabel(file.file_identified_by).toLowerCase()})</span>;
}

/** A badge for each thing to check in the file. */
export function HintBadges({ hints }: { hints: FileHint[] }) {
  return hints.map((hint) => (
    <span key={hint.kind}>
      {" "}
      <span className="status status-warn">{HINT_LABELS[hint.kind]}</span>
    </span>
  ));
}

/** The questions to check in the file, if any. */
export function HintList({ file, hints }: { file: InventoryFile; hints: FileHint[] }) {
  if (hints.length === 0) return null;
  return (
    <ul className="inventory-hints" aria-label={`What to check in ${file.file_path}`}>
      {hints.map((hint) => (
        <li key={hint.kind}>
          {hint.question}
          {hint.related?.length ? <> Same as: {hint.related.join(", ")}.</> : null}
        </li>
      ))}
    </ul>
  );
}
