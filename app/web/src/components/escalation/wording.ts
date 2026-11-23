/**
 * The words the researcher and the steward read about an escalation to a data steward: one status line that
 * answers "what is happening with my request?" (docs/specs/stewardship.md, invariant 10), and what
 * a refusal means, by its slug, never by the server's wording.
 */

import type { Escalation, EscalationState } from "../../project/escalations";
import type { MoveName } from "../../project/steward";
import { formatDate } from "../../format";

const STATE: Record<EscalationState, string> = {
  open: "Waiting for a data steward to take it",
  taken: "A data steward is looking at it",
  waiting_for_researcher: "Waiting for you to reply",
  resolved: "Resolved",
  handed_back: "Handed back to you",
  withdrawn: "Withdrawn",
};

/** The state alone, as a short phrase. */
export function stateSaid(state: EscalationState): string {
  return STATE[state];
}

/** "Sent to Research Data Support on 12 Nov 2026 · Taken by Ada · Waiting for you to reply". */
export function statusLine(escalation: Escalation): string {
  const parts = [`Sent to ${escalation.team_name} on ${formatDate(escalation.opened_at)}`];
  if (escalation.taken_by && escalation.state !== "withdrawn") parts.push(`Taken by ${escalation.taken_by.name}`);
  parts.push(STATE[escalation.state]);
  return parts.join(" · ");
}

/** What each move in an escalation's history says, as a marker in the conversation. */
export const MOVE_SAID: Record<string, string> = {
  open: "sent this to the data stewards",
  take: "took this request",
  release: "handed this request back to the team",
  wait: "asked you a question",
  reply: "replied",
  resolve: "marked this request resolved",
  hand_back: "handed this back to you",
  withdraw: "withdrew this request",
  reopen: "re-opened this request",
};

const REFUSED: Record<string, string> = {
  "no-steward-team": "No data steward team is set up for this project.",
  "team-required": "Choose which data steward team to send this to.",
  "unknown-team": "That data steward team is no longer listed. Choose another.",
  "already-escalated": "This has already been sent to a data steward.",
  "note-required": "Write a note to go with it.",
  "note-too-long": "The note is too long. Shorten it and try again.",
  "move-not-allowed": "This request has moved on since you last saw it. It has been read again.",
  "unknown-escalation": "This request is no longer listed. It has been read again.",
};

/** What a refusal means for the researcher, by its slug; the server's words for any other. */
export function refusalSaid(slug: string, fallback: string): string {
  return REFUSED[slug] ?? fallback;
}

const STEWARD_STATE: Record<EscalationState, string> = {
  open: "Not taken",
  taken: "Taken",
  waiting_for_researcher: "Waiting for the researcher",
  resolved: "Resolved",
  handed_back: "Handed back",
  withdrawn: "Withdrawn",
};

/** The state as a steward reads it in the queue. */
export function stewardStateSaid(state: EscalationState): string {
  return STEWARD_STATE[state];
}

/** What each move's control says, what its note is for, and what is announced once it is made. */
export const MOVE_CONTROL: Record<
  MoveName,
  { label: string; field: string; done: string }
> = {
  take: { label: "Take", field: "", done: "You took this request." },
  release: { label: "Release", field: "Why you are releasing it (optional)", done: "Request released to the team." },
  wait: { label: "Ask the researcher", field: "Your question to the researcher", done: "Question sent. The request is waiting for the researcher." },
  reply: { label: "Reply", field: "Your reply to the data steward", done: "Reply sent." },
  resolve: { label: "Resolve", field: "How it was resolved", done: "Request resolved." },
  hand_back: { label: "Hand back", field: "Your note to the researcher", done: "Request handed back to the researcher." },
  withdraw: { label: "Withdraw", field: "", done: "Request withdrawn." },
  reopen: { label: "Re-open", field: "Why you are re-opening it", done: "Request re-opened." },
};

const MOVE_REFUSED: Record<string, string> = {
  "member-of-project":
    "You are a member of this project, so you act in it as a member, not as its data steward. Another steward on the team can take it.",
};

/** Why a move is refused, by its code. */
export function moveRefusalSaid(code: string): string {
  return MOVE_REFUSED[code] ?? "This is not yours to do here.";
}

/** Where an escalation came from, as a short phrase. */
export function originSaid(kind: string): string {
  if (kind === "policy_gate") return "A step that needs approval";
  if (kind === "agent") return "An agent referred it";
  if (kind === "orchestrator") return "Offered in a conversation";
  return "Asked by the researcher";
}
