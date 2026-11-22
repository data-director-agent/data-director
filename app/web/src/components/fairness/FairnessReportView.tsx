/**
 * A FAIR report as a researcher reads it (docs/ui/fair-feedback.md): how many checks each of F, A,
 * I and R meets, what to do next, what is newly met, every check by principle, and what the report
 * is and is not. It adds no score: the counts are the report's own, and it always says that the
 * checks are a short list, not a FAIRness evaluation (R4).
 */

import "./Fairness.css";

import {
  CircleCheck,
  CircleDashed,
  Lock,
  MessageSquarePlus,
  PartyPopper,
} from "lucide-react";

import {
  type FairCheck,
  type FairnessReport,
  PRINCIPLES,
  askHowToMeet,
  checkLabel,
  checksOf,
  newlyMet,
  nextSteps,
  readyForDeposit,
} from "../../project/fairness";
import { Button } from "../ui/Button";
import { PrincipleMeters } from "./PrincipleMeters";

type Ask = ((text: string) => void) | undefined;
type HeadingTag = "h3" | "h4";

function CheckRow({ check }: { check: FairCheck }) {
  const [Icon, word] = check.after_deposit
    ? [Lock, "Checked at deposit"]
    : check.met
      ? [CircleCheck, "Met"]
      : [CircleDashed, "To do"];
  return (
    <li className={check.met ? "fair-check fair-met" : "fair-check"}>
      <span className="fair-check-state">
        <Icon size="1em" aria-hidden="true" /> {word}
      </span>{" "}
      <span>
        {checkLabel(check)} <span className="hint">({check.principle})</span>
      </span>
      {!check.met && !check.after_deposit && check.recommendation && (
        <p className="fair-check-advice">{check.recommendation}</p>
      )}
    </li>
  );
}

function NextSteps({
  steps,
  onAsk,
  Heading,
}: {
  steps: FairCheck[];
  onAsk: Ask;
  Heading: HeadingTag;
}) {
  if (steps.length === 0) return null;
  return (
    <section className="fair-next" aria-label="What to do next">
      <Heading>Next</Heading>
      <ol>
        {steps.map((check) => (
          <li key={check.check}>
            <span>{check.recommendation ?? checkLabel(check)}</span>
            {onAsk && (
              <Button
                size="small"
                variant="quiet"
                icon={MessageSquarePlus}
                onPress={() => onAsk(askHowToMeet(check))}
              >
                Ask how
              </Button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function FairnessReportView({
  report,
  previous = null,
  onAsk,
  compact = false,
  headingLevel = 4,
}: {
  report: FairnessReport;
  /** The report before this one in the project, to say what has changed since. */
  previous?: FairnessReport | null;
  /** Puts a question in the message box, unsent; with none, no question is offered. */
  onAsk?: Ask;
  /** Only the counts, what is next and what is new: for the project pane. */
  compact?: boolean;
  /** The level of its own headings, one below the heading it sits under. */
  headingLevel?: 3 | 4;
}) {
  const Heading: HeadingTag = headingLevel === 3 ? "h3" : "h4";
  const gained = newlyMet(report, previous);
  const ready = readyForDeposit(report);
  return (
    <div className="fair-report">
      <PrincipleMeters report={report} previous={previous} />
      {ready && (
        <p className="fair-ready" role="note">
          <PartyPopper size="1em" aria-hidden="true" /> Every check a draft can
          meet is met. What remains is checked at deposit.
        </p>
      )}
      {gained.length > 0 && (
        <section
          className="fair-gained"
          aria-label={
            previous
              ? "Newly met since the last check"
              : "Newly met since approval"
          }
        >
          <Heading>
            {previous
              ? "New since the last check"
              : "New since the version approved"}
          </Heading>
          <ul>
            {gained.map((check) => (
              <li key={check.check}>
                <CircleCheck size="1em" aria-hidden="true" />{" "}
                {checkLabel(check)}
              </li>
            ))}
          </ul>
        </section>
      )}
      <NextSteps steps={nextSteps(report)} onAsk={onAsk} Heading={Heading} />
      {!compact && (
        <>
          <section aria-label="Every check">
            <Heading>Every check</Heading>
            {PRINCIPLES.map(({ id, name }) => {
              const checks = checksOf(report, id);
              if (checks.length === 0) return null;
              return (
                <details key={id} className="fair-principle">
                  <summary>
                    {name}{" "}
                    <span className="hint">({checks.length} {checks.length === 1 ? "check" : "checks"})</span>
                  </summary>
                  <ul className="fair-checks">
                    {checks.map((check) => (
                      <CheckRow key={check.check} check={check} />
                    ))}
                  </ul>
                </details>
              );
            })}
          </section>
          {report.limitations.length > 0 && (
            <details className="fair-limits">
              <summary>What these checks are not</summary>
              <ul>
                {report.limitations.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
