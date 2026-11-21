# Referrals and reviews

A run in Data Director ends in one of five outcomes ([Understanding outcomes](../user-guide/outcomes.md)).
Two of them can bring a matter to you:

- **`referred`**: the matter needs a person's decision. Today only the policy gate refers. A run
  whose action class needs approval is referred to `data_steward` with the reason
  `policy_requires_approval`, and the agent is not run.
- **`abstained`**: the agent declined rather than guess, for example because no source supported
  an answer. This is a valid answer, not an error. The researcher is offered the chance to ask you.
  An abstention never reaches you unless the researcher agrees.

Neither is a failure. How often agents refer and abstain, and how you resolve those cases, is
evidence about where the tool helps and where it does not.

!!! note "Not built yet"
    Today a referred run stops and shows its reason, but cannot yet reach you or be cleared
    ([#16](https://github.com/data-director-agent/data-director/issues/16), [#373](https://github.com/data-director-agent/data-director/issues/373), [#374](https://github.com/data-director-agent/data-director/issues/374)).

## Mandatory reviews

The Blueprint makes some reviews compulsory. Each stops its step until the reviewer acts, and
"Not now" cannot skip it. Your profile chooses the reviewer for each; these are the defaults:

| Trigger | Blueprint | Default reviewer | What stays stopped |
|---|---|---|---|
| The policy gate refers a run | §5.1, §5.4 | steward | the referred run |
| A conflict between funder, journal and institutional requirements | R1, §5.1 | steward | repository choice and what depends on it |
| Personal identifiers or sensitive information flagged | C2, §5.4 | researcher | the deposit |
| Generic or low-quality metadata before submission | C15, §5.4 | researcher | the deposit |
| Ethics approval or embargo not confirmed | R8, §5.2 | researcher | the deposit |

A review that concludes that data should not be shared, in whole or in part, is a valid outcome of
the review (R8), not a failure.

## Who approves what

There are two kinds of approval, and Data Director keeps them apart:

- **You clear a policy exception.** When policy stops a step, you decide whether it may go ahead,
  with a reason (§5.1).
- **The researcher approves the content.** Every document version and the deposit are approved by
  the project's owners (R2). The researcher is responsible for the final submission (§8).

So clearing a step never approves what it produces, and you never approve on a researcher's
behalf. Your profile may add your co-approval before deposit, but this is an extra check and never
replaces theirs ([Deposit readiness](deposit-readiness.md)).
