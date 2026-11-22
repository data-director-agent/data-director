/**
 * Each FAIR report stored in the project, newest first, as a table of the four counts, so that how
 * the metadata record has improved over the project can be read, and read aloud, row by row.
 */

import { type Assessment, PRINCIPLES, tallyOf } from "../../project/fairness";
import { TableScroll } from "../ui/TableScroll";

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}

export function FairnessHistory({ history }: { history: Assessment[] }) {
  if (history.length < 2) return null;
  return (
    <section aria-labelledby="fair-history-heading" className="fair-history">
      <h3 id="fair-history-heading">Over the project</h3>
      <TableScroll label="Checks met at each check of the metadata record">
        <table>
          <caption className="visually-hidden">
            Checks met of those assessed, newest first
          </caption>
          <thead>
            <tr>
              <th scope="col">Checked</th>
              <th scope="col">Record version</th>
              {PRINCIPLES.map(({ id, name }) => (
                <th key={id} scope="col">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.map(({ envelope, report }) => (
              <tr key={envelope.invocation_id}>
                <th scope="row">{when(envelope.completed_at)}</th>
                <td>
                  {report.assessed_version
                    ? `v${report.assessed_version.version}`
                    : "—"}
                </td>
                {PRINCIPLES.map(({ id }) => {
                  const t = tallyOf(report, id);
                  return (
                    <td key={id}>
                      {t.assessed > 0 ? `${t.met} of ${t.assessed}` : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
    </section>
  );
}
