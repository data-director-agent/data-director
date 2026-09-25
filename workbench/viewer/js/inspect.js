// Inspect: run one agent on one input, or reload a stored run, and show its envelope.
// ?invocation_id=… reloads a run.
import { $, el, icon, statusIcon, wireCopy, inputs, rememberInput, copyButton, fmtTime, shortId, statusPill, kvList, inspectLink, chatLink, parseSse, newRequest, postRun } from "./common.js";
import { closeTip, help } from "./help.js";
import { agents, classSchema, notRunnable, loadRegistry, renderAgents, renderAgentDetail, renderClasses, renderSamples, fetchSample } from "./registry.js";
import { payloadView } from "./payload.js";
import { inputForm } from "./inputform.js";

// A payload renders from the class schema it was checked against: the envelope names its digest
// and the run store keeps it (ADR-0019), so a new payload class renders as soon as its agent is
// registered, and a stored run still renders after its agent's card has changed. A run stored
// before digests were recorded has none and is shown as JSON.
let current = null;
const showPayload = payloadView($("form"));
const editor = inputForm($("input-form"));
const schemas = new Map();  // digest -> Promise of the schema, or of null

function payloadSchema(envelope) {
  const digest = envelope.payload_schema;
  if (!digest) return Promise.resolve(null);
  if (!schemas.has(digest)) {
    schemas.set(digest, fetch(`/schema/sha256/${digest}`).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  }
  return schemas.get(digest);
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
const FACT_ICONS = { delegations: "git-branch", parent_invocation_id: "corner-down-right" };
function fact(key, value, helpKeys = key) {
  return el("div", {}, el("dt", {}, FACT_ICONS[key] ? icon(FACT_ICONS[key]) : null, key, help(helpKeys)), el("dd", {}, value));
}
// Whom the run acted for (ADR-0018): the name, the identifier (a link if it is a web address), and
// how the workbench came to know it. Runs stored before ADR-0018 name no one and show no fact.
function actingFor(p) {
  const id = /^https?:/.test(p.principal_id)
    ? el("a", { href: p.principal_id, target: "_blank", rel: "noopener", textContent: p.principal_id })
    : el("code", { textContent: p.principal_id });
  return el("span", {}, p.name, " ", id, " ", el("span", { className: "chip", textContent: p.assurance }));
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
    envelope.acting_for ? fact("acting_for", actingFor(envelope.acting_for), ["acting_for", `assurance:${envelope.acting_for.assurance}`]) : "",
    fact("grounding_mode", el("span", { className: "chip", textContent: envelope.grounding_mode }), ["grounding_mode", `mode:${envelope.grounding_mode}`]),
    fact("completed_at", el("span", { textContent: fmtTime(envelope.completed_at), title: envelope.completed_at })),
    fact("invocation_id", el("span", {}, el("code", { textContent: envelope.invocation_id }), " ", copyButton(envelope.invocation_id))),
    envelope.requires_human_review ? fact("requires_human_review", el("code", { textContent: "true" }), "human-review") : "",
    envelope.conversation_id ? fact("conversation_id", el("span", {}, chatLink(envelope.conversation_id), " ", copyButton(envelope.conversation_id))) : "",
    envelope.parent_invocation_id ? fact("parent_invocation_id", runLink(envelope.parent_invocation_id, envelope.parent_invocation_id)) : "",
    envelope.delegations?.length ? fact("delegations", el("span", { className: "delegation-list" },
      ...envelope.delegations.map((d) => el("span", {}, runLink(d.delegated_invocation_id, `${d.delegated_agent_id}@${d.delegated_agent_version}`), " ", statusPill(d.delegated_status)))), "delegation") : "");
  const p = $("problem"); p.replaceChildren();
  if (envelope.problem) p.append(el("div", { className: "problem", role: "alert" }, el("h3", {}, icon("triangle-alert"), "Problem", help("problem")), kvList(envelope.problem)));

  // Input: known only for runs started from this tab; the envelope stores its hash, not the input.
  const input = inputs.get(envelope.invocation_id);
  const inputEvidence = (envelope.evidence || []).find((e) => e.source_id === `input:${envelope.invocation_id}`);
  $("input-class").textContent = input?.schema_class || "";
  $("input").replaceChildren(input ? kvList(input) : el("p", { className: "muted" },
    "Input not stored with the envelope.",
    inputEvidence ? el("br") : null,
    inputEvidence ? el("span", { className: "hash" }, icon("fingerprint-pattern"), `${inputEvidence.hash_algorithm}:${inputEvidence.content_hash}`) : null));
  $("tab-input").hidden = !input;
  $("input-json").textContent = input ? JSON.stringify(input, null, 2) : "";

  // Payload: schema-driven through RJSF, badged from the agent's declared derivations.
  const payload = envelope.payload;
  $("payload-class").textContent = payload?.schema_class || "";
  const derivations = agents[envelope.agent_id]?.derivations || {};
  payloadSchema(envelope).then((ps) => {
    if (current === envelope) showPayload(payload, ps, derivations, envelope.evidence || []);
  });

  // Evidence, with a cross-check against the payload's grounded_on hashes.
  const cited = collectCited(payload);
  const rows = (envelope.evidence || []).map((e) => {
    const src = e.source_uri ? el("a", { href: e.source_uri, target: "_blank", rel: "noopener", textContent: e.source_id })
      : e.source_id.startsWith("invocation:") ? runLink(e.source_id.slice("invocation:".length), e.source_id)
      : el("code", { textContent: e.source_id });
    return el("tr", {},
      el("td", {}, src),
      el("td", {}, cited.has(e.content_hash) ? el("span", { className: "chip" }, icon("link"), "cited") : el("span", { className: "faint", textContent: "—" })),
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
wireCopy($("copy-envelope"), () => $("envelope-json").textContent);
wireCopy($("copy-input"), () => $("input-json").textContent);

// --- Transport --------------------------------------------------------------------------
async function replay(id) {
  $("status").textContent = `Loading ${shortId(id)}…`;
  const r = await fetch(`/agui/runs/${id}`);
  const fin = parseSse(await r.text()).find((e) => e.type === "RUN_FINISHED");
  if (!fin) { $("status").textContent = `No stored run ${id}`; return; }
  render(fin.result);
  $("status").textContent = `Showing ${shortId(id)}`;
}

async function run(agentId) {
  if (!editor.validate()) { $("status").textContent = "Not run: correct the input first."; return; }
  const input = editor.value();
  const button = $("run");
  button.disabled = true; button.textContent = "Running…";
  $("status").textContent = `Running ${agentId} on a ${input.schema_class}…`;
  try {
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
    const b = el("button", { type: "button", title: `${r.status} · ${r.invocation_id}` },
      statusIcon(r.status), el("span", { className: "mono", textContent: r.agent_id }),
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

// The form offers only the input classes the chosen agent accepts, so the mismatch path is
// reachable only deliberately (via the CLI or A2A), not by accident here.
let formReady = false, loading = 0;
function refreshClasses() {
  const agent = agents[selectedAgent()];
  renderClasses($("class-select"), $("class-row"), agent);
  if (!agent) {
    $("sample-select").replaceChildren(new Option(notRunnable(selectedAgent()) ? `Agent ${notRunnable(selectedAgent()).state.toLowerCase()}` : "Choose an agent first", ""));
    ++loading; $("input-fieldset").hidden = true; formReady = editor.show(null);
    refreshRunButton();
  } else refreshSamples();
}
function refreshSamples() {
  renderSamples($("sample-select"), $("class-select").value);
  return loadSample();
}
// Fill the form from the chosen sample, or blank; either way the user edits it from there.
async function loadSample() {
  const cls = $("class-select").value, mine = ++loading;
  const doc = await fetchSample($("sample-select").value);
  if (mine !== loading) return;  // a later choice has superseded this one
  formReady = editor.show(cls, classSchema(selectedAgent(), cls), doc);
  $("input-fieldset").hidden = !cls;
  refreshRunButton();
}
function refreshRunButton() {
  $("run").disabled = !(agents[selectedAgent()] && formReady);
}

async function main() {
  await loadRegistry();
  renderAgents($("agent-select"));
  $("agent-select").addEventListener("change", () => { renderAgentDetail(selectedAgent(), $("agent-detail")); refreshClasses(); });
  refreshClasses();
  $("class-select").addEventListener("change", refreshSamples);
  $("sample-select").addEventListener("change", loadSample);
  $("run").addEventListener("click", () => run(selectedAgent()));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    if (!$("run").disabled) run(selectedAgent());
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
