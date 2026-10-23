"""The harness's own server: the conductor over A2A, and nothing else (#55, ADR-0022).

`dd-harness serve` is for deployments. It serves the A2A JSON-RPC endpoint and the agent card,
with no viewer, AG-UI, run index, test kit or Inspect AI. Other systems call it: an app, another
Data Director instance, or a delegation agent calling back under its grant (ADR-0012).
`workbench serve` builds the same conductor with `serving` and adds its own routes.

Every setting comes from the real environment (`Settings.from_env()` with no defaults): an unset
`DD_PROFILE`, `DD_AGENTS_CONFIG`, `DD_SOURCES_CONFIG`, `DD_RUNS_DIR` or principal stops start-up.
No `.env` file is read.

There is no authentication of callers yet (ADR-0018, #17, #43): every invocation acts for the
operator's principal, whoever sent it. Do not expose this server beyond a trusted network.
"""

from __future__ import annotations

import argparse
import sys

from starlette.applications import Starlette

from dd_harness.conductor import Conductor
from dd_harness.identity import Authenticator, IdentityError, OperatorAssertion
from dd_harness.policy import PolicyError
from dd_harness.registry import RegistryError
from dd_harness.settings import Settings, SettingsError, build_authenticator, build_conductor
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes

# Hosts that are reachable from this machine only; any other prints the warning below.
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
UNTRUSTED_WARNING = (
    "dd-harness: warning: serving on {host}. Callers are not authenticated, so every "
    "invocation acts for the configured principal; expose this server to a trusted network "
    "only, or set DD_OIDC_ISSUER to sign callers in.\n"
)


def serving(settings: Settings, base_url: str) -> tuple[Conductor, Authenticator]:
    """A conductor and authenticator for a server reached at `base_url`.

    The conductor's delegation callback is `DD_HARNESS_URL` if set, else `base_url` (ADR-0012).
    An unset principal or a missing or malformed file raises here, before anything is served."""
    authenticator = build_authenticator(settings)
    conductor = build_conductor(settings)
    conductor.harness_url = settings.harness_url or base_url
    return conductor, authenticator


def build_app(conductor: Conductor, authenticator: Authenticator, base_url: str) -> Starlette:
    """The A2A endpoint at `/a2a` and the agent card at `/.well-known/agent-card.json`."""
    _card, routes = a2a_routes(conductor, authenticator, base_url)
    return Starlette(routes=routes)


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        sys.exit("dd-harness: serve needs uvicorn; install data-director-harness[serve]")

    settings = Settings.from_env()
    # The address other systems reach the harness by. Binding all interfaces is no such address,
    # so a deployment behind a proxy or a container network sets DD_HARNESS_URL.
    base_url = settings.harness_url or f"http://{args.host}:{args.port}"
    conductor, authenticator = serving(settings, base_url)
    if args.host not in LOOPBACK and isinstance(authenticator, OperatorAssertion):
        sys.stderr.write(UNTRUSTED_WARNING.format(host=args.host))
    uvicorn.run(build_app(conductor, authenticator, base_url), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-harness", description="Data Director harness: serve the conductor over A2A"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="serve the A2A endpoint and the agent card")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    # No principal (ADR-0018), a path the deployment must name (ADR-0022), or a profile, agent
    # list or source list that is missing or malformed: nothing may be served.
    except (IdentityError, SettingsError, PolicyError, RegistryError, SourceConfigError) as exc:
        sys.exit(f"dd-harness: {exc}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
