/**
 * A data steward's queue (docs/ui/steward-escalation-flows.md, flow C; #376): the escalations
 * routed to the steward's teams, the oldest first, with each one's project, researcher, request,
 * age, state and who has taken it. By default it shows the live ones (not taken, taken, waiting
 * for the researcher); a filter shows those in one state. Each row offers the moves the harness
 * lists for it, such as **Take**, so that colleagues see who has it, and links to the project,
 * which opens as the steward's view of it.
 *
 * What a move did is announced in the polite live region, and the queue is read again after it.
 */

import "./Steward.css";

import { useId, useState } from "react";

import type { EscalationState } from "../../project/escalations";
import { LIVE_STATES } from "../../project/escalations";
import { type QueuedEscalation, useStewardApi } from "../../project/steward";
import { formatDate, formatNumber } from "../../format";
import { Link, projectTabPath } from "../../route";
import { useResource } from "../../useResource";
import { PageHeader } from "../frame/PageHeader";
import { TableScroll } from "../ui/TableScroll";
import { MoveControls } from "./MoveControls";
import { StewardNav } from "./StewardNav";
import { originSaid, stewardStateSaid } from "./wording";

const FILTERS: { value: string; label: string; states: readonly EscalationState[] }[] = [
  { value: "live", label: "Still to finish", states: LIVE_STATES },
  { value: "open", label: "Not taken", states: ["open"] },
  { value: "taken", label: "Taken", states: ["taken"] },
  { value: "waiting_for_researcher", label: "Waiting for the researcher", states: ["waiting_for_researcher"] },
  { value: "resolved", label: "Resolved", states: ["resolved"] },
  { value: "handed_back", label: "Handed back", states: ["handed_back"] },
  { value: "withdrawn", label: "Withdrawn", states: ["withdrawn"] },
];

const DAY = 86_400_000;

/** How long ago `at` was, in whole days. */
export function ageSaid(at: string, now: number = Date.now()): string {
  const days = Math.max(0, Math.floor((now - new Date(at).getTime()) / DAY));
  if (days === 0) return "Today";
  return days === 1 ? "1 day" : `${formatNumber(days)} days`;
}

export function StewardQueuePage() {
  const api = useStewardApi();
  const id = useId();
  const [filter, setFilter] = useState("live");
  const states = (FILTERS.find((f) => f.value === filter) ?? FILTERS[0])?.states ?? LIVE_STATES;
  const read = useResource(filter, (_, signal) => api.queue(states, signal));
  const { resource, reload } = read;

  const table = () => {
    if (resource.state === "loading") return <p role="status">Reading the requests…</p>;
    if (resource.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the requests: {resource.message}</p>
        </div>
      );
    }
    if (resource.value.length === 0) {
      return <p>No requests to a data steward are {filter === "live" ? "waiting for your team" : "in this state"}.</p>;
    }
    return (
      <TableScroll label="Requests to your data steward teams">
        <table className="steward-queue">
          <caption className="visually-hidden">Requests to your data steward teams, the oldest first</caption>
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">Researcher</th>
              <th scope="col">Request</th>
              <th scope="col">Age</th>
              <th scope="col">State</th>
              <th scope="col">Taken by</th>
              <th scope="col">What you can do</th>
            </tr>
          </thead>
          <tbody>
            {resource.value.map((row) => (
              <QueueRow
                key={row.escalation_id}
                row={row}
                onMove={async (move, note, to) => {
                  try {
                    await api.move(row.project_id, row.escalation_id, move, note, to);
                  } finally {
                    reload();
                  }
                }}
              />
            ))}
          </tbody>
        </table>
      </TableScroll>
    );
  };

  return (
    <>
      <PageHeader title="Requests to the data stewards">
        <p className="hint">
          The requests researchers sent to your data steward teams. Take one so that your colleagues
          can see you have it, then open its project to work on it with the researcher.
        </p>
      </PageHeader>
      <StewardNav current="/steward" />
      <div className="field steward-queue-filter">
        <label htmlFor={`${id}-filter`}>Show</label>
        <select id={`${id}-filter`} value={filter} onChange={(event) => setFilter(event.target.value)}>
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>
      {table()}
    </>
  );
}

function QueueRow({
  row,
  onMove,
}: {
  row: QueuedEscalation;
  onMove: Parameters<typeof MoveControls>[0]["onMove"];
}) {
  const project = row.project_title ?? "Untitled project";
  return (
    <tr>
      <th scope="row">
        <Link to={projectTabPath(row.project_id)}>{project}</Link>
        <span className="hint"> · {row.team_name}</span>
      </th>
      <td>{row.opened_by.name}</td>
      <td>
        <span className="hint">{originSaid(row.origin.kind)}: </span>
        {row.note}
      </td>
      <td>
        <time dateTime={row.opened_at} title={formatDate(row.opened_at)}>
          {ageSaid(row.opened_at)}
        </time>
      </td>
      <td>{stewardStateSaid(row.state)}</td>
      <td>{row.taken_by?.name ?? "Nobody yet"}</td>
      <td>
        <MoveControls escalation={row} onMove={onMove} context={`the request on ${project}`} />
      </td>
    </tr>
  );
}
