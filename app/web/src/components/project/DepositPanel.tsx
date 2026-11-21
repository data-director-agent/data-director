/**
 * The project checked against its chosen repository's requirements, and the deposit package built
 * from it (docs/specs/deposit.md).
 *
 * The harness validates and builds; the panel asks it to and draws what it found. Each problem
 * that stops the package and each warning is the harness's message, as it wrote it. The package
 * can be built only after a check the project passed, and is downloaded by its digest from the
 * project log. That a build is running, and what a check or a build did, is said once, in a live
 * region that is in the panel from the start, so that a screen reader announces it. A check leaves
 * focus on the button pressed. A build removes that button, so focus moves to what it left: the
 * built package, or the callout that says why there is none, which scrolls it into view (#1315).
 *
 * A decision changes the project (`revision`), so a check made before it no longer stands: the
 * panel says so and offers no build until the project is checked again.
 *
 * A project with no problem may still wait on a person: each file the check marks, and the checks
 * before deposit, are decided and confirmed in `BeforePackaging`, and the panel says it is ready
 * to package, and offers the build, only once nothing waits (docs/specs/deposit.md, "The pause
 * before packaging"). After each decision it checks the project again.
 *
 * Once a package is built, the panel offers to create a draft in the repository with the person's
 * own account, where the deployment deposits to it (`DepositToRepository`), and says what the
 * researcher does next to deposit by hand. The field labels, the repository's address and what is
 * not yet confirmed come from the chosen repository's requirements, never from this file.
 */

import { ListChecks, Package } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import {
  type BuiltPackage,
  PackageRefused,
  type RepositoryRequirements,
  type Validation,
  type ValidationResult,
  useProjectApi,
} from "../../project/api";
import { Button } from "../ui/Button";
import { formatNumber } from "../../format";
import { BeforePackaging } from "./BeforePackaging";
import { PackageBuilt } from "./PackageBuilt";

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
  return `${formatNumber(value, { maximumFractionDigits: 1 })} ${units[unit]}`;
}

/** What waits on a person before a valid project can be packaged, in one sentence. */
function waiting(validation: Validation): string {
  const open = validation.review?.items.filter((i) => !i.decision).length ?? 0;
  const parts: string[] = [];
  if (open > 0) parts.push(`${count(open, "file waits", "files wait")} for your decision`);
  if (!validation.review?.confirmation) {
    parts.push("the checks before deposit wait for your confirmation");
  }
  const what = parts.length > 0 ? parts.join(", and ") : "a decision waits for you";
  return `Nothing must be fixed, but ${what} before the package can be built.`;
}

/** What a validation found, in one sentence for the live region. */
export function outcome(validation: Validation): string {
  const warnings = validation.warnings.length;
  if (validation.conforms && !validation.ready) return waiting(validation);
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

/** A callout that takes focus when it appears, and so scrolls into view. */
function FocusedCallout({
  role,
  className,
  children,
}: {
  role?: "alert";
  className: string;
  children: ReactNode;
}) {
  const callout = useRef<HTMLDivElement>(null);
  useEffect(() => callout.current?.focus(), []);
  return (
    <div role={role} className={`callout ${className}`} ref={callout} tabIndex={-1}>
      {children}
    </div>
  );
}

// eslint-disable-next-line complexity -- recorded debt: split it, do not add to it (docs/architecture-review.md)
export function DepositPanel({ projectId, revision }: { projectId: string; revision: number }) {
  const api = useProjectApi();
  const [busy, setBusy] = useState<"checking" | "building" | null>(null);
  const [result, setResult] = useState<(Result & { revision: number }) | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const [choice, setChoice] = useState<RepositoryRequirements | null>(null);

  // Read the chosen repository for the steps after a build. Failing to read it leaves the steps
  // general; it does not stop a check or a build.
  useEffect(() => {
    const controller = new AbortController();
    api.repository(projectId, controller.signal).then(
      (value) => setChoice(value),
      () => {
        if (!controller.signal.aborted) setChoice(null);
      },
    );
    return () => controller.abort();
  }, [api, projectId, revision]);

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
        setSaid("Building the package…");
        const built = await api.buildPackage(projectId);
        setResult({ state: "built", built, revision });
        setSaid(
          `The package is built (${sizeInWords(built.package.size)}). Download it, then follow ` +
            "the steps below to deposit.",
        );
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
        nothing stops it, it builds a package: the approved documents, the record of who decided
        what, and how generative AI was used. Your data files are listed in it but not included; you
        upload them to the repository yourself, as the panel says once the package is built.
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
        <FocusedCallout role="alert" className="status-danger">
          <p>Data Director could not check or package the project: {failed}</p>
        </FocusedCallout>
      )}
      {stale && (
        <div className="callout status-warn">
          <p>The project has changed since it was checked. Check it again before packaging.</p>
        </div>
      )}
      {shown?.state === "refused" && (
        <FocusedCallout className="status-danger">
          <p>No package was built: the project is not yet valid for deposit.</p>
        </FocusedCallout>
      )}
      {validation && (
        <>
          <Results
            id="deposit-violations"
            heading="Must be fixed before packaging"
            results={validation.violations}
          />
          <Results id="deposit-warnings" heading="Worth fixing" results={validation.warnings} />
          {validation.review && shown?.state !== "built" && (
            <BeforePackaging
              projectId={projectId}
              review={validation.review}
              onChanged={() => void run("checking")}
            />
          )}
        </>
      )}
      {shown?.state === "checked" && shown.validation.ready && (
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
        <PackageBuilt
          projectId={projectId}
          built={shown.built}
          size={sizeInWords(shown.built.package.size)}
          revision={revision}
          choice={choice}
        />
      )}
    </section>
  );
}
