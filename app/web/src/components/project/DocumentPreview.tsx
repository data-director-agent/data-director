/**
 * A document's text read by its media type, for a person to check: Markdown rendered, CSV as a
 * table with its first row as the column headings, JSON indented. Any other type, or text that
 * cannot be read as its type says, is shown as it is stored, with a line saying why.
 *
 * A preview is a reading aid. A decision always names the stored text, which the reader's Source
 * tab shows unchanged.
 */

import { CsvError, parseCsv } from "../../project/csv";
import { readingOf } from "../../project/media";
import { Markdown } from "../ui/Markdown";

function Source({ text, note }: { text: string; note?: string }) {
  return (
    <>
      {note && <p className="hint">{note}</p>}
      <pre className="json-view document-text">{text}</pre>
    </>
  );
}

function CsvTable({ rows, caption }: { rows: string[][]; caption: string }) {
  const [head = [], ...body] = rows;
  const width = Math.max(...rows.map((row) => row.length));
  const pad = (row: string[]) => [...row, ...Array<string>(width - row.length).fill("")];
  return (
    <div className="table-scroll document-table">
      <table className="data-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {pad(head).map((cell, i) => (
              <th scope="col" key={i}>
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, r) => (
            <tr key={r}>
              {pad(row).map((cell, i) => (
                <td key={i}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DocumentPreview({
  text,
  mediaType,
  name,
}: {
  text: string;
  mediaType: string;
  /** What the document is called, for a table's caption. */
  name: string;
}) {
  const reading = readingOf(mediaType);
  if (reading === "markdown") {
    return (
      <div className="markdown document-body">
        <Markdown>{text}</Markdown>
      </div>
    );
  }
  if (reading === "csv") {
    let rows: string[][];
    try {
      rows = parseCsv(text);
    } catch (error) {
      if (!(error instanceof CsvError)) throw error;
      return (
        <Source
          text={text}
          note={`Shown as stored: it could not be read as CSV (${error.message}).`}
        />
      );
    }
    if (rows.length === 0) return <Source text={text} note="The table is empty." />;
    return <CsvTable rows={rows} caption={name} />;
  }
  if (reading === "json") {
    let value: unknown;
    try {
      value = JSON.parse(text);
    } catch {
      return <Source text={text} note="Shown as stored: it could not be read as JSON." />;
    }
    return <Source text={JSON.stringify(value, null, 2)} />;
  }
  return <Source text={text} />;
}
