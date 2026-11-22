/**
 * The person's message: as typed, or, when it sends answers to a reply's questions, the Markdown
 * the answers were put in (`answersText`), each question in bold with its answer. The same in the
 * transcript and while the reply is awaited, so nothing changes when the turn is stored.
 */

import { Markdown } from "../ui/Markdown";

export function PersonText({ text, answers }: { text: string | null | undefined; answers: boolean }) {
  if (!answers || !text) return <p>{text}</p>;
  return (
    <div className="markdown">
      <Markdown>{text}</Markdown>
    </div>
  );
}
