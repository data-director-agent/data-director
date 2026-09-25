// The payload view: react-jsonschema-form (RJSF) with templates that present a payload as a
// read-only document, and the derivation badges. Only Inspect imports it.
import React from "https://esm.sh/react@19";
import { createRoot } from "https://esm.sh/react-dom@19/client";
import Form from "https://esm.sh/@rjsf/core@6.8.0?deps=react@19,react-dom@19";
import validator from "https://esm.sh/@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19";

import { isEmpty } from "./common.js";
import { wireTip } from "./help.js";

const h = React.createElement;

// The same tip for RJSF, where the text is the payload schema's own field description.
function HelpTip({ term, text }) {
  const button = React.useRef(null), tip = React.useRef(null), id = React.useId();
  React.useEffect(() => wireTip(button.current, tip.current), []);
  return h("span", { className: "help-wrap" },
    h("button", { ref: button, type: "button", className: "help", "aria-label": `About ${term}`, "aria-describedby": id, "aria-controls": id }, "?"),
    h("span", { ref: tip, id, className: "tip", popover: "manual" }, h("strong", null, term), h("span", null, text)));
}

// --- Derivation badge: the uiSchema convention -----------------------------------------
// A field declares `ui:options.dd:derivation` ("verified" | "model" | "template" | "lexical" | "registry").
// If it also names `dd:derivation_field`, the badge reads the live value of that sibling field
// (e.g. rationale_derivation), so a template rationale is badged as template even where a model
// would normally have written it. New agents inherit the treatment by declaring their fields.
// `verified` is the unmarked default: only fields something other than the harness wrote are badged.
function badgeFor(derivation) {
  if (!derivation || derivation === "verified") return null;
  return h("span", { className: `badge ${derivation}`, title: `dd:derivation = ${derivation}` }, derivation);
}
function valueNode(value, schema = {}) {
  if (isEmpty(value)) return h("span", { className: "null" }, "null");
  if (typeof value === "boolean") return h("code", null, String(value));
  if (schema.enum || schema.$ref) return h("span", { className: "value-enum", "data-value": String(value) }, String(value));
  return h("span", null, String(value));
}
function DerivationBadge(props) {
  const { value, options = {}, id, schema } = props;
  const formContext = props.registry?.formContext || props.formContext || {};
  let derivation = options["dd:derivation"] || "verified";
  const sibling = options["dd:derivation_field"];
  if (sibling && formContext.siblingValue) {
    const v = formContext.siblingValue(id, sibling);
    if (v) derivation = v;
  }
  return h("span", null, valueNode(value, schema), badgeFor(derivation));
}
function PlainValue(props) { return valueNode(props.value, props.schema); }
function Hidden() { return null; }
const widgets = {
  derivationBadge: DerivationBadge, hidden: Hidden,
  TextWidget: PlainValue, TextareaWidget: PlainValue, SelectWidget: PlainValue, CheckboxWidget: PlainValue,
};

// Resolve the object holding a field from an RJSF id like root_findings_0_message. Property
// names contain underscores, so match the longest key that exists at each level.
function makeSiblingLookup(formData) {
  return (id, siblingName) => {
    const tokens = id.replace(/^root_?/, "").split("_").filter(Boolean);
    function walk(node, i) {
      if (i === tokens.length) return null;
      for (let j = tokens.length; j > i; j--) {
        const key = tokens.slice(i, j).join("_");
        const k = Array.isArray(node) && /^\d+$/.test(key) ? Number(key) : key;
        if (node != null && typeof node === "object" && k in node) {
          if (j === tokens.length) return node;
          const found = walk(node[k], j);
          if (found) return found;
        }
      }
      return null;
    }
    return walk(formData, 0)?.[siblingName];
  };
}

// --- RJSF templates: read-only document presentation -----------------------------------
// Direct properties of an array item render as cells under a header row, so their labels are
// dropped; everything else is a label/value pair.
const inArrayItem = (fieldPathId) => {
  const p = fieldPathId?.path || [];
  return p.length >= 2 && typeof p[p.length - 2] === "number";
};
// A payload field's help is its own schema description, so an agent documents its payload by
// describing its LinkML slots, and the shell names no agent.
const describe = (term, text) => (text ? h(HelpTip, { term, text }) : null);
function FieldTemplate(props) {
  const { hidden, label, children, schema, fieldPathId, uiSchema = {}, rawDescription } = props;
  if (hidden || uiSchema["ui:widget"] === "hidden") return null;
  const path = fieldPathId?.path || [];
  if (path.length === 0 || typeof path[path.length - 1] === "number") return children;
  const container = schema.type === "object" || schema.type === "array" || (Array.isArray(schema.type) && (schema.type.includes("array") || schema.type.includes("object")));
  const name = uiSchema["ui:title"] || path[path.length - 1] || label;
  return h("div", { className: `rjsf-field${container ? " block" : ""}` },
    inArrayItem(fieldPathId) ? null : h("div", { className: "label" }, name, describe(name, schema.description || rawDescription)),
    h("div", { className: "value" }, children));
}
function visibleProps(itemSchema, itemUi = {}) {
  const props = Object.keys(itemSchema?.properties || {}).filter((k) => itemUi[k]?.["ui:widget"] !== "hidden");
  const order = itemUi["ui:order"] || [];
  return props.sort((a, b) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999));
}
// The container owns the column grid; rows are `display: contents`, so cells align across rows.
const gridFor = (n) => ({ gridTemplateColumns: `repeat(${n}, minmax(6rem, auto))` });
function ArrayFieldTemplate(props) {
  const { items, schema, uiSchema = {}, registry, formData } = props;
  if (!items.length) return h("span", { className: "null" }, Array.isArray(formData) ? "[] (empty)" : "null");
  const itemSchema = registry.schemaUtils.retrieveSchema(schema.items || {});
  if (itemSchema.type !== "object") return h("div", null, items);
  const cols = visibleProps(itemSchema, uiSchema.items);
  return h("div", { className: "rows", role: "table", style: gridFor(cols.length) },
    h("div", { className: "row head", role: "row" },
      cols.map((c) => {
        const name = uiSchema.items?.[c]?.["ui:title"] || c;
        return h("span", { key: c, role: "columnheader" }, name, describe(name, itemSchema.properties[c]?.description));
      })),
    items);
}
function ArrayFieldItemTemplate(props) { return props.children; }
function ObjectFieldTemplate(props) {
  const { properties, fieldPathId, uiSchema = {} } = props;
  const path = fieldPathId?.path || [];
  const shown = properties.filter((p) => !p.hidden && uiSchema[p.name]?.["ui:widget"] !== "hidden");
  if (typeof path[path.length - 1] === "number") {
    return h("div", { className: "row", role: "row" },
      shown.map((p) => h("div", { key: p.name, role: "cell" }, p.content)));
  }
  return h("div", { className: path.length === 0 ? "rjsf-root" : "nested" }, shown.map((p) => p.content));
}
function BaseInputTemplate(props) { return valueNode(props.value, props.schema); }
const templates = { FieldTemplate, ArrayFieldTemplate, ArrayFieldItemTemplate, ObjectFieldTemplate, BaseInputTemplate };

// Render into `node`: nothing, an unknown-class fallback, or the payload through RJSF with its
// agent's fragment. `ps` is the payload class's schema from the envelope schema's $defs.
export function payloadView(node) {
  const root = createRoot(node);
  return (payload, ps, uiSchema) => {
    if (!payload) root.render(h("p", { className: "muted" }, "No payload: the outcome is not succeeded."));
    else if (!ps) root.render(h("pre", { className: "json" }, `Unknown payload class ${payload.schema_class}:\n${JSON.stringify(payload, null, 2)}`));
    else root.render(h(Form, {
      schema: ps, uiSchema, validator, widgets, templates,
      formData: payload, readonly: true, liveValidate: false, showErrorList: false,
      formContext: { siblingValue: makeSiblingLookup(payload) },
      onSubmit: () => {}, children: h("span"),
    }));
  };
}
