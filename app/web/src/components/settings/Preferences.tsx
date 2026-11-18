/**
 * The person's preferences, on the Settings page (docs/specs/app.md, "Preferences"): how the app
 * looks, how it writes dates and times, and which project it opens in, a section to a tab. Each choice applies at
 * once and is kept in this browser only (`preferences.ts`); nothing here reaches the server.
 */

import { formatDateTime } from "../../format";
import {
  type PreferenceName,
  type Preferences as PreferenceValues,
  setPreference,
  usePreferences,
} from "../../preferences";

interface Setting<K extends PreferenceName> {
  name: K;
  legend: string;
  options: { value: PreferenceValues[K]; label: string }[];
}

type AnySetting = { [K in PreferenceName]: Setting<K> }[PreferenceName];

const APPEARANCE: AnySetting[] = [
  {
    name: "theme",
    legend: "Colour scheme",
    options: [
      { value: "light", label: "Light" },
      { value: "dark", label: "Dark" },
      { value: "system", label: "Match my device" },
    ],
  },
  {
    name: "textSize",
    legend: "Text size",
    options: [
      { value: "standard", label: "Standard" },
      { value: "large", label: "Large" },
      { value: "larger", label: "Larger" },
    ],
  },
  {
    name: "density",
    legend: "Spacing",
    options: [
      { value: "comfortable", label: "Comfortable" },
      { value: "compact", label: "Compact" },
    ],
  },
  {
    name: "motion",
    legend: "Animation",
    options: [
      { value: "system", label: "Match my device" },
      { value: "reduce", label: "Reduce" },
      { value: "full", label: "Show" },
    ],
  },
];

const DATES: AnySetting[] = [
  {
    name: "dateLocale",
    legend: "Date style",
    options: [
      { value: "browser", label: "My browser’s language" },
      { value: "en-GB", label: "British (16 Nov 2026)" },
      { value: "en-US", label: "American (Nov 16, 2026)" },
    ],
  },
  {
    name: "hourCycle",
    legend: "Clock",
    options: [
      { value: "locale", label: "As the date style writes it" },
      { value: "h23", label: "24-hour" },
      { value: "h12", label: "12-hour" },
    ],
  },
];

const STARTING: AnySetting[] = [
  {
    name: "startupProject",
    legend: "When you open Data Director",
    options: [
      { value: "last", label: "Return to the project you used last" },
      { value: "none", label: "Start with no project chosen" },
    ],
  },
];

function Choice({
  setting,
  current,
}: {
  setting: AnySetting;
  current: PreferenceValues;
}) {
  const group = `preference-${setting.name}`;
  return (
    <fieldset className="field preference">
      <legend>{setting.legend}</legend>
      {setting.options.map(({ value, label }) => (
        <div className="field-check" key={value}>
          <input
            type="radio"
            id={`${group}-${value}`}
            name={group}
            value={value}
            checked={current[setting.name] === value}
            onChange={() => setPreference(setting.name, value as never)}
          />
          <label htmlFor={`${group}-${value}`}>{label}</label>
        </div>
      ))}
    </fieldset>
  );
}

/** A fixed moment, so that the example shows the clock's afternoon hours. */
const EXAMPLE = new Date(2026, 10, 16, 14, 5);

/** The preference sections, one tab each on the Settings page. */
export type PreferenceSection = "appearance" | "dates" | "starting";

export const PREFERENCE_SECTIONS: { id: PreferenceSection; title: string }[] = [
  { id: "appearance", title: "Appearance" },
  { id: "dates", title: "Dates and times" },
  { id: "starting", title: "Starting up" },
];

export function Preferences({ section }: { section: PreferenceSection }) {
  const current = usePreferences();
  const title = PREFERENCE_SECTIONS.find(({ id }) => id === section)?.title;
  const settings = { appearance: APPEARANCE, dates: DATES, starting: STARTING }[
    section
  ];
  return (
    <section
      className="preferences"
      aria-labelledby={`preferences-${section}-heading`}
    >
      <h2 id={`preferences-${section}-heading`}>{title}</h2>
      <p>
        These apply straight away and are kept in this browser only, so another
        browser or device starts with the defaults.
      </p>
      {settings.map((setting) => (
        <Choice key={setting.name} setting={setting} current={current} />
      ))}
      {section === "dates" && (
        <p className="hint">
          For example:{" "}
          <time dateTime={EXAMPLE.toISOString()}>
            {formatDateTime(EXAMPLE, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </time>
        </p>
      )}
    </section>
  );
}
