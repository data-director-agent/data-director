/**
 * What the conversation's parts share about the project's data stewards: its escalations, what
 * stewards did in it, and the one dialog in which the researcher confirms an escalation before it
 * is sent (docs/specs/stewardship.md, invariant 5: the agent offers; a person confirms).
 *
 * The provider reads both again when a turn settles, when the window is focused, and every minute
 * while the page is shown, and announces in the polite live region each change it did not make
 * itself: a steward's reply, or a request taken, resolved or handed back. Outside a project there
 * is no provider, and the parts that use it render nothing.
 */

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  type Escalation,
  type NewEscalation,
  type NewOrigin,
  type ProjectEscalations,
  type ProjectStewarding,
  type ResearcherMove,
  useEscalationsApi,
} from "../../project/escalations";
import { useResource } from "../../useResource";
import { useAnnounceIfMounted } from "../ui/Announcer";
import { AskSteward } from "./AskSteward";
import { stewardEvents, eventSaid } from "./events";

/** An offer the researcher is shown before anything is sent. */
export interface Offer {
  origin: NewOrigin;
  /** The note as first written for them, which they may change. */
  note?: string;
  /** Lines of what is shared beside the project and the conversation, such as the run's outcome. */
  matter?: string[];
  /** A step stopped for a mandatory review: it stays stopped whatever is chosen. */
  mandatory?: boolean;
  /** Called once the escalation is sent. */
  onSent?: () => void;
}

export interface Steward {
  projectId: string;
  escalations: ProjectEscalations | undefined;
  stewarding: ProjectStewarding | undefined;
  /** Opens the dialog in which the researcher checks what is shared, and sends it. */
  offer(offer: Offer): void;
  /** Makes a move on the researcher's side, and reads the escalations again. */
  move(escalation: Escalation, move: ResearcherMove, note?: string): Promise<void>;
}

const StewardContext = createContext<Steward | null>(null);

/** The project's stewards, or null outside a project. */
export function useSteward(): Steward | null {
  return useContext(StewardContext);
}

const EVERY_MINUTE = 60_000;

export function StewardProvider({
  projectId,
  project,
  refresh,
  children,
}: {
  projectId: string | null;
  /** The project as listed, for its title; null or undefined until it is. */
  project?: { title: string | null } | null | undefined;
  /** Changes when a turn settles, so that both are read again. */
  refresh?: unknown;
  children: ReactNode;
}) {
  const api = useEscalationsApi();
  const announce = useAnnounceIfMounted();
  const [offered, setOffered] = useState<Offer | null>(null);
  // The control that opened the dialog, which takes the focus back when it closes.
  const opener = useRef<HTMLElement | null>(null);
  const open = useCallback((offer: Offer) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOffered(offer);
  }, []);
  const close = useCallback(() => {
    setOffered(null);
    // After the dialog's own restoring, in case the page moved the focus to the body meanwhile.
    requestAnimationFrame(() => {
      if (document.activeElement === document.body && opener.current?.isConnected) opener.current.focus();
    });
  }, []);
  const read = useResource(projectId, (id, signal) => api.escalations(id, signal), refresh);
  const steps = useResource(projectId, (id, signal) => api.stewarding(id, signal), refresh);
  const { reload: readAgain } = read;
  const { reload: stepsAgain } = steps;
  const reload = useCallback(() => {
    readAgain();
    stepsAgain();
  }, [readAgain, stepsAgain]);

  useEffect(() => {
    if (projectId === null) return;
    const again = () => {
      if (document.visibilityState === "visible") reload();
    };
    const timer = window.setInterval(again, EVERY_MINUTE);
    window.addEventListener("focus", again);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", again);
    };
  }, [projectId, reload]);

  useAnnounceChanges(projectId, read.latest, steps.latest, announce);

  const value = useMemo<Steward | null>(
    () =>
      projectId === null
        ? null
        : {
            projectId,
            escalations: read.latest,
            stewarding: steps.latest,
            offer: open,
            async move(escalation, move, note) {
              try {
                await api.move(projectId, escalation.escalation_id, move, note);
              } finally {
                reload();
              }
            },
          },
    [api, projectId, read.latest, steps.latest, reload, open],
  );

  async function send(escalation: NewEscalation) {
    if (projectId === null) return;
    const now = await api.open(projectId, escalation);
    read.set(projectId, now);
    offered?.onSent?.();
    close();
    announce(`Sent to the data stewards. You can follow it in the project panel.`);
  }

  return (
    <StewardContext.Provider value={value}>
      {children}
      {projectId !== null && offered && (
        <AskSteward
          offer={offered}
          escalations={read.latest}
          projectTitle={project?.title ?? null}
          onSend={send}
          onClose={close}
        />
      )}
    </StewardContext.Provider>
  );
}

/** Announces what changed between reads of the same project that the researcher did not do. */
function useAnnounceChanges(
  projectId: string | null,
  escalations: ProjectEscalations | undefined,
  stewarding: ProjectStewarding | undefined,
  announce: (said: string) => void,
) {
  const seen = useRef<{ projectId: string | null; keys: Set<string> } | null>(null);
  useEffect(() => {
    if (!escalations || !stewarding) return;
    const events = stewardEvents(escalations.escalations, stewarding.messages);
    const keys = new Set(events.map((e) => e.key));
    const was = seen.current;
    seen.current = { projectId, keys };
    if (!was || was.projectId !== projectId) return;
    const fresh = events.filter((e) => !was.keys.has(e.key) && e.fromSteward);
    for (const event of fresh) announce(eventSaid(event));
  }, [projectId, escalations, stewarding, announce]);
}
