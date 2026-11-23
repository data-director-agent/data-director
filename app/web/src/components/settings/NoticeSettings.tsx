/**
 * What the person is told about, on the Settings page (docs/specs/stewardship.md, invariant 13):
 * which kinds of update from a data steward the banner's "Updates" shows, kept in this browser
 * only (`session/notices`). A steward also sees where their team is emailed, and about what, which
 * the deployment's profile decides, so it is shown and not changed here.
 */

import { NOTICE_KINDS, setShown, useNoticeChoices } from "../../session/notices";
import type { StewardTeam } from "../../session/api";

// What each notice a team may be emailed about is called (`dd_harness.stewardship.TEAM_NOTICES`).
const TEAM_NOTICES: Record<string, string> = {
  opened: "a new request",
  rerouted: "a request nobody has taken, sent again",
  replied: "a researcher's reply",
  withdrawn: "a request withdrawn",
  reopened: "a request re-opened",
};

function TeamMail({ team }: { team: StewardTeam }) {
  if (!team.notify) {
    return (
      <li>
        {team.name}: not emailed. Look at <strong>Requests</strong> for new requests.
      </li>
    );
  }
  const told = team.notifyOn.map((n) => TEAM_NOTICES[n] ?? n).join(", ");
  return (
    <li>
      {team.name}: emailed at <code>{team.notify}</code> about {told || "nothing"}.
    </li>
  );
}

export function NoticeSettings({ teams }: { teams: readonly StewardTeam[] }) {
  const choices = useNoticeChoices();
  return (
    <section className="preferences" aria-labelledby="notices-heading">
      <h2 id="notices-heading">Notifications</h2>
      <p>
        When a data steward acts on your request, <strong>Updates</strong> in the banner says so.
        Data Director keeps no email address for you, so it does not email you. These choices are
        kept in this browser only.
      </p>
      <fieldset className="field preference">
        <legend>Show an update when</legend>
        {NOTICE_KINDS.map(({ kind, label }) => (
          <div className="field-check" key={kind}>
            <input
              type="checkbox"
              id={`notice-${kind}`}
              checked={!choices.hidden.has(kind)}
              onChange={(event) => setShown(kind, event.currentTarget.checked)}
            />
            <label htmlFor={`notice-${kind}`}>{label}</label>
          </div>
        ))}
      </fieldset>
      {teams.length > 0 && (
        <>
          <h3>Your steward teams</h3>
          <p>Where each team is emailed is set in this deployment&apos;s profile.</p>
          <ul>
            {teams.map((team) => (
              <TeamMail key={team.teamId} team={team} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
