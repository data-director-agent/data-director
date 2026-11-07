/**
 * The text of a drafted document (the contract's `Document` payload) in a run's result, for a
 * person to read, check and take away (#442).
 *
 * Markdown (`text/markdown`) is rendered (`ui/Markdown`), tables included, so that headings, lists
 * and a data dictionary's rows can be read. Any other media type is shown as
 * it is, with its line breaks kept. Either way the person can copy the text exactly or download
 * it as a file, since what they take away is the text, not the rendering. Whether the document is
 * kept is decided on the project's documents page.
 */

import { Copy, Download } from "lucide-react";
import { useState } from "react";

import { dataUrl, essence, fileName } from "../../../project/media";
import { Button } from "../../ui/Button";
import { Markdown } from "../../ui/Markdown";

export function DocumentText({
  text,
  mediaType,
  title,
  headingId,
}: {
  text: string;
  mediaType: string;
  /** What the document is called, for the heading, the buttons and the file name. */
  title: string;
  headingId: string;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const markdown = essence(mediaType) === "text/markdown";
  const name = fileName(title, mediaType);
  const href = dataUrl(mediaType, text);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(`Copied the text of ${title}.`);
    } catch {
      setCopied("Could not copy; download the file instead.");
    }
  }

  return (
    <section className="document-result" aria-labelledby={headingId}>
      <h4 id={headingId}>{title}</h4>
      <p className="document-actions">
        <Button variant="quiet" size="small" icon={Copy} onPress={() => void copy()}>
          Copy the text
        </Button>{" "}
        <a className="button button-quiet button-small" href={href} download={name}>
          <Download className="button-icon" size="1.125em" aria-hidden="true" />
          Download {name}
        </a>{" "}
        <span role="status">{copied}</span>
      </p>
      {markdown ? (
        <div className="markdown document-body">
          <Markdown>{text}</Markdown>
        </div>
      ) : (
        <pre className="json-view document-body">{text}</pre>
      )}
    </section>
  );
}
