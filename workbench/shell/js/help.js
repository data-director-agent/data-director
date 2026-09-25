// Built-in help: a "?" button beside a term opens a tip; the Glossary dialog lists every term.
// Importing this module expands the page's [data-help] placeholders and wires the dialog.
import { $, el } from "./common.js";
import { GLOSSARY } from "./glossary.js";

// --- Help tips --------------------------------------------------------------------------
// A "?" button opens a popover="manual" tip: click pins it, hover shows it while the pointer is
// on the button or the tip, Escape or a click elsewhere closes it (WCAG 1.4.13). Positioned by
// script so it does not depend on CSS anchor positioning.
let tipSeq = 0, openTip = null;
export function closeTip() {
  const t = openTip; openTip = null;
  try { t?.tip.hidePopover(); } catch {}
}
export function wireTip(button, tip) {
  const state = { button, tip, pinned: false, timer: 0 };
  state.place = () => {
    const b = button.getBoundingClientRect(), r = tip.getBoundingClientRect(), gap = 6, pad = 8;
    const left = Math.min(Math.max(pad, b.left + b.width / 2 - r.width / 2), innerWidth - r.width - pad);
    const fitsBelow = b.bottom + gap + r.height <= innerHeight - pad;
    tip.style.left = `${Math.max(pad, left)}px`;
    tip.style.top = `${fitsBelow ? b.bottom + gap : Math.max(pad, b.top - gap - r.height)}px`;
  };
  const show = (pin) => {
    clearTimeout(state.timer);
    if (openTip && openTip !== state) closeTip();
    state.pinned ||= pin;
    if (!tip.matches(":popover-open")) tip.showPopover();
    state.place();
    openTip = state;
  };
  const hideSoon = () => {
    clearTimeout(state.timer);
    if (!state.pinned) state.timer = setTimeout(() => { if (openTip === state) closeTip(); }, 200);
  };
  button.setAttribute("aria-expanded", "false");
  tip.addEventListener("toggle", (e) => {
    const open = e.newState === "open";
    button.setAttribute("aria-expanded", String(open));
    if (!open) { state.pinned = false; if (openTip === state) openTip = null; }
  });
  button.addEventListener("click", () => (state.pinned && openTip === state ? closeTip() : show(true)));
  button.addEventListener("mouseenter", () => { clearTimeout(state.timer); state.timer = setTimeout(() => show(false), 250); });
  button.addEventListener("mouseleave", hideSoon);
  tip.addEventListener("mouseenter", () => clearTimeout(state.timer));
  tip.addEventListener("mouseleave", hideSoon);
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && openTip) { const b = openTip.button; closeTip(); b.focus(); e.preventDefault(); }
});
document.addEventListener("pointerdown", (e) => {
  if (openTip && !openTip.tip.contains(e.target) && !openTip.button.contains(e.target)) closeTip();
});
addEventListener("resize", () => openTip?.place());
addEventListener("scroll", () => openTip?.place(), { capture: true, passive: true });

// help("key") or help(["key", "key:value"]): a tip holding one or more glossary entries.
export function help(keys) {
  const entries = [].concat(keys).map((k) => GLOSSARY[k]).filter(Boolean);
  return entries.length ? helpTip(entries) : null;
}
export function helpTip(entries) {
  const id = `tip-${++tipSeq}`;
  const tip = el("span", { id, className: "tip" },
    ...entries.flatMap((e) => [el("strong", { textContent: e.term }), el("span", { textContent: e.text })]));
  tip.popover = "manual";
  const button = el("button", { type: "button", className: "help", textContent: "?" });
  button.setAttribute("aria-label", `About ${entries[0].term}`);
  button.setAttribute("aria-describedby", id);
  button.setAttribute("aria-controls", id);
  wireTip(button, tip);
  return el("span", { className: "help-wrap" }, button, tip);
}

for (const node of document.querySelectorAll("[data-help]")) node.replaceWith(help(node.dataset.help) ?? "");
// In the dialog an enum value is qualified by its vocabulary, so "none" and "model" read unambiguously.
const VOCABULARY = { status: "outcome status", mode: "grounding mode", derivation: "derivation" };
$("glossary-list").append(...Object.entries(GLOSSARY)
  .map(([key, e]) => ({ ...e, term: key.includes(":") ? `${e.term} (${VOCABULARY[key.split(":")[0]]})` : e.term }))
  .toSorted((a, b) => a.term.localeCompare(b.term, "en-GB"))
  .flatMap((e) => [el("dt", { textContent: e.term }), el("dd", { textContent: e.text })]));
$("open-glossary").addEventListener("click", () => { closeTip(); $("glossary").showModal(); });
$("glossary").addEventListener("click", (e) => { if (e.target === $("glossary")) $("glossary").close(); });
