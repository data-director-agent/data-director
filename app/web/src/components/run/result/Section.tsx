/** One top-level field of a result that is more than a value: records, an object or raw JSON. */

import { fieldName } from "../../../manifest/wording";
import { type JsonSchema, shapeOf } from "../../../run/schema";
import type { Context } from "./context";
import { Facts } from "./Facts";
import { RecordsTable } from "./RecordsTable";

export function Section({
  name,
  schema,
  value,
  ctx,
}: {
  name: string;
  schema: JsonSchema;
  value: unknown;
  ctx: Context;
}) {
  const shape = shapeOf(ctx.root, schema);
  const label = schema.title ?? fieldName(name);
  if (shape.kind === "records") {
    return (
      <RecordsTable
        label={label}
        path={name}
        schema={shape.schema}
        rows={value as Record<string, unknown>[]}
        ctx={ctx}
      />
    );
  }
  if (shape.kind === "object") {
    const headingId = `${ctx.idPrefix}-${name}-heading`;
    return (
      <section aria-labelledby={headingId}>
        <h4 id={headingId}>{label}</h4>
        <Facts
          schema={shape.schema}
          value={value as Record<string, unknown>}
          path={name}
          ctx={ctx}
        />
      </section>
    );
  }
  if (shape.kind === "other") {
    return (
      <section aria-label={label}>
        <h4>{label}</h4>
        <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>
      </section>
    );
  }
  return null;
}
