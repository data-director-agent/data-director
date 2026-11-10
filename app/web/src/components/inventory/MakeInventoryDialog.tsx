/**
 * The **Make an inventory** button and its dialog, beside Attach a file (#553). The dialog says
 * in one sentence what an inventory is, then how to make one with `dd-inventory` on each
 * operating system, a tab apiece with the browser's own selected, each command with a button that
 * copies it. It ends at the file picker, so the researcher goes straight on to attach what they
 * made, and links to the user guide for more.
 *
 * The text is `@data-director/inventory`'s `MAKING_AN_INVENTORY`, which the user guide renders
 * too (docs/hooks_inventory.py), so the two say the same. The dialog names no agent and holds no
 * policy.
 *
 * TODO(#367): once the browser scanner exists, its first choice is to describe a folder in this
 * browser, and the command becomes the route for data on a server or a cluster.
 */

import {
  MAKING_AN_INVENTORY,
  systemFromPlatform,
  type SystemId,
  type SystemInstructions,
} from "@data-director/inventory";
import { Copy, FilePlus2, Paperclip } from "lucide-react";
import { useId, useState } from "react";
import { FileTrigger } from "react-aria-components";

import { INVENTORY_GUIDE } from "../../conversation/inventory";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";
import { Tab, TabList, TabPanel, Tabs } from "../ui/Tabs";
import "./MakeInventoryDialog.css";

/** The system this browser runs on, or null when the browser does not say or it is not covered. */
export function browserSystem(nav: Navigator | undefined = globalThis.navigator): SystemId | null {
  if (!nav) return null;
  const hints = (nav as Navigator & { userAgentData?: { platform?: string } }).userAgentData;
  return systemFromPlatform(hints?.platform || nav.platform);
}

export function MakeInventoryDialog({
  onAttach,
  isDisabled = false,
}: {
  /** Called with the file chosen at the end of the dialog, which then closes. */
  onAttach: (file: File) => void;
  isDisabled?: boolean;
}) {
  return (
    <DialogTrigger>
      <Button icon={FilePlus2} isDisabled={isDisabled}>
        Make an inventory
      </Button>
      <ModalDialog title="Make an inventory">
        {(close) => (
          <MakeInventory
            onAttach={(file) => {
              close();
              onAttach(file);
            }}
          />
        )}
      </ModalDialog>
    </DialogTrigger>
  );
}

function MakeInventory({ onAttach }: { onAttach: (file: File) => void }) {
  const { summary, systems } = MAKING_AN_INVENTORY;
  const [detected] = useState(browserSystem);
  const attachHeading = useId();
  return (
    <div className="make-inventory">
      <p>{summary}</p>
      <p>Make it on the computer where your data are, following the steps for its system.</p>
      <Tabs defaultSelectedKey={detected ?? systems[0]?.id ?? "windows"}>
        <TabList aria-label="Operating system">
          {systems.map((s) => (
            <Tab key={s.id} id={s.id}>
              {s.name}
              {s.id === detected && <span className="visually-hidden">, this computer</span>}
            </Tab>
          ))}
        </TabList>
        {systems.map((s) => (
          <TabPanel key={s.id} id={s.id}>
            <Steps system={s} />
          </TabPanel>
        ))}
      </Tabs>
      <section aria-labelledby={attachHeading}>
        <h3 id={attachHeading}>Attach it</h3>
        <p>When the command has finished, choose the file it wrote to attach it to your message.</p>
        <FileTrigger
          acceptedFileTypes={["application/json", ".json"]}
          onSelect={(files) => {
            const file = files?.[0];
            if (file) onAttach(file);
          }}
        >
          <Button variant="primary" icon={Paperclip}>
            Choose inventory.json
          </Button>
        </FileTrigger>
      </section>
      <p>
        <a href={INVENTORY_GUIDE}>More about inventories in the user guide</a>
      </p>
    </div>
  );
}

function Steps({ system }: { system: SystemInstructions }) {
  const { steps, uvGuide } = MAKING_AN_INVENTORY;
  return (
    <>
      <ol className="make-inventory-steps">
        <li>{system.terminal}</li>
        <li>
          <p>
            {steps.install} <a href={uvGuide}>About installing uv</a>
          </p>
          <Command command={system.install} label={`Copy the command that installs uv on ${system.name}`} />
        </li>
        <li>
          <p>{steps.run}</p>
          <Command command={system.run} label={`Copy the command that makes the inventory on ${system.name}`} />
        </li>
      </ol>
      <p>{steps.after}</p>
    </>
  );
}

/** A command to type, with a button that copies it exactly and says whether it did. */
function Command({ command, label }: { command: string; label: string }) {
  const [said, setSaid] = useState<string | null>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setSaid("Copied.");
    } catch {
      setSaid("Could not copy; select the command instead.");
    }
  }
  return (
    <div className="make-inventory-command">
      <pre>
        <code>{command}</code>
      </pre>
      <Button variant="quiet" size="small" icon={Copy} aria-label={label} onPress={() => void copy()}>
        Copy
      </Button>
      <span role="status">{said}</span>
    </div>
  );
}
