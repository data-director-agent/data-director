/**
 * A project's people (docs/specs/projects.md, Roles and invariant 27; #391): who works on it, their
 * roles and since when, and the facts each kept from their own public ORCID record, which agents in
 * the project are given. A member is headed by the name they kept, else the name on their public
 * ORCID record, which the server reads for the page and does not keep, else their iD. The
 * signed-in person brings in, changes and withdraws their own facts on their own entry
 * (`MyOrcidFacts`). Facts kept by people who are no longer members are still given to agents, so
 * they are listed too.
 *
 * What the page offers is what the server says the person may do, and nothing else: an owner adds
 * members, changes roles and removes them; any member may leave, except the last owner. The server
 * checks every change again (docs/specs/app.md).
 */

import { ExternalLink, LogOut, UserMinus } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { formatDateTime } from "../../format";
import { useActiveProject } from "../../project/active";
import { type MemberRole, type ProjectMember, type ProjectMembers, useMembersApi } from "../../project/members";
import type { ResearcherRecord } from "../../project/researcher";
import { navigate } from "../../route";
import { OrcidIcon } from "../ui/BrandIcon";
import { loadInto, message, type PanelLoad } from "./panelLoad";
import { Button } from "../ui/Button";
import { AddMember } from "./AddMember";
import { ConfirmMemberChange } from "./ConfirmMemberChange";
import { KeptFacts } from "./KeptFacts";
import { MyOrcidFacts } from "./MyOrcidFacts";

const HEADING_ID = "people-heading";
const ROLE_NAMES: Record<MemberRole, string> = {
  owner: "Owner",
  member: "Member",
};

type Load = PanelLoad<ProjectMembers>;

/** A member's iD as people write it: an ORCID iD without its `https://orcid.org/`. */
function shortId(memberId: string): string {
  return memberId.replace(/^https:\/\/orcid\.org\//, "");
}

/** A member's name: the one they kept from ORCID, else the one on their public ORCID record. */
function nameOf(member: ProjectMember): string | undefined {
  return member.researcher_name ?? member.public_name;
}

/** What a member is called on the page: their name, or their iD. */
function calledBy(member: ProjectMember): string {
  return nameOf(member) ?? shortId(member.member_id);
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

/** The facts a person kept, under a heading, or a word that they kept none. */
function FactsKept({ record, children }: { record: ResearcherRecord | undefined; children?: ReactNode }) {
  return (
    <div className="member-facts">
      <h4>Facts given to agents</h4>
      {record ? <KeptFacts record={record} /> : <p className="muted">None kept from ORCID.</p>}
      {children}
    </div>
  );
}

function MemberEntry({
  member,
  busy,
  onRole,
  onRemove,
  children,
}: {
  member: ProjectMember;
  busy: boolean;
  onRole: (role: MemberRole) => void;
  onRemove: () => void;
  /** What goes under the member's facts: on the signed-in person's own entry, their controls. */
  children?: ReactNode;
}) {
  const other: MemberRole = member.role === "owner" ? "member" : "owner";
  const name = nameOf(member);
  return (
    <li className="member">
      <h3>
        {name ?? <IdLink memberId={member.member_id} />} {member.is_you && <span className="muted">(you)</span>}
      </h3>
      {name && (
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
                  Remove
                  <span className="visually-hidden"> {calledBy(member)}</span>
                </>
              }
              icon={UserMinus}
              title="Remove a member"
              confirm="Remove"
              busy={busy}
              onConfirm={onRemove}
            >
              <p>
                <strong>{calledBy(member)}</strong> will no longer see this project or work on it. What they did in it
                keeps their name. You can add them again later.
              </p>
            </ConfirmMemberChange>
          )}
        </p>
      )}
      <FactsKept record={member.record}>{children}</FactsKept>
    </li>
  );
}

/** Facts kept by people who are no longer members, which agents are still given. */
function FormerResearchers({ records }: { records: ResearcherRecord[] }) {
  if (records.length === 0) return null;
  return (
    <>
      <h3>No longer members</h3>
      <p className="hint">
        These people kept facts in this project and have since left it. Agents are still given what they kept until they
        withdraw it.
      </p>
      <ul className="plain-list members">
        {records.map((record) => (
          <li key={record.orcid_id} className="member">
            <h4>{record.researcher_name ?? <IdLink memberId={record.orcid_id} />}</h4>
            {record.researcher_name && (
              <p>
                <IdLink memberId={record.orcid_id} />
              </p>
            )}
            <KeptFacts record={record} />
          </li>
        ))}
      </ul>
    </>
  );
}

export function PeoplePanel({ projectId }: { projectId: string }) {
  const api = useMembersApi();
  const { projectId: activeId, setProjectId, reloadProjects } = useActiveProject();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => loadInto((signal) => api.members(projectId, signal), setLoad), [api, projectId]);

  /** Read the people again, once the signed-in person has kept or withdrawn their facts. */
  const reload = () => {
    api.members(projectId).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) =>
        setSaid({
          text: `Data Director could not read the project's people: ${message(error)}`,
          ok: false,
        }),
    );
  };

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
        setSaid({
          text: `Data Director could not do that: ${message(error)}`,
          ok: false,
        });
        return false;
      },
    );
  };

  const body = () => {
    if (load.state === "loading") return <p>Reading who works on this project…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the project&apos;s people: {load.message}</p>
        </div>
      );
    }
    const { members, may_manage: mayManage, may_leave: mayLeave } = load.value;
    const formerResearchers = load.value.former_researchers;
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
            >
              {member.is_you && (
                <MyOrcidFacts projectId={projectId} mine={member.record} onChanged={reload} onSaid={setSaid} />
              )}
            </MemberEntry>
          ))}
        </ul>
        <FormerResearchers records={formerResearchers} />
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
                You will no longer see this project or work on it. What you did in it keeps your name. An owner can add
                you again.
              </p>
            </ConfirmMemberChange>
          </p>
        )}
      </>
    );
  };

  return (
    <section className="members-panel" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>People</h2>
      <p className="hint">
        Everyone listed here sees all of this project: its inventory, documents, decisions and facts, and every
        conversation in it, including one another&apos;s messages, each with the sender&apos;s name. Members work on the
        project; owners also approve or reject documents and manage who is a member. Names are read from each
        person&apos;s public ORCID record.
      </p>
      <p className="hint">
        Facts you keep from your public ORCID record, such as your affiliation, keywords, works and funding, are given
        to the agents working on this project, so that they can fill in creators, subjects and funding instead of asking
        you. Agents that send data to a model hosted elsewhere are given them only where this deployment allows it. Your
        email address is never read.
      </p>
      <div role="status" className={said ? `callout ${said.ok ? "status-ok" : "status-danger"}` : undefined}>
        {said && <p>{said.text}</p>}
      </div>
      {body()}
    </section>
  );
}
