/** One value, written for reading: rounded numbers, Yes or No, option names without underscores. */

import type { Shape } from "../../../run/schema";

export function Scalar({ value, shape }: { value: unknown; shape: Shape }) {
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
