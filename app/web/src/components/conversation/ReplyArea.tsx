/**
 * Where the researcher replies (docs/specs/app.md, rules 21 and 25): one way at a time. While the
 * latest reply asks questions, they are answered here, in the message box's place, with Attach a
 * file in their action row so that a file goes with the answers. While the project's intake is
 * open its card takes the box's place in the same way, after any questions. Beneath each way, a
 * button shows each other way open ("Reply in my own words instead", "Answer the questions
 * instead", "Answer the setup questions instead"). Text put in the box for the researcher, as by
 * a step's prompt or a question asked from the project pane, shows the box (`useReplyMode`). With
 * nothing open there is only the message box. The dialogs that check a file before it is attached
 * to a message are drawn once, beside whichever is shown.
 */

import { ClipboardList, ListChecks, type LucideIcon, MessageSquareText } from "lucide-react";
import {
  type ReactNode,
  type Ref,
  type RefObject,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import type { DocumentReaders } from "../../conversation/documentation";
import type { Question, ReplyAnswers } from "../../conversation/question";
import { useSteward } from "../escalation/StewardContext";
import { isStewardOffer, StewardOfferQuestion } from "../escalation/StewardOffer";
import { Button } from "../ui/Button";
import { AttachmentDialogs } from "./AttachmentDialogs";
import { Composer } from "./Composer";
import { AttachControls } from "./ComposerAttach";
import { type QuestionFocus, QuestionSeries } from "./QuestionSeries";
import type { Attachments } from "./useAttachments";

/** The questions the latest turn asks, to be answered. */
export interface Asking {
  /** The invocation whose reply asks them. */
  askedBy: string;
  askedByName: string;
  questions: Question[];
}

/** Moves the focus to the way of replying shown, once it has been drawn. */
export interface ReplyFocus {
  focus(): void;
}

/** The ways of replying: the latest reply's questions, the project's intake, or the message box. */
export type ReplyMode = "questions" | "intake" | "words";

/** The intake card, drawn by the page, given what moves the focus to it and whether it is hidden. */
export type IntakeSlot = (focus: Ref<QuestionFocus>, hidden: boolean) => ReactNode;

/**
 * Which way of replying is shown. A reply that asks comes first, then the open intake, then the
 * message box; the researcher may choose another that is open. When a new turn asks, its questions
 * show; when the questions go, the box shows, as the researcher has replied; and when the intake
 * opens, as for a new project or from the phase tracker, it shows unless questions are open.
 */
export function useReplyMode(questions: Asking | null, intakeOpen: boolean) {
  const asking = questions?.askedBy ?? null;
  const [chosen, setChosen] = useState<ReplyMode | null>(null);
  const [askedBy, setAskedBy] = useState(asking);
  const [wasOpen, setWasOpen] = useState(intakeOpen);
  if (askedBy !== asking) {
    setAskedBy(asking);
    setChosen(asking === null ? "words" : null);
  }
  if (wasOpen !== intakeOpen) {
    setWasOpen(intakeOpen);
    if (intakeOpen) setChosen(null);
  }
  const open = (m: ReplyMode) => m === "words" || (m === "questions" ? asking !== null : intakeOpen);
  const first: ReplyMode = asking !== null ? "questions" : intakeOpen ? "intake" : "words";
  return { mode: chosen !== null && open(chosen) ? chosen : first, setMode: setChosen };
}

const SWAPS: { mode: ReplyMode; label: string; icon: LucideIcon }[] = [
  { mode: "questions", label: "Answer the questions instead", icon: ListChecks },
  { mode: "intake", label: "Answer the setup questions instead", icon: ClipboardList },
  { mode: "words", label: "Reply in my own words instead", icon: MessageSquareText },
];

/** The buttons beneath one way of replying that show each other one open. */
function Swaps({ from, open, onSwap }: { from: ReplyMode; open: (m: ReplyMode) => boolean; onSwap: (m: ReplyMode) => void }) {
  return SWAPS.filter((s) => s.mode !== from && open(s.mode)).map((s) => (
    <Button key={s.mode} variant="quiet" icon={s.icon} onPress={() => onSwap(s.mode)}>
      {s.label}
    </Button>
  ));
}

export function ReplyArea({
  asking,
  intake,
  mode,
  onMode,
  box,
  text,
  onText,
  attachments,
  busy,
  answering,
  onSend,
  onAnswer,
  readers,
  ref,
}: {
  asking: Asking | null;
  /** The open intake's card, or null while it is closed. */
  intake: IntakeSlot | null;
  /** Which way of replying is shown (`useReplyMode`). */
  mode: ReplyMode;
  onMode: (mode: ReplyMode) => void;
  box: RefObject<HTMLTextAreaElement | null>;
  text: string;
  onText: (text: string) => void;
  attachments: Attachments;
  busy: boolean;
  /** Whether a message is on its way, so the questions are kept but cannot be answered. */
  answering: boolean;
  onSend: () => void;
  onAnswer: (answers: ReplyAnswers, text: string) => void;
  readers: DocumentReaders;
  ref?: Ref<ReplyFocus>;
}) {
  const card = useRef<QuestionFocus>(null);
  // In a project, the orchestrator's offer of a data steward is answered by its own card.
  const steward = useSteward();
  const setup = useRef<QuestionFocus>(null);
  // Read when the focus moves, a frame after a change of mode has been drawn.
  const shown = useRef(mode);
  useLayoutEffect(() => {
    shown.current = mode;
  });
  useImperativeHandle(ref, () => ({ focus: () => requestAnimationFrame(() => focusOn(shown.current)) }));

  function focusOn(m: ReplyMode) {
    (m === "words" ? box.current : m === "questions" ? card.current : setup.current)?.focus();
  }

  // When the intake card closes while shown, the focus goes to the way of replying shown next.
  const was = useRef(mode);
  useEffect(() => {
    if (was.current === "intake" && intake === null) focusOn(mode);
    was.current = mode;
  });

  function swap(to: ReplyMode) {
    onMode(to);
    requestAnimationFrame(() => focusOn(to));
  }

  const open = (m: ReplyMode) => m === "words" || (m === "questions" ? asking !== null : intake !== null);
  const swaps = (from: ReplyMode) => <Swaps from={from} open={open} onSwap={swap} />;

  // Every way stays drawn, those not in use hidden, so that what was chosen or typed in one stays
  // and what refers to its controls, as the Send button's announcement, still finds them.
  return (
    <div className="reply-area">
      {asking !== null && (
        <div hidden={mode !== "questions"}>
          {/* Kept while a message is sent, disabled, so a failed send keeps the answers. */}
          {steward && asking.questions[0] && isStewardOffer(asking.questions) ? (
            <StewardOfferQuestion
              key={asking.askedBy}
              ref={card}
              question={asking.questions[0]}
              askedBy={asking.askedBy}
              onAnswer={onAnswer}
              disabled={answering}
            />
          ) : (
            <QuestionSeries
              key={asking.askedBy}
              ref={card}
              questions={asking.questions}
              askedBy={asking.askedBy}
              askedByName={asking.askedByName}
              onAnswer={onAnswer}
              disabled={answering}
              attach={<AttachControls attachments={attachments} busy={busy} />}
              drop={attachments}
            />
          )}
          {swaps("questions")}
        </div>
      )}
      {intake !== null && (
        <div hidden={mode !== "intake"}>
          {intake(setup, mode !== "intake")}
          {swaps("intake")}
        </div>
      )}
      <div hidden={mode !== "words"}>
        <Composer box={box} text={text} onText={onText} attachments={attachments} busy={busy} onSend={onSend} />
        {swaps("words")}
      </div>
      <AttachmentDialogs attachments={attachments} readers={readers} />
    </div>
  );
}
