# Deploying to a VM

This directory sets up one Ubuntu VM to run the Data Director app (`app/`) and its agents, and to
keep it deployed: every five minutes the VM fetches `main`, and if CI passed on its tip, builds
and serves that commit. A commit that fails to start is rolled back. The VM pulls; GitHub never
connects to it, so it needs no inbound access but HTTP(S) and no deploy key.

```text
 GitHub ── push to main ──▶ CI ──▶ "CI passed" check on the commit
   ▲                                          │
   │ git fetch, checks API (every 5 min)      │
   │                                          ▼
 VM: data-director-deploy.timer ──▶ deploy.sh ── build ──▶ /opt/data-director/releases/<sha>
                                              └─ switch /opt/data-director/current, restart
 browser ──HTTPS──▶ NGINX (password) ──▶ app 127.0.0.1:7860 ──▶ agents 127.0.0.1:8101, 8102, 8105, 8106
```

The app is alpha and has no authentication (#17): every run acts for the operator named in
`/etc/data-director/app.env`, not for the person using the page (ADR-0018). NGINX therefore asks
for a password, and the app and agents listen on loopback only (ADR-0011). Keep it that way until
#17 is done.

## What is here

| File | What it does |
|---|---|
| `install.sh` | Run once as root: packages, Node 22, uv, the `datadirector` user, directories, units, NGINX site (in place of the packaged default site), first deployment. Run again to install changed units or NGINX config. |
| `deploy.sh` | One pass of the deployment (fetch, check CI, build, switch, check health, roll back). |
| `deploy.env.example` | `deploy.sh`'s settings: repository, branch, check name, releases kept. |
| `systemd/data-director.target` | The app and the agents, started and restarted together. |
| `systemd/data-director-app.service` | The app (`data-director`), on 127.0.0.1:7860. |
| `systemd/data-director-agent@.service` | One agent per instance: `@hello`, `@quality`, `@standards`, `@director`, and `@orchestrator` once it has a key. |
| `systemd/data-director-agent@standards.service.d/` | The standards advisor's model key, loaded as a systemd credential. |
| `systemd/data-director-agent@orchestrator.service.d/` | The model-backed orchestrator's key, likewise. |
| `systemd/data-director-deploy.{service,timer}` | Runs `deploy.sh` every five minutes. |
| `agents/<name>.env` | Each agent's port, which must match `app/config/agents.yaml`. |
| `wait-for-ports.sh` | Holds the app back until the agents answer, since it reads their cards once at start-up. |
| `nginx/data-director.conf` | The reverse proxy: password, long timeouts for runs, `/a2a` closed from outside. |

Every agent, the standards advisor included, is a service of its own; the app runs none in its
process (ADR-0027).

## Layout on the VM

| Path | Holds |
|---|---|
| `/opt/data-director/repo.git` | A bare clone of the branch. |
| `/opt/data-director/releases/<sha>/` | One built commit each: source, `.venv`, `app/web/dist`, and `REVISION`, the full commit hash the app reports as its build. The newest three are kept. |
| `/opt/data-director/current` | Link to the live release. The units run from it. |
| `/opt/data-director/failed-commits` | Commits that did not start. They are not tried again. |
| `/var/lib/data-director/runs/` | The run store (`DD_RUNS_DIR`). It outlives releases. |
| `/var/lib/data-director/` | Also the service user's home: uv's Python and package cache, npm's cache. |
| `/etc/data-director/app.env` | The app's settings (`app/env.example`); `DD_PRINCIPAL_*` are required. |
| `/etc/data-director/agents.env` | Settings every agent service shares. |
| `/etc/data-director/agents/<name>.env` | One agent service's own settings (`DD_STANDARDS_*`, a model id). |
| `/etc/data-director/credentials/` | Model keys, readable by root alone. Never put a key in an `.env` file. |
| `/etc/data-director/deploy.env` | `deploy.sh`'s settings. |
| `/etc/nginx/data-director.htpasswd` | Who may use the site. |

## Set up the VM

You need Ubuntu 22.04 or later, sudo, and a DNS name for the VM if it is to have HTTPS.

1. Clone the repository anywhere and run the installer. It asks for the first user name and
   password for the site.

   ```bash
   git clone https://github.com/data-director-agent/data-director.git
   cd data-director
   sudo deploy/install.sh --domain data-director.example.ac.uk
   ```

2. It stops to ask for the operator. Set `DD_PRINCIPAL_ID` (an ORCID iD URL, for example) and
   `DD_PRINCIPAL_NAME` in `/etc/data-director/app.env`, then run it again. That builds the first
   release, which takes some minutes, starts everything and enables the timer.

   ```bash
   sudoedit /etc/data-director/app.env
   sudo deploy/install.sh --domain data-director.example.ac.uk
   ```

3. Open the firewall to the web only, and add HTTPS. certbot edits the NGINX site and renews the
   certificate itself. It needs the name to resolve to the VM and port 80 to be reachable from the
   internet; on a network that is not, ask IT for a certificate instead.

   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
   sudo certbot --nginx -d data-director.example.ac.uk
   ```

The clone from step 1 is only needed for `install.sh`; the VM deploys from its own bare clone.

### Why it fetches over HTTPS

The repository is public, so the VM fetches it, and reads its checks, over HTTPS with no
credential at all. Nothing on the VM can push, and there is no key to rotate or revoke. HTTPS on
port 443 also passes firewalls that block outbound SSH.

If the repository becomes private, give the VM a read-only
[deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys):
generate it as `datadirector` (`sudo -u datadirector ssh-keygen -t ed25519`), add the public half
to the repository without write access, add GitHub's host key to
`/var/lib/data-director/.ssh/known_hosts`, and set `DD_DEPLOY_REPO=git@github.com:data-director-agent/data-director.git`
in `deploy.env`. The checks API then needs `GITHUB_TOKEN` too, since a deploy key does not
reach the API.

## Day to day

Merging to `main` is the deployment. Within about five minutes of "CI passed" turning green on
the merge commit, the VM runs it.

```bash
systemctl list-timers data-director-deploy.timer        # when it next looks
journalctl -u data-director-deploy -n 50                # what each pass did
sudo systemctl start data-director-deploy.service       # look now
journalctl -u data-director -u 'data-director-agent@*' -f   # the app and agents
readlink /opt/data-director/current                     # which commit is live
sudo htpasswd -B /etc/nginx/data-director.htpasswd NAME # add a user (or change a password)
```

`deploy.sh` waits while CI is running, and skips a commit whose CI failed until it passes on a
re-run. If a release does not answer on `/api/agents` within two minutes of starting, it puts
the previous release back, records the commit in `failed-commits`, and the deploy unit fails,
which `systemctl --failed` shows.

To deploy a commit by hand anyway, or to retry one that failed to start (after removing it from
`failed-commits`):

```bash
sudo -u datadirector /opt/data-director/current/deploy/deploy.sh --force
```

To roll back by hand, point `current` at an earlier release and restart:

```bash
sudo -u datadirector ln -sfn /opt/data-director/releases/<sha> /opt/data-director/current
sudo systemctl restart data-director.target
```

The timer will move it forward again at the next new commit on `main`. To hold the VM on one
release, stop the timer: `sudo systemctl disable --now data-director-deploy.timer`.

## Problem reports

The app's "Report a problem" page files a GitHub issue for the person, who needs no GitHub
account (ADR-0030). It is off until the app holds a token, and the page says so. The token is
a fine-grained personal access token for this repository only, with Issues: write and nothing
else. Issues are public.

```bash
sudo install -d -m 0700 /etc/data-director/credentials/app
sudo install -m 0600 /dev/stdin /etc/data-director/credentials/app/feedback-github-token
# paste the token, then Ctrl-D
sudo systemctl edit data-director-app.service   # add the lines below
sudo systemctl restart data-director-app.service
```

```ini
[Service]
LoadCredential=feedback-github-token:/etc/data-director/credentials/app/feedback-github-token
Environment=DD_FEEDBACK_GITHUB_TOKEN_FILE=feedback-github-token
```

The drop-in is not shipped, because a unit with `LoadCredential=` does not start if the file is
missing, and the app should start without reports.

`DD_FEEDBACK_REPO` in `/etc/data-director/app.env` names another repository
(`owner/name`; default `data-director-agent/data-director`). The version and commit that reports
carry come from the app's package version and `releases/<sha>/REVISION`.

## A model key

An agent that calls a hosted model holds the key itself. The app never does, and the key never
appears in a run, a trace or an export (ADR-0026). Two agents can call a model: the standards
advisor's optional explainer, which in its default mode uses templates and needs no key, and the
model-backed orchestrator, which always needs one (see below).

To give it a model:

1. Put the key where only root can read it. Its unit loads it as a credential
   (`systemd/data-director-agent@standards.service.d/credentials.conf`), so no other agent can
   read it, although every agent runs as `datadirector`.

   ```bash
   sudo install -d -m 0700 /etc/data-director/credentials/standards
   sudo install -m 0600 /dev/stdin /etc/data-director/credentials/standards/anthropic-api-key
   # paste the key, then Ctrl-D
   ```

2. Configure the advisor in its own settings file, `/etc/data-director/agents/standards.env`:

   ```bash
   DD_STANDARDS_EXPLAINER=anthropic
   DD_MODEL_ID=<model identifier from the provider>
   ```

3. Restart it:

   ```bash
   sudo systemctl restart data-director-agent@standards.service
   ```

If the key is missing or empty, the unit stops at start-up with one line in
`journalctl -u data-director-agent@standards`, and is not restarted until the configuration is
fixed. The standards advisor's About tab then names Anthropic and the model.

### The model-backed orchestrator

`orchestrator.model` is not part of `data-director.target`, because it cannot start without a
key. The app converses with `director.stub` until the profile names the orchestrator. To switch:

1. Install its key as in step 1 above, under `/etc/data-director/credentials/orchestrator/`.
   Its settings, all optional, go in `/etc/data-director/agents/orchestrator.env`
   (`workbench/agents/env.example` lists them). It calls a small model by default;
   `DD_MODEL_ID` selects another (some models are not available to an organisation under zero
   data retention).
2. Start it, and have it start with the rest:

   ```bash
   sudo systemctl enable --now data-director-agent@orchestrator.service
   ```

3. Add `8107` to `DD_WAIT_PORTS` in a drop-in for `data-director-app.service`, so the app waits
   for it.
4. In the deployment's profile, set `orchestrator: orchestrator.model` and raise `version`
   (`app/README.md`, "Choosing the orchestrator"). Then restart the app.

Give each model-backed agent its own key, so that one key can be revoked without the others and
the provider's usage reports show each agent separately. Sharing one key is allowed, but
spending limits are set on the provider's side, for the Console workspace a key belongs to, not
per key. To rotate a key, replace the file and restart that agent's unit.

## Changing the deployment

- **`deploy.sh` and `wait-for-ports.sh`** run from the live release, so a change to them is
  deployed like any other; `deploy.sh`'s change takes effect from the pass after the one that
  ships it.
- **The units and the NGINX site** are installed by root, not from the release, so that a commit
  to `main` cannot change whom the services run as. After merging a change to them, pull the
  clone and run `sudo deploy/install.sh --domain …` again. `deploy.sh` logs a warning while the
  installed units differ from the live release's.
- **An agent** added to `app/config/agents.yaml` also needs `agents/<name>.env` with its port,
  an instance in `data-director.target` and `data-director-app.service`, and its port in the
  app's `ExecStartPre`.

## Not done yet

- TODO: no notice reaches anyone when a deployment fails; the journal and `systemctl --failed`
  are the record (#144).
- TODO: GitHub does not show what is deployed (#145).
- The site's password is the only access control until the app authenticates people (#17).
