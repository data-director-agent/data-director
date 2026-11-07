/**
 * The project checked against its chosen repository's requirements, and the deposit package built
 * from it (docs/specs/deposit.md).
 *
 * The harness validates and builds; the panel asks it to and draws what it found. Each problem
 * that stops the package and each warning is the harness's message, as it wrote it. The package
 * can be built only after a check the project passed, and is downloaded by its digest from the
 * project log. What a check or a build did is said once, in a live region that is in the panel
 * from the start, so that a screen reader announces it; focus stays on the button pressed.
 *
 * A decision changes the project (`revision`), so a check made before it no longer stands: the
 * panel says so and offers no build until the project is checked again.
 */

import { Download, ListChecks, Package } from "lucide-react";
import { useState } from "react";

import {
  type BuiltPackage,
  PackageRefused,
  type Validation,
  type ValidationResult,
  useProjectApi,
} from "../../project/api";
import { Button } from "../ui/Button";

const HEADING_ID = "deposit-heading";

type Result =
  | { state: "checked"; validation: Validation }
  | { state: "refused"; validation: Validation; detail: string }
  | { state: "built"; built: BuiltPackage };

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** A size in bytes, in words a person reads. */
export function sizeInWords(bytes: number): string {
  if (bytes < 1024) return count(bytes, "byte", "bytes");
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("en-GB", { maximumFractionDigits: 1 })} ${units[unit]}`;
}

/** What a validation found, in one sentence for the live region. */
export function outcome(validation: Validation): string {
  const warnings = validation.warnings.length;
  if (validation.conforms) {
    return warnings === 0
      ? "The project is ready to package."
      : `The project is ready to package, with ${count(warnings, "warning", "warnings")}.`;
  }
  const problems = count(validation.violations.length, "problem", "problems");
  return `${problems} must be fixed before the package can be built.`;
}

function Results({
  id,
  heading,
  results,
}: {
  id: string;
  heading: string;
  results: ValidationResult[];
}) {
  if (results.length === 0) return null;
  return (
    <section aria-labelledby={id}>
      <h3 id={id}>
        {heading} ({results.length})
      </h3>
      <ul>
        {results.map((result, index) => (
          <li key={`${result.component}-${result.focus}-${index}`}>{result.message}</li>
        ))}
      </ul>
    </section>
  );
}

export function DepositPanel({ projectId, revision }: { projectId: string; revision: number }) {
  const api = useProjectApi();
  const [busy, setBusy] = useState<"checking" | "building" | null>(null);
  const [result, setResult] = useState<(Result & { revision: number }) | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [said, setSaid] = useState("");

  const stale = result !== null && result.revision !== revision;
  const shown = stale ? null : result;
  const validation = shown ? (shown.state === "built" ? shown.built : shown.validation) : null;

  const run = async (kind: "checking" | "building") => {
    setBusy(kind);
    setFailed(null);
    try {
      if (kind === "checking") {
        const found = await api.validate(projectId);
        setResult({ state: "checked", validation: found, revision });
        setSaid(outcome(found));
      } else {
        const built = await api.buildPackage(projectId);
        setResult({ state: "built", built, revision });
        setSaid(`The package is built (${sizeInWords(built.package.size)}). Download it below.`);
      }
    } catch (error: unknown) {
      if (error instanceof PackageRefused) {
        setResult({
          state: "refused",
          validation: error.validation,
          detail: error.message,
          revision,
        });
        setSaid(`No package was built. ${outcome(error.validation)}`);
      } else {
        const message = error instanceof Error ? error.message : String(error);
        setFailed(message);
        setSaid("");
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="deposit" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Deposit package</h2>
      <p className="hint">
        Data Director checks the project against what the repository you chose asks for. Once
        nothing stops it, it builds a package to upload: the approved documents, the record of who
        decided what, and how generative AI was used. Your data files are listed in it but not
        included; upload them beside it.
      </p>
      <p className="document-actions">
        <Button
          icon={ListChecks}
          isPending={busy === "checking"}
          isDisabled={busy === "building"}
          onPress={() => void run("checking")}
        >
          {busy === "checking" ? "Checking the project…" : "Check the project"}
        </Button>
      </p>
      <div role="status" className={said && shown ? "callout status-ok" : undefined}>
        {said && shown && <p>{said}</p>}
      </div>
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not check or package the project: {failed}</p>
        </div>
      )}
      {stale && (
        <div className="callout status-warn">
          <p>The project has changed since it was checked. Check it again before packaging.</p>
        </div>
      )}
      {shown?.state === "refused" && (
        <div className="callout status-danger">
          <p>No package was built: the project is not yet valid for deposit.</p>
        </div>
      )}
      {validation && (
        <>
          <Results
            id="deposit-violations"
            heading="Must be fixed before packaging"
            results={validation.violations}
          />
          <Results id="deposit-warnings" heading="Worth fixing" results={validation.warnings} />
        </>
      )}
      {shown?.state === "checked" && shown.validation.conforms && (
        <p className="document-actions">
          <Button
            variant="primary"
            icon={Package}
            isPending={busy === "building"}
            isDisabled={busy === "checking"}
            onPress={() => void run("building")}
          >
            {busy === "building" ? "Building the package…" : "Build the package"}
          </Button>
        </p>
      )}
      {shown?.state === "built" && (
        <>
          <p className="document-actions">
            <a
              className="button button-primary"
              href={shown.built.package.href}
              download={`deposit-package-${shown.built.package.digest.slice(0, 12)}.zip`}
            >
              <Download className="button-icon" size="1.125em" aria-hidden="true" />
              Download the package (zip, {sizeInWords(shown.built.package.size)})
            </a>
          </p>
          <p className="hint">
            SHA-256 <code className="deposit-digest">{shown.built.package.digest}</code>
          </p>
        </>
      )}
    </section>
  );
}
