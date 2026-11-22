# The policy and the profile

Every run in Data Director is held to the institution's **profile**: a YAML file that says which
agents may run, what each is allowed to do, which actions need a person's approval, what may reach a
hosted AI model, and, once built, who the stewards are. Your team owns it. It is written in YAML,
not code, so that you can read it and propose changes yourself.

## Reading the policy

In the app, select **Policy** in the banner. The page shows:

- the profile's name, version and digest. Every run records these, so you can always tell which
  rules a past run was held to;
- each agent the profile enables, and the action class you assigned it;
- the action classes that need approval;
- **What it does at each step**: for each step of the Blueprint's workflow, whether Data Director
  does it with an agent (*delegated*), only with a data steward's approval (*must approve*), leaves
  it to a person (*never delegated*), or does not offer it.

Researchers see the same page, so you and they read the same rules.

## The keys

Every key, with an example, is in [Institutional profiles](../../../workbench/profiles/README.md).
The ones that most concern a steward:

| Key | What it decides |
|---|---|
| `agents` | Which agents may run ([the agents](../user-guide/agents.md)), and the action class you assign each. If an agent declares another class, its runs fail until you update the profile. |
| `actions_requiring_approval` | The classes a person must approve before an agent acts. A run of such a class is **referred** to a data steward and not run. |
| `hosted_models` | Which kinds of project content may be sent to an agent that uses a hosted AI model. Read [AI models](../operations/ai-models.md) with your data protection officer before you widen it. |
| `attached_documents` | Whether researchers may attach their own documents to a project. |
| `model_accounts` | Whether people may, or must, pay for model calls with their own account. |
| `stewardship` | Who the stewards are, and what they may see ([Becoming a steward](becoming-a-steward.md)). Not built yet. |

A key that nothing enforces is refused when the instance starts. A key that appears in the file
is therefore always in force.

## Changing the profile

Today you propose a change and whoever runs the instance applies it: they edit the file, raise its
`version`, and run `sudo data-director apply` ([The command](../operations/commands.md)).

!!! note "Not built yet"
    Editing and reviewing the profile from the app is [#225](https://github.com/data-director-agent/data-director/issues/225).
