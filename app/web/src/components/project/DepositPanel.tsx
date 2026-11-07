/**
 * Checking a project for deposit and building its package (docs/specs/deposit.md, #623).
 *
 * The harness validates the project against the requirements of the repository chosen for it,
 * keeps the SHACL report, and builds the package only from a report with no violation. The panel
 * draws what the server answers, each problem in the harness's own words, violations first and
 * then warnings, and offers the package for download by its digest once it is built. It decides
 * nothing: the build button is offered after a check with no violation, and a build the harness
 * refuses shows the validation it refused with.
 *
 * What each press did is said once in the panel's live region; a failure to reach the server is
 * an alert that takes focus.
 */

import { Download, ListChecks, Package } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  type BuiltPackage,
  PackageRefused,
  type Validation,
  type ValidationResult,
  packageHref,
  useProjectApi,
} from "../../project/api";
import { Link } from "../../route";
import { Button } from "../ui/Button";

const HEADING_ID = "deposit-heading";

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Results({ heading, results }: { heading: string; results: ValidationResult[] }) {
  if (results.length === 0) return null;
  return (
    <>
      <h3>{heading}</h3>
      <ul>
        {results.map((r, i) => (
          <li key={`${r.focus}-${r.path ?? ""}-${i}`}>{r.message}</li>
        ))}
      </ul>
    </>
  );
}

/** What a validation comes to, in one sentence for the live region. */
function summary(validation: Validation): string {
  const warnings = plural(validation.warnings.length, "warning", "warnings");
  if (validation.conforms) return `The project is ready to deposit, with ${warnings}.`;
  return `${plural(validation.violations.length, "problem stops", "problems stop")} the package being built, and there ${validation.warnings.length === 1 ? "is" : "are"} ${warnings}.`;
}

export function DepositPanel({ projectId }: { projectId: string }) {
  const api = useProjectApi();
  const [validation, setValidation] = useState<Validation | null>(null);
  const [built, setBuilt] = useState<BuiltPackage | null>(null);
  const [sending, setSending] = useState<"check" | "build" | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  async function check() {
    setSending("check");
    setError(null);
    setBuilt(null);
    try {
      const found = await api.validate(projectId);
      setValidation(found);
      setSaid(summary(found));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSending(null);
    }
  }

  async function build() {
    setSending("build");
    setError(null);
    try {
      const found = await api.buildPackage(projectId);
      setBuilt(found);
      setValidation(found.validation);
      setSaid(`The deposit package is built (${size(found.size)}). Download it below.`);
    } catch (caught) {
      if (caught instanceof PackageRefused) {
        setValidation(caught.validation);
        setSaid(`No package was built. ${summary(caught.validation)}`);
      } else {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      setSending(null);
    }
  }

  return (
    <section className="deposit" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Deposit package</h2>
      <p className="hint">
        Data Director checks the project against what the{" "}
        <Link to={`/projects/${encodeURIComponent(projectId)}?doc=repository`}>chosen repository</Link>{" "}
        asks for. Once nothing stops it, it builds a package of the approved documents, their
        record and the project&apos;s audit trail. The package holds no data files: you add them
        when you deposit.
      </p>
      <p className="document-actions">
        <Button icon={ListChecks} isDisabled={sending !== null} onPress={() => void check()}>
          {sending === "check" ? "Checking…" : "Check the project"}
        </Button>{" "}
        {validation?.conforms && !built && (
          <Button
            variant="primary"
            icon={Package}
            isDisabled={sending !== null}
            onPress={() => void build()}
          >
            {sending === "build" ? "Building…" : "Build the package"}
          </Button>
        )}
      </p>
      {error && (
        <div role="alert" className="callout status-danger" ref={errorRef} tabIndex={-1}>
          <p>Data Director could not do this: {error}</p>
        </div>
      )}
      <div role="status" className={said ? `callout status-${validation?.conforms ? "ok" : "warn"}` : undefined}>
        {said && <p>{said}</p>}
      </div>
      {built && (
        <p>
          <a
            className="button button-primary"
            href={packageHref(projectId, built.digest)}
            download
          >
            <Download className="button-icon" size="1.125em" aria-hidden="true" />
            Download the deposit package
          </a>{" "}
          <span className="muted">
            SHA-256 <code>{built.digest}</code>
          </span>
        </p>
      )}
      {validation && (
        <>
          <Results heading="What stops the package" results={validation.violations} />
          <Results heading="What the repository recommends" results={validation.warnings} />
        </>
      )}
    </section>
  );
}
