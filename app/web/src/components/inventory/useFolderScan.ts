/**
 * One scan of a folder at a time, for **Describe a folder…** (DescribeFolder.tsx): what it is
 * doing, its progress, and its end. Each stage is announced once, politely; a failure or a choice
 * that is not a folder goes to the assertive region (components/ui/Announcer.tsx). Progress is
 * shown, not announced file by file. A scan still running when the component goes is cancelled.
 */

import type { ChosenFolder, FileProgress, ScanHandle, ScanStage } from "@data-director/inventory";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Scanner } from "../../scan/scanner";
import { useAnnounce } from "../ui/Announcer";

/** Before the worker says anything, the page is fetching the scanner. */
export type Stage = "fetching" | ScanStage;

export const STAGE_TEXT: Record<Stage, string> = {
  fetching: "Fetching the scanner.",
  starting: "Starting the scanner.",
  installing: "Installing the scanner.",
  reading: "Reading the files.",
};

export type FolderScan =
  | { status: "idle"; error: string | null }
  | { status: "scanning"; folder: string; stage: Stage; progress: FileProgress | null };

const IDLE: FolderScan = { status: "idle", error: null };

export function useFolderScan(scanner: Scanner, onDescribed: (file: File) => void) {
  const announce = useAnnounce();
  const [scan, setScan] = useState<FolderScan>(IDLE);
  const running = useRef<ScanHandle | null>(null);

  useEffect(
    () => () => {
      const handle = running.current;
      running.current = null; // gone: its end is neither shown nor said
      handle?.cancel();
    },
    [],
  );

  const fail = useCallback(
    (message: string) => {
      setScan({ status: "idle", error: message });
      announce(message, { assertive: true });
    },
    [announce],
  );

  const start = useCallback(
    (folder: ChosenFolder) => {
      if (running.current) return;
      setScan({ status: "scanning", folder: folder.name, stage: "fetching", progress: null });
      announce(`Describing ${folder.name}. ${STAGE_TEXT.fetching}`);
      const handle = scanner.scan(folder, (event) => {
        if (running.current !== handle) return;
        if (event.type === "stage") {
          setScan((s) => (s.status === "scanning" ? { ...s, stage: event.stage } : s));
          announce(STAGE_TEXT[event.stage]);
        } else if (event.type === "progress") {
          const progress = { path: event.path, size: event.size, done: event.done, total: event.total };
          setScan((s) => (s.status === "scanning" ? { ...s, progress } : s));
        }
      });
      running.current = handle;
      void handle.outcome.then((outcome) => {
        if (running.current !== handle) return;
        running.current = null;
        if (outcome.status === "done") {
          setScan(IDLE);
          announce(`Described ${folder.name}.`);
          const name = `${folder.name}-inventory.json`;
          onDescribed(new File([outcome.inventory], name, { type: "application/json" }));
        } else if (outcome.status === "failed") fail(outcome.reason);
        else {
          setScan(IDLE);
          announce("Stopped describing the folder.");
        }
      });
    },
    [announce, fail, onDescribed, scanner],
  );

  const cancel = useCallback(() => running.current?.cancel(), []);

  return { scan, start, cancel, fail };
}
