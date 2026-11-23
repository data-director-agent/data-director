/**
 * Whom a move passes an escalation to: a colleague in the team for `reassign`, another team for
 * `transfer`, chosen from the targets the harness lists (`permitted_moves[].targets`), never typed.
 */

import { useId } from "react";

import type { PermittedMove } from "../../project/steward";

export function TargetField({
  label,
  targets,
  value,
  onChange,
}: {
  label: string;
  targets: NonNullable<PermittedMove["targets"]>;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} required value={value} onChange={(event) => onChange(event.target.value)}>
        {targets.map((target) => (
          <option key={target.id} value={target.id}>
            {target.name}
          </option>
        ))}
      </select>
    </div>
  );
}
