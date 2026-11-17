/**
 * The advice **Describe a folder…** gives before it describes a folder holding a very large file
 * (DescribeFolder.tsx). A browser's memory grows while it hashes a large file, and the page can be
 * closed by the system when memory runs short (inventory/browser/README.md, Browser scanner): in
 * headless Chromium capped at 1 GB, a 4 GB file closed the page. The researcher is told so and
 * pointed to the command, and may still go on.
 */

import { formatBytes, type ChosenFile, type ChosenFolder } from "@data-director/inventory";
import { useEffect, useRef } from "react";

import { Button } from "../ui/Button";

/** From this size of file on, the command is advised (4 GB). */
export const LARGE_FILE_BYTES = 4_000_000_000;

/** The largest file in `folder` if it is at least `LARGE_FILE_BYTES`, else null. */
export function largestLargeFile(folder: ChosenFolder): ChosenFile | null {
  let largest: ChosenFile | null = null;
  for (const chosen of folder.files) {
    if (chosen.file.size >= LARGE_FILE_BYTES && chosen.file.size > (largest?.file.size ?? 0)) {
      largest = chosen;
    }
  }
  return largest;
}

interface Props {
  folder: ChosenFolder;
  file: ChosenFile;
  onGoOn: () => void;
  onCancel: () => void;
}

export function LargeFileNotice({ folder, file, onGoOn, onCancel }: Props) {
  // The button that chose the folder has gone: focus moves to the advice, so it is read first.
  const advice = useRef<HTMLParagraphElement>(null);
  useEffect(() => advice.current?.focus(), []);
  return (
    <div className="describe-folder-large">
      <p ref={advice} tabIndex={-1}>
        {folder.name} holds a file of {formatBytes(file.file.size)}, {file.path}. A browser uses a
        lot of memory on files this large, and may close the page if it runs short. The command
        (below) is better for this folder.
      </p>
      <div className="describe-folder-actions">
        <Button onPress={onGoOn}>Describe it here anyway</Button>
        <Button onPress={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}
