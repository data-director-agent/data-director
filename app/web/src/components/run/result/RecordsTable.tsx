/** A list of records as a table, one column per field, with what each record rests on. */

import { fieldName } from "../../../manifest/wording";
import { type JsonSchema, properties, shapeOf } from "../../../run/schema";
import type { GroundingRef } from "../../../run/types";
import { Badge } from "./Badge";
import { type Context, isEmpty, recorders } from "./context";
import { RestsOn } from "./RestsOn";
import { Scalar } from "./Scalar";

/** Characters past which a text value is prose rather than a label. */
const LONG = 80;

export function RecordsTable({
  label,
  path,
  schema,
  rows,
  ctx,
}: {
  label: string;
  path: string;
  schema: JsonSchema;
  rows: Record<string, unknown>[];
  ctx: Context;
}) {
  const hidden = recorders(ctx, `${path}.`);
  const columns = properties(schema).filter(
    ([name]) => name !== "grounded_on" && !hidden.has(name),
  );
  const cites = "grounded_on" in (schema.properties ?? {});
  // A column of prose gets room to wrap; the rest stay as narrow as their values.
  const long = new Set(
    columns
      .map(([name]) => name)
      .filter((name) => rows.some((r) => typeof r[name] === "string" && r[name].length > LONG)),
  );
  const headingId = `${ctx.idPrefix}-${path}-heading`;
  return (
    <div className="records-result">
      <h4 id={headingId}>
        {label} ({rows.length})
      </h4>
      {/* A wide table scrolls within its own region rather than the page (WCAG 1.4.10 exempts
          data tables); the region takes focus so it can be scrolled from the keyboard. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="table-scroll" role="region" aria-labelledby={headingId} tabIndex={0}>
        <table className="data-table result-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              {columns.map(([name, s]) => (
                <th key={name} scope="col">
                  {s.title ?? fieldName(name)}
                </th>
              ))}
              {cites && <th scope="col">Rests on</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                {columns.map(([name, s]) => {
                  const derivation = ctx.derivations.get(`${path}.${name}`);
                  return (
                    <td key={name} className={long.has(name) ? "long" : undefined}>
                      {isEmpty(row[name]) ? (
                        <span className="muted">Not given</span>
                      ) : (
                        <Scalar value={row[name]} shape={shapeOf(ctx.root, s)} />
                      )}
                      {derivation && (
                        <>
                          {" "}
                          <Badge derivation={derivation} record={row} />
                        </>
                      )}
                    </td>
                  );
                })}
                {cites && (
                  <td>
                    <RestsOn refs={(row.grounded_on as GroundingRef[] | undefined) ?? []} ctx={ctx} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
