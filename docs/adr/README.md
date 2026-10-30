# Architecture decision records

An architecture decision record (ADR) states one decision about how Data Director is built, the
question that led to it and what follows from it. Together the records explain why the code is
the way it is, so that a later change can be checked against the reasons for the current design
rather than only against the code.

## When a decision needs a record

A change to a fixed format needs an ADR: the contract schema, the `dd.*` trace attributes, the
evidence canonicalisation or the outcome vocabulary. So does a new dependency, which the record
places in a tier with a fallback ([ADR-0006](0006-dependency-tiering.md)), and any other choice
that a contributor would otherwise have to rediscover from the code.

## Questioning a record

Anyone may question a record or object to it, with or without proposing an alternative, by
opening a
[decision record feedback](https://github.com/data-director-agent/data-director/issues/new?template=adr-feedback.yml)
issue.

## How a record is made

1. Copy [the template](0000-template.md) to `NNNN-short-title.md`, taking the next unused number.
2. Open it in a pull request with the status **Proposed**, usually with the change it describes.
3. The pull request is decided like any other, by lazy consensus
   ([Governance: decision-making](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md#decision-making-lazy-consensus)).
   A decision that changes how the project conforms to the Blueprint first goes through an `RFC`
   issue ([Governance: RFC process](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md#rfc-process-for-spec-conformance-changes)).
4. Once the decision is settled, its status becomes **Accepted**.

A record is not rewritten after it is accepted. A later decision that changes it says so in its
own status line (`Accepted (amends ADR-0003)`), and the earlier record gains a matching note
(`amended by ADR-0017`) or, if replaced outright, the status **Superseded by ADR-NNNN**.

## Numbering

Numbers are not reused. Two records share 0016, from before this rule was written; cite either by
its file name. ADR-0025, the oversight extension on agent cards, is cited in the code but not yet
written, TODO(#67).
