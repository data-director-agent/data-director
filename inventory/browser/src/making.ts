/**
 * How a researcher makes an inventory with `dd-inventory`, in words. The text is in
 * `making.json`, which the user guide's "Making an inventory" page also renders (docs/hooks_inventory.py),
 * so that the app and the guide say the same thing.
 */

import making from "./making.json";

/** An operating system the instructions cover. */
export type SystemId = "windows" | "macos" | "linux";

export interface SystemInstructions {
  id: SystemId;
  /** The system's name, as a tab shows it. */
  name: string;
  /** How to open a terminal on it. */
  terminal: string;
  /** The command that installs uv. */
  install: string;
  /** The command that makes the inventory, with a placeholder path to replace. */
  run: string;
}

export interface MakingAnInventory {
  /** One sentence: what an inventory is, and that the data stay on the researcher's computer. */
  summary: string;
  /** uv's own installation page. */
  uvGuide: string;
  systems: SystemInstructions[];
  /** What each step says, the same on every system. */
  steps: { install: string; run: string; after: string };
}

export const MAKING_AN_INVENTORY: MakingAnInventory = making as MakingAnInventory;

/**
 * The system a browser runs on, from `navigator.userAgentData.platform` or `navigator.platform`
 * (either may be given), or `null` when it is none of those covered, such as a phone.
 */
export function systemFromPlatform(platform: string | undefined): SystemId | null {
  const p = (platform ?? "").toLowerCase();
  if (p.startsWith("win")) return "windows";
  if (p.startsWith("mac")) return "macos";
  if (p.includes("linux") && !p.includes("android")) return "linux";
  return null;
}
