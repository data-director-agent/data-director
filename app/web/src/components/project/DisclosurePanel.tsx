/**
 * What a project's approved documents owe to generative AI (docs/specs/disclosure.md): which were
 * drafted with a model and reproduced verbatim, which a person revised, which were drafted by
 * rule, and who approved each.
 *
 * The statement is the harness's, shown as it is and offered for download, so that a researcher
 * can cite it in a paper or a deposit. The PROV-O graph is the same account for a machine. The
 * panel reads the disclosure again whenever `revision` changes, that is, after each decision.
 */

import { Download } from "lucide-react";
import { useEffect, useState } from "react";

import { type Disclosure, useProjectApi } from "../../project/api";
import { Markdown } from "../ui/Markdown";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: Disclosure };

const HEADING_ID = "disclosure-heading";

/** The statement without its title, which the panel's own heading gives, one level down. */
export function statementBody(statement: string): string {
  return statement
    .replace(/^# [^\n]*\n+/, "")
    .replace(/^## /gm, "### ");
}

function dataUrl(mediaType: string, text: string): string {
  return `data:${mediaType};charset=utf-8,${encodeURIComponent(text)}`;
}

export function DisclosurePanel({ projectId, revision }: { projectId: string; revision: number }) {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    api.disclosure(projectId, controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setLoad({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      },
    );
    return () => controller.abort();
  }, [api, projectId, revision]);

  const content = () => {
    if (load.state === "loading") return <p>Reading how the documents came about…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read the disclosure: {load.message}</p>
        </div>
      );
    }
    const { statement, prov } = load.value;
    return (
      <>
        <div className="markdown">
          <Markdown>{statementBody(statement)}</Markdown>
        </div>
        <p className="document-actions">
          <a
            className="button button-quiet button-small"
            href={dataUrl("text/markdown", statement)}
            download="use-of-generative-ai.md"
          >
            <Download className="button-icon" size="1.125em" aria-hidden="true" />
            Download the statement
          </a>{" "}
          <a
            className="button button-quiet button-small"
            href={dataUrl("application/ld+json", JSON.stringify(prov, null, 2) + "\n")}
            download="provenance.jsonld"
          >
            <Download className="button-icon" size="1.125em" aria-hidden="true" />
            Download the provenance (PROV-O)
          </a>
        </p>
      </>
    );
  };

  return (
    <section className="disclosure" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Use of generative AI</h2>
      <p className="hint">
        Your institution or publisher may ask you to say how generative AI was used. This
        statement is made from the project&apos;s record: which documents a model drafted, which
        you changed, and who approved each.
      </p>
      {content()}
    </section>
  );
}
