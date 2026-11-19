# Privacy notice for your instance

The Data Director app holds personal data for your institution. This page says what, so that you
can write the privacy notice your users are owed, and how to make the app link to it.

## Why the instance needs its own notice

The app and its agents run on your computer or server. **Your institution decides why and how
personal data is processed**, so it is the controller under the UK GDPR, or the equivalent law
where you are, and it must give the people who use the app privacy information of its own. The
Data Director project does not receive this data. The project's [privacy notice](../privacy.md) covers
only its documentation website and its work on GitHub, so linking to it would tell your users
nothing about their data.

## What the app holds

Check each line against how you have configured the instance. This is a starting point for the
notice, not the notice, and it is not legal advice.

| What | Why it is held | Where it goes |
|---|---|---|
| **Name and ORCID iD** of each person who signs in, or the operator's where nobody does. | So that each run is recorded as done for a named person, and so that people see only their own work. | Your server. ORCID is asked for the iD and name only ([What is recorded](../user-guide/records.md)). |
| **Run records:** each request, result, the evidence behind it, the checks, the steps taken, who ran it and when. | To let a person and a reviewer check how advice was reached. | Your server, until you remove them. There is no automatic expiry yet. |
| **Conversations and projects:** messages, the inventory of files a person attaches (facts about files, never their content) and the documents agents draft, with every decision on them. | To continue work and to build a deposit package. | Your server. |
| **Decided facts:** a project's funders, the repositories it must use, which files go in, whether sensitive data may be published, and its licence, as a person confirmed them, with what an agent proposed. | To draft documents that respect what was decided. | Your server, and an agent that calls a hosted model unless the profile's `hosted_models` leaves `decisions` out. An agent is never given anyone's reasons. |
| **Facts from ORCID records**, such as affiliations and works, if a person chooses to use them. | To fill in metadata. | Your server, and an agent that calls a hosted model only if the profile's `hosted_models` allows it. |
| **A session cookie.** | To keep a person signed in. It is opaque, unreadable by script and needed for the sign-in the person asked for. | The person's browser. |
| **Problem reports**, if you switch them on. | To fix faults. | **A public GitHub issue**, in the repository `DD_FEEDBACK_REPO` names. The reporter needs no GitHub account, and the page tells them it is public. |
| **Model input**, if you turn on a model-backed agent. | The orchestrator and the advisors write replies, explanations and suggestions with a hosted model. | The model provider, today Anthropic, whose terms govern retention. [AI models](ai-models.md) lists what each agent sends. An advisor calls a model by default, so nothing is sent until it is given a key or a broker credential; set its switch to `template` to keep it from ever sending. |
| **A person's own model key**, if you switch on the model broker. | To let their own account pay for model calls. | The [model broker](model-broker.md), which alone holds it. |

## What to say, and what to decide

The ICO's list of [what privacy information to provide](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/the-right-to-be-informed/what-privacy-information-should-we-provide/)
applies. For this app, decide at least:

- **Who the controller is** and how to reach them and your data protection officer.
- **The lawful basis** for each purpose. Your data protection officer will know your
  institution's policy.
- **How long records are kept.** The app keeps them until you remove them, so the notice needs a
  rule and you need a way to follow it.
- **Who receives the data:** the model provider, if any, GitHub for problem reports, and your
  hosting provider.
- **Transfers outside the UK or EEA**, such as to a model provider in the United States, and
  the safeguard used.
- **How people use their rights**, including access and erasure. The app cannot yet delete a
  run or conversation ([What is recorded](../user-guide/records.md)), so say who does it.

## Link the app to it

Put the notice where your users can read it without signing in, then name its address in
`deployment.yaml`:

```yaml
privacy_notice: https://example.ac.uk/data-director/privacy
```

Apply it (`sudo data-director apply` on a server, `uv run scripts/dd.py apply` in development).
`apply` sets `DD_PRIVACY_NOTICE_URL` in `app.env`, and the app shows a **Privacy notice** link in
the footer of every page once it restarts, which `apply` does on a server.

- **The address must be an absolute `https` URL.** `apply` refuses anything else, and so does the
  app at start-up.
- **Unset, there is no link.** The footer never points to a notice that does not exist, or to the
  project's, which would not cover your instance. Removing `privacy_notice` and applying again
  removes the setting.
- **It is not part of the profile.** The institutional profile holds rules for runs. Changing
  the address does not change the profile or its recorded digest.
- `data-director doctor` reports an address in `deployment.yaml` that has not been applied.
