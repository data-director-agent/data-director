/** The tokens used for a person in the last 30 days, in the Profile page's AI account section. */

import type { ModelAccount as Account } from "../../model-account/api";
import { formatNumber } from "../../format";
import { TableScroll } from "../ui/TableScroll";
import { describe } from "./modelProviders";

export function ModelAccountUsage({ usage }: { usage: Account["usage"] }) {
  return (
    <>
      <h3>Your token use</h3>
      {usage.length === 0 ? (
        <p>No model calls have been made for you in the last 30 days.</p>
      ) : (
        <TableScroll label="Your token use">
          <table className="data-table">
            <caption className="visually-hidden">Tokens used for you in the last 30 days</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Provider</th>
                <th scope="col">Model</th>
                <th scope="col">Paid by</th>
                <th scope="col" className="num">
                  Input tokens
                </th>
                <th scope="col" className="num">
                  Output tokens
                </th>
              </tr>
            </thead>
            <tbody>
              {usage.map((row) => (
                <tr key={`${row.day} ${row.payer} ${row.provider} ${row.model}`}>
                  <td>
                    <time dateTime={row.day}>{row.day}</time>
                  </td>
                  <td>{describe(row.provider).name}</td>
                  <td>{row.model}</td>
                  <td>{row.payer === "own" ? "Your account" : "The deployment"}</td>
                  <td className="num">{formatNumber(row.inputTokens)}</td>
                  <td className="num">{formatNumber(row.outputTokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}
    </>
  );
}
