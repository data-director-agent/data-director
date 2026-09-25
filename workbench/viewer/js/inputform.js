// The input form: an editable react-jsonschema-form (RJSF) built from an input class's schema in
// the contract's generated invocation-request schema. It names no class and no agent; a sample,
// when chosen, is only the form's starting data. Inspect and Chat import it.
import React from "https://esm.sh/react@19";
import { createRoot } from "https://esm.sh/react-dom@19/client";
import Form from "https://esm.sh/@rjsf/core@6.8.0?deps=react@19,react-dom@19";
import validator from "https://esm.sh/@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19";

const h = React.createElement;

// One input class's schema, with the shared $defs so nested classes ($ref) resolve.
export function inputSchema(schema, cls) {
  const def = cls && schema?.$defs?.[cls];
  return def ? { ...def, $defs: schema.$defs } : null;
}

// RJSF's default buttons are Bootstrap glyphs with no visible text; these carry their label.
function textButton(label) {
  return ({ id, className = "", onClick, disabled }) =>
    h("button", { id, type: "button", className: `small ${className}`, onClick, disabled }, label);
}
const templates = {
  ButtonTemplates: {
    AddButton: textButton("Add item"), RemoveButton: textButton("Remove"), CopyButton: textButton("Copy"),
    MoveUpButton: textButton("Move up"), MoveDownButton: textButton("Move down"), ClearButton: textButton("Clear"),
  },
};

// The class designator is fixed by the class the form was built for, so it is not a field.
const UISCHEMA = { schema_class: { "ui:widget": "hidden" }, "ui:globalOptions": { orderable: false } };

// Render into `node`. `show` builds the form for a class (from blank or from a sample),
// `value` is what would be sent, `validate` checks it against the schema and shows the errors.
// The form has no submit button of its own and renders as a <div>, so it can sit inside Chat's
// composer <form>; the page's own Run or Send button acts on it.
export function inputForm(node) {
  const root = createRoot(node);
  const ref = React.createRef();
  let props = null, data = null, generation = 0;
  const render = () => root.render(props ? h(Form, { ...props, formData: data, ref }) : null);
  return {
    show(cls, schema, formData) {
      const s = inputSchema(schema, cls);
      data = s ? { ...(formData || {}), schema_class: cls } : null;
      props = s && {
        key: ++generation, schema: s, uiSchema: UISCHEMA, validator, templates,
        // Field ids are in_<slot>; the prefix must not collide with an id on either page (Inspect has #input).
        idPrefix: "in", tagName: "div", noHtml5Validate: true, showErrorList: false, liveValidate: false,
        onChange: (e) => { data = e.formData; },
        onError: () => {},  // errors are shown beside their fields; RJSF would also log them
        children: h("span"),
      };
      if (!s) root.render(cls ? h("p", { className: "muted" }, `No schema for input class ${cls}.`) : null);
      else render();
      return Boolean(s);
    },
    value: () => data,
    // After the first failed check, errors update as the user corrects them.
    validate() {
      if (!props || !ref.current) return false;
      const ok = ref.current.validateForm();
      if (!ok && !props.liveValidate) { props = { ...props, liveValidate: "onChange" }; render(); }
      return ok;
    },
  };
}
