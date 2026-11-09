/**
 * An agent's specification (the `agent-spec/v0` extension, `describe(spec)`) field by field. Its
 * id, version and description repeat the card's own and are left out unless asked for; each
 * class's schema is named with its digest, and its JSON Schema can be unfolded.
 */

import type { ReactNode } from "react";

import type { AgentSpec } from "../../spec/read";
import { className as classWords, DERIVATION } from "../../wording";
import { Chips, Code, Items, KeyValues, RawJson } from "./parts";

export function AgentSpecView({ spec, withIdentity = false }: { spec: AgentSpec; withIdentity?: boolean }) {
  const classes = Object.keys(spec.schemas).sort();
  return (
    <KeyValues
      pairs={[
        ...(withIdentity
          ? ([
              ["id", <Code key="id">{spec.id}</Code>],
              ["title", spec.title],
              ["version", spec.version],
              ["description", spec.description],
            ] as [string, ReactNode][])
          : []),
        ["action class", spec.declaredActionClass],
        ["accepts", <Chips key="accepts" items={spec.accepts} />],
        ["payload", spec.payload],
        ["grounding mode", spec.groundingMode],
        ["contract version", spec.contractVersion],
        [
          "models",
          spec.modelsDeclared ? (
            <Chips key="models" items={spec.models.map((m) => `${m.provider}/${m.model} (${m.hosting})`)} />
          ) : (
            <span className="dd-none">not declared</span>
          ),
        ],
        ["serves", spec.serves.length ? <Chips key="serves" items={spec.serves} /> : null],
        [
          "derivations",
          spec.derivations.length ? (
            <Items
              key="derivations"
              list={spec.derivations}
              itemKey={(d) => d.path}
              render={(d) => (
                <>
                  <Code>{d.path}</Code> <span title={DERIVATION[d.how] ?? d.how}>{d.how}</span>
                  {d.recordedIn && (
                    <span className="dd-muted">
                      {" "}
                      recorded in <Code>{d.recordedIn}</Code>
                    </span>
                  )}
                </>
              )}
            />
          ) : null,
        ],
        [
          "schemas",
          classes.length ? (
            <Items
              key="schemas"
              list={classes}
              itemKey={(c) => c}
              render={(c) => {
                const digest = spec.digests[c];
                return (
                  <>
                    <Code>{c}</Code> <span className="dd-muted">({classWords(c)})</span>{" "}
                    {digest && (
                      <span className="dd-digest" title={digest}>
                        sha256 {digest.slice(0, 12)}…
                      </span>
                    )}
                    <RawJson label={`JSON Schema of ${c}`} value={spec.schemas[c]} />
                  </>
                );
              }}
            />
          ) : null,
        ],
      ]}
    />
  );
}
