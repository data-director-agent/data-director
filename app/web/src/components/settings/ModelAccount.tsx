/**
 * The person's own AI account on the Settings page (docs/specs/model-accounts.md, Enrolment).
 *
 * The key typed here goes to the model broker alone (`model-account/api.ts`); the page keeps it
 * only until it is sent, and shows nothing of it afterwards but the label the broker returns. A key
 * the provider refuses is not saved, and the page says why in plain words. Removing the account
 * erases it at the broker at once.
 *
 * The page offers only the providers the profile allows (`providers`, from the session), and for an
 * OpenAI-compatible service only an address under one of the origins the profile lists. The broker
 * checks both again; the page only saves a person a refusal.
 */

import { KeyRound, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import {
  AccountRefused,
  type ModelAccount as Account,
  reasonText,
  useModelAccountApi,
} from "../../model-account/api";
import { type ModelAccountProvider, SignedOut } from "../../session/api";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";
import { formatDateTime } from "../../format";
import { KeyField } from "./KeyField";
import { ModelAccountUsage } from "./ModelAccountUsage";
import { COMPATIBLE, DEFAULT_PROVIDERS, describe, underOrigin } from "./modelProviders";

type Load = { state: "loading" } | { state: "loaded"; value: Account } | { state: "failed" };
type Change =
  | { state: "idle" }
  | { state: "sending" }
  | { state: "failed"; message: string }
  | { state: "done"; message: string };

function messageOf(error: unknown): string {
  return error instanceof AccountRefused ? reasonText(error.reason) : reasonText("");
}

// eslint-disable-next-line complexity -- recorded debt: split it, do not add to it (docs/architecture-review.md)
export function ModelAccount({
  providers: offered = DEFAULT_PROVIDERS,
}: {
  /** The providers the profile lets a person's own account be with. */
  providers?: ModelAccountProvider[];
}) {
  const providers = offered.length > 0 ? offered : DEFAULT_PROVIDERS;
  const api = useModelAccountApi();
  const [chosen, setChosen] = useState(providers[0]?.provider ?? "anthropic");
  const choice = providers.find((p) => p.provider === chosen) ?? providers[0];
  const origins = choice?.baseUrls ?? [];
  const [baseUrl, setBaseUrl] = useState(origins[0] ?? "");
  const [baseUrlTouched, setBaseUrlTouched] = useState(false);
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [change, setChange] = useState<Change>({ state: "idle" });
  const [replacing, setReplacing] = useState(false);
  const [key, setKey] = useState("");
  const outcome = useRef<HTMLDivElement>(null);
  const baseUrlId = useId();
  const baseUrlHintId = useId();
  const baseUrlErrorId = useId();
  const providerName = useId();
  const compatible = chosen === COMPATIBLE;
  const baseUrlValid = !compatible || underOrigin(baseUrl.trim(), origins);

  function choose(provider: string, baseUrls: string[] = []) {
    setChosen(provider);
    setBaseUrl(baseUrls[0] ?? "");
    setBaseUrlTouched(false);
  }

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
    if (!baseUrlValid) {
      setBaseUrlTouched(true);
      return;
    }
    const typed = key.trim();
    // The key leaves the page's state as soon as it is sent, whatever the answer.
    setKey("");
    setChange({ state: "sending" });
    try {
      const value = compatible
        ? await api.enrol(chosen, typed, baseUrl.trim().replace(/\/+$/, ""))
        : await api.enrol(chosen, typed);
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
        You can use your own AI provider account for the AI models Data Director calls for you. Your
        key goes to Data Director’s model broker, which checks it with the provider and keeps it
        encrypted. The rest of Data Director never sees it, and this page shows only its last four
        characters.
      </p>
      <p className="hint">
        An AI model is called with your account only if your provider serves it. Otherwise the
        deployment pays, if it allows that, or the run stops and says why.
      </p>
      <p className="hint">
        Each run records whether your account or the deployment’s paid for each call to a model,
        and never which account it was.
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
              <dt>Provider</dt>
              <dd>{describe(account.provider).name}</dd>
            </div>
            <div>
              <dt>Account</dt>
              <dd>{account.label}</dd>
            </div>
            <div>
              <dt>Added</dt>
              <dd>
                <time dateTime={account.created}>{formatDateTime(account.created)}</time>
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
                    may finish first. Your account with {describe(account.provider).name} is not
                    changed.
                  </p>
                </ModalDialog>
              </DialogTrigger>
            </div>
          )}
        </>
      )}

      {showForm && (
        <form className="model-account-form" noValidate onSubmit={(event) => void enrol(event)}>
          {providers.length > 1 && (
            <fieldset className="field">
              <legend>Provider</legend>
              {providers.map(({ provider, baseUrls }) => (
                <div className="field-check" key={provider}>
                  <input
                    type="radio"
                    id={`${providerName}-${provider}`}
                    name={providerName}
                    value={provider}
                    checked={chosen === provider}
                    onChange={() => choose(provider, baseUrls)}
                  />
                  <label htmlFor={`${providerName}-${provider}`}>{describe(provider).name}</label>
                </div>
              ))}
            </fieldset>
          )}
          {compatible && (
            <div className="field">
              <label htmlFor={baseUrlId}>Address of the service</label>
              <p className="hint" id={baseUrlHintId}>
                The address its software is reached at, such as {origins[0] ?? "https://…"}/v1. It
                must start with {origins.length > 1 ? "one of " : ""}
                {origins.join(", ")}.
              </p>
              <input
                type="url"
                id={baseUrlId}
                aria-describedby={
                  baseUrlTouched && !baseUrlValid
                    ? `${baseUrlHintId} ${baseUrlErrorId}`
                    : baseUrlHintId
                }
                aria-invalid={baseUrlTouched && !baseUrlValid}
                autoComplete="off"
                spellCheck={false}
                required
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                onBlur={() => setBaseUrlTouched(true)}
              />
              {baseUrlTouched && !baseUrlValid && (
                <p className="field-error" id={baseUrlErrorId}>
                  Data Director may send your key only to an address that starts with{" "}
                  {origins.length > 1 ? "one of " : ""}
                  {origins.join(", ")}.
                </p>
              )}
            </div>
          )}
          <KeyField
            provider={chosen}
            offered={providers.map((p) => p.provider)}
            value={key}
            onChange={setKey}
            onSwitch={choose}
          />
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

      {load.state === "loaded" && <ModelAccountUsage usage={usage} />}
    </section>
  );
}
