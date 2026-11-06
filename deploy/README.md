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
 browser ──HTTPS──▶ NGINX (password) ──▶ app 127.0.0.1:7860 ──▶ agents 127.0.0.1:8101–8117
```

The app is alpha and has no authentication (#17): every run acts for the operator named in
`/etc/data-director/app.env`, not for the person using the page ([Policy and identity](../docs/specs/policy-and-identity.md)). NGINX therefore asks
for a password, and the app and agents listen on loopback only ([Agents](../docs/specs/agents.md)). Keep it that way until
#17 is done.

## What is here

| File | What it does |
|---|---|
| `install.sh` | Run once as root: packages, Node 22, uv, the `datadirector` user, directories, units, NGINX site (in place of the packaged default site), first deployment. Run again to install changed units or NGINX config. |
| `deploy.sh` | One pass of the deployment (fetch, check CI, build, switch, check health, roll back). |
| `deploy.env.example` | `deploy.sh`'s settings: repository, branch, check name, releases kept. |
| `systemd/data-director.target` | The app and the agents, started and restarted together. |
| `systemd/data-director-app.service` | The app (`data-director`), on 127.0.0.1:7860. |
| `systemd/data-director-agent@.service` | One agent per instance, named as in `app/config/agents.yaml` (`@example-hello`, `@advisor-quality`, …): every agent the app lists, and `@orchestrator-model` once it has a key. |
| `credentials/<agent>.conf` | A drop-in that loads the agent's model key as a systemd credential. `install.sh` installs it only while the key file exists. |
| `systemd/data-director-deploy.{service,timer}` | Runs `deploy.sh` every five minutes. |
| `agents/<name>.env` | Each agent's port, which must match `app/config/agents.yaml`. |
| `wait-for-ports.sh` | Holds the app back until the agents answer, since it reads their cards once at start-up. |
| `nginx/data-director.conf` | The reverse proxy: HTTPS only, password, long timeouts for runs, `/a2a` closed from outside. |

Every agent, the standards advisor included, is a service of its own; the app runs none in its
process ([The app](../docs/specs/app.md)).

## Layout on the VM

| Path | Holds |
|---|---|
| `/opt/data-director/repo.git` | A bare clone of the branch. |
| `/opt/data-director/releases/<sha>/` | One built commit each: source, `.venv`, the re3data registry, `app/web/dist`, and `REVISION`, the full commit hash the app reports as its build. The newest three are kept. |
| `/opt/data-director/current` | Link to the live release. The units run from it. |
| `/opt/data-director/cache/sources/` | What agents' built sources are built from (`dd-sources prepare`), one subdirectory per source, such as the pinned re3data export: downloaded once per pin and shared by releases. |
| `/opt/data-director/failed-commits` | Commits that did not start. They are not tried again. |
| `/var/lib/data-director/runs/` | The run store (`DD_RUNS_DIR`). It outlives releases. |
| `/var/lib/data-director/` | Also the service user's home: uv's Python and package cache, npm's cache. |
| `/etc/data-director/app.env` | The app's settings (`config/examples/app.env`); `DD_PRINCIPAL_*` are required. |
| `/etc/data-director/agents.env` | Settings every agent service shares. |
| `/etc/data-director/agents/<name>.env` | One agent service's own settings (`DD_STANDARDS_*`, a model id). |
| `/etc/data-director/credentials/` | Model keys, readable by root alone. Never put a key in an `.env` file. |
| `/etc/data-director/deploy.env` | `deploy.sh`'s settings. |
| `/etc/nginx/data-director.htpasswd` | Who may use the site. |

## Set up the VM

You need Ubuntu 22.04 or later, sudo, and a DNS name that resolves to the VM.

1. Open the firewall to the web only. Port 80 must be reachable from the internet for Let's
   Encrypt to issue and renew the certificate; on a network where it is not, ask IT for a
   certificate and put it at `/etc/letsencrypt/live/<name>/fullchain.pem` and `privkey.pem`.

   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
   ```

2. Clone the repository anywhere and run the installer. It gets the certificate with certbot
   (which asks for an email address the first time) and asks for the first user name and
   password for the site.

   ```bash
   git clone https://github.com/data-director-agent/data-director.git
   cd data-director
   sudo deploy/install.sh --domain data-director.example.ac.uk
   ```

3. It stops to ask for the operator. Set `DD_PRINCIPAL_ID` (an ORCID iD URL, for example) and
   `DD_PRINCIPAL_NAME` in `/etc/data-director/app.env`, then run it again. That builds the first
   release, which takes some minutes, starts everything and enables the timer.

   ```bash
   sudoedit /etc/data-director/app.env
   sudo deploy/install.sh --domain data-director.example.ac.uk
   ```

The site is then HTTPS only: port 80 redirects, TLS 1.3 alone is offered, and HSTS is set. A
certificate from IT needs renewing by hand. One from certbot renews itself, and a hook that
`install.sh` adds reloads NGINX when it does.

The clone from step 2 is only needed for `install.sh`; the VM deploys from its own bare clone.

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
readlink /opt/data-director/current                     # which commit is linked
curl -s http://127.0.0.1:7860/api/about                 # which commit is running
sudo htpasswd -B /etc/nginx/data-director.htpasswd NAME # add a user (or change a password)
```

`deploy.sh` waits while CI is running, and skips a commit whose CI failed until it passes on a
re-run. If the app does not report the new commit on `/api/about` within two minutes of
starting, it puts the previous release back, records the commit in `failed-commits`, and the
deploy unit fails, which `systemctl --failed` shows.

`deploy.sh` restarts the services through one sudo rule, `/etc/sudoers.d/data-director`, which
`install.sh` writes. If the rule is missing, the restart fails, `deploy.sh` puts the link back
and the deploy unit fails on every pass, while the old release goes on running: the About page
shows an old commit. Re-run `install.sh` to restore the rule. Where sudoers is managed centrally,
the rule must be added there, or it will be removed again.

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
account ([The app](../docs/specs/app.md)). It is off until the app holds a token, and the page says so. The token is
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
appears in a run, a trace or an export ([Policy and identity](../docs/specs/policy-and-identity.md)). Two agents can call a model: the standards
advisor's optional explainer and the model-backed orchestrator, which is not in
`data-director.target` because it cannot start without a key. The steps to supply a key, turn
either on, rotate it and read a start-up error are in the operations guide,
[AI models](../docs/guide/operations/ai-models.md). Each key is loaded as a systemd credential from
`/etc/data-director/credentials/<name>/`, by the drop-in `credentials/<name>.conf`.

systemd does not start a unit whose credential file is missing (`status=243/CREDENTIALS`, "Failed
to set up credentials"). So `install.sh` installs an agent's drop-in only while its key file
exists, and removes it otherwise. The standards advisor therefore runs without a key, with its
template explainer. After adding or removing a key, run `install.sh` again.

## Changing the deployment

- **`deploy.sh` and `wait-for-ports.sh`** run from the live release, so a change to them is
  deployed like any other; `deploy.sh`'s change takes effect from the pass after the one that
  ships it.
- **The units and the NGINX site** are installed by root, not from the release, so that a commit
  to `main` cannot change whom the services run as. After merging a change to them, pull the
  clone and run `sudo deploy/install.sh --domain …` again. `deploy.sh` logs a warning while the
  installed units differ from the live release's.
- **An agent** added to `app/config/agents.yaml` also needs `agents/<name>.env` with its port,
  a `Wants=` line for its instance in `data-director.target`, an `After=` line in
  `data-director-app.service`, and its port in that unit's `DD_WAIT_PORTS`.
  `scripts/check_deploy.py`, run in CI, fails until all four agree with `agents.yaml`.

## Not done yet

- TODO(#144): no notice reaches anyone when a deployment fails; the journal and
  `systemctl --failed` are the record.
- TODO(#145): GitHub does not show what is deployed.
- The site's password is the only access control until the app authenticates people (#17).
