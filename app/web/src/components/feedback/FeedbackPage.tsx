/**
 * Report a problem or ask for a feature. The server files a GitHub issue (ADR-0030).
 *
 * The page says that the issue is public, and shows exactly what will be sent beside the form:
 * the words typed, the build's version and commit, and, if the reporter agrees, the identifiers
 * of the run and conversation they came from. A run's inputs and results are never sent.
 */

import "./FeedbackPage.css";

import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type About,
  type FeedbackKind,
  type FiledIssue,
  type Report,
  describeBuild,
  useFeedbackApi,
} from "../../feedback/api";
import { Button } from "../ui/Button";
import { ISSUES } from "../NotBuilt";
import { PageHeader } from "../frame/PageHeader";

const KINDS: { value: FeedbackKind; label: string }[] = [
  { value: "bug", label: "Something is wrong" },
  { value: "feature", label: "I would like a feature" },
  { value: "other", label: "Something else" },
];

type Load = { state: "loading" } | { state: "failed" } | { state: "loaded"; about: About };
type Send =
  | { state: "idle" }
  | { state: "sending" }
  | { state: "failed"; message: string }
  | { state: "filed"; issue: FiledIssue };

/** Where the reporter came from, read from the address: `?from=/agents&run=…&conversation=…`. */
export function FeedbackPage({ query }: { query: string }) {
  const api = useFeedbackApi();
  const params = new URLSearchParams(query);
  const page = params.get("from") ?? undefined;
  const run = params.get("run") ?? undefined;
  const conversation = params.get("conversation") ?? undefined;
  const hasContext = Boolean(run ?? conversation);

  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [send, setSend] = useState<Send>({ state: "idle" });
  const [kind, setKind] = useState<FeedbackKind>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [includeContext, setIncludeContext] = useState(false);
  const outcome = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.about(controller.signal).then(
      (about) => setLoad({ state: "loaded", about }),
      () => {
        if (!controller.signal.aborted) setLoad({ state: "failed" });
      },
    );
    return () => controller.abort();
  }, [api]);

  useEffect(() => {
    if (send.state === "filed" || send.state === "failed") outcome.current?.focus();
  }, [send.state]);

  const report: Report = {
    kind,
    title,
    description,
    include_context: includeContext && hasContext,
    ...(page ? { page } : {}),
    ...(run ? { run } : {}),
    ...(conversation ? { conversation } : {}),
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSend({ state: "sending" });
    try {
      setSend({ state: "filed", issue: await api.send(report) });
    } catch (error) {
      setSend({
        state: "failed",
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const about = load.state === "loaded" ? load.about : null;
  const disabled = load.state === "loaded" && !load.about.feedback_enabled;

  if (send.state === "filed") {
    return (
      <>
        <PageHeader title="Report a problem" />
        <div role="status" className="callout status-ok" ref={outcome} tabIndex={-1}>
          <p>
            Thank you. Your report is{" "}
            <a href={send.issue.url} target="_blank" rel="noreferrer">
              issue #{send.issue.number} on GitHub
            </a>
            , where you can follow it.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Report a problem or ask for a feature">
        <p className="hint">
          {about ? `This is Data Director ${describeBuild(about)}.` : "Finding the version…"}
        </p>
      </PageHeader>
      {load.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not say whether reports can be filed from here.</p>
        </div>
      )}
      {disabled && (
        <div role="status" className="callout status-warn">
          <p>
            Reports cannot be filed from this deployment. You can{" "}
            <a href={`${ISSUES}new/choose`} target="_blank" rel="noreferrer">
              open an issue on GitHub
            </a>{" "}
            and mention the version above.
          </p>
        </div>
      )}
      <div className="feedback-layout">
        <form className="feedback-form" onSubmit={submit}>
          <fieldset className="field">
            <legend>What is this about?</legend>
            {KINDS.map(({ value, label }) => (
              <div className="field-check" key={value}>
                <input
                  type="radio"
                  id={`feedback-kind-${value}`}
                  name="kind"
                  value={value}
                  checked={kind === value}
                  onChange={() => setKind(value)}
                />
                <label htmlFor={`feedback-kind-${value}`}>{label}</label>
              </div>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor="feedback-title">Title</label>
            <p className="hint" id="feedback-title-hint">
              One line that says what happened or what you would like.
            </p>
            <input
              type="text"
              id="feedback-title"
              aria-describedby="feedback-title-hint"
              required
              maxLength={120}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="feedback-description">Details</label>
            <p className="hint" id="feedback-description-hint">
              What you did, what you expected and what happened instead.
            </p>
            <textarea
              id="feedback-description"
              aria-describedby="feedback-description-hint"
              required
              rows={8}
              maxLength={5000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          {hasContext && (
            <div className="field field-check">
              <input
                type="checkbox"
                id="feedback-context"
                checked={includeContext}
                onChange={(event) => setIncludeContext(event.target.checked)}
              />
              <label htmlFor="feedback-context">
                Include the identifiers of the run and conversation I came from
              </label>
            </div>
          )}
          <p className="hint">
            The report becomes a public issue on GitHub. Do not include personal or confidential
            information.
          </p>
          {send.state === "failed" && (
            <div role="alert" className="callout status-danger" ref={outcome} tabIndex={-1}>
              <p>The report was not filed: {send.message}</p>
            </div>
          )}
          <Button
            type="submit"
            variant="primary"
            isDisabled={disabled || load.state !== "loaded" || send.state === "sending"}
          >
            {send.state === "sending" ? "Sending…" : "Send report"}
          </Button>
        </form>
        <aside className="feedback-preview" aria-labelledby="feedback-preview-heading">
          <h2 id="feedback-preview-heading">What will be sent</h2>
          <dl className="facts">
            <dt>Kind</dt>
            <dd>{KINDS.find((k) => k.value === kind)?.label}</dd>
            <dt>Version</dt>
            <dd>{about ? describeBuild(about) : "…"}</dd>
            {about?.harness_version && (
              <>
                <dt>Harness</dt>
                <dd>v{about.harness_version}</dd>
              </>
            )}
            {page && (
              <>
                <dt>Page</dt>
                <dd>
                  <code>{page}</code>
                </dd>
              </>
            )}
            {report.include_context && run && (
              <>
                <dt>Run</dt>
                <dd>
                  <code>{run}</code>
                </dd>
              </>
            )}
            {report.include_context && conversation && (
              <>
                <dt>Conversation</dt>
                <dd>
                  <code>{conversation}</code>
                </dd>
              </>
            )}
          </dl>
        </aside>
      </div>
    </>
  );
}
