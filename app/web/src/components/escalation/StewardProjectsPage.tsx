/**
 * A data steward's projects (docs/ui/steward-escalation-flows.md, "The project overview"; #232):
 * the projects the harness lets the steward see, the one created last first. By default those
 * are the projects with a request to, or a pause held by, one of their teams; where the profile
 * lets stewards see the projects their teams support, those too. Each row shows who started the
 * project, where it is in the process flow, its latest runs and their outcomes, what waits for a
 * person's review, and why the steward may see it. The project's name opens it as the steward's
 * view.
 *
 * Listing a project counts as looking at it: the server records it, and the researcher sees it,
 * as the page says. More projects are read a page at a time.
 */

import "./Steward.css";

import { useState } from "react";

import { journey } from "../../flow/journey";
import { useFlowApi } from "../../flow/api";
import type { ProcessFlow } from "../../flow/types";
import { OUTCOME } from "../../manifest/wording";
import { day } from "../../project/name";
import { type StewardProject, type StewardProjectsPage, useStewardApi } from "../../project/steward";
import { formatDate } from "../../format";
import { Link, projectTabPath } from "../../route";
import { errorMessage } from "../../run/api";
import { useResource } from "../../useResource";
import { PageHeader } from "../frame/PageHeader";
import { Button } from "../ui/Button";
import { TableScroll } from "../ui/TableScroll";
import { StewardNav } from "./StewardNav";
import { stewardStateSaid } from "./wording";

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The phase the project is in: the one with the step the harness suggests next, else the first
 * with a step not yet finished; null without the flow or once every phase is finished. */
export function phaseOf(flow: ProcessFlow | null, project: StewardProject): string | null {
  if (!flow) return null;
  const lines = journey(flow, project.progress);
  const suggested = lines.find((line) =>
    line.items.some((item) => item.kind === "station" && item.suggested),
  );
  const unfinished = lines.find((line) => line.finished < line.counted);
  return (suggested ?? unfinished)?.phase.name ?? null;
}

function Phase({ flow, project }: { flow: ProcessFlow | null; project: StewardProject }) {
  const phase = phaseOf(flow, project);
  if (phase) return <>{phase}</>;
  return <span className="hint">{flow ? "Every phase finished" : "Not known"}</span>;
}

function Runs({ project }: { project: StewardProject }) {
  if (project.recent_runs.length === 0) return <span className="hint">No runs yet</span>;
  return (
    <ul className="plain-list steward-runs">
      {project.recent_runs.map((run) => {
        const outcome = OUTCOME[run.status];
        return (
          <li key={run.invocation_id}>
            <span className={`status status-${outcome.tone}`}>{outcome.label}</span>{" "}
            <time dateTime={run.completed_at} title={formatDate(run.completed_at)}>
              {day(run.completed_at)}
            </time>
          </li>
        );
      })}
    </ul>
  );
}

function Awaiting({ project }: { project: StewardProject }) {
  const { proposed_versions, fact_proposals, referred_runs } = project.awaiting_review;
  const items = [
    referred_runs.length > 0 && plural(referred_runs.length, "step referred to you", "steps referred to you"),
    proposed_versions > 0 && plural(proposed_versions, "document version", "document versions"),
    fact_proposals > 0 && plural(fact_proposals, "proposed fact", "proposed facts"),
  ].filter((item): item is string => typeof item === "string");
  if (items.length === 0) return <span className="hint">Nothing</span>;
  return (
    <ul className="plain-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Reach({ project }: { project: StewardProject }) {
  const { access, escalations, paused } = project;
  const teams = access.teams.map((t) => t.name).join(", ");
  return (
    <>
      {escalations.map((e) => (
        <p key={e.escalation_id}>Request: {stewardStateSaid(e.state)}</p>
      ))}
      {paused && <p className="status status-warn">Paused by {paused.by.name}</p>}
      {!access.escalated && !access.holds_pause && <p>Supported by your team</p>}
      <p className="hint">{teams}</p>
    </>
  );
}

function Row({ flow, project }: { flow: ProcessFlow | null; project: StewardProject }) {
  return (
    <tr>
      <th scope="row">
        <Link to={projectTabPath(project.project_id)}>
          {project.title ?? `Untitled project, started ${day(project.created_at)}`}
        </Link>
      </th>
      <td>
        {project.created_by.name}
        {project.owners.length > 1 && <span className="hint"> and {plural(project.owners.length - 1, "other owner", "other owners")}</span>}
      </td>
      <td>
        <Phase flow={flow} project={project} />
      </td>
      <td>
        <Runs project={project} />
      </td>
      <td>
        <Awaiting project={project} />
      </td>
      <td>
        <Reach project={project} />
      </td>
    </tr>
  );
}

export function StewardProjectsPage() {
  const api = useStewardApi();
  const flowApi = useFlowApi();
  const flow = useResource("flow", (_, signal) => flowApi.get(signal)).latest ?? null;
  const read = useResource("first", (_, signal) => api.projects(null, signal));
  const [more, setMore] = useState<StewardProjectsPage[]>([]);
  const [reading, setReading] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const { resource } = read;

  const table = () => {
    if (resource.state === "loading") return <p role="status">Reading the projects…</p>;
    if (resource.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the projects: {resource.message}</p>
        </div>
      );
    }
    const pages = [resource.value, ...more];
    const rows = pages.flatMap((page) => page.items);
    const next = pages[pages.length - 1]?.next ?? null;
    if (rows.length === 0) {
      return <p>No project is waiting for your teams: none has a request or a pause of theirs.</p>;
    }
    const readMore = async () => {
      setReading(true);
      setFailed(null);
      try {
        const page = await api.projects(next);
        setMore((held) => [...held, page]);
      } catch (error) {
        setFailed(errorMessage(error));
      } finally {
        setReading(false);
      }
    };
    return (
      <>
        <TableScroll label="Projects your data steward teams may see">
          <table className="data-table steward-projects">
            <caption className="visually-hidden">Projects your data steward teams may see, the newest first</caption>
            <thead>
              <tr>
                <th scope="col">Project</th>
                <th scope="col">Started by</th>
                <th scope="col">Phase</th>
                <th scope="col">Latest runs</th>
                <th scope="col">Waiting for review</th>
                <th scope="col">Why you can see it</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((project) => (
                <Row key={project.project_id} flow={flow} project={project} />
              ))}
            </tbody>
          </table>
        </TableScroll>
        {failed && (
          <div role="alert" className="callout status-danger">
            <p>Data Director could not read more projects: {failed}</p>
          </div>
        )}
        {next && (
          <p>
            <Button size="small" onPress={() => void readMore()} isPending={reading}>
              {reading ? "Reading more projects…" : "Show more projects"}
            </Button>
          </p>
        )}
      </>
    );
  };

  return (
    <>
      <PageHeader title="Projects your teams support">
        <p className="hint">
          The projects you may open as a data steward. Listing a project here counts as looking at
          it: the researchers see that you did, as when you open it.
        </p>
      </PageHeader>
      <StewardNav current="/steward/projects" />
      {table()}
    </>
  );
}
