import { type ReactNode, useCallback, useEffect, useState } from "react";

import { AgentDirectory } from "./components/capabilities/AgentDirectory";
import { ActivityLog } from "./components/workspace/ActivityLog";
import { FeedbackPage } from "./components/feedback/FeedbackPage";
import { ConversationHome } from "./components/conversation/ConversationHome";
import { ErrorBoundary } from "./components/errors/ErrorBoundary";
import { NotFoundPage } from "./components/errors/ErrorPage";
import { Frame } from "./components/frame/Frame";
import { JourneyLanding } from "./components/journey/JourneyLanding";
import { JourneyPage } from "./components/journey/JourneyPage";
import { PolicyPage } from "./components/policy/PolicyPage";
import { ProfilePage } from "./components/profile/ProfilePage";
import { ProjectLanding } from "./components/project/ProjectLanding";
import { ProjectPage } from "./components/project/ProjectPage";
import { ProjectPanelPage } from "./components/project/ProjectPanelPage";
import { ProjectsPage } from "./components/project/ProjectsPage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { PageHeader } from "./components/frame/PageHeader";
import { Account } from "./components/session/Account";
import { SessionTimeout } from "./components/session/SessionTimeout";
import { SignedOutPage } from "./components/session/SignedOutPage";
import { SignInPage } from "./components/session/SignInPage";
import { ActiveProjectProvider } from "./project/active";
import { RunActivityProvider } from "./run/activity";
import { type ProjectTab, isProjectTab, useLocation } from "./route";
import { type Directory, normalise } from "./manifest/normalise";
import type { RawAgentsResponse } from "./manifest/types";
import {
  SIGNED_OUT,
  type Session,
  checkSignedIn,
  useSessionApi,
} from "./session/api";

// The person's projects: `/projects`; a project's documents: `/projects/{project_id}`
// (docs/specs/projects.md); its other tabs, such as its repository or journey map:
// `/projects/{project_id}/{tab}` (`PROJECT_TABS`). `/project` and
// `/journey`, in the main navigation, open the current project's page or journey map, or the list
// of projects (asking which project's, for the map) when none is current.
const PROJECT_PREFIX = "/projects/";

type Load<T> = { state: "loading" } | { state: "failed"; message: string } | { state: "loaded"; value: T };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function fetchDirectory(signal?: AbortSignal): Promise<Directory> {
  const response = await fetch("/api/agents", signal ? { signal } : {});
  checkSignedIn(response);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return normalise((await response.json()) as RawAgentsResponse);
}

/** A project and which of its tabs, from the path; no project when the path is another. A path
 * whose last part is not a tab is all project id, which `hasPage` refuses if it has a `/`. */
function projectRoute(path: string): { projectId: string | null; tab: ProjectTab } {
  if (!path.startsWith(PROJECT_PREFIX)) return { projectId: null, tab: "documents" };
  const rest = path.slice(PROJECT_PREFIX.length);
  const cut = rest.lastIndexOf("/");
  const last = rest.slice(cut + 1);
  if (cut > 0 && last !== "documents" && isProjectTab(last)) {
    return { projectId: rest.slice(0, cut), tab: last };
  }
  return { projectId: rest, tab: "documents" };
}

/** The main navigation's entry that `path` is under. A project's journey map is under Journey
 * map; its other pages, the list of projects and `/project` are under Projects (`/project`). */
function navCurrent(path: string): string {
  const { projectId, tab } = projectRoute(path);
  if (path === "/journey" || (projectId && tab === "journey")) return "/journey";
  if (path === "/project" || path === "/projects" || projectId) return "/project";
  const pages = [
    "/activity",
    "/agents",
    "/feedback",
    "/policy",
    "/profile",
    "/settings",
    "/sign-in",
    "/signed-out",
  ];
  return pages.includes(path) ? path : "/";
}

/** The page for one of a project's tabs. */
function projectPage(projectId: string, tab: ProjectTab, query: string) {
  if (tab === "journey") return <JourneyPage projectId={projectId} query={query} />;
  if (tab === "documents") return <ProjectPage projectId={projectId} query={query} />;
  return <ProjectPanelPage key={`${projectId}/${tab}`} projectId={projectId} tab={tab} />;
}

/** Whether the shell has a page at `path`; anything else is answered with the not-found page. */
function hasPage(path: string): boolean {
  const { projectId } = projectRoute(path);
  if (projectId !== null) return projectId !== "" && !projectId.includes("/");
  return path === "/" || path === "/agents" || path === "/policy" || path in SESSION_PAGES;
}

/** The pages that need only the session and the query, by path. */
const SESSION_PAGES: Record<string, (session: Session, query: string) => ReactNode> = {
  "/feedback": (_, query) => <FeedbackPage query={query} />,
  "/profile": (session) => <ProfilePage session={session} />,
  "/settings": (session) => <SettingsPage session={session} />,
  "/activity": () => <ActivityLog />,
  "/project": () => <ProjectLanding />,
  "/projects": () => <ProjectsPage />,
  "/journey": () => <JourneyLanding />,
};

/**
 * The shell. It asks the server who is signed in before anything else (docs/specs/policy-and-identity.md): where the
 * server signs people in and nobody is, it shows the sign-in page and loads nothing more. Any
 * request the server refuses with `401` later brings the sign-in page back. The server decides;
 * the shell shows what it says.
 */
export function App({ load = fetchDirectory }: { load?: typeof fetchDirectory }) {
  const sessionApi = useSessionApi();
  const [session, setSession] = useState<Load<Session>>({ state: "loading" });
  const [state, setState] = useState<Load<Directory>>({ state: "loading" });
  const location = useLocation();
  const [path = "/", query] = location.split("?");
  const onAgents = path === "/agents";
  const onFeedback = path === "/feedback";
  const onPolicy = path === "/policy";
  const { projectId, tab } = projectRoute(path);
  const current = navCurrent(path);

  useEffect(() => {
    const controller = new AbortController();
    sessionApi.get(controller.signal).then(
      (value) => setSession({ state: "loaded", value }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setSession({ state: "failed", message: message(error) });
      },
    );
    return () => controller.abort();
  }, [sessionApi]);

  // The server refused a request because the session has ended, or the person signed out.
  useEffect(() => {
    const signedOut = () =>
      setSession((current) =>
        current.state === "loaded" && current.value.signsIn
          ? { state: "loaded", value: { ...current.value, principal: null, expiresAt: null } }
          : current,
      );
    window.addEventListener(SIGNED_OUT, signedOut);
    return () => window.removeEventListener(SIGNED_OUT, signedOut);
  }, []);

  const updateSession = useCallback((value: Session) => setSession({ state: "loaded", value }), []);

  const known = session.state === "loaded" ? session.value : null;
  const signedIn = known !== null && (!known.signsIn || known.principal !== null);
  const principalId = known?.principal?.principalId ?? null;

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    load(controller.signal).then(
      (directory) => setState({ state: "loaded", value: directory }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ state: "failed", message: message(error) });
      },
    );
    return () => controller.abort();
  }, [load, signedIn, principalId]);

  // eslint-disable-next-line complexity -- recorded debt: split it, do not add to it (docs/architecture-review.md)
  const content = () => {
    if (path === "/signed-out") return <SignedOutPage issuer={known?.issuer ?? null} />;
    if (session.state === "loading") return <p role="status">Loading…</p>;
    if (session.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not say who is signed in: {session.message}.</p>
        </div>
      );
    }
    if (path === "/sign-in" || !signedIn) {
      return (
        <SignInPage
          issuer={session.value.issuer}
          returnTo={path === "/sign-in" ? "/" : location}
          problem={path === "/sign-in" ? new URLSearchParams(query).get("problem") : null}
        />
      );
    }
    if (!hasPage(path)) return <NotFoundPage path={path} />;
    const sessionPage = SESSION_PAGES[path];
    if (sessionPage) return sessionPage(session.value, query ?? "");
    if (projectId) return projectPage(projectId, tab, query ?? "");
    if (state.state === "loading") return <p role="status">Loading the agents…</p>;
    if (state.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list its agents: {state.message}.</p>
        </div>
      );
    }
    if (onPolicy) return <PolicyPage directory={state.value} />;
    if (!onAgents) return <ConversationHome directory={state.value} />;
    return (
      <>
        <PageHeader title="Agents: what Data Director can do here" titleHidden />
        <AgentDirectory
          directory={state.value}
          initial={new URLSearchParams(query).get("agent") ?? undefined}
          ownAccounts={session.value.modelAccounts && session.value.signsIn}
        />
      </>
    );
  };

  return (
    <Frame
      current={current}
      from={onFeedback ? (new URLSearchParams(query).get("from") ?? "/") : location}
      account={known && <Account session={known} />}
    >
      {known?.signsIn && known.principal && (
        <SessionTimeout session={known} onChange={updateSession} />
      )}
      {/* The app works in one project at a time (docs/specs/app.md); only someone signed in has
          projects to work in. */}
      {/* The runs this tab streams, for the activity log: kept per person signed in. */}
      {signedIn ? (
        <ActiveProjectProvider key={principalId}>
          <RunActivityProvider>
            <ErrorBoundary resetKey={location}>{content()}</ErrorBoundary>
          </RunActivityProvider>
        </ActiveProjectProvider>
      ) : (
        <ErrorBoundary resetKey={location}>{content()}</ErrorBoundary>
      )}
    </Frame>
  );
}
