# Reaching the admin interfaces over SSH

Several of a deployment's interfaces for its operators listen on the VM's loopback address only.
NGINX does not serve them, the firewall does not open them, and most have no sign-in of their own:
SSH access to the VM is the credential. From your own machine, reach each one through a port
tunnel.

## What is on loopback

| Interface | Port on the VM | Local port used below | Where it is described |
|---|---|---|---|
| The admin service (read-only view of the deployment) | 8200 | 8200 | [The admin service](admin.md) |
| The LLM gateway's admin UI (`/ui`), when the gateway runs | 4000 | 4000 | [LLM gateway](../../../deploy/llm-gateway/README.md) |
| Grafana, Prometheus and Alertmanager, when the gateway's `monitoring` profile runs | 3000, 9090, 9093 | 3000, 9090, 9093 | [LLM gateway](../../../deploy/llm-gateway/README.md) |

Two other services also listen on loopback, but they are APIs that other services call, not pages
for a person: the model broker (8300) and the deposit broker (8310). They need no tunnel.

The app and the workbench are not on this list. They are served by NGINX over HTTPS, the app on
port 443 and the workbench on port 8443, and people sign in to them with ORCID
([Deploying to a VM](../../../deploy/README.md#the-workbench)).

## An SSH config entry

Put one entry in `~/.ssh/config` on your own machine, with a `LocalForward` for each interface you
use. Replace the host name and user with your own.

```sshconfig
Host data-director-admin
    HostName data-director.example.ac.uk
    User you
    # Keep the tunnel to the VM, and nothing else, open.
    RequestTTY no
    ExitOnForwardFailure yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    # The admin service
    LocalForward 127.0.0.1:8200 127.0.0.1:8200
    # The LLM gateway's admin UI
    LocalForward 127.0.0.1:4000 127.0.0.1:4000
    # Grafana, Prometheus and Alertmanager (the gateway's monitoring profile)
    LocalForward 127.0.0.1:3000 127.0.0.1:3000
    LocalForward 127.0.0.1:9090 127.0.0.1:9090
    LocalForward 127.0.0.1:9093 127.0.0.1:9093
```

Then open the tunnel and leave it running:

```bash
ssh -N data-director-admin
```

and open the interface in your browser:

| Interface | Address | Sign in |
|---|---|---|
| The admin service | <http://localhost:8200> | None |
| The LLM gateway | <http://localhost:4000/ui> | `admin`, with the gateway's master key as the password |
| Grafana | <http://localhost:3000> | The first login is `admin`/`admin`; change it |
| Prometheus | <http://localhost:9090> | None |
| Alertmanager | <http://localhost:9093> | None |

The admin service's [Monitoring page](admin.md#monitoring) links to these and shows the alerts
Prometheus and Alertmanager hold, so the tunnel is needed only to open them.

What each setting does:

- `127.0.0.1:` at the start of a `LocalForward` binds the local end to your own loopback address,
  so nobody else on your network can use your tunnel. Without it, OpenSSH may bind a wider address
  if `GatewayPorts` is set.
- `ExitOnForwardFailure yes` makes `ssh` stop if a local port is already taken, rather than
  carrying on with the tunnel half made.
- `ServerAliveInterval` and `ServerAliveCountMax` end a tunnel that has silently died, so it does
  not look open when it is not.
- `RequestTTY no` and `-N` run no command on the VM: the connection exists only to carry the ports.

A `LocalForward` for an interface that is not running on the VM does no harm: the browser reports
that the connection was refused. Delete the lines you do not need, so that the tunnel opens only
what you use.

### One tunnel for one interface

If you want a tunnel for a single interface, say only the admin service, give it its own entry and
open it on demand:

```sshconfig
Host data-director-admin-only
    HostName data-director.example.ac.uk
    User you
    RequestTTY no
    ExitOnForwardFailure yes
    LocalForward 127.0.0.1:8200 127.0.0.1:8200
```

```bash
ssh -N data-director-admin-only
```

### A local port that is already taken

If a port is in use on your machine, use another one for the local end. Only the first number
changes:

```sshconfig
    LocalForward 127.0.0.1:9200 127.0.0.1:8200
```

Then open <http://localhost:9200>.

### Through a jump host

If the VM is reachable only through a bastion host, add `ProxyJump`:

```sshconfig
Host data-director-admin
    HostName data-director.example.ac.uk
    User you
    ProxyJump you@bastion.example.ac.uk
    RequestTTY no
    ExitOnForwardFailure yes
    LocalForward 127.0.0.1:8200 127.0.0.1:8200
```

### Keeping the tunnel up

`ssh -N` runs in the foreground, and stops when you close the terminal. To open it in the
background and close it again by name, use OpenSSH's control socket:

```bash
ssh -fN -o ControlMaster=yes -o ControlPath=~/.ssh/cm-%C -o ControlPersist=no data-director-admin
ssh -O check -o ControlPath=~/.ssh/cm-%C data-director-admin   # is it open?
ssh -O exit  -o ControlPath=~/.ssh/cm-%C data-director-admin    # close it
```

## What not to do

- Do not proxy these interfaces through NGINX, and do not open their ports in the firewall. The
  admin service has no sign-in, and refuses to listen on any address that is not loopback.
- Do not bind a tunnel's local end to `0.0.0.0`, which shares your sign-in-free view with
  everyone on your network.
- Do not put the gateway's master key, or any other secret, in `~/.ssh/config`.

## If it does not work

| Symptom | Likely cause |
|---|---|
| `bind [127.0.0.1]:8200: Address already in use` | Another process on your machine holds the port, perhaps an earlier tunnel. Close it, or use another local port. |
| The browser says the connection was refused | The tunnel is open, but nothing listens on that port on the VM. Check the service there: `systemctl status data-director-admin`, or `data-director-llm-gateway` for the gateway. |
| The admin service answers 421 | The address in the browser is not `localhost` or a loopback address. Use <http://localhost:8200>, not the VM's name or a forwarded name. |
| Grafana, Prometheus or Alertmanager are refused, but the gateway is up | The gateway runs without the `monitoring` profile. Start it as the [gateway's README](../../../deploy/llm-gateway/README.md) describes. |
| The tunnel closes after a while | A firewall drops idle connections. Keep `ServerAliveInterval` set. |
