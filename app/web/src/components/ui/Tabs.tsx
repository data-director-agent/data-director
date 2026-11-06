/**
 * The shell's tabs: React Aria's Tabs, TabList, Tab and TabPanel, styled from the tokens. React
 * Aria gives the tab roles, moves between tabs with the arrow keys and Home and End, and puts a
 * single tab stop on the list, with the selected panel next.
 *
 * ```tsx
 * <Tabs defaultSelectedKey="macos">
 *   <TabList aria-label="Operating system">
 *     <Tab id="windows">Windows</Tab>
 *     <Tab id="macos">macOS</Tab>
 *   </TabList>
 *   <TabPanel id="windows">…</TabPanel>
 *   <TabPanel id="macos">…</TabPanel>
 * </Tabs>
 * ```
 */

import {
  Tab as AriaTab,
  TabList as AriaTabList,
  TabPanel as AriaTabPanel,
  Tabs as AriaTabs,
  type TabListProps,
  type TabPanelProps,
  type TabProps,
  type TabsProps,
} from "react-aria-components";

import "./Tabs.css";

export function Tabs(props: TabsProps) {
  return <AriaTabs {...props} className="tabs" />;
}

export function TabList<T extends object>(props: TabListProps<T>) {
  return <AriaTabList {...props} className="tab-list" />;
}

export function Tab(props: TabProps) {
  return <AriaTab {...props} className="tab" />;
}

export function TabPanel(props: TabPanelProps) {
  return <AriaTabPanel {...props} className="tab-panel" />;
}
