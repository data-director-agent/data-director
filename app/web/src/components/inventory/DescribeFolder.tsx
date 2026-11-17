/**
 * **Describe a folder…**, the first choice in Make an inventory (MakeInventoryDialog.tsx,
 * docs/specs/app.md). The researcher chooses a folder; the browser scanner (`src/scan/`) describes
 * it here, and the inventory it makes is handed on as a file, as if chosen at the end of the
 * dialog, so that it goes through the check before attaching (#472) like any other.
 *
 * The folder is chosen with `showDirectoryPicker` where the browser has it, since Chromium's
 * `<input webkitdirectory>` asks to "upload" files that are never sent; elsewhere with that input.
 * Dropping a folder on the section is a shortcut for the button. The section is shown only where
 * the deployment serves the scanner.
 */

import {
  canPickDirectory,
  fromDirectoryHandle,
  fromEntries,
  fromFileList,
  NotAFolder,
  type ChosenFolder,
  type DirectoryHandleLike,
  type EntryLike,
} from "@data-director/inventory";
import { FolderOpen, X } from "lucide-react";
import { useEffect, useId, useState, type DragEvent } from "react";
import { FileTrigger } from "react-aria-components";

import { NOTICES_PATH, pageScanner, type Scanner } from "../../scan/scanner";
import { Button } from "../ui/Button";
import { STAGE_TEXT, useFolderScan, type FolderScan } from "./useFolderScan";

/** The attribution the PRONOM signatures' licence asks for (inventory/browser, NOTICES.md). */
const OGL = "Contains public sector information licensed under the Open Government Licence v3.0.";

interface Props {
  /** Called with the inventory made, as `<folder>-inventory.json`. */
  onDescribed: (file: File) => void;
  scanner?: Scanner;
}

export function DescribeFolder({ onDescribed, scanner = pageScanner() }: Props) {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let current = true;
    void scanner.available().then((yes) => current && setAvailable(yes));
    return () => {
      current = false;
    };
  }, [scanner]);
  return available ? <DescribePanel onDescribed={onDescribed} scanner={scanner} /> : null;
}

type Picker = { showDirectoryPicker(options?: { mode?: "read" }): Promise<DirectoryHandleLike> };

/** The folder chosen, or null when the researcher closed the picker without choosing. */
async function pickDirectory(): Promise<ChosenFolder | null> {
  try {
    const handle = await (window as unknown as Picker).showDirectoryPicker({ mode: "read" });
    return await fromDirectoryHandle(handle);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return null;
    throw error;
  }
}

function DescribePanel({ onDescribed, scanner }: Required<Props>) {
  const heading = useId();
  const { scan, start, cancel, fail } = useFolderScan(scanner, onDescribed);
  const [dropping, setDropping] = useState(false);

  const choose = async (pick: () => Promise<ChosenFolder | null>) => {
    try {
      const folder = await pick();
      if (folder) start(folder);
    } catch (error) {
      fail(error instanceof NotAFolder ? error.message : "The folder could not be read.");
    }
  };

  const onDragOver = (event: DragEvent<HTMLElement>) => {
    if (scan.status !== "idle" || !event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(true);
  };
  const onDrop = (event: DragEvent<HTMLElement>) => {
    if (scan.status !== "idle" || !event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(false);
    // Entries are only to be had while the drop event lasts.
    const entries = Array.from(event.dataTransfer.items, (item) => item.webkitGetAsEntry());
    void choose(() => fromEntries(entries as (EntryLike | null)[]));
  };

  return (
    // Dropping a folder is a shortcut for the Choose a folder button, which keyboard and screen
    // reader users have, so the section's drag listeners need no role of their own.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <section
      aria-labelledby={heading}
      className={dropping ? "describe-folder dropping" : "describe-folder"}
      onDragOver={onDragOver}
      onDragLeave={() => setDropping(false)}
      onDrop={onDrop}
    >
      <h3 id={heading}>Describe a folder in this browser</h3>
      <p>
        Your browser reads the files in the folder you choose and makes the inventory here. None of
        the files is sent anywhere: only the inventory is attached, after you have checked it.
      </p>
      {scan.status === "scanning" ? (
        <Scanning scan={scan} onCancel={cancel} />
      ) : (
        <>
          {canPickDirectory() ? (
            <Button variant="primary" icon={FolderOpen} onPress={() => void choose(pickDirectory)}>
              Choose a folder…
            </Button>
          ) : (
            <FileTrigger
              acceptDirectory
              allowsMultiple
              onSelect={(files) =>
                files && void choose(async () => fromFileList(Array.from(files)))
              }
            >
              <Button variant="primary" icon={FolderOpen}>
                Choose a folder…
              </Button>
            </FileTrigger>
          )}
          {/* Said in the assertive region already (useFolderScan), so not an alert again. */}
          {scan.error && <p className="describe-folder-error">{scan.error}</p>}
        </>
      )}
      <p className="describe-folder-notices">
        It runs fido with The National Archives&rsquo; PRONOM signatures in Pyodide. {OGL}{" "}
        <a href={NOTICES_PATH}>Licence notices</a>
      </p>
    </section>
  );
}

function Scanning({
  scan,
  onCancel,
}: {
  scan: Extract<FolderScan, { status: "scanning" }>;
  onCancel: () => void;
}) {
  const label = useId();
  const { progress } = scan;
  return (
    <div className="describe-folder-scanning">
      <p id={label}>
        Describing {scan.folder}: {STAGE_TEXT[scan.stage]}
        {progress && ` ${progress.done} of ${progress.total} files.`}
      </p>
      {progress ? (
        <progress aria-labelledby={label} max={progress.total} value={progress.done} />
      ) : (
        <progress aria-labelledby={label} />
      )}
      {progress && <p className="describe-folder-file">{progress.path}</p>}
      <Button icon={X} onPress={onCancel}>
        Cancel
      </Button>
    </div>
  );
}
