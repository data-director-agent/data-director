# Data Director admin

A read-only view of one Data Director deployment, for the people who run it. It shows in one place
what an operator otherwise reads from several commands:

- **Operations:** what `data-director doctor` finds, with the fix for each problem; the releases on
  disk and which is live; each service's state and the last lines of its journal.
- **Agents:** each agent in the app's `agents.yaml`, whether its card answers, its version, action
  class and models, and the card itself.
- **People, runs and projects:** everyone a run acted for or who created a project, and every run
  and project in the stores, across all people.
- **Spend:** what the LLM gateway (`deploy/llm-gateway/`) says the month's and the last 30
  days' model calls cost, against an optional budget, and the tokens each run recorded, priced at
  the gateway's prices, by model, agent, person and project.
- **Configuration:** the settings files under `/etc/data-director`, with any value whose name says
  it is a secret hidden, and the command that changes each.
- **Feedback:** where the app's feedback goes (GitHub issues).

It changes nothing. Every change is still made on the VM's command line, and each page names the
command.

## Who can reach it

It has no sign-in. It listens on loopback only (`dd-admin serve` refuses any other address), is not
proxied by NGINX, and refuses a request whose `Host` is not a loopback name, so a web page cannot
reach it through your tunnel. Whoever can open an SSH session to the VM can therefore read it,
which is everyone who could read the same files there already.

```bash
ssh -N -L 8200:127.0.0.1:8200 you@data-director.example.ac.uk
```

then open <http://localhost:8200>. See
[the operations guide](../docs/guide/operations/admin.md) for running it, its settings and what it
reads.

## Running it locally

```bash
DD_RUNS_DIR=/path/to/runs DD_PROJECTS_DIR=/path/to/projects \
DD_AGENTS_CONFIG=app/config/agents.yaml \
uv run dd-admin serve
```

Every setting is optional; a page whose setting is unset says which one.

## Licence

MIT.
