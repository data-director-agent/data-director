/**
 * The box a drafter's question is answered in (`DocumentQuestionField`): a text area, and for a
 * question answered with a list of values (`answer_kind` `list`) one value on each line, a
 * "no value means missing" choice, what will be recorded, and a warning when a line reads like
 * several values or a note (`listAnswer`).
 */

import { type DocumentQuestion } from "../../project/api";
import { NO_VALUES, isList, listAnswer, listWarnings } from "../../project/listAnswer";
import { charactersIn } from "../../conversation/question";

/** The length of the answer a box's text records, which the harness limits. */
export function answerLength(q: DocumentQuestion, value: string): number {
  return charactersIn(isList(q) ? listAnswer(value.trim()) : value.trim());
}

/** The identifiers of what describes a list box beyond its question's target, for `aria-describedby`. */
export function listDescriptions(id: string, q: DocumentQuestion, value: string): string[] {
  if (!isList(q)) return [];
  return [`${id}-preview`, ...(listWarnings(value).length > 0 ? [`${id}-warnings`] : [])];
}

export function AnswerBox({
  id,
  question: q,
  value,
  describedBy,
  invalid,
  onChange,
}: {
  id: string;
  question: DocumentQuestion;
  value: string;
  describedBy: string;
  invalid: boolean;
  onChange: (text: string) => void;
}) {
  const list = isList(q);
  const none = list && value.trim() === NO_VALUES;
  const recorded = list ? listAnswer(value.trim()) : "";
  const warnings = list ? listWarnings(value) : [];
  return (
    <>
      <textarea
        id={id}
        aria-describedby={describedBy}
        {...(invalid ? { "aria-invalid": true } : {})}
        rows={list ? 4 : 2}
        value={none ? "" : value}
        disabled={none}
        onChange={(e) => onChange(e.target.value)}
      />
      {list && (
        <>
          <div className="field-check">
            <input
              type="checkbox"
              id={`${id}-none`}
              checked={none}
              onChange={(e) => onChange(e.target.checked ? NO_VALUES : "")}
            />
            <label htmlFor={`${id}-none`}>No value means missing, only an empty cell does</label>
          </div>
          <p className="hint" id={`${id}-preview`}>
            {recorded === "" ? (
              "One value on each line. Nothing will be recorded yet."
            ) : (
              <>
                One value on each line. Will be recorded as <code>{recorded}</code>.
              </>
            )}
          </p>
          {warnings.length > 0 && (
            <ul className="hint" id={`${id}-warnings`}>
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}
