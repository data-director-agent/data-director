/**
 * The project's intake (docs/specs/app.md, rule 25), read when the project is known and after each
 * turn, as a turn may record the entry point Data Director worked out. The card opens while the
 * intake is first read pending, or when asked for again from the phase tracker, and stays open
 * until the researcher closes or dismisses it, so that it can end with its summary; a read after a
 * turn changes what the card holds, never whether it is open.
 */

import { useCallback, useState } from "react";

import type { ProjectProgress } from "../../flow/types";
import { type ProjectIntake, useProjectApi } from "../../project/api";
import { errorMessage } from "../../run/api";
import { useResource } from "../../useResource";

/** The intake of the project being worked in, and whether its card is open. */
export interface IntakeShown {
  intake: ProjectIntake;
  open: boolean;
  /** Opened again from the tracker, rather than first read pending. */
  again: boolean;
}

export interface IntakeRead {
  intake: IntakeShown | null;
  /** Whether the first read of the project's intake has landed or failed. */
  settled: boolean;
  /** Opens the card again for project `of`, with the answers as they are now. */
  openAgain(of: string): void;
  answer(of: string, questionId: string, values: string[]): Promise<ProjectIntake>;
  /** Skips the setup questions for project `of`, closing the card. */
  dismiss(of: string): void;
  close(): void;
}

export interface IntakeEvents {
  /** The project's progress, as a change to the intake returned it. */
  progressed(of: string, progress: ProjectProgress): void;
  announce(said: string): void;
  failed(message: string): void;
}

export function useIntake(
  projectId: string | null,
  turnCount: number,
  events: IntakeEvents,
): IntakeRead {
  const projectApi = useProjectApi();
  // Whether the card is open, kept with the project it is of.
  const [card, setCard] = useState<{ projectId: string; open: boolean; again: boolean } | null>(
    null,
  );
  const { resource, latest, set } = useResource(
    projectId,
    (of, signal) => projectApi.intake(of, signal),
    turnCount,
    {
      loaded: (intake, of) =>
        setCard((was) =>
          was?.projectId === of ? was : { projectId: of, open: intake.state === "pending", again: false },
        ),
    },
  );
  const { progressed, announce, failed } = events;

  const changed = useCallback(
    (of: string, intake: ProjectIntake) => {
      set(of, intake);
      progressed(of, intake.progress);
    },
    [set, progressed],
  );

  const close = useCallback(() => {
    setCard((was) => (was ? { ...was, open: false, again: false } : was));
  }, []);

  // Asked again from the tracker, the card shows the answers as they are now, read afresh: the
  // entry point may have been chosen in the tracker or by Data Director since the last read.
  function openAgain(of: string) {
    const open = () =>
      setCard((was) => (was?.projectId === of ? { ...was, open: true, again: true } : was));
    projectApi.intake(of).then(
      (read) => {
        set(of, read);
        open();
      },
      open,
    );
  }

  async function answer(of: string, questionId: string, values: string[]) {
    const result = await projectApi.answerIntake(of, questionId, values);
    changed(of, result);
    return result;
  }

  function dismiss(of: string) {
    projectApi.dismissIntake(of).then(
      (result) => {
        changed(of, result);
        close();
        announce("Setup questions skipped. You can answer them from the phase tracker.");
      },
      (e: unknown) => failed(`Data Director could not skip the setup questions: ${errorMessage(e)}`),
    );
  }

  const intake =
    projectId && latest && card?.projectId === projectId
      ? { intake: latest, open: card.open, again: card.again }
      : null;
  return { intake, settled: resource.state !== "loading", openAgain, answer, dismiss, close };
}
