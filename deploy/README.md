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
 browser ──HTTPS──▶ NGINX ──▶ app (ORCID sign-in) 127.0.0.1:7860 ──▶ agents 127.0.0.1:8101–8117
```

The app signs people in with ORCID, and each run acts for the person who signed in
([Policy and identity](../docs/specs/policy-and-identity.md)). NGINX adds no password of its own; the app answers 401 to
a request without a session. The app and agents listen on loopback only ([Agents](../docs/specs/agents.md)). Keep
it that way: a request that reaches an agent directly carries no sign-in.

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
| `systemd/data-director-restart.{path,service}` | Restart `data-director.target`, as root, when `deploy.sh` writes `/opt/data-director/restart-requested`. The deploy user has no sudo rule. |
| `agents/<name>.env` | Each agent's port, which must match `app/config/agents.yaml`. |
| `wait-for-ports.sh` | Holds the app back until the agents answer, since it reads their cards once at start-up. |
| `nginx/data-director.conf` | The reverse proxy: HTTPS only, long timeouts for runs, `/a2a` closed from outside. |

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
| `/var/lib/data-director/projects/` | The project store (`DD_PROJECTS_DIR`): each project's log and documents. It outlives releases. |
| `/var/lib/data-director/` | Also the service user's home: uv's Python and package cache, npm's cache. |
| `/etc/data-director/app.env` | The app's settings (`config/examples/app.env`); `DD_OIDC_*` and `DD_APP_PUBLIC_URL` are required. |
| `/etc/data-director/agents.env` | Settings every agent service shares. |
| `/etc/data-director/agents/<name>.env` | One agent service's own settings (`DD_STANDARDS_*`, a model id). |
| `/etc/data-director/credentials/` | Model keys and the ORCID client's secret, readable by root alone. Never put a key or secret in an `.env` file. |
| `/etc/data-director/deploy.env` | `deploy.sh`'s settings. |
| `/var/lib/data-director/.sign-in` | Marks that the run store has started afresh for sign-in (see the upgrade below). |

## Set up the VM

You need Ubuntu 22.04 or later, sudo, a DNS name that resolves to the VM, and an ORCID public API
client (free, at <https://orcid.org/developer-tools>; use <https://sandbox.orcid.org> to try it out)
whose redirect URI is `https://<name>/api/sign-in/callback`.

1. Open the firewall to the web only. Port 80 must be reachable from the internet for Let's
   Encrypt to issue and renew the certificate; on a network where it is not, ask IT for a
   certificate and put it at `/etc/letsencrypt/live/<name>/fullchain.pem` and `privkey.pem`.

   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
   ```

2. Clone the repository anywhere and run the installer. It gets the certificate with certbot
   (which asks for an email address the first time).

   ```bash
   git clone https://github.com/data-director-agent/data-director.git
   cd data-director
   sudo deploy/install.sh --domain data-director.example.ac.uk
   ```

3. It stops and lists what it still needs: the ORCID client. Uncomment and set `DD_OIDC_ISSUER`
   (`https://orcid.org`) and `DD_OIDC_CLIENT_ID` in `/etc/data-director/app.env`
   (`DD_APP_PUBLIC_URL` is already filled in), and put the client's secret in a root-only file.
   Then run it again. That builds the first release, which takes some minutes, starts everything
   and enables the timer.

   ```bash
   sudoedit /etc/data-director/app.env
   sudo install -m 0600 /dev/stdin /etc/data-director/credentials/app/orcid-client-secret   # paste, Ctrl-D
   sudo deploy/install.sh --domain data-director.example.ac.uk
   ```

   Leave `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` empty: the app stops at start-up if it is given
   both a provider and an operator, and `install.sh` refuses to go on.

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
```

`deploy.sh` waits while CI is running, and skips a commit whose CI failed until it passes on a
re-run. If the app does not report the new commit on `/api/about` within two minutes of
starting, it puts the previous release back, records the commit in `failed-commits`, and the
deploy unit fails, which `systemctl --failed` shows.

`deploy.sh` runs nothing as root and needs no sudo rule. To restart the services it writes
`/opt/data-director/restart-requested`, and `data-director-restart.path`, which root installed,
restarts `data-director.target`. The path unit can do that one thing and no other. If it is not
active, `deploy.sh` puts the link back and the deploy unit fails on every pass, while the old
release goes on running: the About page shows an old commit. Re-run `install.sh` to install and
start it, or on a host where sudoers or `install.sh` is out of reach:

```bash
sudo install -m 0644 /opt/data-director/current/deploy/systemd/data-director-restart.{path,service} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now data-director-restart.path
```

A deployment that fails to restart needs this once, and then a pass of `deploy.sh --force` after
removing its commit from `failed-commits`.

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
account ([The app](../docs/specs/app.md)). It is off until the app holds a credential for GitHub,
and the page says so. Issues are public. Use a GitHub App; a personal token is the fallback
([below](#a-token-instead)). Set one, not both: the app stops at start-up if it finds both.

### Create the GitHub App

An organisation owner does this once, at the organisation's **Settings → Developer settings →
GitHub Apps → New GitHub App**.

1. Name it (for example `data-director-feedback`; issues appear as `<name>[bot]`) and give any
   homepage URL, such as the repository's.
2. Untick **Webhook → Active**. The app calls GitHub; GitHub never calls it.
3. Under **Repository permissions**, set **Issues** to **Read and write**. Leave every other
   permission at "No access" (GitHub adds Metadata: read itself).
4. Under **Where can this GitHub App be installed?**, choose **Only on this account**.
5. **Create GitHub App**. Note the **App ID** at the top of its settings page.
6. Under **Private keys**, **Generate a private key**. GitHub downloads a `.pem` file once; keep it
   to install below, then delete your copy.
7. **Install App** (left menu), choose the organisation, **Only select repositories**, and pick
   `data-director`. The installation's ID is the number at the end of the installation's URL
   (`.../settings/installations/<id>`); the app finds it itself, so it is optional.

### Give the app its key

```bash
sudo install -d -m 0700 /etc/data-director/credentials/app
sudo install -m 0600 /path/to/downloaded.pem /etc/data-director/credentials/app/feedback-github-app.pem
shred -u /path/to/downloaded.pem
sudo systemctl edit data-director-app.service   # add the lines below
sudo systemctl restart data-director-app.service
```

```ini
[Service]
LoadCredential=feedback-github-app.pem:/etc/data-director/credentials/app/feedback-github-app.pem
Environment=DD_FEEDBACK_GITHUB_APP_ID=<the App ID>
Environment=DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE=feedback-github-app.pem
```

The drop-in is not shipped, because a unit with `LoadCredential=` does not start if the file is
missing, and the app should start without reports. To name the installation instead of letting
the app find it, add `Environment=DD_FEEDBACK_GITHUB_APP_INSTALLATION_ID=<id>`.

Test it by filing a report from the app. The issue should appear in the repository, opened by
`<name>[bot]`. If the page says the report was not filed, `journalctl -u data-director-app`
shows what GitHub answered: `401` means the App ID or key is wrong, `404` that the App is not
installed on the repository, and `403` that its Issues permission is missing (an owner must
accept a changed permission on the installation).

To rotate the key, generate a second one in the App's settings, replace the file, restart the
app, and then delete the old key in GitHub.

### A token instead

A fine-grained personal access token for this repository only, with Issues: write and nothing
else, also works. It belongs to the person who made it and expires, so make it from a dedicated
service account; issues are filed as that account.

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

### Either way

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

## Moving a VM from the operator and password to sign-in

Pull the repository, delete the `DD_PRINCIPAL_*` lines from `app.env`, set the ORCID client as in
step 3 and run `sudo deploy/install.sh --domain …`. It stops the services and moves the run store
to `/var/lib/data-director/runs.before-sign-in-<date>`, because a store holds no run for a person
who signed in beside runs recorded for an operator. Then remove the password file,
`sudo rm /etc/nginx/data-director.htpasswd`.

## Not done yet

- TODO(#144): no notice reaches anyone when a deployment fails; the journal and
  `systemctl --failed` are the record.
- TODO(#145): GitHub does not show what is deployed.
- Everyone signed in sees every run (#153).
