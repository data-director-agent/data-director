/**
 * An owner adding a person to a project by their ORCID iD (docs/specs/projects.md, Roles): the iD,
 * the role, and Add. No email address is asked for or kept. What was typed stays in the field
 * until the server accepts it, so a refusal (someone already a member, an iD that is not one)
 * loses nothing.
 */

import { UserPlus } from "lucide-react";
import { type FormEvent, useState } from "react";

import type { MemberRole } from "../../project/members";
import { Button } from "../ui/Button";

const ROLES: [MemberRole, string][] = [
  ["member", "Member: works on the project"],
  ["owner", "Owner: also approves documents and manages members"],
];

export function AddMember({
  busy,
  onAdd,
}: {
  busy: boolean;
  /** Add the person; resolves true once the server has added them. */
  onAdd: (member: string, role: MemberRole) => Promise<boolean>;
}) {
  const [member, setMember] = useState("");
  const [role, setRole] = useState<MemberRole>("member");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!member.trim()) return;
    void onAdd(member.trim(), role).then((added) => {
      if (added) {
        setMember("");
        setRole("member");
      }
    });
  };

  return (
    <form className="member-add" onSubmit={submit} aria-labelledby="member-add-heading">
      <h3 id="member-add-heading">Add a member</h3>
      <div className="field">
        <label htmlFor="member-add-id">Their ORCID iD</label>
        <p className="hint" id="member-add-hint">
          Such as <code>0000-0002-1825-0097</code>. They need not have signed in to Data Director
          yet.
        </p>
        <input
          type="text"
          id="member-add-id"
          aria-describedby="member-add-hint"
          autoComplete="off"
          spellCheck={false}
          value={member}
          onChange={(e) => setMember(e.target.value)}
        />
      </div>
      <fieldset className="field">
        <legend>Role</legend>
        {ROLES.map(([value, label]) => (
          <div className="field-check" key={value}>
            <input
              type="radio"
              id={`member-add-role-${value}`}
              name="member-add-role"
              value={value}
              checked={role === value}
              onChange={() => setRole(value)}
            />
            <label htmlFor={`member-add-role-${value}`}>{label}</label>
          </div>
        ))}
      </fieldset>
      <p>
        <Button type="submit" icon={UserPlus} isPending={busy} isDisabled={!member.trim()}>
          Add to the project
        </Button>
      </p>
    </form>
  );
}
