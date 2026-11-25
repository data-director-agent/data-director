/**
 * The metadata standard a project's record is drafted and checked in, on the Repository tab
 * (docs/specs/deposit.md, invariant 5): which standard, why it is that one, a warning when it was
 * assumed, and, unless the deployment's settings for the repository name the standard, a choice
 * of another the deployment has a set for. A choice is recorded as a new choice of the repository,
 * and choosing the repository again goes back to the rule. `onChosen` lets the panel read the
 * requirements the choice resolved to.
 */

import { useEffect, useState } from "react";

import {
  type StandardChoice,
  chooseStandard,
  reasonInWords,
  standardChoice,
} from "../../project/standards";
import { Button } from "../ui/Button";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: StandardChoice | null };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function MetadataStandardChoice({
  projectId,
  revision,
  onChosen,
}: {
  projectId: string;
  revision: number;
  onChosen: () => void;
}) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [picked, setPicked] = useState("");
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    standardChoice(projectId, controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (!controller.signal.aborted)
          setLoad({ state: "failed", message: message(error) });
      },
    );
    return () => controller.abort();
  }, [projectId, revision]);

  if (
    load.state === "loading" ||
    (load.state === "loaded" && load.value === null)
  )
    return null;
  if (load.state === "failed") {
    return (
      <p role="alert" className="callout status-danger">
        Data Director could not read the metadata standard: {load.message}
      </p>
    );
  }
  const choice = load.value as StandardChoice;
  const current = choice.standard;
  const others = choice.standards.filter((s) => s.title !== current?.title);

  const choose = () => {
    setRefused(null);
    chooseStandard(projectId, picked).then(
      (value) => {
        setLoad({ state: "loaded", value });
        setPicked("");
        onChosen();
      },
      (error: unknown) => setRefused(message(error)),
    );
  };

  return (
    <section
      className="metadata-standard"
      aria-labelledby="metadata-standard-heading"
    >
      <h3 id="metadata-standard-heading">Metadata standard</h3>
      {current ? (
        <p
          className={
            current.reason === "fallback" ? "callout status-warn" : undefined
          }
        >
          The metadata record is drafted and checked in{" "}
          <strong>{current.title}</strong>: {reasonInWords(current)}.
        </p>
      ) : (
        <p className="muted">
          This choice was recorded before Data Director said why it uses its
          standard.
        </p>
      )}
      {choice.may_choose && others.length > 0 && (
        <div className="standard-choice">
          <label htmlFor="standard-select">
            Draft the record in another standard
          </label>{" "}
          <select
            id="standard-select"
            value={picked}
            onChange={(e) => setPicked(e.target.value)}
          >
            <option value="">Choose a standard…</option>
            {others.map((s) => (
              <option key={s.conforms_to} value={s.conforms_to}>
                {s.title}
              </option>
            ))}
          </select>{" "}
          <Button isDisabled={picked === ""} onPress={choose}>
            Use this standard
          </Button>
        </div>
      )}
      {refused && (
        <p role="alert" className="callout status-danger">
          The standard was not changed: {refused}
        </p>
      )}
    </section>
  );
}
