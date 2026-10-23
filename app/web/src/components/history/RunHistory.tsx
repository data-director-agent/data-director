/**
 * The History tab: this agent's stored runs, newest first, each of which reopens read-only in
 * the same outcome view (`GET /api/runs`, `GET /api/runs/{id}`).
 *
 * Every run is listed, whoever it acted for: until there is authentication (#17) there is one
 * operator. Paging, filtering, the run's own schema and its spans are #107.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import { OUTCOME } from "../../manifest/wording";
import { errorMessage, useRunApi } from "../../run/api";
import { inferStages } from "../../run/stages";
import type { RunResult, RunRow } from "../../run/types";
import { Outcome } from "../run/Outcome";
import { Stages } from "../run/Stages";
import { Button } from "../ui/Button";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; rows: RunRow[] };

export function RunHistory({ agent, refresh = 0 }: { agent: AgentView; refresh?: number }) {
  const api = useRunApi();
  const idPrefix = `history${useId().replace(/:/g, "")}`;
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [open, setOpen] = useState<{ id: string; result: RunResult | null; error?: string } | null>(
    null,
  );
  const openHeading = useRef<HTMLHeadingElement>(null);
  const listHeading = useRef<HTMLHeadingElement>(null);
  const headingId = `${idPrefix}-heading`;

  const reload = useCallback(
    (signal?: AbortSignal) =>
      api.list(signal).then(
        (rows) => setLoad({ state: "loaded", rows: rows.filter((r) => r.agent_id === agent.id) }),
        (error: unknown) => {
          if (!signal?.aborted) setLoad({ state: "failed", message: errorMessage(error) });
        },
      ),
    [api, agent.id],
  );

  useEffect(() => {
    const abort = new AbortController();
    void reload(abort.signal);
    return () => abort.abort();
  }, [reload, refresh]);

  useEffect(() => {
    if (open?.result) openHeading.current?.focus();
  }, [open]);

  function show(id: string) {
    setOpen({ id, result: null });
    api.get(id).then(
      (result) => setOpen({ id, result }),
      (error: unknown) => setOpen({ id, result: null, error: errorMessage(error) }),
    );
  }

  function back() {
    setOpen(null);
    queueMicrotask(() => listHeading.current?.focus());
  }

  if (open) {
    return (
      <div className="history-run">
        <p>
          <Button onPress={back}>Back to all runs</Button>
        </p>
        {open.error ? (
          <div role="alert" className="callout status-danger">
            <p>Data Director could not open run {open.id}: {open.error}.</p>
          </div>
        ) : open.result === null ? (
          <p role="status">Opening the run…</p>
        ) : (
          <>
            <h3 className="visually-hidden">Run {open.id}</h3>
            <Stages stages={inferStages(open.result)} inferred />
            <Outcome
              result={open.result}
              agent={agent}
              idPrefix={`${idPrefix}-open`}
              headingRef={openHeading}
            />
          </>
        )}
      </div>
    );
  }

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} ref={listHeading} tabIndex={-1}>
        Runs of this agent
      </h3>
      <p>
        <Button onPress={() => void reload()}>Refresh</Button>
      </p>
      {load.state === "loading" && <p role="status">Loading the runs…</p>}
      {load.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list the runs: {load.message}.</p>
        </div>
      )}
      {load.state === "loaded" && load.rows.length === 0 && <p>No runs yet. Start one from Run.</p>}
      {load.state === "loaded" && load.rows.length > 0 && (
        <table className="data-table">
          <caption className="visually-hidden">Runs of {agent.id}, newest first</caption>
          <thead>
            <tr>
              <th scope="col">Completed</th>
              <th scope="col">Outcome</th>
              <th scope="col">Acted for</th>
              <th scope="col">
                <span className="visually-hidden">Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {load.rows.map((row) => {
              const { label, tone } = OUTCOME[row.status];
              return (
                <tr key={row.invocation_id}>
                  <td>{row.completed_at}</td>
                  <td>
                    <span className={`status status-${tone}`}>{label}</span>
                  </td>
                  <td>{row.acting_for ?? "Not recorded"}</td>
                  <td>
                    <Button
                      variant="quiet"
                      size="small"
                      onPress={() => show(row.invocation_id)}
                      aria-label={`Open the run completed at ${row.completed_at}`}
                    >
                      Open
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
