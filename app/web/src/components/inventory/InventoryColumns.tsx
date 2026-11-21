/**
 * The columns of an inventory's tables: each column's type and format, the summary values the
 * command wrote after disclosure control (#611), and, while editing, an Include checkbox and a
 * description. Part of `InventoryView`.
 */

import {
  DESCRIPTION_LIMIT,
  fieldValues,
  hasSuppressed,
  isOmitted,
  suppressedText,
  type TableField,
  type TableSummary,
} from "@data-director/inventory";
import { useContext } from "react";
import { TableScroll } from "../ui/TableScroll";
import { EditingContext } from "./InventoryEditing";

export function columns(count: number): string {
  return count === 1 ? "1 column" : `${count} columns`;
}

/** A column's summary values, and a note when some were left out. */
function FieldValues({ field }: { field: TableField }) {
  const values = fieldValues(field);
  const threshold = field.field_disclosure_check?.check_threshold;
  return (
    <>
      {values.join("; ")}
      {hasSuppressed(field) && threshold !== undefined && (
        <span className="muted"> {suppressedText(threshold)}</span>
      )}
    </>
  );
}

/** An Include checkbox for the column `name` of the table at `path`. */
function IncludeColumn({ path, name }: { path: string; name: string }) {
  const editing = useContext(EditingContext);
  if (!editing) return null;
  const { omitted } = editing.edits;
  const tableOmitted = isOmitted(path, omitted.paths);
  const left = tableOmitted || (omitted.columns.get(path)?.has(name) ?? false);
  return (
    <input
      type="checkbox"
      className="inventory-include"
      aria-label={`Include the column ${name} of ${path}`}
      checked={!left}
      disabled={tableOmitted}
      onChange={(e) =>
        editing.dispatch({
          kind: e.currentTarget.checked ? "include-column" : "omit-column",
          path,
          column: name,
        })
      }
    />
  );
}

/** A column's description: a field while editing, its text otherwise. */
function ColumnDescription({ path, field }: { path: string; field: TableField }) {
  const editing = useContext(EditingContext);
  if (!editing) return <>{field.field_description ?? ""}</>;
  const left =
    isOmitted(path, editing.edits.omitted.paths) ||
    (editing.edits.omitted.columns.get(path)?.has(field.name) ?? false);
  if (left) return null;
  return (
    <input
      type="text"
      className="inventory-column-description"
      aria-label={`Describe the column ${field.name} of ${path}`}
      maxLength={DESCRIPTION_LIMIT}
      defaultValue={field.field_description ?? ""}
      onBlur={(e) =>
        editing.dispatch({ kind: "describe-column", path, column: field.name, text: e.currentTarget.value })
      }
    />
  );
}

export function Tables({ tables }: { tables: readonly TableSummary[] }) {
  const editing = useContext(EditingContext) !== null;
  if (tables.length === 0) return null;
  const described = editing || tables.some((t) => t.fields.some((f) => f.field_description));
  const valued = tables.some((t) => t.fields.some((f) => f.field_summary));
  return (
    <section aria-labelledby="inventory-tables">
      <h3 id="inventory-tables">Tables</h3>
      <p>
        The columns of each table, with the type inferred from a sample of its rows and the values
        that passed disclosure control on your computer. Column headings and values are kept and
        shown to agents.
      </p>
      {tables.map((table) => (
        <details key={table.path} className="inventory-table">
          <summary>
            <span className="inventory-file-name">{table.path}</span>{" "}
            <span className="muted">{columns(table.fields.length)}</span>
          </summary>
          <TableScroll label={`Columns of ${table.path}`}>
            <table className="data-table">
              <caption className="visually-hidden">Columns of {table.path}</caption>
              <thead>
                <tr>
                  {editing && <th scope="col">Include</th>}
                  <th scope="col">Column</th>
                  <th scope="col">Type</th>
                  <th scope="col">Format</th>
                  {valued && <th scope="col">Values</th>}
                  {described && <th scope="col">Description</th>}
                </tr>
              </thead>
              <tbody>
                {table.fields.map((field, index) => (
                  <tr key={`${index}-${field.name}`}>
                    {editing && (
                      <td>
                        <IncludeColumn path={table.path} name={field.name} />
                      </td>
                    )}
                    <td>
                      <code>{field.name}</code>
                    </td>
                    <td>{field.field_type ?? <span className="muted">Not known</span>}</td>
                    <td>{field.field_format ?? ""}</td>
                    {valued && (
                      <td>
                        <FieldValues field={field} />
                      </td>
                    )}
                    {described && (
                      <td>
                        <ColumnDescription path={table.path} field={field} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        </details>
      ))}
    </section>
  );
}
