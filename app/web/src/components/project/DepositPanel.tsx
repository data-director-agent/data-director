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
 *
 * Once a package is built, the panel says what the researcher does next to deposit by hand, since
 * Data Director does not deposit (TODO(#383)). The field labels, the repository's address and what
 * is not yet confirmed come from the chosen repository's requirements, never from this file.
 */

import { Download, ListChecks, Package } from "lucide-react";
import { useEffect, useState } from "react";

import {
  type BuiltPackage,
  PackageRefused,
  type RepositoryRequirements,
  type Validation,
  type ValidationResult,
  useProjectApi,
} from "../../project/api";
import { Button } from "../ui/Button";

const HEADING_ID = "deposit-heading";
const NEXT_ID = "deposit-next";

/** The user guide's page on depositing by hand. */
export const DEPOSIT_GUIDE =
  "https://data-director-agent.github.io/data-director/user-guide/depositing/";

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

function FieldLabels({
  choice,
  obligation,
}: {
  choice: RepositoryRequirements;
  obligation: string;
}) {
  const labels = choice.fields
    .filter((f) => f.obligation === obligation && f.form_label)
    .map((f) => f.form_label as string);
  const unique = [...new Set(labels)];
  if (unique.length === 0) return null;
  return (
    <ul
      aria-label={obligation === "required" ? "Fields the form requires" : "Fields worth filling"}
    >
      {unique.map((label) => (
        <li key={label}>{label}</li>
      ))}
    </ul>
  );
}

/** What to do with a built package, for the chosen repository where it is known. */
export function NextSteps({ choice }: { choice: RepositoryRequirements | null }) {
  const name = choice?.repository_name ?? "the repository you chose";
  const where = choice
    ? (choice.repository_url ??
      `https://www.re3data.org/repository/${encodeURIComponent(choice.re3data_id)}`)
    : null;
  const labelled = choice?.fields.some((f) => f.form_label) ?? false;
  const unlabelled = [
    ...new Set(choice?.fields.filter((f) => !f.form_label).map((f) => f.property) ?? []),
  ];
  const unconfirmed = choice?.unconfirmed ?? [];
  return (
    <section className="deposit-next" aria-labelledby={NEXT_ID}>
      <h3 id={NEXT_ID}>What to do next</h3>
      <p>
        Data Director does not deposit, register a DOI or release an embargo. You do, in {name}:
      </p>
      <ol>
        <li>Create a new item in {where ? <a href={where}>{name}</a> : name}.</li>
        <li>
          Enter the metadata from the approved metadata record, copying each value into the
          repository&apos;s form.
          {labelled && choice && (
            <>
              {" "}
              The form&apos;s fields that the record fills are:
              <FieldLabels choice={choice} obligation="required" />
              and, if the record has them:
              <FieldLabels choice={choice} obligation="recommended" />
              {unlabelled.length > 0 && (
                <p className="hint">
                  The repository&apos;s profile names no form field for{" "}
                  {unlabelled.map((property, i) => (
                    <span key={property}>
                      {i > 0 && ", "}
                      <code>{property}</code>
                    </span>
                  ))}
                  ; put these where the form allows, or leave them in the record.
                </p>
              )}
            </>
          )}
        </li>
        <li>
          Attach your data files. The package lists each one with its SHA-256 digest, so you can
          show the files you upload are the files described.
        </li>
        <li>
          Keep the package with the project. It is the audit and metadata bundle: the approved
          documents, the record of who decided what, and how generative AI was used. The repository
          does not read it, though you may attach it to the item.
        </li>
        <li>Review the item and publish it from the repository.</li>
      </ol>
      {unconfirmed.length > 0 && (
        <div className="callout status-warn">
          <p>
            <strong>Not yet confirmed for {name}:</strong>
          </p>
          <ul>
            {unconfirmed.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <p>
        <a href={DEPOSIT_GUIDE}>Depositing your data, step by step, in the user guide</a>
      </p>
    </section>
  );
}

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
          <NextSteps choice={choice} />
        </>
      )}
    </section>
  );
}
