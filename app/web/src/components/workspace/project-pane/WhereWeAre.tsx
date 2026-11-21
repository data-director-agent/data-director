/**
 * Where the project stands, in one line, and the step suggested next with a way to ask about it.
 * The phase strip above the conversation holds the whole journey and its controls (mark done,
 * skip), so they are not repeated here.
 */

import { MessageSquarePlus } from "lucide-react";

import { locate } from "../../../flow/journey";
import type { ProcessFlow, ProjectProgress } from "../../../flow/types";
import { Link, journeyPath } from "../../../route";
import { askAboutStep } from "../../conversation/useAskAbout";
import { Button } from "../../ui/Button";

/** The first step, in the flow's order, that the project has started and not finished. */
function currentStep(flow: ProcessFlow, progress: ProjectProgress): string | null {
  for (const phase of flow.phases) {
    const started = phase.steps.find((step) => progress.steps[step.id] === "started");
    if (started) return started.id;
  }
  return null;
}

export function WhereWeAre({
  projectId,
  flow,
  progress,
  onAsk,
}: {
  projectId: string;
  flow: ProcessFlow | null;
  progress: ProjectProgress | null;
  onAsk?: ((text: string) => void) | undefined;
}) {
  const now = flow && progress ? locate(flow, currentStep(flow, progress)) : null;
  const next = flow && progress ? locate(flow, progress.suggested) : null;
  return (
    <section aria-labelledby="where-heading" className="pane-section">
      <h3 id="where-heading">Where we are</h3>
      {!flow || !progress ? (
        <p className="hint">Where the project stands shows here once Data Director has read it.</p>
      ) : (
        <dl className="pane-facts">
          <div>
            <dt>Now</dt>
            <dd>
              {now ? (
                <>
                  {now.phase.name} › {now.step.label} <span className="status status-warn">Started</span>
                </>
              ) : (
                <span className="hint">No step under way</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Suggested next</dt>
            <dd>
              {next ? (
                <>
                  {next.phase.name} › {next.step.label}
                </>
              ) : (
                <span className="hint">Nothing suggested</span>
              )}
            </dd>
          </div>
        </dl>
      )}
      <p className="pane-actions">
        {next && onAsk && (
          <Button size="small" icon={MessageSquarePlus} onPress={() => onAsk(askAboutStep(next))}>
            Ask about the next step
          </Button>
        )}
        <Link to={journeyPath(projectId)}>Journey map</Link>
      </p>
    </section>
  );
}
