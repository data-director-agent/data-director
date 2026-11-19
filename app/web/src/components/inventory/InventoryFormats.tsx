import { formatBytes, pronomUrl, type FormatGroup } from "@data-director/inventory";
import { TableScroll } from "../ui/TableScroll";

/** The formats found in an inventory, with how many files and how many bytes each holds. */
export function Formats({ formats }: { formats: readonly FormatGroup[] }) {
  if (formats.length === 0) return null;
  return (
    <section aria-labelledby="inventory-formats">
      <h3 id="inventory-formats">Formats</h3>
      <TableScroll label="Formats in the inventory">
        <table className="data-table">
          <caption className="visually-hidden">Formats in the inventory</caption>
          <thead>
            <tr>
              <th scope="col">Media type</th>
              <th scope="col">PRONOM</th>
              <th scope="col" className="num">
                Files
              </th>
              <th scope="col" className="num">
                Size
              </th>
            </tr>
          </thead>
          <tbody>
            {formats.map((format) => (
              <tr key={format.mediaType ?? ""}>
                <td>{format.mediaType ? <code>{format.mediaType}</code> : "Not known"}</td>
                <td>
                  <Puids ids={format.pronomIds} />
                </td>
                <td className="num">{format.fileCount}</td>
                <td className="num">{formatBytes(format.bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
    </section>
  );
}

function Puids({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span className="muted">None</span>;
  return (
    <>
      {ids.map((id, index) => (
        <span key={id}>
          {index > 0 && ", "}
          <a href={pronomUrl(id)}>{id}</a>
        </span>
      ))}
    </>
  );
}
