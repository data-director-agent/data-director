/**
 * The check a supporting document goes through before it is attached. Whether it was chosen
 * with the Attach button or dropped on the form, the researcher sees its text and what will
 * become of it, and attaches it only by pressing **Attach this document**. Until then nothing is
 * attached, so nothing can be sent or recorded; closing the dialog any other way discards it.
 * That documentation goes to a hosted model only where the deployment allows it is the Projects
 * spec's rule, stated here so that the researcher knows it when deciding; the dialog holds no
 * policy.
 *
 * The server checks the text for possible personal data and secrets (#473). What it finds is
 * named by kind, never quoted; to attach the document anyway, the researcher ticks that they have
 * checked it, the button reads **Attach anyway**, and the turn says which kinds they confirmed.
 * The server holds back a document sent without that, so this dialog is not the only guard.
 * What the check finds is shown below the text, beside the buttons, so that its answer arriving
 * moves nothing the researcher is reading or about to press (#1328).
 *
 * A message carries one document, so where one is already attached the dialog says, before the
 * researcher decides, that attaching this one replaces it (#1170).
 *
 * Which agents read its text is said here, from what each agent's card declares
 * (`documentReaders`), and so are the agents that do not, so that nobody attaches a policy
 * believing an agent that reads only web addresses will use it (#1326).
 */

import "./DocumentReviewDialog.css";

import { Check } from "lucide-react";
import { useEffect, useId, useState } from "react";

import {
  type AttachedDocument,
  checkDocument,
  DOCUMENT_GUIDE,
  type DocumentCheck,
  type DocumentReader,
  type DocumentReaders,
  describeSize,
  findingWords,
} from "../../conversation/documentation";
import { ReviewDialog } from "../ui/ReviewDialog";

/** "A, B and C". */
function listed(names: readonly string[]): string {
  return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

/** `text` with its first letter capitalised, to start a sentence. */
function opening(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Which agents read the document's text and for what, and which are told only of it. */
function whoReads(readers: readonly DocumentReader[], others: readonly string[]): string {
  const told = "told only its name, type and size, and cannot use its text";
  if (readers.length === 0) return `No agent in this deployment reads its text: each is ${told}.`;
  const reading = listed(readers.map((r, i) => `${r.name} reads ${i === 0 ? "its text" : "it"} ${r.readsAttached}`));
  if (others.length === 0) return `${opening(reading)}.`;
  return `${opening(reading)}. ${opening(listed(others))} ${others.length === 1 ? "is" : "are"} ${told}.`;
}

type Checked = { state: "checking" } | { state: "failed"; why: string } | ({ state: "done" } & DocumentCheck);

/** The server's check of `pending`, run again whenever another document is chosen. A result is
 * kept with the document it is for, so a newly chosen document reads as being checked. */
function useCheck(pending: AttachedDocument | null, check: typeof checkDocument): Checked {
  const [result, setResult] = useState<{ of: AttachedDocument; checked: Checked } | null>(null);
  useEffect(() => {
    if (!pending) return;
    const abort = new AbortController();
    check(pending, abort.signal).then(
      (found) => setResult({ of: pending, checked: { state: "done", ...found } }),
      (e: unknown) => {
        if (abort.signal.aborted) return;
        const why = e instanceof Error ? e.message : String(e);
        setResult({ of: pending, checked: { state: "failed", why } });
      },
    );
    return () => abort.abort();
  }, [pending, check]);
  return result && result.of === pending ? result.checked : { state: "checking" };
}

export function DocumentReviewDialog({
  pending,
  replaces,
  onAttach,
  onDiscard,
  readers = { readers: [], others: [] },
  check = checkDocument,
}: {
  /** The document read from the file, not yet attached; null when there is none to check. */
  pending: AttachedDocument | null;
  /** The name of the document already on the message, which attaching this one replaces. */
  replaces?: string | undefined;
  onAttach: (attached: AttachedDocument) => void;
  onDiscard: () => void;
  /** The agents that read its text and the other agents, by name (`documentReaders`). */
  readers?: DocumentReaders;
  /** How the text is checked; the server's check unless a test gives another. */
  check?: typeof checkDocument;
}) {
  const checked = useCheck(pending, check);
  // Ticked for one document only: choosing another leaves the box unticked.
  const [confirmedFor, setConfirmedFor] = useState<AttachedDocument | null>(null);
  const confirmed = pending !== null && confirmedFor === pending;
  const confirmId = useId();
  const found = checked.state === "done" && checked.kinds.length > 0;
  const ready = checked.state !== "checking" && (!found || confirmed);
  return (
    <ReviewDialog
      title="Check the document before attaching it"
      isOpen={pending !== null}
      onDiscard={onDiscard}
      attach={{
        label: found ? "Attach anyway" : "Attach this document",
        icon: Check,
        isDisabled: !ready,
        onPress: () => pending && onAttach(found ? { ...pending, confirmed: checked.kinds } : pending),
      }}
    >
      {pending && (
        <>
          <div className="callout">
            {replaces && (
              <p>
                <strong>Attaching it replaces {replaces}</strong>, which is attached now: a message
                carries one document. Cancel to keep {replaces}.
              </p>
            )}
            {pending.data && (
              <p>
                Data Director read this text from the{" "}
                {pending.media_type === "application/pdf" ? "PDF" : "Word document"} inside this
                deployment. The project keeps the file beside the text, and agents are given the
                text.
              </p>
            )}
            <p>
              <strong>{pending.name}</strong> ({describeSize(pending.size)}) will be stored in the
              project, where anyone working on the project can read it.{" "}
              {whoReads(readers.readers, readers.others)} Its text goes to an AI model hosted
              outside your institution only if this deployment allows that.
            </p>
            <p>
              Attach documents <em>about</em> your data, such as a protocol or a codebook, never
              the data themselves, and nothing that identifies a person.{" "}
              <a href={DOCUMENT_GUIDE}>What to attach</a>
            </p>
          </div>
          <h3 className="document-review-heading">What it says</h3>
          {/* Scrollable, so it must be reachable by keyboard. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <pre className="document-review-text" tabIndex={0} aria-label={`The text of ${pending.name}`}>
            {pending.text}
          </pre>
          <section aria-labelledby={`${confirmId}-heading`} className="document-review-check">
            <h3 id={`${confirmId}-heading`} className="document-review-heading">
              Possible personal data or secrets
            </h3>
            {checked.state === "checking" && <p role="status">Checking the text…</p>}
            {checked.state === "failed" && (
              <p role="alert">
                The text could not be checked ({checked.why}). Data Director checks it again when
                you send the message.
              </p>
            )}
            {checked.state === "done" && !found && (
              <p>
                Nothing was found. That does not mean there is nothing: names and places are not
                looked for in text, and a check by pattern misses what it does not know.
              </p>
            )}
            {checked.state === "done" && found && (
              <>
                <p>
                  The text may hold what is listed here. Remove it from the file and choose the
                  file again, or attach it anyway if it should be kept, such as a public contact
                  address. The values are not shown here or kept anywhere else.
                </p>
                <ul>
                  {checked.findings.map((f) => (
                    <li key={`${f.kind}:${f.detail ?? ""}`}>{findingWords(f)}</li>
                  ))}
                </ul>
                <p className="document-review-confirm">
                  <input
                    id={`${confirmId}-confirm`}
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmedFor(e.currentTarget.checked ? pending : null)}
                  />{" "}
                  <label htmlFor={`${confirmId}-confirm`}>
                    I have checked the document, and it should be attached with what is listed.
                  </label>
                </p>
              </>
            )}
          </section>
        </>
      )}
    </ReviewDialog>
  );
}
