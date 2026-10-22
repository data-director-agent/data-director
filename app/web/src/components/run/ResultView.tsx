/**
 * A result, laid out from its class's JSON Schema and the manifest's derivations: a simplified
 * port of the workbench viewer's `payloadUi` (workbench/viewer/js/payload.js).
 *
 * A list of records is a table with one column per field. A field the manifest says is produced
 * by a template, a model, keyword rules or a registry carries a badge saying so, read from the
 * record's own `recorded_in` field when there is one; that field is not shown as a column. Each
 * record's `grounded_on` becomes numbered links to the evidence it rests on, named from the
 * evidence; a citation with no matching evidence item is flagged. The top-level `grounded_on`
 * is the evidence list itself, so it is not repeated.
 *
 * TODO: the full renderer, with per-class renderers in a registry, is #70.
 */

import "./ResultView.css";

import type { Derivation } from "../../manifest/normalise";
import type { DerivationHow } from "../../manifest/types";
import { DERIVATION, DERIVATION_SHORT, fieldName } from "../../manifest/wording";
import { type JsonSchema, type Shape, properties, shapeOf } from "../../run/schema";
import type { EvidenceItem, GroundingRef } from "../../run/types";
import { evidenceAnchor, evidenceKey } from "./EvidencePanel";

/** Characters past which a text value is prose rather than a label. */
const LONG = 80;

interface Context {
  root: JsonSchema;
  derivations: Map<string, Derivation>;
  evidence: Map<string, { index: number; name: string }>;
  idPrefix: string;
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || (Array.isArray(value) && value.length === 0);
}

/** The fields at `prefix` that only record how a sibling was derived. */
function recorders(ctx: Context, prefix: string): Set<string> {
  const names = new Set<string>();
  for (const d of ctx.derivations.values()) {
    if (d.recordedIn && d.path.startsWith(prefix) && !d.path.slice(prefix.length).includes(".")) {
      names.add(d.recordedIn);
    }
  }
  return names;
}

function Scalar({ value, shape }: { value: unknown; shape: Shape }) {
  if (typeof value === "number") {
    return <>{Number.isInteger(value) ? value : value.toFixed(2)}</>;
  }
  if (typeof value === "boolean") return <>{value ? "Yes" : "No"}</>;
  if (shape.kind === "scalar" && shape.options && typeof value === "string") {
    return <>{value.replace(/_/g, " ")}</>;
  }
  if (Array.isArray(value)) return <>{value.map(String).join(", ")}</>;
  if (typeof value === "object" && value !== null) return <code>{JSON.stringify(value)}</code>;
  return <>{String(value)}</>;
}

function Badge({ derivation, record }: { derivation: Derivation; record: Record<string, unknown> }) {
  const recorded = derivation.recordedIn ? record[derivation.recordedIn] : undefined;
  const how = (typeof recorded === "string" ? recorded : derivation.how) as DerivationHow;
  return (
    <span className="derivation" title={DERIVATION[how] ?? how}>
      {DERIVATION_SHORT[how] ?? how}
    </span>
  );
}

function RestsOn({ refs, ctx }: { refs: GroundingRef[]; ctx: Context }) {
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

function RecordsTable({
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

function Facts({
  schema,
  value,
  path,
  ctx,
}: {
  schema: JsonSchema;
  value: Record<string, unknown>;
  path: string;
  ctx: Context;
}) {
  const hidden = recorders(ctx, path ? `${path}.` : "");
  const entries = properties(schema).filter(
    ([name]) => name !== "grounded_on" && !hidden.has(name) && !isEmpty(value[name]),
  );
  return (
    <dl className="facts">
      {entries.map(([name, s]) => {
        const shape = shapeOf(ctx.root, s);
        const v = value[name];
        return (
          <div key={name} className="facts-row">
            <dt>{s.title ?? fieldName(name)}</dt>
            <dd>
              {shape.kind === "list" && Array.isArray(v) ? (
                <ul className="plain-list">
                  {v.map((item, i) => (
                    <li key={i}>{String(item)}</li>
                  ))}
                </ul>
              ) : (
                <Scalar value={v} shape={shape} />
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export function ResultView({
  payload,
  schema,
  derivations,
  evidence,
  idPrefix,
}: {
  payload: Record<string, unknown>;
  schema: JsonSchema | undefined;
  derivations: Derivation[];
  evidence: EvidenceItem[];
  idPrefix: string;
}) {
  if (!schema) {
    return (
      <>
        <p>This deployment has no schema for this result, so it is shown as it arrived.</p>
        <pre className="json-view">{JSON.stringify(payload, null, 2)}</pre>
      </>
    );
  }
  const ctx: Context = {
    root: schema,
    derivations: new Map(derivations.map((d) => [d.path, d])),
    evidence: new Map(
      evidence.map((item, index) => [
        evidenceKey(item),
        { index, name: typeof item.content?.name === "string" ? item.content.name : item.source_id },
      ]),
    ),
    idPrefix,
  };
  const hidden = recorders(ctx, "");
  const sections = properties(schema).filter(
    ([name]) => name !== "grounded_on" && !hidden.has(name) && !isEmpty(payload[name]),
  );
  const scalars = sections.filter(([, s]) => {
    const kind = shapeOf(schema, s).kind;
    return kind === "scalar" || kind === "list";
  });
  return (
    <div className="result">
      {scalars.length > 0 && (
        <Facts
          schema={{ properties: Object.fromEntries(scalars) }}
          value={payload}
          path=""
          ctx={ctx}
        />
      )}
      {sections.map(([name, s]) => {
        const shape = shapeOf(schema, s);
        const label = s.title ?? fieldName(name);
        if (shape.kind === "records") {
          return (
            <RecordsTable
              key={name}
              label={label}
              path={name}
              schema={shape.schema}
              rows={payload[name] as Record<string, unknown>[]}
              ctx={ctx}
            />
          );
        }
        if (shape.kind === "object") {
          const headingId = `${idPrefix}-${name}-heading`;
          return (
            <section key={name} aria-labelledby={headingId}>
              <h4 id={headingId}>{label}</h4>
              <Facts
                schema={shape.schema}
                value={payload[name] as Record<string, unknown>}
                path={name}
                ctx={ctx}
              />
            </section>
          );
        }
        if (shape.kind === "other") {
          return (
            <section key={name} aria-label={label}>
              <h4>{label}</h4>
              <pre className="json-view">{JSON.stringify(payload[name], null, 2)}</pre>
            </section>
          );
        }
        return null;
      })}
    </div>
  );
}
