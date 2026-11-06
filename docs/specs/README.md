# Specifications

A specification (spec) states how one part of Data Director is meant to work today: what it is
for, what must stay true, where its boundaries are, and why it is built this way rather than
another tempting way. There is one spec per topic, and each is kept current. Git history, pull
requests and RFC issues are the record of how the design got here; a spec is the result.

These specs replaced the architecture decision records that used to be in `docs/adr/`. A log of
decisions shows the current design only to a reader who reads every record and works out which
ones amended or superseded which. A spec states the current design directly.

## What a spec is for

A spec should let an agent or a person rebuild a component from the spec and the code without
making a worse choice than the team made. Each statement in a spec passes one test:

> Would a competent agent with full access to the code make a different, worse choice without
> this?

If so, it belongs in a spec. That covers:

- intent and scope: what the component is for and what it deliberately does not do;
- invariants: what must stay true, stated so that a change can be checked against it;
- boundaries and contracts: what the component promises other parts, and what it may depend on;
- rationale: why the design is this one;
- tempting alternatives that were rejected, and why;
- non-functional requirements: security, privacy, accessibility, performance, portability.

Anything a reader can see in the code stays out: module layouts, API shapes, column and field
lists, configuration keys and how-to steps. Those are in the code, its docstrings, the package
READMEs and the [guides](../guide/). The exception is something both critical and easy to break,
which gets one line that points to the code.

## The specs

| Spec | What it covers |
|---|---|
| [System and boundaries](system.md) | The packages, what each may depend on, the harness as its own package, what lives in other repositories, and names. |
| [Dependencies](dependencies.md) | How a dependency is tiered, the fallback each one needs, and the current register. |
| [Contract](contract.md) | The core contract, agent-owned classes, LinkML as its source, identifiers, outcomes and problem reports, the dataset profile and RO-Crate. |
| [Evidence and grounding](grounding.md) | Grounding modes, evidence and its canonicalisations, the grounding linter and the source check. |
| [Transport and tracing](transport.md) | A2A between harness and agents, AG-UI to the browser, OpenTelemetry spans and `dd.*` attributes. |
| [Agents](agents.md) | Agents as separate services, the registry and manifest, derivations, and the roster. |
| [Orchestration](orchestration.md) | Conversations, delegation through the harness, entry points and the process steps an agent serves. |
| [Policy and identity](policy-and-identity.md) | Institutional profiles, signing in, the human an invocation acts for, and model credentials. |
| [The app](app.md) | The browser shell, the app's process boundary and problem reports. |
| [Projects](projects.md) | Projects, file inventories, documents and their versions, proposed changes and approval, sharing. |
| [Drafting documents](drafting.md) | What a drafter may infer, ask and write; gaps, questions to the researcher and their answers. |
| [Deposit](deposit.md) | Repository requirements and the deposit package. |
| [Storage](storage.md) | The run and project storage protocols, their guarantees, the file backends and how another backend is added. |
| [Disclosure](disclosure.md) | Model calls and their prompts, and the disclosure of how each approved document came about, as a statement and a PROV-O graph. |
| [Evaluation and conformance](evaluation.md) | Evaluation, assessment lanes, and how conformance to the Blueprint is reported. |

## The shape of a spec

Each spec has these sections, in this order, and leaves out any that has nothing to say. A spec
may add a section of its own after **Boundaries and contracts** when its topic needs one.

1. **Intent and scope**
2. **Invariants**: a numbered list. Each item can be checked against a change, and says where
   it is enforced (a test, a check in CI) when it is.
3. **Boundaries and contracts**
4. **Rationale**
5. **Rejected alternatives**
6. **Non-functional requirements**
7. **Open questions**: each with its `TODO(#123)` issue reference.

A spec states the design that is meant to hold now. Where the code does not yet do what the spec
says, the spec says so in place, with the issue that will close the gap. Requirements of the
Blueprint are cited by their ID (`R3`, `C5`), and other specs by a relative link to the section.

## Changing a spec

A change to the design changes its spec in the same pull request, so a spec is never behind
`main`. The pull request is decided like any other, by lazy consensus
([Governance: decision-making](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md#decision-making-lazy-consensus)).
A change to how the project conforms to the Blueprint first goes through an `RFC` issue
([Governance: RFC process](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md#rfc-process-for-spec-conformance-changes)).

A change to a fixed format always changes a spec: the contract schema, the `dd.*` trace
attributes, the evidence canonicalisations or the outcome vocabulary. So does a new dependency,
which [Dependencies](dependencies.md) places in a tier with a fallback.

Edit a spec to say what is now true; do not append a dated amendment. The reasons for the change
go in the pull request description, where the history keeps them. When a choice is replaced,
keep the old choice under **Rejected alternatives** if a later contributor might be tempted back
to it.

Anyone may question a spec, with or without proposing an alternative, by opening a
[spec feedback](https://github.com/data-director-agent/data-director/issues/new?template=spec-feedback.yml)
issue.

## Former decision records

Issues, changelogs and older commits cite decision records by number. Each record's content now
lives in the spec below; the record itself is in the history of `docs/adr/` (for example,
`git log --all -- docs/adr/0019-core-contract-and-agent-owned-classes.md`).

| Record | Title | Now in |
|---|---|---|
| ADR-0001 | Tier 1 transport is A2A JSON-RPC; AG-UI carries run events to the viewer | [Transport and tracing](transport.md) |
| ADR-0002 | OpenTelemetry as the trace substrate | [Transport and tracing](transport.md) |
| ADR-0003 | Institutional policy as declarative YAML profiles | [Policy and identity](policy-and-identity.md) |
| ADR-0004 | UUIDv7 for `invocation_id`; RFC 9457 Problem Details | [Contract](contract.md) |
| ADR-0005 | A minimal `DatasetProfile`; SHACL Validation Report | [Contract](contract.md) |
| ADR-0006 | Dependency tiering and the mandatory fallback line | [Dependencies](dependencies.md) |
| ADR-0007 | Polymorphic input and payload, discriminated by `schema_class` | [Contract](contract.md) |
| ADR-0008 | Agents declare a grounding mode | [Evidence and grounding](grounding.md) |
| ADR-0009 | Evidence names a registered canonicalisation | [Evidence and grounding](grounding.md) |
| ADR-0010 | Agents discovered through entry points (superseded by ADR-0011) | [Agents](agents.md) |
| ADR-0011 | Agents are separate services the workbench calls over A2A | [Agents](agents.md), [Transport and tracing](transport.md) |
| ADR-0012 | Conversations, and orchestration through the workbench | [Orchestration](orchestration.md) |
| ADR-0013 | Evaluation on Inspect AI, starting with seeded defects | [Evaluation and conformance](evaluation.md) |
| ADR-0014 | Requirements assessed by test, by human review, or both | [Evaluation and conformance](evaluation.md) |
| ADR-0015 | Evidence carries the content its hash covers | [Evidence and grounding](grounding.md) |
| ADR-0016 (derivations) | The manifest declares derivations; the viewer works out presentation | [Agents](agents.md) |
| ADR-0016 (source check) | The linter checks consistency; a source check verifies citations | [Evidence and grounding](grounding.md) |
| ADR-0017 | The institutional profile belongs to the deployment | [Policy and identity](policy-and-identity.md) |
| ADR-0018 | Every invocation records the human it acted for | [Policy and identity](policy-and-identity.md) |
| ADR-0019 | A core contract, and classes owned by their agents | [Contract](contract.md) |
| ADR-0020 | LinkML is the source of the contract | [Contract](contract.md) |
| ADR-0021 | RO-Crate is a record written after a run | [Contract](contract.md) |
| ADR-0022 | The harness is a package of its own | [System and boundaries](system.md) |
| ADR-0023 | Names that mean the harness say "harness" | [System and boundaries](system.md) |
| ADR-0024 | The app is a React shell drawn from each agent's manifest | [The app](app.md) |
| ADR-0025 | Never written; the number was skipped | — |
| ADR-0026 | A model key stays with the agent that calls the model | [Policy and identity](policy-and-identity.md) |
| ADR-0027 | The app runs no agent in its own process | [The app](app.md), [System and boundaries](system.md) |
| ADR-0028 | The orchestrators route by the Blueprint's entry points | [Orchestration](orchestration.md) |
| ADR-0029 | A person signs in with ORCID through OpenID Connect | [Policy and identity](policy-and-identity.md) |
| ADR-0030 | The app files problem reports as GitHub issues | [The app](app.md) |
| ADR-0031 | The ecosystem and its repository boundaries | [System and boundaries](system.md) |
| ADR-0032 | An agent serves steps of the process flow, not requirements | [Orchestration](orchestration.md) |
| ADR-0033 | The agent roster: one persona per kind of expertise | [Agents](agents.md) |
| ADR-0034 | A project holds an inventory of its files | [Projects](projects.md) |
| ADR-0035 | Project documents and their versions | [Projects](projects.md) |
| ADR-0036 | A person approves or rejects each proposed document version | [Projects](projects.md) |
| ADR-0037 | A project is shared by its members | [Projects](projects.md) |
| ADR-0038 | Repository requirements and the deposit package | [Deposit](deposit.md) |
