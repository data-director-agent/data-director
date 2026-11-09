import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import type { JsonSchema } from "../src";
import { AgentViewProvider, PayloadView, type PayloadRendererProps } from "../src/react";

const SCHEMA: JsonSchema = {
  type: "object",
  properties: {
    schema_class: { type: "string" },
    summary: { type: "string", title: "Summary" },
    count: { type: "integer" },
    flags: { type: "array", items: { type: "string" } },
    grounded_on: { type: "array", items: { $ref: "#/$defs/GroundingRef" } },
    findings: { type: "array", items: { $ref: "#/$defs/Finding" } },
    detail: { $ref: "#/$defs/Detail" },
    extra: {},
  },
  $defs: {
    GroundingRef: { type: "object", properties: { source_id: { type: "string" } } },
    Finding: {
      type: "object",
      properties: {
        text: { type: "string" },
        text_derivation: { type: "string" },
        grounded_on: { type: "array", items: { $ref: "#/$defs/GroundingRef" } },
      },
    },
    Detail: { type: "object", properties: { note: { type: "string" } } },
  },
};

const PAYLOAD = {
  schema_class: "Review",
  summary: "All good",
  count: 2,
  flags: ["a", "b"],
  grounded_on: [{ source_id: "in", content_hash: "h" }],
  findings: [
    { text: "First", text_derivation: "model", grounded_on: [{ source_id: "in", content_hash: "h" }] },
    { text: "Second", grounded_on: [{ source_id: "gone", content_hash: "x" }] },
  ],
  detail: { note: "noted" },
  extra: { any: [1] },
};

describe("PayloadView", () => {
  it("lays a payload out from its schema, derivations and evidence", async () => {
    const { container } = render(
      <PayloadView
        payload={PAYLOAD}
        schema={SCHEMA}
        derivations={[{ path: "findings.text", how: "template", recordedIn: "text_derivation" }]}
        evidence={[{ source_id: "in", content_hash: "h", content: { name: "Your input" } }]}
        idPrefix="p"
      />,
    );
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("All good")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).queryByText("Text derivation")).not.toBeInTheDocument();
    expect(within(table).getByText("Language model")).toBeInTheDocument();
    expect(within(table).getByText("Template")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "[1] Your input" })).toHaveAttribute("href", "#p-evidence-1");
    expect(within(table).getByText("Not in the evidence")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Detail" })).toHaveTextContent("noted");
    expect(screen.getByRole("region", { name: "Extra" })).toHaveTextContent('"any"');
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a payload as it arrived when there is no schema", () => {
    render(<PayloadView payload={{ a: 1 }} schema={undefined} idPrefix="p" />);
    expect(screen.getByText(/no schema for this result/)).toBeInTheDocument();
  });

  it("shows a drafted document through the host's slots", () => {
    const schema: JsonSchema = {
      properties: { document_kind: { type: "string" }, media_type: { type: "string" }, document_text: { type: "string" } },
    };
    render(
      <AgentViewProvider components={{ Markdown: ({ children }) => <article>md: {children}</article> }}>
        <PayloadView
          payload={{ document_kind: "data_dictionary", media_type: "text/markdown; charset=utf-8", document_text: "# Hi" }}
          schema={schema}
          idPrefix="d"
        />
      </AgentViewProvider>,
    );
    expect(screen.getByRole("region", { name: "Data dictionary" })).toHaveTextContent("md: # Hi");
  });

  it("keeps a document that is not Markdown as written", () => {
    const schema: JsonSchema = { properties: { media_type: { type: "string" }, document_text: { type: "string" } } };
    render(<PayloadView payload={{ media_type: "text/csv", document_text: "a,b\n" }} schema={schema} idPrefix="d" />);
    expect(screen.getByRole("region", { name: "Document" }).querySelector("pre")?.textContent).toBe("a,b\n");
  });

  it("draws a class with the renderer registered for it", () => {
    function Mine({ payload, className, ctx }: PayloadRendererProps) {
      return <p>{`${className}: ${String(payload.summary)} (${ctx ? "schema" : "no schema"})`}</p>;
    }
    const { rerender } = render(
      <AgentViewProvider renderers={{ Review: Mine }}>
        <PayloadView payload={PAYLOAD} schema={SCHEMA} idPrefix="p" className="Review" />
      </AgentViewProvider>,
    );
    expect(screen.getByText("Review: All good (schema)")).toBeInTheDocument();
    rerender(<PayloadView payload={PAYLOAD} schema={undefined} idPrefix="p" className="Review" renderers={{ Review: Mine }} />);
    expect(screen.getByText("Review: All good (no schema)")).toBeInTheDocument();
  });
});
