# The `data-director` command

One command configures and checks an instance. On a VM, `deploy/install.sh` installs it as
`data-director`, run as root. In development it is `uv run scripts/dd.py`. Both are
[`scripts/dd.py`](../../../scripts/dd.py), and they take the same arguments. On a VM the command
runs from the clone you installed from, never from a release, so `deploy.sh` cannot run it.

It finds its target by itself: a VM when `/etc/data-director` and `/opt/data-director` exist,
development otherwise. `--target dev` or `--target vm` overrides that.

## What an instance runs

`deployment.yaml` says what an instance runs: its name, the orchestrator the home page
converses with (`stub` or `model`) and any agents it does not run. It is the one file to edit for
that, and `apply` writes the rest from it: the profile, and on a VM the systemd units and each
agent's credentials. A commented example is in
[`config/examples/deployment.yaml`](../../../config/examples/deployment.yaml).

| | On a VM | In development |
|---|---|---|
| `deployment.yaml` | `/etc/data-director/deployment.yaml` | `config/local/deployment.yaml` |

Agent settings stay in `agents/<name>.env` and secrets in `credentials/`: the file says only what
runs. [Configuration](configuration.md) maps every setting to its home.

## Commands

| Command | Does | Changes anything |
|---|---|---|
| `doctor` | Checks the whole instance against the [configuration](configuration.md) map and names the fix for each problem: a missing key, a unit that is not running, a profile that has fallen behind, a backup that is too old, a disk filling up. On a VM, `--json` prints the report as one JSON document, which [the admin service](admin.md) shows. | No |
| `apply` | Makes the instance what `deployment.yaml` says. `apply --check` says what would change. It refuses to run the model-backed orchestrator before its key is in place, and says which command supplies it. | Yes; `--check` does not |
| `secret set AGENT SECRET` | Stores a secret for one agent, such as `orchestrator-model anthropic-api-key`, prompting for the value without showing it. `remove` takes it away and `list` shows which agent has which secret, by size and never by value. See [AI models](ai-models.md#supply-a-key). | `set` and `remove`: yes |
| `backup` | VM only. Backs up the settings, the secrets and every store now, as the nightly timer does. See [Backups](../../../deploy/README.md#backups). | Writes a backup; stops the app for seconds while a store kept in files is copied |
| `restore [--force] BACKUP` | VM only. Checks a backup, then puts back the settings, secrets and stores, ahead of `deploy/install.sh`. It refuses a store that already holds something unless given `--force`. See [Restore on a clean VM](../../../deploy/README.md#restore-on-a-clean-vm). | Yes |
| `setup` | Development only. Asks for your settings, writes `config/local/`, installs and builds. `--yes` accepts every default and `--no-install` writes the settings only. | Yes |
| `start` | Development only. Applies `config/local/deployment.yaml`, then runs the agents, the app and the shell's dev server. `--agents-only`, `--no-web` and `--no-reload` narrow it. | Yes |

On a VM, put `sudo` before the command (`sudo data-director doctor`). In development, put
`uv run scripts/dd.py` before it instead.

## Switch to the model-backed orchestrator

```bash
sudo data-director secret set orchestrator-model anthropic-api-key   # prompts; the value is not shown
sudoedit /etc/data-director/deployment.yaml                          # orchestrator: model
sudo data-director apply
```

`apply` writes the profile with `orchestrator.model` and a raised `version`, starts the agent with
the rest, makes the app wait for it and restarts the services. To go back, set
`orchestrator: stub` and apply again. What the provider receives, how to choose a model and how
to check the result are in [AI models](ai-models.md#turn-on-the-model-backed-orchestrator).

## Related

- [Deploying to a VM](../../../deploy/README.md): installing the VM, updating it and recovering
  from a stuck deployment.
- [Configuration](configuration.md): where each setting lives, and who reads it.
