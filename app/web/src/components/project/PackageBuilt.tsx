/**
 * A built deposit package: the link to download it, its digest, the offer to create a draft in the
 * repository and what the researcher does next (docs/specs/deposit.md).
 *
 * It takes focus when it appears, and so scrolls into view. Building removes the button that was
 * pressed and the decisions above it, so without that the page would jump and leave the result
 * above the fold with nothing focused, which reads as nothing having happened (#1315).
 */

import { Download } from "lucide-react";
import { useEffect, useRef } from "react";

import type { BuiltPackage, RepositoryRequirements } from "../../project/api";
import { DepositToRepository } from "./DepositToRepository";
import { Unconfirmed } from "./Unconfirmed";

const BUILT_ID = "deposit-built";
const NEXT_ID = "deposit-next";

/** The user guide's page on depositing by hand. */
export const DEPOSIT_GUIDE =
  "https://data-director-agent.github.io/data-director/user-guide/depositing/";

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
      <Unconfirmed items={unconfirmed} name={name} />
      <p>
        <a href={DEPOSIT_GUIDE}>Depositing your data, step by step, in the user guide</a>
      </p>
    </section>
  );
}

/** The built package, which takes focus when it appears. `size` is its size in words. */
export function PackageBuilt({
  projectId,
  built,
  size,
  revision,
  choice,
}: {
  projectId: string;
  built: BuiltPackage;
  size: string;
  revision: number;
  choice: RepositoryRequirements | null;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const { digest, href } = built.package;
  return (
    <section className="deposit-built" aria-labelledby={BUILT_ID}>
      <h3 id={BUILT_ID} ref={heading} tabIndex={-1}>
        The package is built
      </h3>
      <p className="document-actions">
        <a
          className="button button-primary"
          href={href}
          download={`deposit-package-${digest.slice(0, 12)}.zip`}
        >
          <Download className="button-icon" size="1.125em" aria-hidden="true" />
          Download the package (zip, {size})
        </a>
      </p>
      <p className="hint">
        SHA-256 <code className="deposit-digest">{digest}</code>
      </p>
      <DepositToRepository projectId={projectId} digest={digest} revision={revision} />
      <NextSteps choice={choice} />
    </section>
  );
}
