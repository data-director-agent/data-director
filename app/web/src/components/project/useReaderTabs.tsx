/**
 * The document reader's tabs (`DocumentReader`): which is shown, and the Questions tab's count of
 * the questions still open.
 */

import { type RefObject, useEffect, useState } from "react";
import type { Key } from "react-aria-components";

import type { DocumentVersion, ProjectDocument } from "../../project/api";
import { versionGaps } from "../../project/gaps";

/**
 * Which of the reader's tabs is shown. A tab chosen holds for the version it was chosen on; another
 * version opens on its own first tab, which is its questions while it has no text yet, and
 * otherwise its preview. `openQuestions` shows the Questions tab and moves the focus to it.
 */
export function useReaderTabs(
  document: ProjectDocument,
  version: DocumentVersion | undefined,
  questionsTab: RefObject<HTMLDivElement | null>,
) {
  const [chosen, setChosen] = useState<{ on: string; tab: Key } | null>(null);
  // Counts each time the Questions tab is asked to take the focus, once it is shown.
  const [focused, setFocused] = useState(0);

  useEffect(() => {
    if (focused > 0) questionsTab.current?.focus();
  }, [focused, questionsTab]);

  const on = `${document.document_id}:${version?.version ?? ""}`;
  const asks = (version?.questions.length ?? 0) > 0;
  const latest = document.versions[document.versions.length - 1];
  const open = version && version === latest ? versionGaps(document, version).open : 0;
  const present = new Set<Key>(["preview", "source"]);
  if (asks) present.add("questions");
  if (document.versions.length > 1) present.add("history");
  const first: Key = asks && version?.stage === "questions" ? "questions" : "preview";
  const selected = chosen?.on === on && present.has(chosen.tab) ? chosen.tab : first;
  const choose = (tab: Key) => setChosen({ on, tab });
  return {
    selected,
    choose,
    asks,
    /** The open questions of the latest version; an earlier version's cannot be answered. */
    open,
    questionsLabel: open > 0 ? `Questions ${open} open` : "Questions",
    openQuestions: () => {
      choose("questions");
      setFocused((n) => n + 1);
    },
  };
}

/** How many questions are open, beside the Questions tab's name, which says it in words. */
export function OpenCount({ open }: { open: number }) {
  if (open === 0) return null;
  return (
    <span className="document-tab-count" aria-hidden="true">
      {open}
    </span>
  );
}
