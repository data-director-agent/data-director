/**
 * What powers an agent, said the same way wherever an agent is shown: a language model (which
 * one, from whom, and whether it runs remotely or locally), or no model at all. All of it is
 * read from the agent's manifest, as configured; a manifest that does not say is shown as not
 * declared, never as deterministic.
 *
 * Where this deployment lets people use their own AI account, the signed-in person also sees the
 * label of their own account (docs/specs/model-accounts.md, What the person sees). The label is
 * read from the model broker with the person's own ticket, so no one else is ever shown it.
 */

import { useEffect, useState } from "react";

import type { AgentView } from "../../manifest/normalise";
import { HOSTING, PROVIDER } from "../../manifest/wording";
import { type AccountLabel, useModelAccountApi } from "../../model-account/api";
import { Link } from "../../route";

type ModelFacts = Pick<AgentView, "models" | "modelsDeclared">;

/** The short form, for a line beside an agent's name. */
export function ModelTag({ agent }: { agent: ModelFacts }) {
  if (!agent.modelsDeclared) {
    return <span className="status status-undeclared">AI model not declared</span>;
  }
  if (agent.models.length === 0) {
    return <span className="status status-ok">No AI model: deterministic</span>;
  }
  return (
    <>
      {agent.models.map((m) => (
        <span
          key={`${m.provider}/${m.model}`}
          className={`status ${m.hosting === "hosted" ? "status-warn" : "status-ok"}`}
        >
          Language model, {HOSTING[m.hosting].label.toLowerCase()}: <code>{m.model}</code>
        </span>
      ))}
    </>
  );
}

/** The full form: each model with its provider and where it runs, or the absence of one. */
export function Models({ agent }: { agent: ModelFacts }) {
  if (!agent.modelsDeclared) {
    return (
      <p>
        <span className="status status-undeclared">Not declared</span> This agent does not say
        whether it uses an AI model.
      </p>
    );
  }
  if (agent.models.length === 0) {
    return (
      <p>
        <strong>No AI model.</strong> This agent is deterministic software: it sends your input to
        no language model.
      </p>
    );
  }
  return (
    <ul>
      {agent.models.map((m) => (
        <li key={`${m.provider}/${m.model}`}>
          <strong>Language model, {HOSTING[m.hosting].label.toLowerCase()}:</strong>{" "}
          {PROVIDER[m.provider] ?? m.provider} <code>{m.model}</code>. As configured, it{" "}
          {HOSTING[m.hosting].explanation}. It is given what you type and the descriptions of your files, never the research data itself.
        </li>
      ))}
    </ul>
  );
}

type Own =
  | { state: "loading" }
  | { state: "loaded"; account: AccountLabel | null }
  | { state: "failed" };

/** The signed-in person's own AI account, for an agent that calls a model. Shown to them alone. */
export function OwnAccount() {
  const api = useModelAccountApi();
  const [own, setOwn] = useState<Own>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    api
      .read(controller.signal)
      .then((value) => setOwn({ state: "loaded", account: value.account }))
      .catch(() => {
        if (!controller.signal.aborted) setOwn({ state: "failed" });
      });
    return () => controller.abort();
  }, [api]);

  if (own.state === "loading") return <p role="status">Reading your AI account…</p>;
  if (own.state === "failed") {
    return (
      <p>
        Your own AI account could not be read. It is on your{" "}
        <Link to="/profile">Profile page</Link>.
      </p>
    );
  }
  if (own.account === null) {
    return (
      <p>
        This deployment lets you use your own AI account for these calls, and you have not added
        one. You can add it on your <Link to="/profile">Profile page</Link>.
      </p>
    );
  }
  return (
    <p>
      <strong>Your AI account:</strong> {own.account.label}. This deployment may use it for these
      calls, and each run records whether it did. Only you see this.
    </p>
  );
}
