// Chat: hold a conversation with one agent, a turn at a time. ?conversation_id=… reopens one.
import { $, el, uuid7, rememberInput, copyButton, fmtTime, shortId, statusPill, kvList, inspectLink, newRequest, postRun } from "./common.js";
import { help } from "./help.js";
import { agents, samples, loadRegistry, renderAgents, renderAgentDetail } from "./registry.js";

// A conversation is a client-minted conversation_id plus whatever the store holds for it.
// `chat.conversation` is GET /conversations/{id}: turns (each with its children), inputs,
// version_changes and the history the next Message carries. The picker is locked once a
// conversation has turns, so every turn of one conversation addresses the same agent.
const chat = { id: null, agentId: "", conversation: null, busy: false };
const turns = () => chat.conversation?.turns || [];
const acceptsMessage = (a) => a?.accepts.includes("Message");
const defaultChatAgent = () =>
  Object.keys(agents).sort((a, b) => a.localeCompare(b)).find((id) => agents[id].grounding_mode === "delegation")
  || Object.keys(agents).sort((a, b) => a.localeCompare(b))[0] || "";

function newConversation(agentId = chat.agentId || defaultChatAgent()) {
  chat.id = uuid7(); chat.agentId = agentId; chat.conversation = null;
  $("chat-text").value = "";
  renderChat();
  refreshComposer();
}
async function openConversation(id) {
  const r = await fetch(`/conversations/${encodeURIComponent(id)}`);
  chat.id = id;
  chat.conversation = r.ok ? await r.json() : null;
  if (!r.ok) $("chat-status").textContent = `No stored turns for ${shortId(id)}; the next turn starts it.`;
  for (const [k, v] of Object.entries(chat.conversation?.inputs || {})) rememberInput(k, v);
  chat.agentId = turns()[0]?.agent_id || chat.agentId || defaultChatAgent();
  renderChat();
  refreshComposer();
}
function renderChat() {
  const sel = $("chat-agent-select");
  if (chat.agentId && ![...sel.options].some((o) => o.value === chat.agentId)) sel.append(new Option(`${chat.agentId} (not registered)`, chat.agentId));
  sel.value = chat.agentId;
  sel.disabled = turns().length > 0;
  renderAgentDetail(chat.agentId, $("chat-agent-detail"));
  $("conversation-line").replaceChildren(
    el("code", { textContent: "conversation_id" }), help("conversation_id"), " ",
    el("code", { textContent: shortId(chat.id), title: chat.id }), " ", copyButton(chat.id),
    turns().length ? ` · ${turns().length} turn${turns().length === 1 ? "" : "s"} · agent locked` : " · no turns yet");
  renderTranscript();
  markCurrentConversation();
  history.replaceState(null, "", turns().length ? `?conversation_id=${chat.id}` : location.pathname);
}
function renderTranscript() {
  const list = $("transcript");
  list.replaceChildren();
  $("chat-empty").hidden = turns().length > 0;
  const changes = Map.groupBy(chat.conversation?.version_changes || [], (c) => c.turn_index);
  for (const t of turns()) {
    for (const c of changes.get(t.turn_index) || []) {
      list.append(el("li", { className: "version-change" },
        el("code", { textContent: c.agent_id }), ` version changed ${c.from} → ${c.to}`, help("version-change")));
    }
    list.append(userTurn(t.input, t.turn_index));
    list.append(el("li", { className: "turn-agent" }, envelopeCard(t.envelope, t.children)));
  }
}
function userTurn(input, index) {
  const who = el("span", { className: "who", textContent: `user · turn ${index + 1}` });
  if (input?.schema_class === "Message") return el("li", { className: "turn-user" }, who, el("div", { className: "bubble", textContent: input.message_text }));
  return el("li", { className: "turn-user" }, who,
    el("div", { className: "bubble" }, el("span", { className: "chip", textContent: input?.schema_class || "input" }), input ? kvList(input) : " not stored"));
}
// One envelope as a chat card: which agent and version, the outcome, the reply or a summary of
// the payload, and the delegated invocations nested beneath, each with its own agent@version.
function envelopeCard(env, children = [], delegated = false) {
  const o = env.outcome;
  const head = el("div", { className: "card-head" },
    delegated ? el("span", { className: "handoff", textContent: "→ delegated to" }) : null,
    el("span", { className: "agent-badge", textContent: `${env.agent_id}@${env.agent_version}`, title: "agent_id@agent_version" }),
    statusPill(o.status),
    o.reason_code ? el("code", { textContent: o.reason_code, title: "reason_code" }) : null,
    el("span", { className: "inspect" }, inspectLink(env.invocation_id)));
  const reply = env.payload?.schema_class === "Reply" ? el("p", { className: "reply", textContent: env.payload.reply_text }) : null;
  const card = el("article", { className: "card", "aria-label": `${env.agent_id}@${env.agent_version} ${o.status}` },
    head, reply, el("p", { className: "statement", textContent: o.statement }));
  if (env.payload && !reply) card.append(payloadSummary(env.payload));
  if (children.length) {
    card.append(el("ol", { className: "children", "aria-label": "Delegated invocations" },
      ...children.map((c) => el("li", {}, envelopeCard(c, [], true)))));
  }
  return card;
}
// The payload's top-level scalar fields; the full render is one click away in Inspect.
function payloadSummary(payload) {
  const shown = Object.fromEntries(Object.entries(payload)
    .filter(([k, v]) => k !== "grounded_on" && !k.endsWith("_derivation") && (typeof v !== "object" || v === null || Array.isArray(v)))
    .map(([k, v]) => [k, Array.isArray(v) ? `${v.length} item${v.length === 1 ? "" : "s"}` : v]));
  return el("div", {}, el("span", { className: "chip", textContent: payload.schema_class }), kvList(shown));
}

function refreshComposer() {
  const a = agents[chat.agentId];
  const textMode = acceptsMessage(a);
  $("composer-text").hidden = !textMode;
  $("composer-json").hidden = textMode || !a;
  $("composer-to").replaceChildren(a
    ? el("span", {}, "To ", el("span", { className: "agent-badge", textContent: `${chat.agentId}@${a.version}` }),
        textMode ? " as a Message" : ` as ${a.accepts.join(" or ")}`, help(textMode ? "message" : "accepts"))
    : el("span", {}, chat.agentId ? `${chat.agentId} is unavailable; start a new conversation with another agent.` : "Choose an agent."));
  if (a && !textMode) {
    const sel = $("chat-sample-select");
    const fit = samples.filter((s) => a.accepts.includes(s.schema_class));
    const kept = sel.value;
    sel.replaceChildren(...(fit.length ? fit.map((s) => new Option(`${s.name} — ${s.schema_class}`, s.name)) : [new Option("No sample; write the JSON", "")]));
    if (fit.some((s) => s.name === kept)) sel.value = kept;
    if (!$("chat-json").value.trim() || !fit.some((s) => s.name === kept)) loadChatSample();
  }
  $("send").disabled = !a || chat.busy;
}
async function loadChatSample() {
  const name = $("chat-sample-select").value;
  if (!name) { $("chat-json").value = ""; return; }
  const doc = await (await fetch(`/samples/${encodeURIComponent(name)}`)).json();
  $("chat-json").value = JSON.stringify(doc, null, 2);
}
function transcriptNote(className, ...content) {
  const li = el("li", { className }, ...content);
  $("transcript").append(li);
  $("chat-empty").hidden = true;
  li.scrollIntoView({ block: "nearest" });
  return li;
}
async function send() {
  const a = agents[chat.agentId];
  if (!a || chat.busy) return;
  let input;
  if (acceptsMessage(a)) {
    const text = $("chat-text").value.trim();
    if (!text) { $("chat-text").focus(); return; }
    input = { schema_class: "Message", message_text: text, history: chat.conversation?.history || [] };
  } else {
    try { input = JSON.parse($("chat-json").value); }
    catch (e) { transcriptNote("turn-error", `Not sent: the input is not valid JSON (${e.message}).`); return; }
  }
  const request = newRequest(chat.agentId, input, chat.id);
  const messages = (chat.conversation?.history || []).map((t, i) => ({ id: `${chat.id}-${i}`, role: t.role === "user" ? "user" : "assistant", content: t.turn_text }));
  chat.busy = true; refreshComposer();
  $("chat-status").textContent = `Waiting for ${chat.agentId}@${a.version}…`;
  const pending = transcriptNote("turn-agent turn-pending", el("div", { className: "card" }, `${chat.agentId}@${a.version} is working…`));
  try {
    const { envelope, error } = await postRun(request, chat.id, messages);
    pending.remove();
    if (!envelope) { transcriptNote("turn-error", `Refused before any agent ran, so nothing was stored: ${error}`); $("chat-status").textContent = "Refused."; return; }
    rememberInput(envelope.invocation_id, input);
    if (acceptsMessage(a)) $("chat-text").value = "";
    await openConversation(chat.id);
    $("chat-status").textContent = `${envelope.agent_id}@${envelope.agent_version} ${envelope.outcome.status}.`;
    loadConversations();
  } catch (e) {
    pending.remove();
    transcriptNote("turn-error", `Error: ${e.message}`);
  } finally {
    chat.busy = false; refreshComposer();
  }
}
async function loadConversations() {
  const items = await (await fetch("/conversations")).json();
  const list = $("conversations"); list.replaceChildren();
  if (!items.length) list.append(el("li", { className: "muted", textContent: "None yet." }));
  for (const c of items) {
    const dot = el("span", { className: "dot", title: c.last_status }); dot.dataset.status = c.last_status;
    const b = el("button", { type: "button", title: `${c.turns} turn(s) · ${c.conversation_id}` },
      dot, el("span", { className: "mono", textContent: c.agent_id }),
      el("span", { className: "id", textContent: `${c.turns}× · ${fmtTime(c.last_completed_at)} · ${shortId(c.conversation_id)}` }));
    b.dataset.id = c.conversation_id;
    b.addEventListener("click", () => openConversation(c.conversation_id));
    list.append(el("li", {}, b));
  }
  markCurrentConversation();
}
function markCurrentConversation() {
  for (const b of $("conversations").querySelectorAll("button")) b.setAttribute("aria-current", String(b.dataset.id === chat.id));
}

async function main() {
  await loadRegistry();
  renderAgents($("chat-agent-select"));
  $("chat-agent-select").addEventListener("change", () => { newConversation($("chat-agent-select").value); });
  $("new-conversation").addEventListener("click", () => newConversation());
  $("chat-sample-select").addEventListener("change", loadChatSample);
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  });
  await loadConversations();

  const id = new URLSearchParams(location.search).get("conversation_id");
  if (id) await openConversation(id); else newConversation(defaultChatAgent());
  $("chat-status").textContent ||= "Ready.";
}
main().catch((e) => { $("chat-status").textContent = `Error: ${e.message}`; console.error(e); });
