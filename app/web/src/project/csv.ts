/**
 * Reads CSV text into rows of fields (RFC 4180), so that a drafted data dictionary can be shown
 * as a table. A field may be quoted, and a quoted field may hold commas, line breaks and doubled
 * quotes. Rows end with LF or CRLF; a final line break adds no empty row.
 */

export class CsvError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CsvError";
  }
}

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  let i = 0;

  const endField = () => {
    row.push(field);
    field = "";
  };
  const endRow = () => {
    endField();
    rows.push(row);
    row = [];
  };

  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        quoted = false;
        i += 1;
        const next = text[i];
        if (next !== undefined && next !== "," && next !== "\n" && next !== "\r") {
          throw new CsvError(`a quoted field is followed by "${next}" rather than a comma`);
        }
        continue;
      }
      field += c;
      i += 1;
      continue;
    }
    if (c === '"' && field === "") {
      quoted = true;
    } else if (c === ",") {
      endField();
    } else if (c === "\n") {
      endRow();
    } else if (c === "\r" && text[i + 1] === "\n") {
      endRow();
      i += 1;
    } else {
      field += c;
    }
    i += 1;
  }
  if (quoted) throw new CsvError("a quoted field is not closed");
  if (field !== "" || row.length > 0) endRow();
  return rows;
}
