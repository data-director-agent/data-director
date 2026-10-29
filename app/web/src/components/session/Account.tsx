/**
 * Who is signed in, in the banner: their name and a way to sign out, or on a development server
 * a badge saying that nobody is signed in and every run acts for the operator (ADR-0029). It is
 * the same on every page.
 */

import "./Session.css";

import { LogOut } from "lucide-react";
import { useState } from "react";

import { navigate } from "../../route";
import { SIGNED_OUT, type Session, useSessionApi } from "../../session/api";
import { Button } from "../ui/Button";

export function Account({ session }: { session: Session }) {
  const api = useSessionApi();
  const [state, setState] = useState<"idle" | "pending" | "failed">("idle");

  if (!session.signsIn) {
    return <span className="status status-warn session-badge">Not signing anyone in</span>;
  }
  if (!session.principal) return null;

  const signOut = () => {
    if (state === "pending") return;
    setState("pending");
    api.signOut().then(
      () => {
        window.dispatchEvent(new Event(SIGNED_OUT));
        navigate("/signed-out");
      },
      () => setState("failed"),
    );
  };

  return (
    <span className="session-account">
      <span>
        <span className="visually-hidden">Signed in as </span>
        {session.principal.name}
      </span>
      {/* Not `isPending`: the button is gone once the page moves on, and its busy indicator
          would be left behind without its label. */}
      <Button variant="quiet" size="small" icon={LogOut} onPress={signOut}>
        Sign out
      </Button>
      {state === "failed" && <span role="alert">Signing out did not work; try again.</span>}
    </span>
  );
}
