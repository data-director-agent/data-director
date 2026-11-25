# Source of the Open Policy Finder records

The policy advisor searches [Jisc Open Policy Finder](https://openpolicyfinder.jisc.ac.uk) (OPF),
which replaced Sherpa Romeo, Juliet and Fact, for the open access policies of funders, journals and
publishers. It reads OPF live, through Jisc's API (`https://api.openpolicyfinder.jisc.ac.uk`).
Nothing is pinned or committed here: this directory holds this note only.

## Citation and credit

The credit the advisor gives, in every payload's limitations and beside each OPF record in the
viewers, names Jisc, the licence and its address:

> Contains data from Jisc Open Policy Finder (https://openpolicyfinder.jisc.ac.uk), licensed under
> CC BY-NC-ND 4.0 (https://creativecommons.org/licenses/by-nc-nd/4.0/).

Each record is cited by its own page on `openpolicyfinder.jisc.ac.uk` and labelled
`open-policy-finder:live:<date>`, the date it was read.

## Licence and use

Jisc licenses the content of OPF under
[CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) and says that, for that
reason, its API is for non-commercial use. Jisc asks for no particular attribution wording, and
states no rate limit, caching rule or rule on use with a model. What follows is what this
repository does about the licence's terms. It is a description of the software, not legal advice.

- **Non-commercial use only.** The API key was requested for non-commercial research use, and the
  licence binds anyone who runs this repository with a key of their own. A deployment that is
  run for a fee, or for commercial advantage, should not set `OPEN_POLICY_FINDER_API_KEY`, or
  should first ask Jisc (help@jisc.ac.uk). The advisor works without the key: FAIRsharing still
  answers, and the run says that OPF was not searched.
- **Credit.** The credit above is shown wherever a record from OPF is. The licence's notice of
  the licence and its link are in it.
- **No copy is kept to fall back to.** OPF is read live only. No snapshot is built, and no OPF
  text is committed to this repository, including as a test fixture (see below).
- **What a run keeps.** The record a run cites is held, as projected, in that run's evidence
  (`EvidenceItem.content`) so that its hash can be checked, and so appears in the run's stored
  envelope. This is the record as Jisc gave it, with its fields renamed and numbers kept as
  strings, not a summary of it. TODO(#952): confirm with Jisc that this is within the licence,
  and whether an exported envelope may be shared.
- **Quoted and adapted text.** Where a model reads a policy, each obligation quotes OPF's own
  words, and the code has found the quote in the record. The obligation's kind, strength and
  value, the brief of what it asks and the model's rationale are the model's reading, not Jisc's
  text, and the payload says so. A person checks each against the record. TODO(#952): confirm
  with Jisc whether such a reading is adapted material, which the licence does not let anyone
  share.
- **No further terms.** Nothing here adds a condition to OPF's content. This repository's MIT
  licence covers the code and not the records it reads.
- **Fields.** `OpfRecord` in `src/dd_agent_advisor_policy/opf.py` keeps names, acronyms, country,
  page address, ISSNs, publishers, identifiers and the policy objects as they came.
- **Load on OPF.** A run makes one request per search the agent needs, at most
  `DD_POLICY_MAX_LOOKUPS` (6 by default) of them for the model's searches. Jisc states no limit.
- **User-Agent.** Requests name the project, not a person.

## The key

The key is free. Jisc issues one on an email to help@jisc.ac.uk with the subject "Open policy
finder API request", which gives the requester's name, email address and organisation and the
purpose of the use. The agent sends it in the `x-api-key` header, never in the query string.

- **Never commit it.** It goes in `OPEN_POLICY_FINDER_API_KEY_FILE` (a file that holds only the
  key, kept outside the repository), or in `OPEN_POLICY_FINDER_API_KEY` for development. On a VM,
  `sudo data-director secret set advisor-policy open-policy-finder-api-key` stores it as a root-only
  credential for the agent alone. `agents/**/*.env` is git-ignored.
- **Do not share it.** It was issued to one person for one purpose. Anyone else who runs the
  agent asks Jisc for their own.
- **Record who holds it.** The deployment's operator keeps the name of the key's holder and the
  date it was issued with the deployment's own records, not here.

## Sources read

Jisc's developer pages under `https://openpolicyfinder.jisc.ac.uk/help/developers`, its
attributions page and the licence at `https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode`.
Jisc's page "About using our content" (`https://www.jisc.ac.uk/website/copyright`) could not be
read. TODO(#952): read it, and amend this note if it adds a term.
