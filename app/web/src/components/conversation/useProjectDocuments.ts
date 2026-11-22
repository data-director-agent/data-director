/**
 * The project's documents, read when the project is known and again after each turn, for the
 * cards on the turns that drafted them and the side bar's list. A read of another project's
 * documents is never shown as this one's.
 *
 * A turn's reply is announced only once the documents have been read again, so that the
 * announcement can name any document version the turn drafted.
 */

import { useCallback, useRef } from "react";

import { type ProjectDocuments, useProjectApi } from "../../project/api";
import { type DocumentsRead, draftedBy } from "../../project/drafted";
import { documentName } from "../../project/name";
import { useResource } from "../../useResource";
import { STATES } from "../project/DocumentFacts";

/** A reply's announcement, waiting on the documents, and the runs the turn made. */
export interface AwaitedDrafts {
  said: string;
  invocationIds: string[];
}

export interface ProjectDocumentsRead {
  documents: DocumentsRead;
  /** Holds the documents a change returned, such as an answered document question. */
  answered(projectId: string, value: ProjectDocuments): void;
  /** The longest answer to a draft's question the harness keeps; null until the server says. */
  answerMaxLength: number | null;
}

/**
 * The documents of project `projectId`, read again when `turnCount` changes. `awaited`, once the
 * documents are next read, is said again with what its runs drafted, if they drafted anything.
 */
export function useProjectDocuments(
  projectId: string | null,
  turnCount: number,
  awaited: AwaitedDrafts | null,
  announce: (said: string) => void,
): ProjectDocumentsRead {
  const projectApi = useProjectApi();
  // The announcement already dealt with, so that it is said at most once.
  const done = useRef<AwaitedDrafts | null>(null);
  const read = useResource(
    projectId,
    (of, signal) => projectApi.documents(of, signal),
    turnCount,
    {
      loaded(value) {
        const pending = awaited === done.current ? null : awaited;
        done.current = awaited;
        const drafted = pending ? draftedBy(pending.invocationIds, value.documents) : [];
        if (!pending || drafted.length === 0) return;
        const what = drafted.map(
          ({ document, version }) =>
            `${documentName(document)} drafted, version ${version.version}: ${STATES[version.state].label}.`,
        );
        announce([pending.said, ...what].join(" "));
      },
      failed() {
        done.current = awaited;
      },
    },
  );
  const { set } = read;
  const answered = useCallback(
    (of: string, value: ProjectDocuments) => set(of, value),
    [set],
  );
  const documents: DocumentsRead =
    read.resource.state === "loaded"
      ? { state: "loaded", documents: read.resource.value.documents }
      : read.resource;
  const answerMaxLength =
    read.resource.state === "loaded" ? read.resource.value.answer_max_length : null;
  return { documents, answered, answerMaxLength };
}
