/**
 * Depositing a built package as a draft through the repository's API, with the person's own
 * account (docs/specs/deposit.md, Depositing through an API).
 *
 * Shown under a built package only where the deployment deposits to the chosen repository for the
 * person. Pressing the button is the person's approval: the harness records it, and the deposit
 * broker creates a draft holding the approved metadata and the package. Nothing is published and no
 * data file is uploaded: the person adds the files and publishes in the repository, or deletes the
 * draft. Where the repository is the platform's sandbox, the panel says that its records and DOIs
 * are not real. What the deposit did is said once, in a live region present from the start.
 */

import { ExternalLink, CloudUpload } from "lucide-react";
import { useEffect, useState } from "react";

import {
  DepositRefused,
  type DepositShown,
  type Deposits,
  reasonText,
  useDepositApi,
} from "../../deposit/api";
import { formatDateTime } from "../../format";
import { Link } from "../../route";
import { Button } from "../ui/Button";

const HEADING_ID = "deposit-draft-heading";

/** A deposit recorded as sandbox stays labelled even if the deployment's connection changed. */
function draftIsSandbox(made: DepositShown, current: boolean): boolean {
  return made.sandbox || current;
}

function failureText(shown: DepositShown): string {
  return reasonText(shown.reason ?? "");
}

function Draft({
  shown,
  name,
  sandbox,
}: {
  shown: DepositShown;
  name: string;
  sandbox: boolean;
}) {
  if (!shown.draft_url) return null;
  return (
    <div className="callout status-ok">
      {sandbox && (
        <p>
          <strong>Sandbox: not a real deposit.</strong> This draft is in the{" "}
          {name} sandbox, a test copy. It will not be found in {name}, and any
          DOI it shows (test DOIs start 10.5072) does not resolve.
        </p>
      )}
      <p>
        A draft was made in {name} on {formatDateTime(shown.approved_at)}.{" "}
        <a href={shown.draft_url} target="_blank" rel="noreferrer">
          Open the draft in {name}
          <ExternalLink
            className="button-icon"
            size="1em"
            aria-label="(opens in a new tab)"
          />
        </a>
      </p>
      <p>
        Data Director did not publish it. In {name}, upload your data files to
        the draft, check it, and publish it, or delete it.
      </p>
      {shown.unplaced && shown.unplaced.length > 0 && (
        <p className="hint">
          {name}&apos;s form has no place for these parts of the metadata
          record, so they were not sent: {shown.unplaced.join(", ")}. Add them
          in {name} if they belong there.
        </p>
      )}
    </div>
  );
}

export function DepositToRepository({
  projectId,
  digest,
  revision,
}: {
  projectId: string;
  /** The package built, by its SHA-256. */
  digest: string;
  revision: number;
}) {
  const api = useDepositApi();
  const [found, setFound] = useState<Deposits | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [needsAccount, setNeedsAccount] = useState(false);
  const [said, setSaid] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api.deposits(projectId, controller.signal).then(
      (value) => setFound(value),
      () => {
        if (!controller.signal.aborted) setFound(null);
      },
    );
    return () => controller.abort();
  }, [api, projectId, revision]);

  const connection = found?.connection;
  if (!found || !connection?.available) return null;
  const listed = found;
  const name = connection.repository_name;
  const made = listed.deposits
    .filter((d) => d.digest === digest && d.state === "recorded")
    .at(-1);

  const deposit = async () => {
    setBusy(true);
    setFailed(null);
    setNeedsAccount(false);
    try {
      const shown = await api.deposit(projectId, digest);
      setFound({ ...listed, deposits: [...listed.deposits, shown] });
      if (shown.state === "recorded") {
        setSaid(
          `${connection.sandbox ? "Sandbox: not a real deposit. " : ""}A draft was made in ${name}. Open it to add your data files and publish.`,
        );
      } else {
        setSaid("");
        setFailed(failureText(shown));
        setNeedsAccount(
          shown.reason === "account-missing" ||
            shown.reason === "account-rejected",
        );
      }
    } catch (error: unknown) {
      setSaid("");
      setFailed(
        error instanceof DepositRefused
          ? reasonText(error.refusal)
          : error instanceof Error
            ? error.message
            : String(error),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="deposit-draft" aria-labelledby={HEADING_ID}>
      <h3 id={HEADING_ID}>Deposit a draft to {name}</h3>
      {connection.sandbox && (
        <div className="callout status-warn">
          <p>
            <strong>Practice deposit.</strong> This deployment deposits to the{" "}
            {name} sandbox, a test copy of {name}. Its records and DOIs are not
            real, and it is emptied from time to time. You need a separate
            account on the sandbox.
          </p>
        </div>
      )}
      <p>
        Data Director can create a draft in {name} with your own {name} account,
        holding the approved metadata and this package. It does not publish the
        draft or upload your data files: you do both in {name}.
      </p>
      <div role="status">{said && <p>{said}</p>}</div>
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>No draft was made. {failed}</p>
          {needsAccount && (
            <p>
              <Link to="/settings">
                Connect your {name} account in Settings
              </Link>
            </p>
          )}
        </div>
      )}
      {made ? (
        <Draft
          shown={made}
          name={name}
          sandbox={draftIsSandbox(made, connection.sandbox)}
        />
      ) : (
        <p className="document-actions">
          <Button
            variant="primary"
            icon={CloudUpload}
            isPending={busy}
            onPress={() => void deposit()}
          >
            {busy
              ? `Creating the draft in ${name}…`
              : `Create a draft in ${name}`}
          </Button>
        </p>
      )}
    </section>
  );
}
