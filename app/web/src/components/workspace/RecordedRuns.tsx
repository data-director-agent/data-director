/**
 * The runs Data Director has recorded, for the activity log (#1330): each stored run the person may
 * read (`GET /api/runs`), newest first, with its outcome and a link to its record. Unlike the runs
 * this tab has streamed, these outlast a reload, another tab and signing in again.
 *
 * A run this tab holds, or one it delegated to, is shown step by step above, so it is not listed
 * again here. The list is read again whenever a run streamed in this tab ends.
 */

import { useState } from "react";

import { formatDateTime } from "../../format";
import { OUTCOME } from "../../manifest/wording";
import { errorMessage, type RunPage, useRunApi } from "../../run/api";
import type { RunRow } from "../../run/types";
import { homePath, Link } from "../../route";
import { useResource } from "../../useResource";
import { Button } from "../ui/Button";

function Row({ row }: { row: RunRow }) {
  const outcome = OUTCOME[row.status];
  return (
    <li className="recorded-run">
      <code>{row.agent_id}</code>{" "}
      <span className={`status status-${outcome.tone}`}>{outcome.label}</span>{" "}
      <span>
        ended {formatDateTime(row.completed_at, { dateStyle: "medium", timeStyle: "short" })}
      </span>
      {row.acting_for && <span>, for {row.acting_for}</span>}{" "}
      <Link to={homePath({ run: row.invocation_id })}>Open its record</Link>
    </li>
  );
}

export function RecordedRuns({
  shownAbove,
  refresh,
}: {
  /** The runs listed step by step above, by invocation, not to be listed twice. */
  shownAbove: ReadonlySet<string>;
  /** Changes whenever the list should be read again, as when a run here ends. */
  refresh: unknown;
}) {
  const api = useRunApi();
  // The older pages asked for since the first was last read.
  const [older, setOlder] = useState<RunPage[]>([]);
  const [more, setMore] = useState<{ loading: boolean; error: string | null }>({
    loading: false,
    error: null,
  });
  const first = useResource("runs", (_, signal) => api.list(null, signal), refresh, {
    loaded: () => setOlder([]),
  });

  const pages = first.latest ? [first.latest, ...older] : [];
  const next = pages.at(-1)?.next ?? null;
  const rows = pages.flatMap((page) => page.items).filter((r) => !shownAbove.has(r.invocation_id));

  async function showOlder() {
    if (!next) return;
    setMore({ loading: true, error: null });
    try {
      const page = await api.list(next);
      setOlder((held) => [...held, page]);
      setMore({ loading: false, error: null });
    } catch (e) {
      setMore({ loading: false, error: errorMessage(e) });
    }
  }

  return (
    <section aria-labelledby="recorded-runs">
      <h2 id="recorded-runs">Recorded runs</h2>
      {first.resource.state === "failed" && !first.latest ? (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list the recorded runs: {first.resource.message}.</p>
        </div>
      ) : !first.latest ? (
        <p role="status">Loading the recorded runs…</p>
      ) : rows.length === 0 ? (
        <p>No other runs recorded yet. Send a message in a conversation to start one.</p>
      ) : (
        <ol className="recorded-runs">
          {rows.map((row) => (
            <Row key={row.invocation_id} row={row} />
          ))}
        </ol>
      )}
      {more.error && (
        <p role="alert" className="status status-danger">
          Data Director could not list the older runs: {more.error}.
        </p>
      )}
      {next && (
        <Button variant="secondary" size="small" isDisabled={more.loading} onPress={showOlder}>
          Show older runs
        </Button>
      )}
    </section>
  );
}
