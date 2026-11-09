import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { fixture, spec as helloSpec } from "./fixtures";
import { AgentCardView, AgentSpecView, AgentViewProvider, type ExtensionViewProps } from "../src/react";


describe("AgentCardView", () => {
  it("shows an agent's card, its skill and its specification", async () => {
    const { container } = render(<AgentCardView card={fixture("agent-card.json")} idPrefix="c" />);
    const skills = screen.getByRole("region", { name: "Skills" });
    expect(within(skills).getByText("test.spec")).toBeInTheDocument();
    expect(within(skills).getByText("grounding:retrieval")).toBeInTheDocument();
    const extensions = screen.getByRole("region", { name: "Extensions" });
    expect(within(extensions).getByRole("link", { name: /agent-spec\/v0$/ })).toBeInTheDocument();
    expect(within(extensions).getByText("required")).toBeInTheDocument();
    expect(within(extensions).getByText("items.rationale")).toBeInTheDocument();
    expect(within(extensions).getByText("rationale_derivation")).toBeInTheDocument();
    expect(within(extensions).getByText("JSON Schema of Findings")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Interfaces" })).toHaveTextContent("JSONRPC");
    expect(screen.getByText("The card's JSON")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the harness's agents, each under its name", async () => {
    const { container } = render(<AgentCardView card={fixture("harness-card.json")} />);
    const agents = screen.getByRole("list", { name: "Agents" });
    expect(within(agents).getAllByRole("group").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says what it could not read", () => {
    render(<AgentCardView card={{ name: "x", version: 1, capabilities: { extensions: [{ uri: "urn:other", params: { colour: "blue" } }] } }} />);
    expect(screen.getByRole("list", { name: "Parts of the card that could not be read" })).toHaveTextContent(
      "version is not text.",
    );
    expect(screen.getByText("colour")).toBeInTheDocument();
    expect(screen.getByText("blue")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Skills" })).toHaveTextContent("none");
  });

  it("says when what arrived is not a card", () => {
    render(<AgentCardView card="nope" />);
    expect(screen.getByText("The card is not a JSON object.")).toBeInTheDocument();
  });

  it("draws an extension with the view a host registered for it", () => {
    function Mine({ extension }: ExtensionViewProps) {
      return <p>mine: {String(extension.params?.colour)}</p>;
    }
    render(
      <AgentViewProvider extensions={{ "urn:other": Mine }}>
        <AgentCardView card={{ name: "x", capabilities: { extensions: [{ uri: "urn:other", params: { colour: "blue" } }] } }} />
      </AgentViewProvider>,
    );
    expect(screen.getByText("mine: blue")).toBeInTheDocument();
    expect(screen.getByText("urn:other").tagName).toBe("CODE");
  });

  it("shows every part of a fuller card", async () => {
    const { container } = render(
      <AgentCardView
        headingLevel={2}
        card={{
          name: "full",
          provider: { organization: "Uni", url: "https://uni.example" },
          documentationUrl: "https://docs.example",
          iconUrl: "file:icon.png",
          signatures: [{}],
          supportedInterfaces: [{ url: "https://a.example/a2a", protocolBinding: "HTTP+JSON", tenant: "t1" }],
          securitySchemes: { key: { apiKeySecurityScheme: { description: "An API key", name: "X-Key" } } },
          skills: [{ id: "s1", name: "Search", examples: ["find soil data"], inputModes: ["text/plain"], outputModes: ["application/json"] }],
          capabilities: {
            streaming: true,
            extensions: [{ uri: "https://w3id.org/data-director/a2a/agent-spec/v0", params: { broken: true } }],
          },
        }}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Security" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://uni.example" })).toBeInTheDocument();
    expect(screen.getByText("file:icon.png").tagName).toBe("CODE");
    expect(screen.getByRole("region", { name: "Security" })).toHaveTextContent("key apiKey — An API key");
    expect(screen.getByRole("region", { name: "Skills" })).toHaveTextContent("find soil data");
    expect(screen.getByRole("region", { name: "Capabilities" })).toHaveTextContent("streamingyes");
    expect(screen.getByText("These params are not a readable agent specification.")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("names an agent's identity when asked to", () => {
    const spec = helloSpec();
    render(<AgentSpecView spec={spec} withIdentity />);
    expect(screen.getByText("test.spec")).toBeInTheDocument();
    expect(screen.getByText(spec.description)).toBeInTheDocument();
  });
});
