/**
 * An A2A 1.0 agent card in a form a person can read: every field the card defines is shown when
 * present; each extension through `ExtensionView`; the card's JSON can be unfolded. Give it the
 * card as it arrived: it is read with `readCard`, and what could not be read is listed rather than
 * failing the page. Conformance with the A2A specification is the A2A Inspector's job, not this
 * view's.
 */

import { type ReactNode, useId } from "react";

import { readCard } from "../../card/read";
import type { AgentSkill, SecurityScheme } from "../../card/types";
import { ExtensionView } from "./ExtensionView";
import { Chips, Code, Heading, type HeadingLevel, Items, KeyValues, RawJson, UrlLink } from "./parts";

const yesNo = (v: unknown) => (v ? "yes" : "no");

function Skill({ skill }: { skill: AgentSkill }) {
  return (
    <>
      <p className="dd-item-head">
        <strong>{skill.name || skill.id}</strong>
        {skill.name && skill.id !== skill.name && (
          <span className="dd-muted">
            {" "}
            <Code>{skill.id}</Code>
          </span>
        )}
      </p>
      {skill.description && <p>{skill.description}</p>}
      <KeyValues
        pairs={[
          ["tags", <Chips key="tags" items={skill.tags} />],
          [
            "examples",
            skill.examples?.length ? (
              <ul className="dd-items">
                {skill.examples.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            ) : null,
          ],
          ["input types", skill.inputModes?.length ? <Chips key="in" items={skill.inputModes} /> : null],
          ["output types", skill.outputModes?.length ? <Chips key="out" items={skill.outputModes} /> : null],
        ]}
      />
    </>
  );
}

/** A security scheme is a oneof; its one key names the kind (apiKeySecurityScheme: apiKey). */
function Security({ name, scheme }: { name: string; scheme: SecurityScheme }) {
  const [kind = "unknown", detail] = Object.entries(scheme)[0] ?? [];
  return (
    <>
      <Code>{name}</Code> {kind.replace(/SecurityScheme$/, "")}
      {typeof detail?.description === "string" && <span className="dd-muted"> — {detail.description}</span>}
    </>
  );
}

export function AgentCardView({
  card: value,
  headingLevel = 3,
  idPrefix,
}: {
  /** The card as it arrived, such as the JSON at `/.well-known/agent-card.json`. */
  card: unknown;
  /** The level of the headings of the card's sections. */
  headingLevel?: HeadingLevel;
  /** Prefixes every element id; one is made up when not given. */
  idPrefix?: string;
}) {
  const made = useId();
  const prefix = idPrefix ?? `dd-card${made.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const { card, issues } = readCard(value);
  if (!card) {
    return (
      <div className="dd-card">
        <p className="dd-issue">{issues[0]}</p>
        <RawJson label="What arrived" value={value} />
      </div>
    );
  }
  const caps = card.capabilities ?? {};
  const section = (key: string, title: string, body: ReactNode) => (
    <section className="dd-card-section" aria-labelledby={`${prefix}-${key}`}>
      <Heading level={headingLevel} id={`${prefix}-${key}`}>
        {title}
      </Heading>
      {body}
    </section>
  );
  return (
    <div className="dd-card">
      {card.description && <p>{card.description}</p>}
      <KeyValues
        pairs={[
          ["name", card.name],
          ["version", card.version],
          [
            "provider",
            card.provider ? (
              <>
                {card.provider.organization}
                {card.provider.organization && card.provider.url && " · "}
                {card.provider.url && <UrlLink url={card.provider.url} />}
              </>
            ) : null,
          ],
          ["documentation", card.documentationUrl ? <UrlLink url={card.documentationUrl} /> : null],
          ["icon", card.iconUrl ? <UrlLink url={card.iconUrl} /> : null],
          ["input types", <Chips key="in" items={card.defaultInputModes} />],
          ["output types", <Chips key="out" items={card.defaultOutputModes} />],
          ["signatures", card.signatures?.length ? String(card.signatures.length) : null],
        ]}
      />
      {issues.length > 0 && (
        <ul className="dd-issues" aria-label="Parts of the card that could not be read">
          {issues.map((issue) => (
            <li key={issue} className="dd-issue">
              {issue}
            </li>
          ))}
        </ul>
      )}
      {section(
        "interfaces",
        "Interfaces",
        <Items
          list={card.supportedInterfaces}
          itemKey={(i) => `${i.protocolBinding}-${i.url}`}
          render={(i) => (
            <>
              <span className="dd-chip">{i.protocolBinding ?? "?"}</span> <Code>{i.url}</Code>
              {i.protocolVersion && <span className="dd-muted"> A2A {i.protocolVersion}</span>}
              {i.tenant && (
                <span className="dd-muted">
                  {" "}
                  tenant <Code>{i.tenant}</Code>
                </span>
              )}
            </>
          )}
        />,
      )}
      {section(
        "capabilities",
        "Capabilities",
        <KeyValues
          pairs={[
            ["streaming", yesNo(caps.streaming)],
            ["push notifications", yesNo(caps.pushNotifications)],
            ["extended card", yesNo(caps.extendedAgentCard)],
          ]}
        />,
      )}
      {section(
        "extensions",
        "Extensions",
        <Items
          list={caps.extensions}
          itemKey={(x) => x.uri}
          render={(x) => <ExtensionView extension={x} idPrefix={`${prefix}-x`} />}
        />,
      )}
      {section(
        "security",
        "Security",
        <Items
          list={Object.entries(card.securitySchemes ?? {})}
          itemKey={([name]) => name}
          render={([name, scheme]) => <Security name={name} scheme={scheme} />}
        />,
      )}
      {section(
        "skills",
        "Skills",
        <Items list={card.skills} itemKey={(s) => s.id} render={(s) => <Skill skill={s} />} />,
      )}
      <RawJson label="The card's JSON" value={value} />
    </div>
  );
}
