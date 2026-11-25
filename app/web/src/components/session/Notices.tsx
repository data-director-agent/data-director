/**
 * What data stewards have done in the person's projects, in the banner (docs/specs/stewardship.md,
 * invariant 13; docs/ui/steward-escalation-flows.md, flow D): "Updates" with how many the person
 * has not seen, opening a list of each one's subject, when it happened and a link to the project.
 * Opening the list marks them seen. A new notice is announced in the polite live region.
 *
 * It reads again every few minutes and when the window regains focus, so that nobody has to
 * reload the page to hear that a steward replied. Which kinds are shown is chosen in Settings.
 */

import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { formatDateTime, formatNumber } from "../../format";
import { Link } from "../../route";
import {
  type Notice,
  fetchNotices,
  markSeen,
  shownNotices,
  unseenCount,
  useNoticeChoices,
} from "../../session/notices";
import { useResource } from "../../useResource";
import { useAnnounceIfMounted } from "../ui/Announcer";

const EVERY_MS = 5 * 60_000;

/** Reads again every `EVERY_MS` and when the window regains focus. */
function useRefreshTick(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const again = () => setTick((t) => t + 1);
    const timer = window.setInterval(again, EVERY_MS);
    window.addEventListener("focus", again);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", again);
    };
  }, []);
  return tick;
}

export function NoticesMenu({ load = fetchNotices }: { load?: (signal: AbortSignal) => Promise<Notice[]> }) {
  const tick = useRefreshTick();
  const { latest } = useResource("notices", (_, signal) => load(signal), tick);
  const choices = useNoticeChoices();
  const announce = useAnnounceIfMounted();
  const notices = shownNotices(latest ?? [], choices);
  const unseen = unseenCount(latest ?? [], choices);
  const previous = useRef(0);

  useEffect(() => {
    if (unseen > previous.current) {
      announce(unseen === 1 ? "1 new update from a data steward." : `${formatNumber(unseen)} new updates from data stewards.`);
    }
    previous.current = unseen;
  }, [unseen, announce]);

  return (
    <details
      className="notices"
      onToggle={(event) => {
        if (event.currentTarget.open) markSeen(notices);
      }}
    >
      <summary className="app-tool-link">
        <Bell className="app-icon" size="1.125em" aria-hidden="true" />
        Updates
        {unseen > 0 && (
          <span className="status status-ok notices-count">
            {formatNumber(unseen)}
            <span className="visually-hidden"> new</span>
          </span>
        )}
      </summary>
      <div className="notices-panel">
        {notices.length === 0 ? (
          <p>Nothing from a data steward in the last 30 days.</p>
        ) : (
          <ul className="notices-list">
            {notices.map((notice) => (
              <li key={notice.event_id} data-seen={choices.seen.has(notice.event_id) || undefined}>
                <Link to={notice.path}>{notice.subject}</Link>{" "}
                <span className="notices-when">{formatDateTime(notice.at)}</span>
              </li>
            ))}
          </ul>
        )}
        <p>
          <Link to="/settings">Choose what you are told about</Link>
        </p>
      </div>
    </details>
  );
}
