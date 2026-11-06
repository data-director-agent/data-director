# Evidence and grounding

## Intent and scope

Nothing an agent presents as a result may rest on something the run cannot account for. Every
payload names what it rests on, every cited thing is identified by a content hash that a reader
can reproduce, and the harness checks both after every run, before a result is stored or shown.
A result that fails is withheld, not annotated.

Two checks do this, and they answer different questions:

- the **grounding linter** is a consistency check. It tests the agent's account of its run
  against itself and against what the conductor recorded;
- the **source check** re-hashes what the evidence cites against a copy of the source that the
  harness holds, independently of the agent.

Neither check judges whether a model's rationale is faithful to its input or to what it
retrieved. That is a question for [evaluation](evaluation.md). Neither verifies a derivation
badge: that is the agent's declaration of how a value was made ([Agents](agents.md)).

This spec covers grounding modes, evidence and its canonicalisations, the linter and the source
check. The rule-by-rule description, with examples, is
[`harness/docs/grounding.md`](../../harness/docs/grounding.md). The envelope and the `Grounded`
mixin are in [Contract](contract.md); the `dd.*` span attributes the rules read are in
[Transport and tracing](transport.md); how a delegating agent obtains the runs it cites is in
[Orchestration](orchestration.md).

## Invariants

1. Every agent declares exactly one grounding mode; there is no default. The conductor, not the
   agent, writes the mode to the envelope and to the root `invoke_agent` span, and computes the
   input hash (`dd-input-json-v1`) and writes it to that span. An agent span that carries a
   conductor-owned attribute, or that lies outside the invocation's tree, is a G0 violation
   (`harness/tests/test_remote.py`, `harness/tests/test_harness.py`).
2. The linter applies the rule table for the declared mode, and G0 and E1 in every mode
   (`harness/tests/test_grounding.py`). The modes and what a result in each may rest on:
   - `retrieval`: records the agent declared it retrieved in this run, matched on both source id
     and content hash; a model call only after a retrieval has ended (G1–G4);
   - `input_only`: only the invocation's input, cited as `input:<invocation_id>` with the
     conductor's input hash; no retrieval; a model call is allowed (R1–R3);
   - `none`: as `input_only`, and no model call (R1–R3, N1);
   - `delegation`: the input, and the envelopes of child runs the conductor itself recorded as
     delegated, by their `dd-envelope-json-v1` hash; no retrieval (R1, D1–D3, G4).
3. A payload the linter cannot check is a violation, never a pass. Every payload has
   `schema_class` and a root `grounded_on`; a succeeded result cites something in every mode,
   if only the input. An agent spec whose payload class does not mix in `Grounded` is refused
   (`sdk/src/dd_sdk/agent.py`, `sdk/tests/test_agent_spec.py`).
4. The linter knows no payload class. It finds grounding references by walking the payload for
   `grounded_on` keys at any depth. Adding an agent or a payload class never changes the linter.
5. `contract.validate` enforces the half of these rules that holds on the envelope alone (mode
   and evidence agree, `grounded_on` present, canonicalisation registered), so an envelope made
   outside Python is checked too (`sdk/tests/test_contract.py`).
6. Every evidence item names a registered canonicalisation. An unknown name is a programmer error
   in `dd_sdk.evidence` and a contract violation in an envelope.
7. A registered canonicalisation never changes the bytes it produces. Changing what a hash
   covers means registering a new name and keeping the old one, so that stored runs still
   verify. No test pins the bytes of each name yet; review is the only guard.
8. A payload states an external identity once, in `grounded_on`. It carries no descriptive copy
   of the record it cites. What a reader is shown about a cited record is the `content` of the
   evidence item with the same source id and content hash (`dd_sdk.evidence.resolve`).
9. E1: evidence that carries `content` hashes to its `content_hash` under its canonicalisation,
   in every mode. `canonicalise(project(d)) == canonicalise(d)` for every registered name
   (`sdk/tests/test_contract.py`).
10. The source check resolves each evidence item by its `snapshot_ref` to a copy pinned by
    SHA-256. S1: the copy holds a record with the item's source id. S2: that record, projected
    under the item's canonicalisation, hashes to its `content_hash` (`harness/tests/test_sources.py`).
11. An item whose `snapshot_ref` has no listed copy is **unresolved**: reported, not a
    violation, and never counted as verified. In `input_only`, `none` and `delegation` modes,
    items citing `input:` or `invocation:` are skipped, because R2, D1 and D2 have already
    checked them against hashes the conductor computed. In `retrieval` mode no rule does that,
    so such items are unresolved.
12. A source file that does not match its pin, or is missing, is a configuration error, and the
    harness does not start. The exception is a copy built outside git, whose entry names the
    command that builds it (`build`): if it has not been built, the harness starts, logs that
    command, and evidence citing it is unresolved. The source check never reads a file without
    its pin and never imports an agent to resolve a source.
13. A violation of either check turns `succeeded` into `failed` with problem type
    `grounding-violation`, and removes the payload and evidence. The two verdicts are stored
    separately (`grounding.txt`, `sources.txt`) and never combined into one.
14. Both checks run offline over a stored run as well as in the conductor, and give the same
    verdict.

## Boundaries and contracts

The facts a run records have two origins, and the strength of each rule follows from which it
relies on:

| Fact | Recorded by |
|---|---|
| grounding mode, input hash, the `invoke_agent` span, `delegations` and each child's envelope hash | the conductor |
| `retrieval` and `chat` spans and their timing, `grounded_on`, evidence, derivation badges | the agent |

An agent runs as a separate service and sends its spans back with its result
([Transport and tracing](transport.md)), so a `retrieval` span is the agent's statement that it
read a record, not the harness's observation of it. Hence:

- in `retrieval` mode a linter pass shows that the agent's citations, evidence and declared
  retrievals agree. It does not show that the agent retrieved anything, or when. With E1 and S2,
  it does show that what the reader sees about a cited record is the source's own projection of
  it;
- the input rules (R2) and delegation rules (D1, D2) are sound, because they compare the agent's
  citations with hashes the conductor computed;
- R1 and N1 show only that the agent reported no retrieval or no model call.

Documentation, the conformance register and the linter's docstring must not describe
`grounding: passed` as proof that an agent retrieved anything.

What the copy of a source is independent of is the agent's process, not its location: the copy
may be a file inside an agent's package, as long as the deployment pins its bytes. It need not be
committed. A copy too large for git, such as the repository advisor's re3data registry, is
built from an archive pinned by URL and SHA-256. The build is deterministic, so the copy's own
SHA-256 can be pinned in advance. Setup, `start`, CI and deployment build it, and `doctor`
checks it. The harness does not require it: an unbuilt copy is one of the agent's sources, and
one agent's data should not decide whether the harness starts, including where that agent is not
deployed or not in the profile. Evidence citing an unbuilt copy is unresolved, which is never
shown as verified. Each
deployment (the workbench, the app) supplies its own list of copies; the harness itself holds
none by default, so a test conductor reports synthetic sources as unresolved, not failed.

A new retrieving agent with a packaged or snapshot source adds one entry to its deployment's
list of copies. An agent whose records need their own projection registers a canonicalisation
in `dd_sdk.evidence`; it does not invent a name in its own package. A new grounding mode is an
entry in the linter's rule table and a contract enum value, and is a change to this spec.

## Rationale

Grounding modes exist because one rule set fitted one agent shape. Rules keyed to one payload
class silently passed any other payload with nothing checked, and a rule requiring retrieval
before any model call made an agent that scores the input it was given impossible. Declaring
the mode lets each shape be held to the strongest rules it can meet, with no shape that slips
through.

The canonicalisation name identifies a projection a reader can reproduce, and evidence carries
that projection as `content`, so a hash can be re-checked offline from the envelope alone, even
if the source has since changed. The cost is one projected record per cited source in the
envelope, a few kilobytes for the standards advisor.

Stating an identity once closes a gap the linter cannot see. If a payload repeated the record's
name or status for the reader, that copy would be unchecked: an agent could change it, pass
every rule, and the reader would see the changed record as verified. With one identity, the
chain from what the reader sees to the source is checked end to end: the content is what the
hash covers (E1), the hash is in the evidence (G4) and on a declared retrieval (G2, G3), and the
hash is what the source holds (S2).

The source check re-resolves citations rather than observing retrieval because the projection
is already reproducible and in the envelope. It needs no registry of source services, no
callback and no change to retrieving agents.

## Rejected alternatives

- **One strict rule set for every agent.** It forces an input-grounded agent to fake a retrieval
  span for its own input.
- **Grounding optional per institutional profile.** It moves a safety invariant into
  configuration ([Policy and identity](policy-and-identity.md)).
- **Per-payload adapters in the linter, or the linter comparing a payload's descriptive fields
  with `grounded_on`.** Both teach the linter payload classes, and adding an agent would then
  change the linter.
- **Building the descriptive copy from the grounding reference.** It states the identifier
  once but leaves the name, status and other descriptive fields unchecked.
- **RFC 8785 (JCS) canonicalisation.** The FAIRsharing projection carries only strings, string
  lists and nulls, for which sorted-key `json.dumps` gives the same bytes without a dependency.
  This reasoning does not cover names whose documents carry numbers; see Open questions.
- **Counting an unresolved item as verified, or one combined verdict.** Either would let a
  reader take an unchecked citation for a checked one.
- **Reading the agent's own copy of a source without a pin.** The copy would then be the
  agent's word again.

## Non-functional requirements

- **Integrity.** Hashes are SHA-256. A stored run stays verifiable for as long as its
  canonicalisation is registered, which is permanently.
- **Portability.** A reader outside Python must be able to reproduce every hash from the
  envelope: canonical bytes are JSON with sorted keys, no whitespace, UTF-8, and lists in
  document order except where a projection sorts them.
- **Availability.** The source check needs no network and no credentials. A source it cannot
  reach is unresolved, not an error.
- **Size.** Evidence `content` adds one projected record per cited source; projections stay
  small.

## Open questions

- TODO(#246): route retrieval through the harness, as delegation is, so that the conductor and
  not the agent records when each record was read. Until then G1 checks only the agent's own
  timeline.
- TODO(#246): a resolver for the standards advisor's `live` route, which needs FAIRsharing
  credentials and network access. Live runs are unresolved.
- TODO(#246): whether an unresolved item in `retrieval` mode should be a violation under some
  profiles, and whether `retrieval`-mode evidence must carry `content`. Evidence without
  `content` passes E1, but a reader then sees only the bare source id.
- TODO(#333): integers in evidence `content` arrive over A2A as floats, so a correct hash fails
  E1. Decide whether evidence travels as a JSON string, as the envelope does, and whether
  canonicalisations that carry numbers need a stricter number form.
- TODO(#247): envelopes stored before evidence carried `content` hold a descriptive copy in
  the payload and no `content`. They are not migrated; decide whether the viewers must keep
  rendering them.
- TODO(#225): how an institution pins a copy of a source of its own, which is neither in the
  repository nor built from a public archive.
