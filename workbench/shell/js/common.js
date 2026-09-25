// Shared by both pages: DOM and formatting helpers, the per-tab input cache, the AG-UI
// transport and the cross-page links. Imports nothing, so every other module can import it.
export const $ = (id) => document.getElementById(id);
export const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const c of children) if (c != null) node.append(c);
  return node;
};
export const isEmpty = (v) => v === null || v === undefined || v === "";
// UUIDv7 (RFC 9562): 48-bit Unix milliseconds, then random bits, with version and variant set.
export function uuid7() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  let ms = BigInt(Date.now());
  for (let i = 5; i >= 0; i--) { b[i] = Number(ms & 0xffn); ms >>= 8n; }
  b[6] = (b[6] & 0x0f) | 0x70;
  b[8] = (b[8] & 0x3f) | 0x80;
  const hex = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// --- Inputs ---------------------------------------------------------------------------
// The envelope stores the input's hash, not the input. Inputs sent from this browser tab are kept
// in sessionStorage, so Inspect can show the input of a turn sent from Chat in the same tab.
export const inputs = new Map(); // invocation_id → input sent from this browser tab
try { for (const [k, v] of Object.entries(JSON.parse(sessionStorage.getItem("dd-inputs") || "{}"))) inputs.set(k, v); } catch {}
export const rememberInput = (id, input) => {
  inputs.set(id, input);
  try { sessionStorage.setItem("dd-inputs", JSON.stringify(Object.fromEntries(inputs))); } catch {}
};

// Lucide icons from the vendored sprite (icons.svg, built by scripts/build_icons.py). Icons are
// decorative: hidden from assistive technology, never focusable, always beside visible text or
// inside a control that carries its own label.
const SVG = "http://www.w3.org/2000/svg";
export function icon(name) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `/shell/icons.svg#${name}`);
  svg.append(use);
  return svg;
}
// One icon per outcome status, so the status never rests on colour alone (WCAG 1.4.1).
export const STATUS_ICONS = {
  succeeded: "circle-check",
  abstained: "circle-minus",
  referred: "circle-arrow-right",
  failed: "circle-x",
  suspended: "circle-pause",
};
export function statusIcon(status) {
  if (!(status in STATUS_ICONS)) return null;
  const i = icon(STATUS_ICONS[status]);
  i.dataset.status = status;
  return i;
}

// --- Formatting -----------------------------------------------------------------------
// Copy on click; the button's icon and text change together to confirm, then revert.
export function wireCopy(button, getText, label = "Copy") {
  const show = (name, text) => button.replaceChildren(icon(name), text);
  show("copy", label);
  button.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(getText()); show("check", "Copied"); } catch { show("x", "Failed"); }
    setTimeout(() => show("copy", label), 1200);
  });
  return button;
}
export function copyButton(text, label = "Copy") {
  return wireCopy(el("button", { type: "button", className: "small", title: `Copy ${text}` }), () => text, label);
}
export const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? d.toLocaleTimeString("en-GB") : d.toLocaleString("en-GB");
};
export const shortId = (id) => id.slice(-8);
export function statusPill(status) {
  const pill = el("span", { className: "pill" }, statusIcon(status), status);
  pill.dataset.status = status;
  return pill;
}

// Links between the two pages. Paths are absolute because Inspect is also served at /.
export const inspectLink = (id, text) =>
  el("a", { href: `/shell/?invocation_id=${id}`, title: `Open ${id} in Inspect` }, ...(text == null ? ["Inspect", icon("arrow-right")] : [text]));
export const chatLink = (conversationId, text = conversationId) =>
  el("a", { href: `/shell/chat.html?conversation_id=${conversationId}`, textContent: text, title: "Open the conversation in Chat" });
export function kvList(obj) {
  const dl = el("dl", { className: "kvs" });
  for (const [k, v] of Object.entries(obj)) {
    if (k === "schema_class") continue;
    const text = isEmpty(v) ? el("span", { className: "null", textContent: "null" }) : (typeof v === "object" ? el("code", { textContent: JSON.stringify(v) }) : String(v));
    dl.append(el("dt", { textContent: k }), el("dd", {}, text));
  }
  return dl;
}

// --- Transport --------------------------------------------------------------------------
export function parseSse(text) {
  return text.split("\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6)));
}
// One AG-UI run: RUN_FINISHED carries the envelope, RUN_ERROR a refused request. In a
// conversation the thread is the conversation_id; `messages` mirrors the history for protocol
// fidelity, but the agent reads its history from the Message input, not from here.
export function newRequest(agentId, input, conversationId = null) {
  const request = { agent_id: agentId, policy_bundle_ref: "profile:default", input,
    invocation_id: uuid7(), issued_at: new Date().toISOString(), requirement_ids: [] };
  if (conversationId) request.conversation_id = conversationId;
  return request;
}
export async function postRun(request, threadId = "shell", messages = []) {
  const body = { threadId, runId: request.invocation_id, messages, state: {}, tools: [], context: [], forwardedProps: { request } };
  const r = await fetch("/agui", { method: "POST", headers: { "content-type": "application/json", accept: "text/event-stream" }, body: JSON.stringify(body) });
  const events = parseSse(await r.text());
  const fin = events.find((e) => e.type === "RUN_FINISHED");
  return { envelope: fin?.result, error: fin ? null : (events.map((e) => e.message).filter(Boolean).join("; ") || `HTTP ${r.status}`) };
}
