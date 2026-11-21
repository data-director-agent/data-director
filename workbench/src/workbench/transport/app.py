"""The Starlette application: A2A, AG-UI, the agent manifest, samples, schema files, the store
index, conversations derived from it, and the static viewer. Nothing here names an agent or a
payload class."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

from dd_harness import gateway
from dd_harness.conductor import Conductor
from dd_harness.identity import Authenticator
from dd_harness.signin import SignIn
from dd_harness.transport.a2a import a2a_routes
from dd_harness.transport.agui import agui_routes
from workbench.transport.routes import SAMPLES_DIR, UISCHEMA, VIEWER_DIR, list_samples, read_routes
from workbench.transport.signin import SESSION_PATH, AdminGate, no_sign_in_session, sign_in_routes


def build_app(
    conductor: Conductor,
    authenticator: Authenticator,
    base_url: str = "http://127.0.0.1:8000",
    *,
    sign_in: SignIn | None = None,
) -> Starlette:
    """The workbench's routes. With `sign_in`, the workbench signs admins in
    (`workbench.transport.signin`): every run acts for the admin whose session it is, `/a2a` takes
    delegation callbacks only, as the app's does, and every other route needs an admin's session.
    `authenticator` is then unused, so the operator's principal never reaches a run."""
    if sign_in is not None:
        authenticator = sign_in.authenticator
        _card, routes = a2a_routes(conductor, None, base_url)
        session_routes = sign_in_routes(sign_in)
        middleware = [Middleware(AdminGate, sign_in=sign_in)]
    else:
        _card, routes = a2a_routes(conductor, authenticator, base_url)
        session_routes = [Route(SESSION_PATH, no_sign_in_session, methods=["GET"])]
        middleware = []

    return Starlette(
        middleware=middleware,
        routes=[
            *routes,
            # The tool gateway, for agents' calls only, beside the delegation callback.
            *gateway.routes(conductor.gateway),
            *session_routes,
            *agui_routes(conductor, authenticator),
            *read_routes(conductor),
        ],
    )


__all__ = ["SAMPLES_DIR", "UISCHEMA", "VIEWER_DIR", "build_app", "list_samples"]
