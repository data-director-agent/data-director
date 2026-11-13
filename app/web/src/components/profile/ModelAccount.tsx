/**
 * The person's own AI account on the Profile page (docs/specs/model-accounts.md, Enrolment).
 *
 * The key typed here goes to the model broker alone (`model-account/api.ts`); the page keeps it
 * only until it is sent, and shows nothing of it afterwards but the label the broker returns. A key
 * the provider refuses is not saved, and the page says why in plain words. Removing the account
 * erases it at the broker at once.
 */

import { KeyRound, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import {
  AccountRefused,
  type ModelAccount as Account,
  reasonText,
  useModelAccountApi,
} from "../../model-account/api";
import { SignedOut } from "../../session/api";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";

type Load = { state: "loading" } | { state: "loaded"; value: Account } | { state: "failed" };
type Change =
  | { state: "idle" }
  | { state: "sending" }
  | { state: "failed"; message: string }
  | { state: "done"; message: string };

const NUMBER = new Intl.NumberFormat();

function messageOf(error: unknown): string {
  return error instanceof AccountRefused ? reasonText(error.reason) : reasonText("");
}

export function ModelAccount() {
  const api = useModelAccountApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [change, setChange] = useState<Change>({ state: "idle" });
  const [replacing, setReplacing] = useState(false);
  const [key, setKey] = useState("");
  const outcome = useRef<HTMLDivElement>(null);
  const keyId = useId();
  const hintId = useId();

  useEffect(() => {
    const controller = new AbortController();
    api
      .read(controller.signal)
      .then((value) => setLoad({ state: "loaded", value }))
      .catch((error: unknown) => {
        if (controller.signal.aborted || error instanceof SignedOut) return;
        setLoad({ state: "failed" });
      });
    return () => controller.abort();
  }, [api]);

  useEffect(() => {
    if (change.state === "failed" || change.state === "done") outcome.current?.focus();
  }, [change]);

  async function enrol(event: FormEvent) {
    event.preventDefault();
    const typed = key.trim();
    // The key leaves the page's state as soon as it is sent, whatever the answer.
    setKey("");
    setChange({ state: "sending" });
    try {
      const value = await api.enrol("anthropic", typed);
      setLoad({ state: "loaded", value });
      setReplacing(false);
      setChange({ state: "done", message: "Your account was checked and saved." });
    } catch (error) {
      if (error instanceof SignedOut) return;
      setChange({ state: "failed", message: messageOf(error) });
    }
  }

  async function remove(close: () => void) {
    setChange({ state: "sending" });
    try {
      await api.remove();
      setLoad((current) =>
        current.state === "loaded"
          ? { state: "loaded", value: { ...current.value, account: null } }
          : current,
      );
      setChange({ state: "done", message: "Your account was removed." });
    } catch (error) {
      if (error instanceof SignedOut) return;
      setChange({ state: "failed", message: messageOf(error) });
    } finally {
      close();
    }
  }

  const account = load.state === "loaded" ? load.value.account : null;
  const usage = load.state === "loaded" ? load.value.usage : [];
  const showForm = load.state === "loaded" && (account === null || replacing);

  return (
    <section className="model-account" aria-labelledby="model-account-heading">
      <h2 id="model-account-heading">Your AI account</h2>
      <p>
        You can use your own Anthropic account for the AI models Data Director calls for you. Your
        key goes to Data Director’s model broker, which checks it with Anthropic and keeps it
        encrypted. The rest of Data Director never sees it, and this page shows only its last four
        characters.
      </p>
      {/* TODO(#810): say whether runs use the account once the profile can turn own accounts on. */}
      <p className="hint">
        Until this deployment’s policy turns own accounts on, the deployment still pays for every
        run.
      </p>

      {load.state === "loading" && <p role="status">Reading your account…</p>}
      {load.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Your account could not be read. Reload the page to try again.</p>
        </div>
      )}

      {change.state === "failed" && (
        <div role="alert" className="callout status-danger" ref={outcome} tabIndex={-1}>
          <p>{change.message}</p>
        </div>
      )}
      {change.state === "done" && (
        <div role="status" className="callout status-ok" ref={outcome} tabIndex={-1}>
          <p>{change.message}</p>
        </div>
      )}

      {account && (
        <>
          <dl className="profile-details">
            <div>
              <dt>Account</dt>
              <dd>{account.label}</dd>
            </div>
            <div>
              <dt>Added</dt>
              <dd>
                <time dateTime={account.created}>{new Date(account.created).toLocaleString()}</time>
              </dd>
            </div>
          </dl>
          {!replacing && (
            <div className="model-account-actions">
              <Button variant="secondary" icon={KeyRound} onPress={() => setReplacing(true)}>
                Replace key
              </Button>
              <DialogTrigger>
                <Button variant="danger" icon={Trash2} isDisabled={change.state === "sending"}>
                  Remove account
                </Button>
                <ModalDialog
                  title="Remove your AI account?"
                  footer={(close) => (
                    <>
                      <Button variant="quiet" onPress={close}>
                        Keep it
                      </Button>
                      <Button
                        variant="danger"
                        icon={Trash2}
                        isPending={change.state === "sending"}
                        onPress={() => void remove(close)}
                      >
                        Remove account
                      </Button>
                    </>
                  )}
                >
                  <p>
                    Your key is erased from Data Director at once. A run that has already started
                    may finish first. Your account with Anthropic is not changed.
                  </p>
                </ModalDialog>
              </DialogTrigger>
            </div>
          )}
        </>
      )}

      {showForm && (
        <form className="model-account-form" onSubmit={(event) => void enrol(event)}>
          <div className="field">
            <label htmlFor={keyId}>Anthropic API key</label>
            <p className="hint" id={hintId}>
              Create a key in the Anthropic Console and paste it here. It is checked with one free
              request before it is saved.
            </p>
            <input
              type="password"
              id={keyId}
              aria-describedby={hintId}
              autoComplete="off"
              spellCheck={false}
              required
              value={key}
              onChange={(event) => setKey(event.target.value)}
            />
          </div>
          <div className="model-account-actions">
            <Button
              type="submit"
              variant="primary"
              icon={KeyRound}
              isPending={change.state === "sending"}
              isDisabled={key.trim() === ""}
            >
              {account ? "Check and replace" : "Check and add"}
            </Button>
            {replacing && (
              <Button
                variant="quiet"
                onPress={() => {
                  setKey("");
                  setReplacing(false);
                }}
              >
                Cancel
              </Button>
            )}
          </div>
        </form>
      )}

      {load.state === "loaded" && (
        <>
          <h3>Your token use</h3>
          {usage.length === 0 ? (
            <p>No model calls have been made for you in the last 30 days.</p>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <caption className="visually-hidden">Tokens used for you in the last 30 days</caption>
                <thead>
                  <tr>
                    <th scope="col">Day</th>
                    <th scope="col">Model</th>
                    <th scope="col">Paid by</th>
                    <th scope="col">Input tokens</th>
                    <th scope="col">Output tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.map((row) => (
                    <tr key={`${row.day} ${row.payer} ${row.provider} ${row.model}`}>
                      <td>
                        <time dateTime={row.day}>{row.day}</time>
                      </td>
                      <td>{row.model}</td>
                      <td>{row.payer === "own" ? "Your account" : "The deployment"}</td>
                      <td>{NUMBER.format(row.inputTokens)}</td>
                      <td>{NUMBER.format(row.outputTokens)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
