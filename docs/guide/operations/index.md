# Operations guide

For people who run, configure and operate Data Director at an institution: the research data
management team, a service owner or a systems administrator. It is not for researchers who use the
app (see the [user guide](../user-guide/index.md)) or for people who write agents (see the
[developer guide](../developer-guide/index.md)).

An operator decides three things that a user and a developer do not:

- **What the instance may do.** The [institutional profile](../../../workbench/profiles/README.md)
  names the agents that may run, the actions that need a person's approval, and the agent a
  researcher converses with.
- **What leaves the institution.** An agent that calls a hosted AI model sends it part of the
  user's input. [AI models](ai-models.md) says which agents do, what they send, and how to choose
  and supply a model.
- **Who holds which secret.** Model keys, the operator's identity and the site's password each
  have one place to live. [Configuration](configuration.md) lists them.

## In this guide

| Page | Read it to |
|---|---|
| [AI models](ai-models.md) | Choose a model, supply a key, turn on the model-backed agents, and check what an instance sends to a provider. |
| [Configuration](configuration.md) | Find where each setting lives, in development and on a server. |
| [Deploying to a VM](../../../deploy/README.md) | Install the app and its agents on an Ubuntu VM and keep it up to date. |
| [Institutional profiles](../../../workbench/profiles/README.md) | Write the rules that apply to every run. |

The [architecture](../../architecture.md) and the
[decision records](../../adr/README.md) explain why the system is built as it is.

## Limits of the alpha

- There is no sign-in yet (#17). Every run acts for the operator named in `DD_PRINCIPAL_ID`, and
  the site's password is the only access control. Keep the app and agent ports on loopback or a
  private network.
- No notice reaches anyone when a deployment fails (#144), and GitHub does not show what is
  deployed (#145). The journal and `systemctl --failed` are the record.
- A profile cannot yet limit which models may receive which class of data (#40).
