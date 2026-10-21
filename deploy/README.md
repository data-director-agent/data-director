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
 browser ──HTTPS──▶ NGINX (password) ──▶ app 127.0.0.1:7860 ──▶ agents 127.0.0.1:8101, 8102, 8106
```

The app is alpha and has no authentication (#17): every run acts for the operator named in
`/etc/data-director/app.env`, not for the person using the page (ADR-0018). NGINX therefore asks
for a password, and the app and agents listen on loopback only (ADR-0011). Keep it that way until
#17 is done.

## What is here

| File | What it does |
|---|---|
| `install.sh` | Run once as root: packages, Node 22, uv, the `datadirector` user, directories, units, NGINX site, first deployment. Run again to install changed units or NGINX config. |
| `deploy.sh` | One pass of the deployment (fetch, check CI, build, switch, check health, roll back). |
| `deploy.env.example` | `deploy.sh`'s settings: repository, branch, check name, releases kept. |
| `systemd/data-director.target` | The app and the agents, started and restarted together. |
| `systemd/data-director-app.service` | The app (`data-director`), on 127.0.0.1:7860. |
| `systemd/data-director-agent@.service` | One agent per instance: `@hello`, `@quality`, `@director`. |
| `systemd/data-director-deploy.{service,timer}` | Runs `deploy.sh` every five minutes. |
| `agents/<name>.env` | Each agent's port, which must match `app/config/agents.yaml`. |
| `wait-for-ports.sh` | Holds the app back until the agents answer, since it reads their cards once at start-up. |
| `nginx/data-director.conf` | The reverse proxy: password, long timeouts for runs, `/a2a` closed from outside. |

The standards advisor runs in the app's process, so it has no service of its own.

## Layout on the VM

| Path | Holds |
|---|---|
| `/opt/data-director/repo.git` | A bare clone of the branch. |
| `/opt/data-director/releases/<sha>/` | One built commit each: source, `.venv`, `app/web/dist`. The newest three are kept. |
| `/opt/data-director/current` | Link to the live release. The units run from it. |
| `/opt/data-director/failed-commits` | Commits that did not start. They are not tried again. |
| `/var/lib/data-director/runs/` | The run store (`DD_RUNS_DIR`). It outlives releases. |
| `/var/lib/data-director/` | Also the service user's home: uv's Python and package cache, npm's cache. |
| `/etc/data-director/app.env` | The app's settings (`app/env.example`); `DD_PRINCIPAL_*` are required. |
| `/etc/data-director/agents.env` | The agents' settings (`DD_STANDARDS_*`, a model id). |
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
  are the record. A `OnFailure=` unit that mails or posts to a channel would close this.
- TODO: GitHub does not show what is deployed. Recording each pass as a GitHub deployment would
  need a token on the VM with write access.
- The site's password is the only access control until the app authenticates people (#17).
