/**
 * What the conversation page reads of the process flow: its load state, and the project's
 * progress through it with the ways to change it. The shell keeps no copy of the flow
 * (docs/specs/orchestration.md); the harness derives where the project is from its log.
 */

import type { FlowStep, ProcessFlow, ProjectProgress, StepMark } from "../../flow/types";
import type { ProjectDocument } from "../../project/api";

export type FlowLoad =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; flow: ProcessFlow };

/** The project's progress and how to change it; absent until the conversation has a project. */
export interface TrackedProgress {
  progress: ProjectProgress;
  chooseEntry(entry: number): void;
  markStep(stepId: string, mark: StepMark): void;
  /** Starts a new conversation with the step's prompt in the message box, unsent. */
  startConversation?: (step: FlowStep) => void;
  /** Why the last change was not recorded, if it was not. */
  error?: string | null;
  /** Opens the intake card with the current answers chosen (docs/specs/app.md, rule 25). */
  answerIntakeAgain?: () => void;
  projectId?: string;
  /** The project's documents, once read, for the count of what waits on the researcher. */
  documents?: readonly ProjectDocument[];
}
