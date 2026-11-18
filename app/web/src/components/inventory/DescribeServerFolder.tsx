/**
 * **Describe a folder on this computer**, offered in Make an inventory (MakeInventoryDialog.tsx,
 * docs/specs/app.md) only by an app installed on the researcher's own machine whose operator named
 * folders it may read (`DD_INVENTORY_FOLDERS`, `src/scan/serverFolders.ts`). The researcher opens
 * one of those folders and steps into its subfolders, which are listed by name only; the app then
 * describes the folder chosen with `dd-inventory` and hands the inventory on as
 * `<folder>-inventory.json`, so that it goes through the check before attaching (#472) like any
 * other. The shared deployment names no folder, and the section is not shown.
 */

import { Folder, FolderSearch, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { pageServerFolders, type ServerFolders } from "../../scan/serverFolders";
import { Button } from "../ui/Button";
import { useAnnounce } from "../ui/Announcer";

interface Props {
  /** Called with the inventory made, as `<folder>-inventory.json`. */
  onDescribed: (file: File) => void;
  folders?: ServerFolders;
}

export function DescribeServerFolder({ onDescribed, folders = pageServerFolders() }: Props) {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let current = true;
    void folders.available().then((yes) => current && setAvailable(yes));
    return () => {
      current = false;
    };
  }, [folders]);
  return available ? <Browser onDescribed={onDescribed} folders={folders} /> : null;
}

/** Where the researcher is: a listed folder and the path under it, or none chosen yet. */
interface Place {
  root: string | null;
  path: string[];
}

type Listed = { folders: string[] } | { error: string };

/** What is listed at `place`, or null while it is being listed. */
function useListing(folders: ServerFolders, place: Place): Listed | null {
  const { root } = place;
  const path = place.path.join("/");
  const key = `${root ?? ""}\u0000${path}`;
  const [listed, setListed] = useState<{ key: string; listed: Listed } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const found =
      root === null
        ? folders.roots(controller.signal)
        : folders.list(root, path, controller.signal).then((l) => l.folders);
    found.then(
      (names) => setListed({ key, listed: { folders: names } }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "It could not be listed.";
        setListed({ key, listed: { error: message } });
      },
    );
    return () => controller.abort();
  }, [folders, root, path, key]);
  return listed?.key === key ? listed.listed : null;
}

function Browser({ onDescribed, folders }: Required<Props>) {
  const heading = useId();
  const announce = useAnnounce();
  const [place, setPlace] = useState<Place>({ root: null, path: [] });
  const [describing, setDescribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = useRef<AbortController | null>(null);
  const shown = useListing(folders, place);
  useEffect(() => () => running.current?.abort(), []);

  const here = place.root === null ? null : (place.path.at(-1) ?? place.root);
  const open = (name: string) =>
    setPlace((p) =>
      p.root === null ? { root: name, path: [] } : { ...p, path: [...p.path, name] },
    );

  const describe = async () => {
    if (place.root === null || here === null) return;
    const controller = new AbortController();
    running.current = controller;
    setError(null);
    setDescribing(true);
    announce(`Describing ${here}.`);
    try {
      const text = await folders.describe(place.root, place.path.join("/"), controller.signal);
      announce(`Described ${here}.`);
      onDescribed(
        new File([text], `${here}-inventory.json`, {
          type: "application/json",
        }),
      );
    } catch (failure) {
      if (controller.signal.aborted) {
        announce("Stopped describing the folder.");
      } else {
        const message = failure instanceof Error ? failure.message : "It could not be described.";
        setError(message);
        announce(message, { assertive: true });
      }
    } finally {
      running.current = null;
      setDescribing(false);
    }
  };

  return (
    <section aria-labelledby={heading} className="describe-folder">
      <h3 id={heading}>Describe a folder on this computer</h3>
      <p>
        Data Director runs here, on your own computer, and may read the folders listed below. It
        makes the inventory here, reading the files but changing none of them.
      </p>
      <Trail place={place} onGo={setPlace} />
      {describing ? (
        <div className="describe-folder-scanning">
          <p>Describing {here}…</p>
          <progress aria-label={`Describing ${here}`} />
          <Button icon={X} onPress={() => running.current?.abort()}>
            Cancel
          </Button>
        </div>
      ) : (
        <>
          <Listing shown={shown} onOpen={open} />
          {here !== null && (
            <Button variant="primary" icon={FolderSearch} onPress={() => void describe()}>
              Describe {here}
            </Button>
          )}
          {error && <p className="describe-folder-error">{error}</p>}
        </>
      )}
    </section>
  );
}

/** The way back up: the listed folders, then each folder opened on the way here. */
function Trail({ place, onGo }: { place: Place; onGo: (place: Place) => void }) {
  if (place.root === null) return null;
  const { root } = place;
  const steps: { label: string; place: Place }[] = [
    { label: "All folders", place: { root: null, path: [] } },
    { label: root, place: { root, path: [] } },
    ...place.path.map((name, i) => ({
      label: name,
      place: { root, path: place.path.slice(0, i + 1) },
    })),
  ];
  return (
    <nav aria-label="Folder">
      <ol className="describe-folder-trail">
        {steps.map((step, i) =>
          i === steps.length - 1 ? (
            <li key={i} aria-current="location">
              {step.label}
            </li>
          ) : (
            <li key={i}>
              <Button size="small" onPress={() => onGo(step.place)}>
                {step.label}
              </Button>
            </li>
          ),
        )}
      </ol>
    </nav>
  );
}

function Listing({ shown, onOpen }: { shown: Listed | null; onOpen: (name: string) => void }) {
  if (shown === null) return <p>Listing folders…</p>;
  if ("error" in shown) return <p className="describe-folder-error">{shown.error}</p>;
  if (shown.folders.length === 0) return <p>It holds no other folders.</p>;
  return (
    <ul className="describe-folder-list" aria-label="Folders">
      {shown.folders.map((name) => (
        <li key={name}>
          <Button size="small" icon={Folder} onPress={() => onOpen(name)}>
            {name}
          </Button>
        </li>
      ))}
    </ul>
  );
}
