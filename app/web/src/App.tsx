import { useCallback, useEffect, useState } from "react";

import { AgentDirectory } from "./components/capabilities/AgentDirectory";
import { FeedbackPage } from "./components/feedback/FeedbackPage";
import { ConversationHome } from "./components/conversation/ConversationHome";
import { Frame } from "./components/frame/Frame";
import { PageHeader } from "./components/frame/PageHeader";
import { Account } from "./components/session/Account";
import { SessionTimeout } from "./components/session/SessionTimeout";
import { SignedOutPage } from "./components/session/SignedOutPage";
import { SignInPage } from "./components/session/SignInPage";
import { useLocation } from "./route";
import { type Directory, normalise } from "./manifest/normalise";
import type { RawAgentsResponse } from "./manifest/types";
import {
  SIGNED_OUT,
  type Session,
  assuranceText,
  checkSignedIn,
  useSessionApi,
} from "./session/api";

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

/**
 * The shell. It asks the server who is signed in before anything else (ADR-0029): where the
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
    if (onFeedback) return <FeedbackPage query={query ?? ""} />;
    if (state.state === "loading") return <p role="status">Loading the agents…</p>;
    if (state.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list its agents: {state.message}.</p>
        </div>
      );
    }
    if (!onAgents) return <ConversationHome directory={state.value} />;
    return (
      <>
        <PageHeader title="Agents: what Data Director can do here" titleHidden>
          <ActingFor directory={state.value} />
        </PageHeader>
        <AgentDirectory
          directory={state.value}
          initial={new URLSearchParams(query).get("agent") ?? undefined}
        />
      </>
    );
  };

  return (
    <Frame
      current={["/agents", "/feedback", "/sign-in", "/signed-out"].includes(path) ? path : "/"}
      from={onFeedback ? (new URLSearchParams(query).get("from") ?? "/") : location}
      account={known && <Account session={known} />}
    >
      {known?.signsIn && known.principal && (
        <SessionTimeout session={known} onChange={updateSession} />
      )}
      {content()}
    </Frame>
  );
}

/**
 * Whom runs act for and whose rules apply: the signed-in person and who vouched for them, or on a
 * development server the operator's assertion, and the line says which. On the conversation the
 * workspace's status bar says this.
 */
function ActingFor({ directory: { actingFor, profileRef } }: { directory: Directory }) {
  return (
    <p className="hint">
      Acting as {actingFor.name} ({assuranceText(actingFor)}) · Policy <code>{profileRef}</code>
    </p>
  );
}
