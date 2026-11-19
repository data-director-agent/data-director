/**
 * The confirmation C2 asks for before any deposit: that ethics approval, data-protection advice
 * and third-party rights were checked (docs/specs/deposit.md, invariant 21).
 *
 * The statements are the server's, the words the project log keeps with the confirmation, never
 * this file's. A confirmation is for the inventory the project holds when it is made, so a new
 * inventory shows the statements unconfirmed again. Only someone who may decide in the project
 * may confirm; the server refuses anyone else, and the panel says what it said.
 */

import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime } from "../../format";
import { type DepositChecks as Checks, useProjectApi } from "../../project/api";
import { Button } from "../ui/Button";

const HEADING_ID = "deposit-checks-heading";
const TICK_ID = "deposit-checks-tick";

type Load = { state: "loading" } | { state: "loaded"; checks: Checks } | { state: "failed" };

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function DepositChecks({
  projectId,
  revision,
  onConfirmed,
}: {
  projectId: string;
  revision: number;
  onConfirmed: () => void;
}) {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [ticked, setTicked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.depositChecks(projectId, controller.signal).then(
      (checks) => setLoad({ state: "loaded", checks }),
      () => {
        if (!controller.signal.aborted) setLoad({ state: "failed" });
      },
    );
    return () => controller.abort();
  }, [api, projectId, revision]);

  if (load.state !== "loaded") return null;
  const { statements, confirmed } = load.checks;

  const confirm = async () => {
    setBusy(true);
    setFailed(null);
    try {
      const made = await api.confirmDepositChecks(projectId);
      setLoad({ state: "loaded", checks: { statements, confirmed: made } });
      onConfirmed();
    } catch (error: unknown) {
      setFailed(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="deposit-checks" aria-labelledby={HEADING_ID}>
      <h3 id={HEADING_ID}>Before deposit</h3>
      <ul>
        {statements.map((statement) => (
          <li key={statement}>{statement}</li>
        ))}
      </ul>
      {confirmed ? (
        <p className="callout status-ok">
          Confirmed by {confirmed.confirmed_by} on {formatDateTime(confirmed.confirmed_at)}, for the
          inventory the project holds now. A new inventory needs a new confirmation.
        </p>
      ) : (
        <>
          <p className="hint">
            Data Director cannot check these for you. An owner of the project confirms them once
            they have been checked; the confirmation is kept in the project log and the package.
          </p>
          <div className="field field-check">
            <input
              type="checkbox"
              id={TICK_ID}
              checked={ticked}
              onChange={(event) => setTicked(event.target.checked)}
            />
            <label htmlFor={TICK_ID}>I confirm each of these for this project&apos;s data</label>
          </div>
          <p className="document-actions">
            <Button
              icon={ShieldCheck}
              isPending={busy}
              isDisabled={!ticked}
              onPress={() => void confirm()}
            >
              Confirm the checks
            </Button>
          </p>
        </>
      )}
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not record the confirmation: {failed}</p>
        </div>
      )}
    </section>
  );
}
