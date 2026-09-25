// The registry manifest (GET /agents) and the samples listing (GET /samples), shared by both
// pages. The objects are filled in place by loadRegistry, so importers read them directly.
import { el } from "./common.js";
import { help } from "./help.js";

export const agents = {}, unavailable = {}, samples = [];
export async function loadRegistry() {
  const [manifest, listing] = await Promise.all([
    fetch("/agents").then((r) => r.json()),
    fetch("/samples").then((r) => r.json()),
  ]);
  for (const a of manifest.agents) agents[a.agent_id] = a;
  Object.assign(unavailable, manifest.unavailable || {});
  samples.push(...listing);
}

// One option per agent, grouped by the id prefix before the first dot, so the picker stays
// one line tall however many agents the registry holds. Unavailable agents stay selectable so
// their reason can be read in the detail card; Run and Send stay disabled for them.
export function renderAgents(sel) {
  const byId = (a, b) => a.localeCompare(b);
  const groups = Map.groupBy(Object.keys(agents).sort(byId), (id) => id.split(".")[0]);
  sel.replaceChildren(new Option("Choose an agent", ""));
  for (const prefix of [...groups.keys()].sort(byId)) {
    sel.append(el("optgroup", { label: prefix },
      ...groups.get(prefix).map((id) => new Option(`${id}  ${agents[id].version}`, id))));
  }
  const down = Object.keys(unavailable).sort(byId);
  if (down.length) sel.append(el("optgroup", { label: "Unavailable" }, ...down.map((id) => new Option(id, id))));
}
export function renderAgentDetail(id, box) {
  const a = agents[id];
  box.toggleAttribute("data-unavailable", id in unavailable);
  box.hidden = !id;
  if (a) box.replaceChildren(
    el("p", { className: "desc", textContent: a.description }),
    el("div", { className: "meta" },
      el("span", {}, el("span", { className: "chip", textContent: a.grounding_mode }), help(["grounding_mode", `mode:${a.grounding_mode}`])),
      el("span", {}, `accepts ${a.accepts.join(", ")}`, help("accepts")),
      ...a.requirement_ids.map((r) => el("span", { className: "chip", textContent: r })),
      a.requirement_ids.length ? help("requirement") : null));
  else box.replaceChildren(el("p", { className: "desc" }, id ? `Unavailable: ${unavailable[id]}` : "", id ? help("unavailable") : null));
}
