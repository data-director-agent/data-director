/** A fake of the project's escalations and stewarding, for components' own tests. */

import { type Mock, vi } from "vitest";

import escalationsFixture from "../../fixtures/escalations.json";
import type { EscalationsApi, ProjectEscalations, ProjectStewarding } from "../project/escalations";

export const ESCALATIONS = escalationsFixture as ProjectEscalations;

export const NO_STEWARDING: ProjectStewarding = { gate_decisions: [], messages: [], paused: null, views: [] };

/** A project with no escalations yet, routed to the fixture's one team. */
export const NONE_YET: ProjectEscalations = { ...ESCALATIONS, escalations: [] };

export function fakeEscalationsApi(
  read: ProjectEscalations = NONE_YET,
  stewarding: ProjectStewarding = NO_STEWARDING,
): {
  escalations: Mock<EscalationsApi["escalations"]>;
  stewarding: Mock<EscalationsApi["stewarding"]>;
  open: Mock<EscalationsApi["open"]>;
  move: Mock<EscalationsApi["move"]>;
} {
  const [first] = ESCALATIONS.escalations;
  if (!first) throw new Error("no escalation in the fixture");
  return {
    escalations: vi.fn<EscalationsApi["escalations"]>(() => Promise.resolve(read)),
    stewarding: vi.fn<EscalationsApi["stewarding"]>(() => Promise.resolve(stewarding)),
    open: vi.fn<EscalationsApi["open"]>(() => Promise.resolve(ESCALATIONS)),
    move: vi.fn<EscalationsApi["move"]>(() => Promise.resolve({ ...first, state: "withdrawn" })),
  };
}
