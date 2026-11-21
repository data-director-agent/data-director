/**
 * The signed-in person's settings, reached from the cog in the banner (docs/specs/app.md): their
 * own AI account, where the deployment offers it (`ModelAccount`), their own repository accounts,
 * where the deployment deposits drafts for them (`RepositoryAccount`), and their preferences for
 * this browser (`Preferences`), each in a tab of its own. What the deployment itself allows is on the Policy page, not here.
 */

import "./SettingsPage.css";

import { Link } from "../../route";
import type { Session } from "../../session/api";
import { PageHeader } from "../frame/PageHeader";
import { ModelAccount } from "./ModelAccount";
import { RepositoryAccount, returned } from "./RepositoryAccount";
import { Tab, TabList, TabPanel, Tabs } from "../ui/Tabs";
import { PREFERENCE_SECTIONS, Preferences } from "./Preferences";

export function SettingsPage({ session }: { session: Session }) {
  const account = session.modelAccounts && session.signsIn;
  const repositories = session.repositoryAccounts;
  // Coming back from connecting a repository account opens its tab.
  const first =
    repositories && returned(window.location.search)
      ? "repositories"
      : account
        ? "account"
        : repositories
          ? "repositories"
          : "appearance";
  return (
    <>
      <PageHeader title="Settings" />
      <p>
        These are your own settings. What this deployment allows, for everyone,
        is on the <Link to="/policy">Policy</Link> page.
      </p>
      <Tabs defaultSelectedKey={first}>
        <TabList aria-label="Settings">
          {account && <Tab id="account">AI account</Tab>}
          {repositories && <Tab id="repositories">Repository accounts</Tab>}
          {PREFERENCE_SECTIONS.map(({ id, title }) => (
            <Tab key={id} id={id}>
              {title}
            </Tab>
          ))}
        </TabList>
        {account && (
          <TabPanel id="account">
            <ModelAccount providers={session.modelAccountProviders} />
          </TabPanel>
        )}
        {repositories && (
          <TabPanel id="repositories">
            <RepositoryAccount />
          </TabPanel>
        )}
        {PREFERENCE_SECTIONS.map(({ id }) => (
          <TabPanel key={id} id={id}>
            <Preferences section={id} />
          </TabPanel>
        ))}
      </Tabs>
      <p>
        <Link to="/">Back to the conversation</Link>
      </p>
    </>
  );
}
