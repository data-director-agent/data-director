/**
 * A proposed fact to talk through (`?fact={proposal}`, from its "Discuss this with Data Director"
 * link on the project's facts tab) fills the message box of a new conversation, unsent. The fact
 * is still decided only on the facts tab (docs/specs/app.md, rule 29).
 */

import type { FactProposal } from "../../project/facts";
import { describeFact, KIND_LABELS } from "../project/factWording";
import { useProjectFacts } from "../workspace/project-pane/facts";
import { type AskInto, useAskedInAddress } from "./useAskAbout";

/**
 * The message that asks for help deciding a proposed fact, in the researcher's voice. It quotes
 * the agent's reason, which the person passes on by sending it; the app never gives it to an agent.
 */
export function askAboutFact(proposal: FactProposal): string {
  const { fact } = proposal;
  const words = fact.commitment_quote ? ` The plan says: “${fact.commitment_quote}”.` : "";
  const because = fact.proposed_because
    ? ` ${proposal.agent_id} proposed it because: “${fact.proposed_because}”.`
    : ` ${proposal.agent_id} proposed it.`;
  return (
    `Can you help me decide on this proposed fact (${KIND_LABELS[fact.fact_kind]}): ` +
    `“${describeFact(fact)}”?${words}${because} ` +
    "I'll confirm, change or reject it in Project facts once we've talked it through."
  );
}

/**
 * Reads the project's facts only when a fact is asked about, puts the question in the box once
 * they are read, then drops the address's `fact` so a reload does not refill. A proposal no longer
 * waiting for a decision is ignored.
 */
export function useAskAboutFact(
  projectId: string | null,
  into: AskInto,
): void {
  const { pending, handle } = useAskedInAddress("fact", into);
  const facts = useProjectFacts(pending ? projectId : null, null);
  if (pending && (facts.state !== "loading" || !projectId)) {
    handle();
    const proposal =
      facts.state === "loaded" ? facts.value.proposals.find((p) => p.proposal === pending) : undefined;
    if (proposal) into.setText(askAboutFact(proposal));
  }
}
