/**
 * A button that opens an inventory in readable form, in a modal dialog. The inventory is the one
 * in hand or, for a project's, fetched when the dialog opens; a fetched one that is not an
 * inventory is said to be so rather than drawn.
 */

import type { FileInventory } from "@data-director/inventory";
import { Eye } from "lucide-react";
import { useEffect, useState } from "react";

import { inventoryFrom, type InventorySource } from "../../conversation/inventory";
import { Button } from "../ui/Button";
import { DialogTrigger, ModalDialog } from "../ui/Dialog";
import { InventoryView } from "./InventoryView";

export function InventoryDialog({ source }: { source: InventorySource }) {
  return (
    <DialogTrigger>
      <Button size="small" variant="quiet" icon={Eye}>
        View inventory
      </Button>
      <ModalDialog title="What the inventory holds">
        <Loaded source={source} />
      </ModalDialog>
    </DialogTrigger>
  );
}

type State =
  | { status: "loading" }
  | { status: "ready"; inventory: FileInventory }
  | { status: "failed"; message: string };

function Loaded({ source }: { source: InventorySource }) {
  const [state, setState] = useState<State>(() =>
    "document" in source ? { status: "ready", inventory: source.document } : { status: "loading" },
  );
  useEffect(() => {
    if ("document" in source) return;
    const controller = new AbortController();
    inventoryFrom(source, controller.signal).then(
      (inventory) => setState({ status: "ready", inventory }),
      (e: unknown) => {
        if (controller.signal.aborted) return;
        const detail = e instanceof Error ? e.message : String(e);
        setState({ status: "failed", message: `The inventory could not be read: ${detail}` });
      },
    );
    return () => controller.abort();
  }, [source]);
  if (state.status === "loading") return <p role="status">Reading the inventory…</p>;
  if (state.status === "failed") return <p role="alert">{state.message}</p>;
  return <InventoryView inventory={state.inventory} />;
}
