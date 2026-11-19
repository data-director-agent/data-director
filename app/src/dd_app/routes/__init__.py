"""The app's routes, one module an area, each exposing `routes(deps) -> list[Route]`.

`dd_app.app.build_app` gathers them. A handler is a module-level function given the request,
the principal it acts for and the app's `Deps` (`dd_app.routes.common`), so it can be tested on
its own. Routes reach the projects' logs only through `dd_app.project_service`, and the run store
only through `dd_app.governance`: an Import Linter contract forbids them the stores.
"""
