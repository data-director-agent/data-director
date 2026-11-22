/**
 * Ask for changes to a document's latest version in your own words, such as "shorten the Files
 * paragraph" (docs/specs/drafting.md, invariant 12). The server records the request and runs the
 * agent that drafted the document; its revision is the next version, which the person reads and
 * decides on as any other. A revision changes only prose, never a gap, a table or a value a person
 * gave, and a fact the request states counts as given by the person, as the form says.
 *
 * The outcome is said in a status the form keeps: the new version's number, or why the agent drew
 * none, in its own statement. A request the server refused because the document has moved on is
 * passed to `onStale`, as a decision is. It is offered only beneath a README's latest draft:
 * a version that only asks questions is not the document yet, and only a README is revised so
 * (#1469).
 */

import { MessageSquareText } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import {
  DecisionConflict,
  type DocumentVersion,
  type ProjectDocuments,
  digestOf,
  useProjectApi,
} from "../../project/api";
import { Button } from "../ui/Button";

export function RevisionRequest({
  projectId,
  name,
  kind,
  version,
  isLatest,
  maxLength,
  onRevised,
  onStale,
}: {
  projectId: string;
  name: string;
  /** The document's kind: only a README is revised as a person asks. */
  kind: string;
  /** The version shown, which the request names by its digest if it is the latest draft. */
  version: DocumentVersion;
  isLatest: boolean;
  /** The longest request the harness keeps, in characters. */
  maxLength: number;
  /** Called with the project's documents as the server read them back after the run. */
  onRevised: (value: ProjectDocuments) => void;
  onStale: (detail: string) => Promise<void>;
}) {
  const api = useProjectApi();
  const id = useId();
  const [instruction, setInstruction] = useState("");
  const [sending, setSending] = useState(false);
  const [said, setSaid] = useState<{ text: string; drafted: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!isLatest || version.stage !== "draft" || kind !== "readme") return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!instruction.trim()) return;
    setSending(true);
    setError(null);
    setSaid(null);
    try {
      const value = await api.revise(projectId, version.document_id, {
        version: version.version,
        // The text this page showed, as it showed it.
        digest: digestOf(version.text),
        instruction,
      });
      const revised = value.revised;
      const drafted = revised?.version ?? null;
      setSaid(
        drafted
          ? {
              text: `Version ${drafted.version} revises version ${version.version} as you asked. Read it, and compare them in Versions, before you decide on it.`,
              drafted: true,
            }
          : { text: `No new version: ${revised?.statement ?? "the agent drafted none."}`, drafted: false },
      );
      if (drafted) setInstruction("");
      onRevised(value);
    } catch (caught) {
      if (caught instanceof DecisionConflict) await onStale(caught.message);
      else setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="revision-request" onSubmit={(event) => void submit(event)} aria-labelledby={`${id}-legend`}>
      <fieldset className="field">
        <legend id={`${id}-legend`}>Ask for changes</legend>
        <label htmlFor={`${id}-instruction`}>What to change in the {name}</label>
        <p className="hint" id={`${id}-hint`}>
          Say it in your own words, such as “shorten the Files paragraph”. The agent that drafted
          the {name} writes a new version for you to review. It changes only the prose: the gaps
          still to fill, the tables and the values you gave stay as they are. A fact you state here
          counts as given by you, and your request is kept in the project’s record.
        </p>
        <textarea
          id={`${id}-instruction`}
          aria-describedby={`${id}-hint`}
          required
          maxLength={maxLength}
          rows={3}
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
        />
      </fieldset>
      {error && (
        <div role="alert" className="callout status-danger">
          <p>The request was not sent: {error}</p>
        </div>
      )}
      <p role="status" className={said && !said.drafted ? "callout status-warn" : undefined}>
        {sending ? `Asking for a new version of the ${name}…` : (said?.text ?? "")}
      </p>
      <Button type="submit" variant="secondary" icon={MessageSquareText} isDisabled={sending}>
        {sending ? "Revising…" : "Ask for changes"}
      </Button>
    </form>
  );
}
