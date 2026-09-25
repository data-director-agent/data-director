// Inspect: run one agent on one input, or reload a stored run, and show its envelope.
// ?invocation_id=… reloads a run.
import { $, el, inputs, rememberInput, copyButton, fmtTime, shortId, statusPill, kvList, inspectLink, chatLink, parseSse, newRequest, postRun } from "./common.js";
import { closeTip, help } from "./help.js";
import { agents, unavailable, samples, loadRegistry, renderAgents, renderAgentDetail } from "./registry.js";
import { payloadView } from "./payload.js";

// The payload fragment comes from the agent's manifest entry, so a new payload class renders
// as soon as its agent ships a fragment. A replayed run uses its own agent's fragment.
let schema, current = null;
const showPayload = payloadView($("form"));

function payloadSchema(payload) {
  const def = payload && schema.$defs?.[payload.schema_class];
  return def ? { ...def, $defs: schema.$defs } : null;
}

// A link to another run that loads it in place, and still works opened in a new tab.
function runLink(id, text) {
  const a = inspectLink(id, text);
  a.addEventListener("click", (e) => {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault(); history.pushState(null, "", `?invocation_id=${id}`); replay(id);
  });
  return a;
}
function qualifier(key, value) {
  return el("span", { className: "qualifier" }, el("code", { textContent: key }), help(key), value);
}
function fact(key, value, helpKeys = key) {
  return el("div", {}, el("dt", {}, key, help(helpKeys)), el("dd", {}, value));
}
function collectCited(node, out = new Set()) {
  if (Array.isArray(node)) node.forEach((n) => collectCited(n, out));
  else if (node && typeof node === "object") {
    if (Array.isArray(node.grounded_on)) for (const g of node.grounded_on) out.add(g.content_hash);
    Object.values(node).forEach((v) => collectCited(v, out));
  }
  return out;
}

// --- Rendering --------------------------------------------------------------------------
function render(envelope) {
  current = envelope;
  closeTip();
  $("empty").hidden = true; $("result").hidden = false;
  const o = envelope.outcome;

  // The answer first (status and statement), then the run's identifying facts in a grid.
  $("outcome-head").replaceChildren(
    el("span", { className: "status" }, statusPill(o.status), help(`status:${o.status}`)),
    el("p", { className: "statement", textContent: o.statement }),
    o.reason_code ? qualifier("reason_code", el("code", { textContent: o.reason_code })) : "",
    o.referred_to ? qualifier("referred_to", el("code", { textContent: o.referred_to })) : "");
  $("facts").replaceChildren(
    fact("agent", el("code", { textContent: `${envelope.agent_id}@${envelope.agent_version}` }), "agent_version"),
    fact("grounding_mode", el("span", { className: "chip", textContent: envelope.grounding_mode }), ["grounding_mode", `mode:${envelope.grounding_mode}`]),
    fact("completed_at", el("span", { textContent: fmtTime(envelope.completed_at), title: envelope.completed_at })),
    fact("invocation_id", el("span", {}, el("code", { textContent: envelope.invocation_id }), " ", copyButton(envelope.invocation_id))),
    envelope.requires_human_review ? fact("requires_human_review", el("code", { textContent: "true" }), "human-review") : "",
    envelope.conversation_id ? fact("conversation_id", el("span", {}, chatLink(envelope.conversation_id), " ", copyButton(envelope.conversation_id))) : "",
    envelope.parent_invocation_id ? fact("parent_invocation_id", runLink(envelope.parent_invocation_id, envelope.parent_invocation_id)) : "",
    envelope.delegations?.length ? fact("delegations", el("span", { className: "delegation-list" },
      ...envelope.delegations.map((d) => el("span", {}, runLink(d.delegated_invocation_id, `${d.delegated_agent_id}@${d.delegated_agent_version}`), " ", statusPill(d.delegated_status)))), "delegation") : "");
  const p = $("problem"); p.replaceChildren();
  if (envelope.problem) p.append(el("div", { className: "problem", role: "alert" }, el("h3", {}, "Problem", help("problem")), kvList(envelope.problem)));

  // Input: known only for runs started from this tab; the envelope stores its hash, not the input.
  const input = inputs.get(envelope.invocation_id);
  const inputEvidence = (envelope.evidence || []).find((e) => e.source_id === `input:${envelope.invocation_id}`);
  $("input-class").textContent = input?.schema_class || "";
  $("input").replaceChildren(input ? kvList(input) : el("p", { className: "muted" },
    "Input not stored with the envelope.",
    inputEvidence ? el("br") : null,
    inputEvidence ? el("span", { className: "hash", textContent: `${inputEvidence.hash_algorithm}:${inputEvidence.content_hash}` }) : null));
  $("tab-input").hidden = !input;
  $("input-json").textContent = input ? JSON.stringify(input, null, 2) : "";

  // Payload: schema-driven through RJSF with the agent's fragment.
  const payload = envelope.payload;
  $("payload-class").textContent = payload?.schema_class || "";
  showPayload(payload, payloadSchema(payload), agents[envelope.agent_id]?.uischema || {});

  // Evidence, with a cross-check against the payload's grounded_on hashes.
  const cited = collectCited(payload);
  const rows = (envelope.evidence || []).map((e) => {
    const src = e.source_uri ? el("a", { href: e.source_uri, target: "_blank", rel: "noopener", textContent: e.source_id })
      : e.source_id.startsWith("invocation:") ? runLink(e.source_id.slice("invocation:".length), e.source_id)
      : el("code", { textContent: e.source_id });
    return el("tr", {},
      el("td", {}, src),
      el("td", {}, cited.has(e.content_hash) ? el("span", { className: "chip", textContent: "cited" }) : el("span", { className: "faint", textContent: "—" })),
      el("td", { title: e.retrieved_at, textContent: fmtTime(e.retrieved_at) }),
      el("td", {}, el("code", { textContent: e.canonicalisation })),
      el("td", {}, e.snapshot_ref ? el("code", { textContent: e.snapshot_ref }) : el("span", { className: "faint", textContent: "—" })),
      el("td", {}, el("span", { className: "hash", title: e.content_hash, textContent: `${e.hash_algorithm}:${e.content_hash.slice(0, 12)}…` }), " ", copyButton(e.content_hash)));
  });
  $("evidence").replaceChildren(rows.length
    ? el("table", {}, el("thead", {}, el("tr", {}, ...["source_id", "cited", "retrieved_at", "canonicalisation", "snapshot_ref", "content_hash"].map((t) => el("th", { scope: "col" }, t, help(t))))), el("tbody", {}, ...rows))
    : el("p", { className: "muted", textContent: "No evidence: this outcome rests on no retrieved record." }));

  const t = envelope.telemetry || {};
  const tel = $("telemetry"); tel.replaceChildren();
  const add = (k, v, helpKey = k) => tel.append(el("dt", {}, k, help(helpKey)), el("dd", {}, v));
  add("trace_id", t.trace_id ? el("span", {}, el("code", { textContent: t.trace_id }), " ", copyButton(t.trace_id)) : el("span", { className: "null", textContent: "null" }));
  add("model_id", t.model_id ? el("code", { textContent: t.model_id }) : el("span", { className: "null", textContent: "null (no model)" }));
  add("tokens in / out", `${t.input_tokens ?? "—"} / ${t.output_tokens ?? "—"}`, "tokens");
  add("energy_estimate_j", t.energy_estimate_j == null ? el("span", { className: "null", textContent: "null" }) : String(t.energy_estimate_j));
  add("energy_method", el("code", { textContent: t.energy_method || "—" }));

  const json = JSON.stringify(envelope, null, 2);
  $("envelope-json").textContent = json;
  const dl = $("download-envelope");
  if (dl.href) URL.revokeObjectURL(dl.href);
  dl.href = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  dl.download = `${envelope.invocation_id}.json`;
  if ($("tab-input").hidden && $("tab-input").getAttribute("aria-selected") === "true") selectTab("tab-overview");

  history.replaceState(null, "", `?invocation_id=${envelope.invocation_id}`);
  markCurrentRun();
}

// --- Tabs -------------------------------------------------------------------------------
const tabIds = ["tab-overview", "tab-envelope", "tab-input"];
function selectTab(id) {
  for (const t of tabIds) {
    const on = t === id;
    $(t).setAttribute("aria-selected", String(on));
    $(t).tabIndex = on ? 0 : -1;
    $($(t).getAttribute("aria-controls")).hidden = !on;
  }
}
for (const t of tabIds) {
  $(t).addEventListener("click", () => selectTab(t));
  $(t).addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const visible = tabIds.filter((x) => !$(x).hidden);
    const next = visible[(visible.indexOf(t) + (e.key === "ArrowRight" ? 1 : visible.length - 1)) % visible.length];
    selectTab(next); $(next).focus();
  });
}
$("copy-envelope").addEventListener("click", () => navigator.clipboard.writeText($("envelope-json").textContent));
$("copy-input").addEventListener("click", () => navigator.clipboard.writeText($("input-json").textContent));

// --- Transport --------------------------------------------------------------------------
async function replay(id) {
  $("status").textContent = `Loading ${shortId(id)}…`;
  const r = await fetch(`/agui/runs/${id}`);
  const fin = parseSse(await r.text()).find((e) => e.type === "RUN_FINISHED");
  if (!fin) { $("status").textContent = `No stored run ${id}`; return; }
  render(fin.result);
  $("status").textContent = `Showing ${shortId(id)}`;
}

async function run(agentId, sampleName) {
  const button = $("run");
  button.disabled = true; button.textContent = "Running…";
  $("status").textContent = `Running ${agentId} on ${sampleName}…`;
  try {
    const input = await (await fetch(`/samples/${encodeURIComponent(sampleName)}`)).json();
    const { envelope, error } = await postRun(newRequest(agentId, input));
    if (!envelope) { $("status").textContent = `Error: ${error}`; return; }
    const fin = { result: envelope };
    rememberInput(fin.result.invocation_id, input);
    await loadRuns();
    render(fin.result);
    $("status").textContent = `Completed ${shortId(fin.result.invocation_id)}`;
  } finally {
    button.textContent = "Run"; refreshRunButton();
  }
}

// --- Controls ---------------------------------------------------------------------------
async function loadRuns() {
  const runs = await (await fetch("/runs")).json();
  const list = $("history"); list.replaceChildren();
  if (!runs.length) list.append(el("li", { className: "muted", textContent: "None yet." }));
  for (const r of runs) {
    const dot = el("span", { className: "dot", title: r.status }); dot.dataset.status = r.status;
    const b = el("button", { type: "button", title: `${r.status} · ${r.invocation_id}` },
      dot, el("span", { className: "mono", textContent: r.agent_id }),
      el("span", { className: "id", textContent: `${fmtTime(r.completed_at)} · ${shortId(r.invocation_id)}` }));
    b.dataset.id = r.invocation_id;
    b.append(el("span", { className: "visually-hidden", textContent: ` ${r.status}` }));
    b.addEventListener("click", () => replay(r.invocation_id));
    list.append(el("li", {}, b));
  }
  markCurrentRun();
}
function markCurrentRun() {
  for (const b of $("history").querySelectorAll("button")) b.setAttribute("aria-current", String(b.dataset.id === current?.invocation_id));
}
const selectedAgent = () => $("agent-select").value;

// Samples are filtered to the input classes the chosen agent accepts, so the mismatch path
// is reachable only deliberately (via the CLI or A2A), not by accident here.
function refreshSamples() {
  const agent = agents[selectedAgent()];
  const sel = $("sample-select");
  sel.replaceChildren();
  if (!agent) sel.append(new Option(selectedAgent() in unavailable ? "Agent unavailable" : "Choose an agent first", ""));
  else {
    const fit = samples.filter((s) => agent.accepts.includes(s.schema_class));
    if (!fit.length) sel.append(new Option("No sample accepted by this agent", ""));
    for (const s of fit) sel.append(new Option(`${s.name} — ${s.schema_class}`, s.name));
  }
  refreshRunButton();
}
function refreshRunButton() {
  $("run").disabled = !(agents[selectedAgent()] && $("sample-select").value);
}

async function main() {
  [schema] = await Promise.all([
    fetch("/schema/envelope.schema.json").then((r) => r.json()),
    loadRegistry(),
  ]);
  renderAgents($("agent-select"));
  $("agent-select").addEventListener("change", () => { renderAgentDetail(selectedAgent(), $("agent-detail")); refreshSamples(); });
  refreshSamples();
  $("sample-select").addEventListener("change", refreshRunButton);
  $("run").addEventListener("click", () => run(selectedAgent(), $("sample-select").value));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
    if (!$("run").disabled) run(selectedAgent(), $("sample-select").value);
  });
  addEventListener("popstate", () => {
    const id = new URLSearchParams(location.search).get("invocation_id");
    if (id) replay(id);
  });
  await loadRuns();

  const id = new URLSearchParams(location.search).get("invocation_id");
  if (id) await replay(id); else $("status").textContent = "Ready.";
}
main().catch((e) => { $("status").textContent = `Error: ${e.message}`; console.error(e); });
