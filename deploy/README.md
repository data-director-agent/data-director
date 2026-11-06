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
| `/usr/local/bin/data-director` | Installed by `install.sh`: `scripts/dd.py`, run from the clone, never from a release. `sudo data-director doctor` checks the deployment; `sudo data-director secret …` is `secret.sh`. See "Day to day". |
| `secret.sh` | As root, gives an agent a secret such as its model key (`set`), takes it away (`remove`) or lists them (`list`); see "Secrets" below. |
| `credentials.sh` | Turns the files in `/etc/data-director/credentials/<agent>/` into that agent's credentials drop-in. `install.sh` and `secret.sh` use it. |
| `install.sh` | Run once as root: packages, Node 22, uv, the `datadirector` user, directories, units, NGINX site (in place of the packaged default site), first deployment. Run again to install changed units or NGINX config. |
| `deploy.sh` | One pass of the deployment (fetch, check CI, build, switch, check health, roll back). |
| `deploy.env.example` | `deploy.sh`'s settings: repository, branch, check name, releases kept. |
| `systemd/data-director.target` | The app and the agents, started and restarted together. |
| `systemd/data-director-app.service` | The app (`data-director`), on 127.0.0.1:7860. |
| `systemd/data-director-agent@.service` | One agent per instance, named as in `app/config/agents.yaml` (`@example-hello`, `@advisor-quality`, …): every agent the app lists, and `@orchestrator-model` once it has a key. |
| `systemd/data-director-deploy.{service,timer}` | Runs `deploy.sh` every five minutes. |
| `systemd/data-director-restart.{path,service}` | Restart `data-director.target`, as root, when `deploy.sh` writes `/opt/data-director/restart-requested`. The deploy user has no sudo rule. |
| `agents/<name>.env` | Each agent's port, which must match `app/config/agents.yaml`. |
| `../scripts/check_systemd.sh` | Lints the units with `systemd-analyze verify` and systemdlint; run it before changing one. CI runs it. |
| `systemd-lint-baseline.txt` | The systemdlint findings accepted, each with its reason. A new finding fails the check; so does a line that no longer matches one. |
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
| `/etc/data-director/credentials/` | Agents' secrets (`<agent>/<secret>`, put there by `secret.sh`) and the app's (`app/`), readable by root alone. Never put a key or secret in an `.env` file. |
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

Start with the doctor. It changes nothing, and names the command that fixes each problem it
finds:

```bash
sudo data-director doctor
```

It checks:
- that the app runs the release `current` points at, and whether the branch's tip is waiting or
  has failed;
- the deployment timer and the restart path unit, and that the installed units match the
  release's;
- that each agent the target starts is active and answers on its port, and that no unit is left
  over from an agent since removed;
- that each agent that calls a model has its key;
- the sign-in settings and the ORCID secret, and that no key sits in a file every agent reads;
- the profile, orchestrator and unreachable agents the app reports on `/api/about`;
- the NGINX site.

Run without `sudo`, it checks what that user can read and says what it skipped. The commands
below are what it reads.

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

A deployment that failed to restart needs this once. If the About page still shows an old commit
afterwards, see [The app shows an old commit](#the-app-shows-an-old-commit).

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

### The app shows an old commit

Every pass builds the new commit, and the About page (`/api/about`) still reports an old one.
Compare what is linked, what is running and what has failed:

```bash
readlink /opt/data-director/current                     # the release linked
curl -s http://127.0.0.1:7860/api/about                 # the commit running
ls -t /opt/data-director/releases | head -3             # the releases built, newest first
cat /opt/data-director/failed-commits                   # commits that did not start
journalctl -u data-director-deploy -n 50                # why each pass stopped
```

The usual cause is that `deploy.sh` itself cannot finish a pass. The timer runs the copy of
`deploy.sh` in the live release (`current`), so a copy that cannot restart the services, for
example one that still asks for a sudo rule the host has withdrawn, builds each new release,
links it, fails to restart, puts the old link back, and never reaches the release that has the
fix. CI is not at fault: "CI passed" is green on those commits.

`deploy.sh --bootstrap` breaks the loop. It points `current` at a release that is already
built, restarts, and waits for the app to report that commit. It fetches nothing, checks no CI,
builds nothing and does not record a failure. Without a commit it takes the newest release that
finished building; with one (a unique prefix is enough) it takes that release. Run the copy in
the release you want, not the one in `current`, so that the script that runs is the fixed one.
It restarts through the path unit as the deploy user, or directly as root:

```bash
ls -t /opt/data-director/releases | head -3     # pick a release built after the fix
sudo -u datadirector /opt/data-director/releases/<sha>/deploy/deploy.sh --bootstrap
# or, where sudo may not run commands as datadirector:
sudo /opt/data-director/releases/<sha>/deploy/deploy.sh --bootstrap
```

If the app does not report the release within two minutes, `--bootstrap` puts the previous link
back and exits with an error. After it succeeds, the next pass of the timer runs the new
`deploy.sh` and deploys the tip of `main` as usual.

A release built before `--bootstrap` existed has no such option. On a VM whose releases all
predate it, do the same by hand once, as root, with a release built after the fix to the restart:

```bash
sudo ln -sfn /opt/data-director/releases/<sha> /opt/data-director/current
sudo systemctl restart data-director.target
```

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

## Secrets

An agent that calls a hosted model holds the key itself. The app never does, and the key never
appears in a run, a trace or an export ([Policy and identity](../docs/specs/policy-and-identity.md)). The orchestrator and three
advisors' optional explainers can call a model; the model-backed orchestrator is not in
`data-director.target` because it cannot start without a key. The steps to supply a key, turn
an agent on, rotate a key and read a start-up error are in the operations guide,
[AI models](../docs/guide/operations/ai-models.md).

```bash
sudo deploy/secret.sh set orchestrator-model anthropic-api-key    # prompts; the value is not shown
sudo deploy/secret.sh set advisor-policy fairsharing-password     # any secret the agent reads as <NAME>_FILE
sudo deploy/secret.sh list
```

A secret is a root-only file, `/etc/data-director/credentials/<agent>/<secret>`. Its name maps to
the variable the agent reads: `anthropic-api-key` to `ANTHROPIC_API_KEY_FILE`,
`fairsharing-password` to `FAIRSHARING_PASSWORD_FILE`. `credentials.sh` writes one drop-in
per agent, `data-director-agent@<agent>.service.d/credentials.conf`, with a `LoadCredential=` and
an `Environment=` line for each file there. systemd copies the file into that unit's own
credentials directory, so no other agent can read it although all run as one user.

systemd does not start a unit whose credential file is missing (`status=243/CREDENTIALS`, "Failed
to set up credentials"), so the drop-in names only the files present and goes with the last of
them; an advisor with no key runs with its template explainer. Anything else in the directory (a
directory, an empty file, a name that is not lower-case words joined by hyphens) is left out and
reported. `secret.sh` rewrites the one agent's drop-in and restarts it if it is running;
`install.sh` rewrites every agent's, so a secret put in place by hand takes effect when it runs.

## Changing the deployment

- **`deploy.sh` and `wait-for-ports.sh`** run from the live release, so a change to them is
  deployed like any other; `deploy.sh`'s change takes effect from the pass after the one that
  ships it. A `deploy.sh` that cannot finish a pass blocks its own replacement; recover with
  `deploy.sh --bootstrap` from a release that has the fix
  ([The app shows an old commit](#the-app-shows-an-old-commit)).
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
