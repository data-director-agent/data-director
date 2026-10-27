// An A2A agent card (A2A 1.0, the JSON an a2a-sdk AgentCard serialises to) in a form a person can
// read (#138). Every field the card defines is shown when present; the Data Director agent-spec
// extension is shown field by field, any other extension's params as key–value pairs. The card is
// the agent's own text, so nothing in it becomes markup, and only http(s) URLs become links.
// Conformance with the A2A specification is the A2A Inspector's job, not this page's.
import { el, isEmpty, kvList } from "./common.js";

const DD_EXTENSION = "https://w3id.org/data-director/a2a/agent-spec/v0";

const none = () => el("span", { className: "faint", textContent: "none" });
const yesNo = (v) => (v ? "yes" : "no");
const code = (text) => el("code", { textContent: text });
const chips = (items) =>
  items?.length ? el("span", { className: "chips" }, ...items.map((t) => el("span", { className: "chip", textContent: t }))) : none();
const link = (url) =>
  /^https?:\/\//i.test(url) ? el("a", { href: url, textContent: url, rel: "noopener noreferrer" }) : code(url);

// A definition list of the pairs whose value is present; values are nodes or strings.
function facts(pairs) {
  const dl = el("dl", { className: "kvs" });
  for (const [k, v] of pairs) if (!isEmpty(v)) dl.append(el("dt", { textContent: k }), el("dd", {}, v));
  return dl;
}
const part = (title, ...body) => el("section", {}, el("h3", { textContent: title }), ...body);
const items = (list, render) =>
  list?.length ? el("ul", { className: "card-items" }, ...list.map((x) => el("li", {}, ...render(x)))) : none();

function provider(p) {
  if (!p) return null;
  return p.url ? el("span", {}, p.organization || "", p.organization ? " · " : "", link(p.url)) : p.organization;
}

// Our extension's params (dd_sdk.agent.describe). Its agent_id, version and description repeat the
// card's own and are left out; each schema is named with its digest, not printed.
function ddParams(p) {
  const derivations = Object.entries(p.derivations || {});
  const schemas = Object.entries(p.schemas || {});
  return facts([
    ["action class", p.action_class],
    ["accepts", chips(p.accepts)],
    ["payload", p.payload],
    ["grounding mode", p.grounding_mode],
    ["contract version", p.contract_version],
    ["models", chips(p.models?.map((m) => `${m.provider}/${m.model} (${m.hosting})`))],
    ["serves", chips(p.serves)],
    ["derivations", items(derivations, ([field, d]) => [code(field), ` ${d.how}`, d.recorded_in ? el("span", { className: "muted" }, " recorded in ", code(d.recorded_in)) : null])],
    ["schemas", items(schemas, ([cls, s]) => [code(cls), " ", el("span", { className: "mono faint", title: s.digest, textContent: s.digest ? `sha256 ${s.digest.slice(0, 12)}…` : "" })])],
  ]);
}

function extension(x) {
  const params = x.uri === DD_EXTENSION ? ddParams(x.params || {}) : (isEmpty(x.params) || !Object.keys(x.params).length ? null : kvList(x.params));
  return [
    el("p", { className: "card-item-head" }, link(x.uri), " ", el("span", { className: "chip", textContent: x.required ? "required" : "optional" })),
    x.description ? el("p", { className: "muted", textContent: x.description }) : null,
    params,
  ];
}

// A security scheme is a oneof; its one key names the kind (apiKeySecurityScheme → apiKey).
function securityScheme([name, scheme]) {
  const [kind, detail = {}] = Object.entries(scheme || {})[0] || ["unknown"];
  return [code(name), ` ${kind.replace(/SecurityScheme$/, "")}`, detail.description ? el("span", { className: "muted", textContent: ` — ${detail.description}` }) : null];
}

function skill(s) {
  return [
    el("p", { className: "card-item-head" }, el("strong", { textContent: s.name || s.id }), s.name && s.id !== s.name ? el("span", { className: "muted" }, " ", code(s.id)) : null),
    s.description ? el("p", { textContent: s.description }) : null,
    facts([
      ["tags", chips(s.tags)],
      ["examples", s.examples?.length ? items(s.examples, (e) => [e]) : null],
      ["input types", s.inputModes?.length ? chips(s.inputModes) : null],
      ["output types", s.outputModes?.length ? chips(s.outputModes) : null],
    ]),
  ];
}

export function renderCard(card) {
  const caps = card.capabilities || {};
  return el("div", { className: "agent-card" },
    card.description ? el("p", { textContent: card.description }) : null,
    facts([
      ["name", card.name],
      ["version", card.version],
      ["provider", provider(card.provider)],
      ["documentation", card.documentationUrl && link(card.documentationUrl)],
      ["icon", card.iconUrl && link(card.iconUrl)],
      ["input types", chips(card.defaultInputModes)],
      ["output types", chips(card.defaultOutputModes)],
      ["signatures", card.signatures?.length ? String(card.signatures.length) : null],
    ]),
    part("Interfaces", items(card.supportedInterfaces, (i) => [
      el("span", { className: "chip", textContent: i.protocolBinding || "?" }), " ", code(i.url),
      i.protocolVersion ? el("span", { className: "muted", textContent: ` A2A ${i.protocolVersion}` }) : null,
      i.tenant ? el("span", { className: "muted" }, " tenant ", code(i.tenant)) : null,
    ])),
    part("Capabilities", facts([
      ["streaming", yesNo(caps.streaming)],
      ["push notifications", yesNo(caps.pushNotifications)],
      ["extended card", yesNo(caps.extendedAgentCard)],
    ])),
    part("Extensions", items(caps.extensions, extension)),
    part("Security", items(Object.entries(card.securitySchemes || {}), securityScheme)),
    part("Skills", items(card.skills, skill)),
  );
}
