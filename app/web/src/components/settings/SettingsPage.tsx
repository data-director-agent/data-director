/**
 * The signed-in person's settings, reached from the cog in the banner (docs/specs/app.md): their
 * own AI account, where the deployment offers it (`ModelAccount`), and their preferences for this
 * browser (`Preferences`). What the deployment itself allows is on the Policy page, not here.
 */

import "./SettingsPage.css";

import { Link } from "../../route";
import type { Session } from "../../session/api";
import { PageHeader } from "../frame/PageHeader";
import { ModelAccount } from "./ModelAccount";
import { Preferences } from "./Preferences";

export function SettingsPage({ session }: { session: Session }) {
  return (
    <>
      <PageHeader title="Settings" />
      <p>
        These are your own settings. What this deployment allows, for everyone, is on the{" "}
        <Link to="/policy">Policy</Link> page.
      </p>
      {session.modelAccounts && session.signsIn && (
        <ModelAccount providers={session.modelAccountProviders} />
      )}
      <Preferences />
      <p>
        <Link to="/">Back to the conversation</Link>
      </p>
    </>
  );
}
