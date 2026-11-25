/**
 * The approved metadata record converted to another standard, on the Repository tab
 * (docs/specs/metadata-standards.md, invariant 9): a choice of the deployment's other standards,
 * each conversion kept with a link to download it and what it did not carry over or kept less
 * precisely, and, when the target requires what the record lacks, what to add to the record.
 * A conversion is never a document and is not approved in the record's place.
 */

import { useEffect, useState } from "react";

import {
  ConversionRefused,
  type ConvertedRecord,
  type MissingField,
  conversionUrl,
  conversions,
  convertRecord,
} from "../../project/conversions";
import { type StandardChoice, standardChoice } from "../../project/standards";
import { Button } from "../ui/Button";

type Outcome =
  | { state: "idle" }
  | { state: "refused"; detail: string; missing: MissingField[] }
  | { state: "failed"; message: string };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function Losses({ made }: { made: ConvertedRecord }) {
  if (made.unplaced.length === 0 && made.reduced.length === 0) {
    return (
      <p className="muted">
        Every value of the approved record was carried over.
      </p>
    );
  }
  return (
    <>
      {made.unplaced.length > 0 && (
        <>
          <p>Not carried over, as {made.title} has no place for them:</p>
          <ul>
            {made.unplaced.map((path) => (
              <li key={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
        </>
      )}
      {made.reduced.length > 0 && (
        <>
          <p>Kept less precisely:</p>
          <ul>
            {made.reduced.map((r) => (
              <li key={`${r.path} ${r.reason}`}>
                <code>{r.path}</code>: {r.reason}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

export function ConvertRecord({
  projectId,
  revision,
}: {
  projectId: string;
  revision: number;
}) {
  const [standards, setStandards] = useState<StandardChoice["standards"]>([]);
  const [made, setMade] = useState<ConvertedRecord[]>([]);
  const [picked, setPicked] = useState("");
  const [outcome, setOutcome] = useState<Outcome>({ state: "idle" });

  useEffect(() => {
    const controller = new AbortController();
    // The section shows once a repository is chosen; `MetadataStandardChoice` says why not.
    Promise.all([
      standardChoice(projectId, controller.signal),
      conversions(projectId, controller.signal),
    ]).then(
      ([choice, kept]) => {
        // The record is already in the chosen standard; the others are offered.
        const own = choice?.standard?.title;
        setStandards((choice?.standards ?? []).filter((s) => s.title !== own));
        setMade(kept);
      },
      () => setStandards([]),
    );
    return () => controller.abort();
  }, [projectId, revision]);

  if (standards.length === 0) return null;

  const convert = () => {
    setOutcome({ state: "idle" });
    convertRecord(projectId, picked).then(
      (kept) =>
        setMade((earlier) => [
          kept,
          ...earlier.filter((e) => e.digest !== kept.digest),
        ]),
      (error: unknown) =>
        setOutcome(
          error instanceof ConversionRefused
            ? {
                state: "refused",
                detail: error.message,
                missing: error.missing,
              }
            : { state: "failed", message: message(error) },
        ),
    );
  };

  return (
    <section
      className="convert-record"
      aria-labelledby="convert-record-heading"
    >
      <h3 id="convert-record-heading">
        The approved record in another standard
      </h3>
      <p className="hint">
        A copy of the approved metadata record in another standard, for a
        repository that asks for it. Nothing is invented: what the other
        standard has no place for is listed.
      </p>
      <div className="standard-choice">
        <label htmlFor="convert-select">Convert to</label>{" "}
        <select
          id="convert-select"
          value={picked}
          onChange={(e) => setPicked(e.target.value)}
        >
          <option value="">Choose a standard…</option>
          {standards.map((s) => (
            <option key={s.conforms_to} value={s.conforms_to}>
              {s.title}
            </option>
          ))}
        </select>{" "}
        <Button isDisabled={picked === ""} onPress={convert}>
          Convert the approved record
        </Button>
      </div>
      {outcome.state === "refused" && (
        <div role="alert" className="callout status-warn">
          <p>No conversion was kept: {outcome.detail}</p>
          <ul>
            {outcome.missing.map((m) => (
              <li key={m.property}>{m.question}.</li>
            ))}
          </ul>
        </div>
      )}
      {outcome.state === "failed" && (
        <p role="alert" className="callout status-danger">
          The record was not converted: {outcome.message}
        </p>
      )}
      {made.length > 0 && (
        <ul className="conversions" aria-label="Converted records">
          {made.map((c) => (
            <li key={c.digest}>
              <a href={conversionUrl(projectId, c.digest)} download>
                {c.title} record
              </a>{" "}
              <span className="muted">
                converted {new Date(c.made_at).toLocaleString()}
              </span>
              <Losses made={c} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
