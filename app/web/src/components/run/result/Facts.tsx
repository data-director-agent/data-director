/** An object's fields as a description list, leaving out empty ones and derivation recorders. */

import { fieldName } from "../../../manifest/wording";
import { type JsonSchema, properties, shapeOf } from "../../../run/schema";
import { type Context, isEmpty, recorders } from "./context";
import { Scalar } from "./Scalar";

export function Facts({
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
