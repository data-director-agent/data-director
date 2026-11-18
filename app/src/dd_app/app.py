"""The app's web server: the shell's API beside the built shell (docs/specs/app.md).

`build_app` wires the server together: the route modules in `dd_app.routes`, one for each area of
the API (each module says what its routes do), the conductor's A2A routes, and the shell. Every
path no route claims serves the shell built from `app/web` (`npm run build` writes
`app/web/dist`). The app stops at start-up, with one line, if a setting is wrong or the shell has
not been built.

`POST /a2a` and `GET /.well-known/agent-card.json` are the conductor's A2A routes, which accept a
delegation agent's callback under a live grant and nothing else (docs/specs/orchestration.md, #129).

Every `/api` route that runs or reads anything acts for the person the request's session names,
and answers `401` with an `unauthenticated` problem when there is none. Every
`/api/projects/{id}/…` route also needs the person to have a role in that project
(`dd_harness.project_access`): someone without one is answered `404`, as for a project that does
not exist, and a member asking for an owner's action `403` (docs/specs/projects.md). A deleted
project is answered as missing to anyone but an owner, and a route that would add to it, or start
or continue a conversation in it, answers `409` with a `project-deleted` problem until it is
restored. `/api/about`, `/api/session` and the sign-in routes are open, so the shell can draw its
sign-in page. A server with no provider configured is a development server: every request acts
for the operator.

Serves on http://127.0.0.1:7860 by default; `DD_APP_HOST` and `DD_APP_PORT` change the address,
and `DD_HARNESS_URL` the address the agents call back on, if they reach the app by another.
`DD_APP_MODEL_BROKER_URL` (a path on the app's origin, such as `/broker`) turns on adding one's own
model account, when the harness also mints model grants (`dd_app.model_accounts`).
A GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` and `DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`) or a
token (`DD_FEEDBACK_GITHUB_TOKEN`, or `_FILE`) turns problem reports on, into `DD_FEEDBACK_REPO`.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import BaseRoute, Mount
from starlette.staticfiles import StaticFiles

from dd_app import feedback, folder_scan
from dd_app.about import about
from dd_app.config import WEB_DIST, settings_from_env
from dd_app.governance import Governance
from dd_app.model_accounts import broker_path
from dd_app.privacy import notice_url
from dd_app.project_service import ProjectService
from dd_app.routes import (
    conversation_deletion,
    conversations,
    deposit,
    documents,
    facts,
    folders,
    materials,
    meta,
    progress,
    projects,
    runs,
    session,
)
from dd_app.routes.common import Deps, Feedback
from dd_app.worker_policy import BundleCaching, WorkerPolicy
from dd_harness.identity import IdentityError
from dd_harness.model_grants import jwks_routes
from dd_harness.policy import PolicyError
from dd_harness.registry import RegistryError
from dd_harness.requirements import RequirementsError
from dd_harness.server import LOOPBACK
from dd_harness.settings import SettingsError
from dd_harness.signin import SignIn, SignInSettings
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes
from dd_sdk import security_log
from dd_sdk.credentials import ConfigError

# Where people reach the app, which the provider sends them back to (dd_harness.signin).
PUBLIC_URL_VARIABLE = "DD_APP_PUBLIC_URL"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860
UNTRUSTED_WARNING = (
    "data-director: warning: serving on {host}. A delegation grant is a bearer token and callers "
    "are not authenticated; expose the app to the host or a private network only "
    "(docs/specs/agents.md).\n"
)
# The areas of the API, each a module of `dd_app.routes`.
AREAS = (
    session,
    meta,
    runs,
    conversation_deletion,
    conversations,
    projects,
    materials,
    folders,
    progress,
    documents,
    facts,
    deposit,
)


class ShellNotBuiltError(FileNotFoundError):
    """`app/web/dist` holds no built shell."""


@dataclass(frozen=True)
class Links:
    """Where the browser reaches what the app links to but does not serve itself, and where on
    this machine the app may read folders.

    `model_broker_path` is where the browser reaches the model broker (`dd_app.model_accounts`);
    with it and a harness that mints model grants, a person may add their own model account.
    `privacy_notice_url` is the operator's privacy notice (`dd_app.privacy`), which `GET /api/about`
    gives so that the footer can link to it; without it the footer has no link. `folder_roots`
    are the folders on this machine the app may describe for an inventory (`dd_app.folder_scan`);
    without them, it describes none.
    """

    model_broker_path: str | None = None
    privacy_notice_url: str | None = None
    folder_roots: folder_scan.FolderRoots | None = None


def build_app(
    governance: Governance,
    web_dist: Path = WEB_DIST,
    *,
    feedback: Feedback | None = None,
    build: Mapping[str, str | None] | None = None,
    sign_in: SignIn | None = None,
    orcid_transport: httpx.BaseTransport | None = None,
    links: Links | None = None,
) -> Starlette:
    """The server. `web_dist` must hold a built shell (its `index.html`).

    Problem reports are on when `feedback` names a credential (`dd_app.feedback`); its client and
    `build` let a test stand in for GitHub and for the build's identity. `sign_in` signs people in;
    its authenticator must be `governance.authenticator`. Without it, the server signs nobody in.
    `orcid_transport` lets a test stand in for ORCID's public API (`dd_harness.orcid`). `links`
    says where the model broker and the operator's privacy notice are, and which folders on this
    machine it may describe (`Links`); without it, there is none of them.
    """
    if not (web_dist / "index.html").is_file():
        raise ShellNotBuiltError(
            f"the shell is not built ({web_dist / 'index.html'} is missing); "
            "run `npm ci && npm run build` in app/web"
        )
    if sign_in is not None and governance.authenticator is not sign_in.authenticator:
        raise IdentityError("the app signs people in, so it must act for whom it signed in")
    links = links or Links()
    deps = Deps(
        governance=governance,
        projects=ProjectService(governance),
        web_dist=web_dist,
        identity=dict(build) if build is not None else about(),
        feedback=feedback or Feedback(),
        sign_in=sign_in,
        orcid_transport=orcid_transport,
        model_broker_path=links.model_broker_path,
        model_account_providers=_model_account_providers(governance, links.model_broker_path),
        privacy_notice_url=links.privacy_notice_url,
        folder_roots=links.folder_roots,
    )
    callback = governance.conductor.harness_url
    # No authenticator: delegation callbacks only, so the app is no other way in
    # (docs/specs/orchestration.md).
    delegation = a2a_routes(governance.conductor, None, callback)[1] if callback else []
    routes: list[BaseRoute] = [route for area in AREAS for route in area.routes(deps)]
    return Starlette(
        routes=[
            *routes,
            *delegation,
            # The harness's public keys for model grants, when it mints them
            # (docs/specs/model-accounts.md).
            *jwks_routes(governance.conductor.model_grants),
            *meta.shell_routes(deps),
            Mount("/", StaticFiles(directory=web_dist, html=True)),
        ],
        middleware=[Middleware(WorkerPolicy), Middleware(BundleCaching)],
    )


def _model_account_providers(
    governance: Governance, model_broker_path: str | None
) -> list[dict[str, Any]] | None:
    """The providers, and the base URL origins, a person's own model account may use, so the
    Profile page offers only those; None where a person may not add one. A person may add their
    own only where the profile lets one pay (docs/specs/model-accounts.md, The profile) and the
    deployment can carry that to the broker. Origins are the profile's, not secrets; the broker
    checks them again."""
    own = governance.conductor.profile.model_accounts
    if governance.conductor.model_grants is None or model_broker_path is None or own.own == "off":
        return None
    return [
        {"provider": p.provider, "base_urls": [u.origin for u in p.base_urls]}
        for p in own.providers
    ]


def main() -> int:
    """The `data-director` console script."""
    host = os.environ.get("DD_APP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("DD_APP_PORT", DEFAULT_PORT))
    base_url = f"http://{host}:{port}"
    try:
        settings = settings_from_env()
        sign_in_settings = SignInSettings.from_env(
            os.environ, settings, base_url, public_url_variable=PUBLIC_URL_VARIABLE
        )
        sign_in = SignIn(sign_in_settings) if sign_in_settings is not None else None
        governance = Governance.create(
            settings, base_url, sign_in.authenticator if sign_in is not None else None
        )
    # No principal (docs/specs/policy-and-identity.md), a provider set wrongly or beside an operator
    # (docs/specs/policy-and-identity.md), or a profile, agent list or source list that is unset,
    # missing or malformed (docs/specs/system.md), requirement sets that are malformed or
    # contradict one another (docs/specs/deposit.md), or an agent in this process configured
    # wrongly: nothing may run.
    except (
        IdentityError,
        SettingsError,
        PolicyError,
        RegistryError,
        SourceConfigError,
        RequirementsError,
        ConfigError,
    ) as exc:
        sys.exit(f"data-director: {exc}")
    feedback_repo = os.environ.get(feedback.REPO_VARIABLE) or feedback.DEFAULT_REPO
    try:
        app = build_app(
            governance,
            feedback=Feedback(feedback.source_from_env(os.environ, feedback_repo), feedback_repo),
            sign_in=sign_in,
            links=Links(
                broker_path(os.environ),
                notice_url(os.environ),
                folder_scan.from_env(os.environ, host, LOOPBACK),
            ),
        )
        if host not in LOOPBACK and sign_in is None:
            sys.stderr.write(UNTRUSTED_WARNING.format(host=host))
        security_log.configure()
        webbrowser.open(f"{base_url}/")
        uvicorn.run(app, host=host, port=port)
    except (ShellNotBuiltError, ConfigError) as exc:
        sys.exit(f"data-director: {exc}")
    finally:
        governance.conductor.close()
    return 0
