/**
 * The signed-in person's settings, reached from the cog in the banner (docs/specs/app.md): their
 * own AI account, where the deployment offers it (`ModelAccount`), their own repository accounts,
 * where the deployment deposits drafts for them (`RepositoryAccount`), their preferences for
 * this browser (`Preferences`), and what they are told about (`NoticeSettings`), each in a tab of
 * its own. What the deployment itself allows is on the Policy page, not here.
 */

import "./SettingsPage.css";

import { Bell, GitBranch, Sparkles, type LucideIcon } from "lucide-react";

import { Link } from "../../route";
import type { Session } from "../../session/api";
import { PageHeader } from "../frame/PageHeader";
import { ModelAccount } from "./ModelAccount";
import { NoticeSettings } from "./NoticeSettings";
import { RepositoryAccount, returned } from "./RepositoryAccount";
import { Tab, TabList, TabPanel, Tabs } from "../ui/Tabs";
import { PREFERENCE_SECTIONS, Preferences } from "./Preferences";

/** A tab's icon: decoration beside a label that says the same, so hidden from screen readers. */
function TabIcon({ icon: Icon }: { icon: LucideIcon }) {
  return <Icon className="tab-icon" size="1.125em" aria-hidden="true" />;
}

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
          {account && (
            <Tab id="account">
              <TabIcon icon={Sparkles} />
              AI account
            </Tab>
          )}
          {repositories && (
            <Tab id="repositories">
              <TabIcon icon={GitBranch} />
              Repository accounts
            </Tab>
          )}
          {PREFERENCE_SECTIONS.map(({ id, title, icon }) => (
            <Tab key={id} id={id}>
              <TabIcon icon={icon} />
              {title}
            </Tab>
          ))}
          <Tab id="notifications">
            <TabIcon icon={Bell} />
            Notifications
          </Tab>
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
        <TabPanel id="notifications">
          <NoticeSettings teams={session.principal?.teams ?? []} />
        </TabPanel>
      </Tabs>
      <p>
        <Link to="/">Back to the conversation</Link>
      </p>
    </>
  );
}
