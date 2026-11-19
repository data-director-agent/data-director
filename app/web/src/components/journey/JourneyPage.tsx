/**
 * A project's journey map, at `/projects/{id}/journey` (docs/specs/app.md, "The journey map"):
 * the whole route from planning to sharing, where the project is on it and why, what waits on the
 * researcher, and the step's details beside the map, open at `?step=`. Everything comes from the
 * server's process flow and the project's progress, which the harness derives; the page keeps
 * none of it. Marking a step goes to the server and the map shows the progress it answers with.
 */

import { Hourglass } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { journey, stations, waitingCount, waitingDocuments } from "../../flow/journey";
import { useFlowApi } from "../../flow/api";
import type { ProcessFlow, ProjectProgress, StepMark } from "../../flow/types";
import { useActiveProject } from "../../project/active";
import { type ProjectDocument, useProjectApi } from "../../project/api";
import { projectName } from "../../project/name";
import { errorMessage } from "../../run/api";
import { homePath, journeyPath, navigate } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { ProjectNav } from "../project/ProjectNav";
import { ToggleButton } from "../ui/Button";
import { JourneyMap, stopId } from "./JourneyMap";
import { StationPanel } from "./StationPanel";

type Load<T> =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: T };

export function JourneyPage({ projectId, query = "" }: { projectId: string; query?: string }) {
  const flowApi = useFlowApi();
  const projectApi = useProjectApi();
  const { projects, setProjectId } = useActiveProject();
  const [flow, setFlow] = useState<Load<ProcessFlow>>({ state: "loading" });
  const [progress, setProgress] = useState<Load<ProjectProgress>>({ state: "loading" });
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [markError, setMarkError] = useState<string | null>(null);
  const [waitingOnly, setWaitingOnly] = useState(false);
  const selected = new URLSearchParams(query).get("step");

  useEffect(() => {
    const abort = new AbortController();
    flowApi.get(abort.signal).then(
      (value) => setFlow({ state: "loaded", value }),
      (e: unknown) => abort.signal.aborted || setFlow({ state: "failed", message: errorMessage(e) }),
    );
    return () => abort.abort();
  }, [flowApi]);

  useEffect(() => {
    const abort = new AbortController();
    projectApi.progress(projectId, abort.signal).then(
      (value) => {
        setProgress({ state: "loaded", value });
        setProjectId(projectId);
      },
      (e: unknown) =>
        abort.signal.aborted || setProgress({ state: "failed", message: errorMessage(e) }),
    );
    // What waits on the researcher is a nicety: if the documents cannot be read, nothing is shown
    // as waiting for a decision, and the map is still drawn.
    projectApi.documents(projectId, abort.signal).then(
      (read) => setDocuments(read.documents),
      () => undefined,
    );
    return () => abort.abort();
  }, [projectApi, projectId, setProjectId]);

  const project = projects.find((p) => p.project_id === projectId) ?? null;
  const loadedProgress = progress.state === "loaded" ? progress.value : null;
  const lines = useMemo(
    () =>
      flow.state === "loaded"
        ? journey(flow.value, loadedProgress, waitingDocuments(documents))
        : [],
    [flow, loadedProgress, documents],
  );
  const station = stations(lines).find((s) => s.step.id === selected) ?? null;
  const waiting = waitingCount(lines);

  const select = useCallback(
    (stepId: string | null) => {
      setMarkError(null);
      navigate(journeyPath(projectId, stepId), true);
    },
    [projectId],
  );
  function close() {
    const was = selected;
    select(null);
    // Focus goes back to the stop that was open, once the map has been drawn without the panel.
    if (was) requestAnimationFrame(() => document.getElementById(stopId(was))?.focus());
  }
  function mark(stepId: string, how: StepMark) {
    projectApi.markStep(projectId, stepId, how).then(
      (value) => {
        setMarkError(null);
        setProgress({ state: "loaded", value });
      },
      (e: unknown) => setMarkError(errorMessage(e)),
    );
  }
  function ask(stepId: string) {
    setProjectId(projectId);
    navigate(homePath({ ask: stepId }));
  }

  return (
    <>
      <ProjectNav
        projectId={projectId}
        name={project ? projectName(project) : null}
        current="journey"
      />
      <PageHeader title="Your data journey">
        <p className="hint">
          The whole route from planning your data to sharing it, and where this project is on it.
          The order is a guide, not a rule: you can do, skip or come back to any step.
        </p>
      </PageHeader>
      {(flow.state === "loading" || progress.state === "loading") && (
        <p role="status">Loading the journey…</p>
      )}
      {flow.state === "failed" && (
        <p role="alert" className="callout status-danger">
          Data Director could not load the journey: {flow.message}.
        </p>
      )}
      {progress.state === "failed" && (
        <p role="alert" className="callout status-danger">
          Data Director could not read where this project is: {progress.message}.
        </p>
      )}
      {flow.state === "loaded" && loadedProgress && (
        <>
          <div className="journey-tools">
            <ToggleButton
              size="small"
              icon={Hourglass}
              isSelected={waitingOnly}
              onChange={setWaitingOnly}
              isDisabled={waiting === 0 && !waitingOnly}
            >
              {waiting === 0 ? "Nothing waiting on you" : `Waiting on you (${waiting})`}
            </ToggleButton>
            {loadedProgress.entry === null && (
              <p className="muted">
                Tell Data Director where you are, or answer the setup questions, to get a
                suggested next step.
              </p>
            )}
          </div>
          <div className={station ? "journey-page has-panel" : "journey-page"}>
            <JourneyMap
              lines={lines}
              entry={loadedProgress.entry}
              entryByModel={loadedProgress.entry_source === "model"}
              selected={selected}
              onSelect={(id) => (id ? select(id) : close())}
              waitingOnly={waitingOnly}
            />
            {station && (
              <StationPanel
                station={station}
                projectId={projectId}
                decisions={loadedProgress.decisions ?? []}
                onMark={(how) => mark(station.step.id, how)}
                onAsk={() => ask(station.step.id)}
                onClose={close}
                error={markError}
              />
            )}
          </div>
        </>
      )}
    </>
  );
}
