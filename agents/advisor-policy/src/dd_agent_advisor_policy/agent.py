"""The policy advisor: retrieve → match → assess → advise, over FAIRsharing's policy records,
Jisc Open Policy Finder's, DOAJ's and Crossref's journals.

It serves the first step of Phase 2 (Figure 2), checking funder, journal and institutional data
sharing policies; the same check in Phase 1, before the Data Management Plan is written
(`setup.requirements`, #1534); and the first step of Phase 3 (Figure 3), whether the funder,
journal or institution mandates a repository. The repositories a policy requires are returned in
the form `advisor.repository` takes as `RepositoryNeeds.mandated`.

Grounding invariant: retrieval precedes any model call, and a model's word is never taken alone.
The first search is fixed rules (`match.py`, `discover.py`); the model advisor then reads what it
found and may search for more, and the agent keeps an obligation it states only with a quote found
in the cited record, a record it adds only if a tool retrieved it in this run and it is a policy
of the actor's kind, and never removes a policy or an obligation the rules found (`advise.py`).
Each value says how it was derived (`match_derivation`, `derivation`). A matched policy names its
record once, in `grounded_on`; what the reader is shown about it is the evidence item's `content`,
which the linter re-hashes (E1, docs/specs/grounding.md). Where policies differ, the agent flags it
for human review and never decides which applies.

A journal is identified by its ISSN or title in Open Policy Finder, DOAJ and Crossref, and its
publisher's name is searched too, since most journals follow their publisher's policy (#905).
Open Policy Finder is read live, with a key; without one it is not searched and the statement
says so. DOAJ needs no key, and its record of an open access journal's terms is matched to the
journal as a policy record (#1517).

Before FAIRsharing is searched, each funder is identified in ROR (`resolve.py`): a name that ROR
gives to one organisation is searched by every name ROR records for it, and the funder's ROR record
is cited, so its identifier can be passed on. A name ROR gives to more than one organisation is not
guessed: the candidates are returned, each grounded on its ROR record, and the researcher is asked
which they mean. ROR's records are evidence like FAIRsharing's, under the same canonicalisation.
Each funder ROR identifies is proposed as a funder project fact, with its ROR identifier and its
Crossref Funder ID from the same record, for a person to confirm (`propose.py`).
"""

from __future__ import annotations

from dd_agent_advisor_policy import assess, attached, given, reading, report, search
from dd_agent_advisor_policy.classes import PolicyChecks, PolicyContext
from dd_agent_advisor_policy.explain import Explainer, Explanation, Item, TemplateExplainer
from dd_agent_advisor_policy.extract import Extractor, NoExtractor
from dd_agent_advisor_policy.policy_text import Pages
from dd_agent_advisor_policy.tools import Lookups
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext, Setting, abstain, setting
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import Derivation, GroundingMode, InvocationRequest, ReasonCode
from dd_sdk.registry import provenance

# The setting that decides whether each policy's own text is read.
POLICY_TEXT = "policy_text"
READ, OFF = "read", "off"


class PolicyAgent:
    spec = AgentSpec(
        agent_id="advisor.policy",
        title="Policy Adviser",
        icon="📜",
        version="0.1.0-alpha",
        description=(
            "Checks what the data and open access policies of a project's funders, journals and "
            "institution ask of it, from FAIRsharing's policy records and Jisc Open Policy "
            "Finder's, with each obligation quoted from its record, and flags where they differ. "
            "A person decides which applies."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(PolicyContext),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(PolicyChecks),
        derivations={
            "policies.match_derivation": Derived(Derivation.REGISTRY),
            "policies.obligations.strength": Derived(Derivation.REGISTRY, recorded_in="derivation"),
            "policies.obligations.recorded_as": Derived(Derivation.REGISTRY),
            "policies.obligations.scope": Derived(Derivation.REGISTRY, recorded_in="derivation"),
            "policies.obligations.value": Derived(Derivation.MODEL, recorded_in="derivation"),
            "policies.obligations.quote": Derived(Derivation.MODEL, recorded_in="derivation"),
            "policies.notes": Derived(Derivation.TEMPLATE),
            "policies.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
            "conflicts.description": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
            "not_searched.reason": Derived(Derivation.TEMPLATE),
            "mandated_repositories.name": Derived(Derivation.REGISTRY),
            "funders.crossref_funder_id": Derived(Derivation.REGISTRY),
            "journals.publisher": Derived(Derivation.REGISTRY),
            "readings.status": Derived(Derivation.TEMPLATE),
            "readings.reason": Derived(Derivation.TEMPLATE),
            "readings.dropped": Derived(Derivation.TEMPLATE),
            # The quote is not listed: the code has found it, word for word, in the cited text.
            "readings.stated.kind": Derived(Derivation.MODEL),
            "readings.stated.strength": Derived(Derivation.MODEL),
            "readings.stated.value": Derived(Derivation.MODEL),
        },
        serves=("setup.requirements", "governance.policies", "repository.mandated"),
        reads_attached=(
            "to find what your institution's policy or your award letter asks of the data, "
            "alongside the published policies, quoting each passage for you to confirm"
        ),
        settings={
            POLICY_TEXT: Setting(
                (READ, OFF),
                READ,
                "Fetch each matched policy's own page or PDF, and any the researcher gives or "
                "attaches, and "
                "have the agent's model report what it requires, quoting the passage each "
                "obligation comes from; the code keeps only quotes it finds in the text. Needs a "
                "model. Off: only the registries' records are read.",
            ),
        },
    )

    def __init__(
        self,
        sources: search.Sources,
        explainer: Explainer | None = None,
        *,
        pages: Pages | None = None,
        extractor: Extractor | None = None,
    ) -> None:
        """`sources` are the registries searched; `pages` fetches each policy's own text, which
        `extractor` reads."""
        self.sources = sources
        self.explainer = explainer or TemplateExplainer()
        self.pages = pages
        self.extractor = extractor or NoExtractor()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        # Which copy answered for each FAIRsharing record the live route returned: FAIRsharing
        # itself or the local cache (docs/specs/grounding.md).
        with provenance.observed() as origins:
            return self._run(request, ctx, origins)

    def _run(
        self, request: InvocationRequest, ctx: RunContext, origins: provenance.Provenance
    ) -> AgentResult:
        assert isinstance(request.input, PolicyContext)  # the conductor checked spec.accepts
        # What people in the project decided takes precedence over what the caller wrote.
        context = given.with_project(request.input)
        if not context.actors:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The context names no funder, journal or institution, so there was no policy "
                "to look up.",
            )
        # --- the first search: fixed rules over each registry --------------------------------
        found = search.first_search(list(context.actors), self.sources)
        if isinstance(found, AgentResult):
            return found
        found.origins = origins
        found.emit_spans(ctx)
        texts = reading.read_texts(
            found.matched,
            ctx,
            off=setting(ctx, self.spec, POLICY_TEXT) == OFF,
            pages=self.pages,
            extractor=self.extractor,
            attached=attached.targets(list(context.project_documents), list(context.actors)),
        )
        if not found.records and not found.organisations and not texts.readings:
            return report.no_policy_found(found, texts)

        # --- assess by rule, then advise ------------------------------------------------------
        explanation, advised = self._advise(context, found, ctx)
        return report.Report(
            found,
            texts,
            explanation,
            advised,
            report.model_use(explanation, texts, self.explainer.model_id, self.extractor.model_id),
            decisions=context.project_decisions,
        ).result()

    def _advise(
        self, context: PolicyContext, found: search.FirstSearch, ctx: RunContext
    ) -> tuple[Explanation, report.Advised]:
        """Assess each record by rule, then have the explainer advise on them. The explainer may
        restate a record's obligations and notes, and add records its tools retrieved; those
        records join `found.records`, of which those cited are evidence."""
        items = [
            Item(
                record=record,
                actor=actor,
                obligations=tuple(assess.obligations(record)),
                notes=tuple(assess.notes(record, context)),
            )
            for actor, records in found.matched
            for record in records
        ] + [
            Item(record=record, actor=actor, obligations=(), notes=())
            for actor, records in found.opf.matched
            for record in records
        ]
        lookups = Lookups(
            policies=self.sources.fallback if found.snapshot_ref.stale else self.sources.policies,
            opf=self.sources.opf,
            crossref=self.sources.crossref,
            doaj=self.sources.doaj,
            records=dict(found.records),
            blocked=frozenset(found.blocked),
        )
        explanation = self.explainer.explain(context, items, ctx, lookups)
        items = _restated(items, explanation)
        advised: report.Advised = list(zip(items, explanation.rationales, strict=True)) + list(
            explanation.found
        )
        for sid, looked_up in lookups.records.items():
            found.records.setdefault(sid, looked_up)
        return explanation, advised


def _restated(items: list[Item], explanation: Explanation) -> list[Item]:
    """Each item with the obligations and notes the explainer restated, where it did."""
    if explanation.obligations is None and explanation.notes is None:
        return items
    return [
        Item(
            record=item.record,
            actor=item.actor,
            obligations=(
                explanation.obligations[n]
                if explanation.obligations is not None
                else item.obligations
            ),
            notes=explanation.notes[n] if explanation.notes is not None else item.notes,
            matched_by=item.matched_by,
        )
        for n, item in enumerate(items)
    ]
