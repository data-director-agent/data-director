/**
 * Where the researcher replies (docs/specs/app.md, rule 21): one way at a time. While the latest
 * reply asks questions, they are answered here, in the message box's place, with Attach a file in
 * their action row so that a file goes with the answers; "Reply in my own words instead" swaps to
 * the message box, and "Answer the questions instead" swaps back. Text put in the box for the
 * researcher, as by a step's prompt or a question asked from the project pane, shows the box
 * (`useReplyMode`). With no questions open there is only the message box. The dialogs that check
 * a file before it is attached are drawn once, beside whichever is shown.
 */

import { ListChecks, MessageSquareText } from "lucide-react";
import { type Ref, type RefObject, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";

import type { DocumentReaders } from "../../conversation/documentation";
import type { Question, ReplyAnswers } from "../../conversation/question";
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

/**
 * Whether the researcher is replying in their own words while questions are open: not when a new
 * turn asks, and so whenever `asking` changes; yes once they choose to, or text is put in the box.
 */
export function useReplyMode(questions: Asking | null) {
  const asking = questions?.askedBy ?? null;
  const [words, setWords] = useState(false);
  const [askedBy, setAskedBy] = useState(asking);
  if (askedBy !== asking) {
    setAskedBy(asking);
    setWords(false);
  }
  return { words: asking === null || words, setWords };
}

export function ReplyArea({
  asking,
  words,
  onWords,
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
  /** Whether the message box is shown in place of the questions (`useReplyMode`). */
  words: boolean;
  onWords: (words: boolean) => void;
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
  // Read when the focus moves, a frame after a change of mode has been drawn.
  const writing = useRef(words);
  useLayoutEffect(() => {
    writing.current = words;
  });
  useImperativeHandle(
    ref,
    () => ({
      focus: () => requestAnimationFrame(() => (writing.current ? box.current : card.current)?.focus()),
    }),
    [box],
  );

  function swap(toWords: boolean) {
    onWords(toWords);
    requestAnimationFrame(() => (toWords ? box.current : card.current)?.focus());
  }

  // Both ways stay drawn, the one not in use hidden, so that what was chosen or typed in it stays
  // and what refers to its controls, as the Send button's announcement, still finds them.
  return (
    <div className="reply-area">
      {asking !== null && (
        <div hidden={words}>
          {/* Kept while a message is sent, disabled, so a failed send keeps the answers. */}
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
          <Button variant="quiet" icon={MessageSquareText} onPress={() => swap(true)}>
            Reply in my own words instead
          </Button>
        </div>
      )}
      <div hidden={!words}>
        <Composer box={box} text={text} onText={onText} attachments={attachments} busy={busy} onSend={onSend} />
        {asking !== null && (
          <Button variant="quiet" icon={ListChecks} onPress={() => swap(false)}>
            Answer the questions instead
          </Button>
        )}
      </div>
      <AttachmentDialogs attachments={attachments} readers={readers} />
    </div>
  );
}
