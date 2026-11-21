/**
 * A project's members (docs/specs/projects.md, Roles; #391): who works on it, by ORCID iD, their
 * roles, and since when. A member is headed by the name they kept from their own ORCID record in
 * the project, where they kept one; the project keeps no other name for them.
 *
 * What the page offers is what the server says the person may do, and nothing else: an owner adds
 * members, changes roles and removes them; any member may leave, except the last owner. The server
 * checks every change again (docs/specs/app.md).
 */

import { ExternalLink, LogOut, UserMinus } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime } from "../../format";
import { useActiveProject } from "../../project/active";
import {
  type MemberRole,
  type ProjectMember,
  type ProjectMembers,
  useMembersApi,
} from "../../project/members";
import { navigate } from "../../route";
import { OrcidIcon } from "../ui/BrandIcon";
import { loadInto, message, type PanelLoad } from "./panelLoad";
import { Button } from "../ui/Button";
import { AddMember } from "./AddMember";
import { ConfirmMemberChange } from "./ConfirmMemberChange";

const HEADING_ID = "members-heading";
const ROLE_NAMES: Record<MemberRole, string> = { owner: "Owner", member: "Member" };

type Load = PanelLoad<ProjectMembers>;

/** A member's iD as people write it: an ORCID iD without its `https://orcid.org/`. */
function shortId(memberId: string): string {
  return memberId.replace(/^https:\/\/orcid\.org\//, "");
}

/** What a member is called on the page: the name they kept from ORCID, or their iD. */
function calledBy(member: ProjectMember): string {
  return member.researcher_name ?? shortId(member.member_id);
}

function IdLink({ memberId }: { memberId: string }) {
  return (
    <a href={memberId} target="_blank" rel="noreferrer">
      <OrcidIcon className="brand-icon" /> {shortId(memberId)}
      <ExternalLink size="0.875em" aria-hidden="true" />
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

function MemberEntry({
  member,
  busy,
  onRole,
  onRemove,
}: {
  member: ProjectMember;
  busy: boolean;
  onRole: (role: MemberRole) => void;
  onRemove: () => void;
}) {
  const other: MemberRole = member.role === "owner" ? "member" : "owner";
  return (
    <li className="member">
      <h3>
        {member.researcher_name ?? <IdLink memberId={member.member_id} />}{" "}
        {member.is_you && <span className="muted">(you)</span>}
      </h3>
      {member.researcher_name && (
        <p>
          <IdLink memberId={member.member_id} />
        </p>
      )}
      <p>
        {ROLE_NAMES[member.role]}, since{" "}
        <time dateTime={member.member_since}>{formatDateTime(member.member_since)}</time>
      </p>
      {(member.role_changeable || (member.removable && !member.is_you)) && (
        <p className="member-actions">
          {member.role_changeable && (
            <Button variant="quiet" size="small" isPending={busy} onPress={() => onRole(other)}>
              {other === "owner" ? "Make owner" : "Make member"}
              <span className="visually-hidden"> ({calledBy(member)})</span>
            </Button>
          )}
          {member.removable && !member.is_you && (
            <ConfirmMemberChange
              label={
                <>
                  Remove<span className="visually-hidden"> {calledBy(member)}</span>
                </>
              }
              icon={UserMinus}
              title="Remove a member"
              confirm="Remove"
              busy={busy}
              onConfirm={onRemove}
            >
              <p>
                <strong>{calledBy(member)}</strong> will no longer see this project or work on
                it. What they did in it keeps their name. You can add them again later.
              </p>
            </ConfirmMemberChange>
          )}
        </p>
      )}
    </li>
  );
}

export function MembersPanel({ projectId }: { projectId: string }) {
  const api = useMembersApi();
  const { projectId: activeId, setProjectId, reloadProjects } = useActiveProject();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => loadInto((signal) => api.members(projectId, signal), setLoad), [api, projectId]);

  /** Make a change; resolves true once the server has made it. */
  const change = (action: () => Promise<ProjectMembers | null>, done: string) => {
    setBusy(true);
    setSaid(null);
    return action().then(
      (value) => {
        setBusy(false);
        if (value === null) {
          // The person left: the project is no longer theirs to read.
          if (activeId === projectId) setProjectId(null);
          reloadProjects();
          navigate("/projects");
          return true;
        }
        setLoad({ state: "loaded", value });
        setSaid({ text: done, ok: true });
        return true;
      },
      (error: unknown) => {
        setBusy(false);
        setSaid({ text: `Data Director could not do that: ${message(error)}`, ok: false });
        return false;
      },
    );
  };

  const body = () => {
    if (load.state === "loading") return <p>Reading who works on this project…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the project&apos;s members: {load.message}</p>
        </div>
      );
    }
    const { members, may_manage: mayManage, may_leave: mayLeave } = load.value;
    const you = members.find((m) => m.is_you);
    return (
      <>
        <ul className="plain-list members">
          {members.map((member) => (
            <MemberEntry
              key={member.member_id}
              member={member}
              busy={busy}
              onRole={(role) =>
                void change(
                  () => api.changeRole(projectId, member.member_id, role),
                  `${calledBy(member)} is now ${role === "owner" ? "an owner" : "a member"}.`,
                )
              }
              onRemove={() =>
                void change(
                  () => api.removeMember(projectId, member.member_id),
                  `${calledBy(member)} is no longer a member of this project.`,
                )
              }
            />
          ))}
        </ul>
        {mayManage && (
          <AddMember
            busy={busy}
            onAdd={(member, role) =>
              change(
                () => api.addMember(projectId, member, role),
                `Added ${member} as ${role === "owner" ? "an owner" : "a member"}.`,
              )
            }
          />
        )}
        {mayLeave && you && (
          <p>
            <ConfirmMemberChange
              label="Leave this project"
              icon={LogOut}
              title="Leave this project"
              confirm="Leave"
              busy={busy}
              onConfirm={() => void change(() => api.removeMember(projectId, you.member_id), "")}
            >
              <p>
                You will no longer see this project or work on it. What you did in it keeps your
                name. An owner can add you again.
              </p>
            </ConfirmMemberChange>
          </p>
        )}
      </>
    );
  };

  return (
    <section className="members-panel" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Members</h2>
      <p className="hint">
        Everyone listed here sees all of this project: its inventory, documents, decisions and
        facts, and every conversation in it, including one another&apos;s messages, each with the
        sender&apos;s name. Members work on the project; owners also approve or reject documents
        and manage who is a member.
      </p>
      <div role="status" className={said ? `callout ${said.ok ? "status-ok" : "status-danger"}` : undefined}>
        {said && <p>{said.text}</p>}
      </div>
      {body()}
    </section>
  );
}
