// Agents: browse the registry the workbench built at start-up (docs/registry.md). Read-only;
// no run or send lives here. ?agent_id=… selects an entry.
import { $, el, wireCopy, kvList } from "./common.js";
import { help } from "./help.js";
import { agents, unavailable, incompatible, notRunnable, loadRegistry, groupedAgents } from "./registry.js";

let current = null;

function statusChip(state) {
  return el("span", { className: "chip", textContent: state });
}

function renderList() {
  const { groups, unavailable: down, incompatible: other } = groupedAgents();
  const list = $("agent-list");
  list.replaceChildren();
  const row = (id, label) => {
    const b = el("button", { type: "button" }, statusChip(notRunnable(id)?.state || "available"), el("span", { className: "mono", textContent: label }));
    b.dataset.id = id;
    b.addEventListener("click", () => select(id));
    return el("li", {}, b);
  };
  for (const [, ids] of groups) for (const id of ids) list.append(row(id, `${id}  ${agents[id].version}`));
  for (const id of down) list.append(row(id, id));
  for (const id of other) list.append(row(id, id));
  if (!list.children.length) list.append(el("li", { className: "muted", textContent: "No agents registered." }));
  markCurrent();
}
function markCurrent() {
  for (const b of $("agent-list").querySelectorAll("button")) b.setAttribute("aria-current", String(b.dataset.id === current));
}

async function select(id) {
  current = id;
  markCurrent();
  history.replaceState(null, "", `?agent_id=${encodeURIComponent(id)}`);
  $("agent-empty").hidden = true;
  $("agent-result").hidden = false;

  const down = notRunnable(id);
  if (down) {
    $("agent-status-head").replaceChildren(el("p", {}, statusChip(down.state), " ", down.reason, " ", help(down.term)));
    $("agent-spec-panel").hidden = true;
    $("agent-card-panel").hidden = true;
    return;
  }
  $("agent-status-head").replaceChildren(el("p", {}, statusChip("available"), ` registered as ${id}`));
  $("agent-spec-panel").hidden = false;
  $("agent-card-panel").hidden = false;
  $("agent-spec").replaceChildren(el("p", { className: "muted", textContent: "Loading…" }));
  $("agent-card-json").textContent = "";

  const r = await fetch(`/agents/${encodeURIComponent(id)}`);
  if (current !== id) return; // superseded by a later choice
  if (!r.ok) { $("agent-spec").replaceChildren(el("p", { className: "muted", textContent: `No detail for ${id}.` })); return; }
  const { card, spec } = await r.json();
  $("agent-spec").replaceChildren(kvList(spec));
  $("agent-card-json").textContent = card ? JSON.stringify(card, null, 2) : "";
  wireCopy($("copy-card"), () => $("agent-card-json").textContent);
}

async function main() {
  await loadRegistry();
  renderList();
  const id = new URLSearchParams(location.search).get("agent_id");
  if (id && (id in agents || id in unavailable || id in incompatible)) await select(id);
}
main().catch((e) => { $("agent-list").replaceChildren(el("li", { className: "muted", textContent: `Error: ${e.message}` })); console.error(e); });
