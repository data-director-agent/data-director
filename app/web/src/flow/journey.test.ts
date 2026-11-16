import flowFixture from "../../fixtures/process-flow.json";
import type { ProjectDocument } from "../project/api";
import {
  journey,
  locate,
  reasonText,
  stations,
  waitingCount,
  waitingDocuments,
} from "./journey";
import type { ProcessFlow, ProjectProgress } from "./types";

const FLOW = flowFixture as ProcessFlow;
const firstStep = (phase: number) => {
  const step = FLOW.phases[phase]?.steps.find((s) => !s.out_of_scope);
  if (!step) throw new Error("the fixture has no such step");
  return step;
};

describe("journey", () => {
  it("draws one line per phase with every step, open where the server gives no state", () => {
    const lines = journey(FLOW, null);
    expect(lines.map((l) => l.phase.number)).toEqual(FLOW.phases.map((p) => p.number));
    expect(stations(lines).map((s) => s.step.id)).toEqual(
      FLOW.phases.flatMap((p) => p.steps.map((s) => s.id)),
    );
    expect(stations(lines).every((s) => s.state === "open" && !s.suggested)).toBe(true);
  });

  it("takes each state, reason and suggestion from the progress, and counts what is finished", () => {
    const done = firstStep(1);
    const next = firstStep(2);
    const progress: ProjectProgress = {
      entry: 2,
      steps: { [done.id]: "done" },
      suggested: next.id,
      reasons: { [done.id]: { state: "done", source: "marked", event: "step_marked" } },
    };
    const lines = journey(FLOW, progress);
    const all = stations(lines);
    const found = all.find((s) => s.step.id === done.id);
    expect(found?.state).toBe("done");
    expect(found?.reason?.source).toBe("marked");
    expect(all.find((s) => s.step.id === next.id)?.suggested).toBe(true);
    const line = lines.find((l) => l.phase.number === FLOW.phases[1]?.number);
    expect(line?.finished).toBe(1);
    // Entry 2 joins at a later phase: the first phase's steps come before it.
    const startsAt = FLOW.entries.find((e) => e.number === 2)?.starts_at ?? 0;
    expect(all.filter((s) => s.beforeEntry).every((s) => s.phase.number < startsAt)).toBe(true);
    expect(lines.find((l) => l.phase.number === startsAt)?.entries.map((e) => e.number)).toContain(2);
  });

  it("places each decision before its step and counts an unanswered one as waiting", () => {
    const before = firstStep(2);
    const progress: ProjectProgress = {
      entry: 1,
      steps: {},
      suggested: null,
      decisions: [
        {
          question_id: "intake.example",
          prompt: "Is it so?",
          before: before.id,
          asked: true,
          answer_values: null,
          answer_labels: null,
        },
      ],
    };
    const lines = journey(FLOW, progress);
    const items = lines.flatMap((l) => l.items);
    const at = items.findIndex((i) => i.kind === "decision");
    const after = items[at + 1];
    expect(after?.kind === "station" && after.step.id).toBe(before.id);
    expect(waitingCount(lines)).toBe(1);
  });

  it("marks a step waiting while the document that started it awaits a decision", () => {
    const step = firstStep(3);
    const progress: ProjectProgress = {
      entry: 1,
      steps: { [step.id]: "started" },
      suggested: null,
      reasons: {
        [step.id]: {
          state: "started",
          source: "produced",
          event: "document_version_added",
          document_id: "d1",
          document_kind: "readme",
        },
      },
    };
    const documents = [
      { document_id: "d1", document_kind: "readme", versions: [{ state: "proposed" }] },
    ] as unknown as ProjectDocument[];
    const lines = journey(FLOW, progress, waitingDocuments(documents));
    expect(stations(lines).find((s) => s.step.id === step.id)?.waiting).toBe(true);
    expect(waitingCount(journey(FLOW, progress))).toBe(0);
  });

  it("finds a step's phase, and says why a step stands as it does", () => {
    const step = firstStep(0);
    expect(locate(FLOW, step.id)?.step.id).toBe(step.id);
    expect(locate(FLOW, "nowhere")).toBeNull();
    const decision = {
      question_id: "intake.x",
      prompt: "Is it so?",
      before: step.id,
      asked: true,
      answer_values: ["no"],
      answer_labels: ["No"],
    };
    const text = reasonText(
      { state: "skipped", source: "intake", event: "intake_answered", question_id: "intake.x" },
      [decision],
    );
    expect(text).toContain("Is it so?");
    expect(text).toContain("No");
  });
});
