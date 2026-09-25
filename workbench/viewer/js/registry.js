// The registry manifest (GET /agents) and the samples listing (GET /samples), shared by both
// pages. The objects are filled in place by loadRegistry, so importers read them directly.
import { el } from "./common.js";
import { help } from "./help.js";

export const agents = {}, unavailable = {}, incompatible = {}, samples = [];
export async function loadRegistry() {
  const [manifest, listing] = await Promise.all([
    fetch("/agents").then((r) => r.json()),
    fetch("/samples").then((r) => r.json()),
  ]);
  for (const a of manifest.agents) agents[a.agent_id] = a;
  Object.assign(unavailable, manifest.unavailable || {});
  Object.assign(incompatible, manifest.incompatible || {});
  samples.push(...listing);
}

// The schema of class `cls` as agent `id`'s card carries it, or null (ADR-0019).
export function classSchema(id, cls) {
  return agents[id]?.schemas?.[cls]?.json_schema || null;
}

// One option per agent, grouped by the id prefix before the first dot, so the picker stays
// one line tall however many agents the registry holds. Unavailable and incompatible agents stay
// selectable so their reason can be read in the detail card; Run and Send stay disabled for them.
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
  const other = Object.keys(incompatible).sort(byId);
  if (other.length) sel.append(el("optgroup", { label: "Incompatible" }, ...other.map((id) => new Option(id, id))));
}
// Why a registered name cannot be run, or null if it can.
export function notRunnable(id) {
  if (id in incompatible) return { state: "Incompatible", reason: incompatible[id], term: "incompatible" };
  if (id in unavailable) return { state: "Unavailable", reason: unavailable[id], term: "unavailable" };
  return null;
}
export function renderAgentDetail(id, box) {
  const a = agents[id];
  const down = notRunnable(id);
  box.toggleAttribute("data-unavailable", down !== null);
  box.hidden = !id;
  if (a) box.replaceChildren(
    el("p", { className: "desc", textContent: a.description }),
    el("div", { className: "meta" },
      el("span", {}, el("span", { className: "chip", textContent: a.grounding_mode }), help(["grounding_mode", `mode:${a.grounding_mode}`])),
      el("span", {}, `accepts ${a.accepts.join(", ")}`, help("accepts")),
      ...a.requirement_ids.map((r) => el("span", { className: "chip", textContent: r })),
      a.requirement_ids.length ? help("requirement") : null));
  else box.replaceChildren(el("p", { className: "desc" }, down ? `${down.state}: ${down.reason}` : "", down ? help(down.term) : null));
}

// The input-class picker, shown only when the agent accepts more than one class. A class kept
// from before stays chosen if the agent still accepts it.
export function renderClasses(sel, row, agent) {
  const kept = sel.value;
  const classes = agent ? agent.accepts : [];
  sel.replaceChildren(...classes.map((c) => new Option(c, c)));
  if (classes.includes(kept)) sel.value = kept;
  row.hidden = classes.length < 2;
}
// "Start from": a blank form, or one of the samples of the chosen class. The first sample is
// chosen unless the one chosen before still fits.
export function renderSamples(sel, cls) {
  const kept = sel.value;
  const fit = samples.filter((s) => s.schema_class === cls);
  sel.replaceChildren(new Option(cls ? `Blank ${cls}` : "Choose an agent first", ""), ...fit.map((s) => new Option(s.name, s.name)));
  sel.value = fit.some((s) => s.name === kept) ? kept : fit[0]?.name || "";
}
export async function fetchSample(name) {
  return name ? (await fetch(`/samples/${encodeURIComponent(name)}`)).json() : null;
}
