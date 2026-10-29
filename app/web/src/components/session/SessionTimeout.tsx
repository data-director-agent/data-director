/**
 * A warning before a session ends for want of use, with a way to keep it going (WCAG 2.2.1,
 * ADR-0029).
 *
 * The server says when the session ends (`expiresAt`). Every request restarts that clock, so
 * shortly before the time the page asks again, without restarting it. If the end is still near,
 * the notice is shown; "Stay signed in" asks the server to keep the session going. If nothing is
 * done, the page is told that the session has ended when it does.
 */

import "./Session.css";

import { useEffect, useState } from "react";

import { SIGNED_OUT, type Session, useSessionApi } from "../../session/api";
import { Button } from "../ui/Button";

/** How long before the end the notice is shown: time enough to read it and act (WCAG 2.2.1). */
export const WARN_MS = 5 * 60 * 1000;
// The longest delay `setTimeout` keeps (about 24.8 days); a longer one fires at once.
const LONGEST_TIMEOUT_MS = 2 ** 31 - 1;

export function SessionTimeout({
  session,
  onChange,
}: {
  session: Session;
  onChange: (session: Session) => void;
}) {
  const api = useSessionApi();
  // The end the notice warns of: a later end, once the session is kept going, has no notice yet.
  const [warnedOf, setWarnedOf] = useState<string | null>(null);
  const { expiresAt } = session;
  const warning = warnedOf !== null && warnedOf === expiresAt;

  useEffect(() => {
    if (!expiresAt) return;
    const end = Date.parse(expiresAt);
    if (end - Date.now() - WARN_MS > LONGEST_TIMEOUT_MS) return; // longer than any session lives
    let ended: ReturnType<typeof setTimeout> | undefined;
    const check = setTimeout(
      () => {
        api.get().then(
          (fresh) => {
            if (fresh.expiresAt !== expiresAt) {
              onChange(fresh); // used since, so it ends later (or has ended): look again
              return;
            }
            setWarnedOf(expiresAt);
            ended = setTimeout(
              () => window.dispatchEvent(new Event(SIGNED_OUT)),
              Math.max(0, end - Date.now()),
            );
          },
          () => setWarnedOf(expiresAt),
        );
      },
      Math.max(0, end - Date.now() - WARN_MS),
    );
    return () => {
      clearTimeout(check);
      if (ended) clearTimeout(ended);
    };
  }, [api, expiresAt, onChange]);

  // The live region is always there, so that a screen reader announces the warning when it is
  // filled in.
  const at =
    expiresAt && new Date(expiresAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return (
    <div role="status">
      {warning && at && (
        <div className="callout status-warn session-timeout">
          <p>You will be signed out at {at}, because nothing has been done here for a while.</p>
          <Button size="small" onPress={() => api.stay().then(onChange, () => undefined)}>
            Stay signed in
          </Button>
        </div>
      )}
    </div>
  );
}
