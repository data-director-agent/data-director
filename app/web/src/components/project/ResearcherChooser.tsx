/** The form in which a researcher ticks what to keep from their ORCID record. */

import { type FormEvent, useState } from "react";

import {
  type KeepChoice,
  RECORD_ITEMS,
  RECORD_SECTIONS,
  type RecordItems,
  type RecordSection,
  type ResearcherRecord,
} from "../../project/api";
import { Button } from "../ui/Button";
import { ITEM_LABELS, SECTION_LABELS, itemsOf, sectionText } from "./researcherFacts";

export function ResearcherChooser({
  offered,
  initial,
  busy,
  onKeep,
  onCancel,
}: {
  offered: ResearcherRecord;
  initial: KeepChoice;
  busy: boolean;
  onKeep: (choice: KeepChoice) => void;
  onCancel: () => void;
}) {
  const [choice, setChoice] = useState<KeepChoice>(initial);
  const sections = RECORD_SECTIONS.filter((s) => sectionText(offered, s) !== "");

  const toggleSection = (section: RecordSection, on: boolean) =>
    setChoice((c) => ({
      ...c,
      sections: on ? [...c.sections, section] : c.sections.filter((s) => s !== section),
    }));
  const toggleItem = (section: RecordItems, code: string, on: boolean) =>
    setChoice((c) => ({
      ...c,
      [section]: on ? [...c[section], code] : c[section].filter((k) => k !== code),
    }));
  const setAll = (section: RecordItems, on: boolean) =>
    setChoice((c) => ({ ...c, [section]: on ? itemsOf(offered, section).map(([k]) => k) : [] }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onKeep(choice);
  };

  return (
    <form className="researcher-chooser" onSubmit={submit} aria-label="Choose what to keep">
      <p className="hint">
        Nothing is ticked until you tick it. Only what you tick is kept in this project and given
        to its agents.
      </p>
      {sections.length > 0 && (
        <fieldset className="field">
          <legend>About you</legend>
          {sections.map((section) => (
            <div className="field-check" key={section}>
              <input
                type="checkbox"
                id={`keep-${section}`}
                checked={choice.sections.includes(section)}
                onChange={(event) => toggleSection(section, event.target.checked)}
              />
              <label htmlFor={`keep-${section}`}>
                {`${SECTION_LABELS[section]}: ${sectionText(offered, section)}`}
              </label>
            </div>
          ))}
        </fieldset>
      )}
      {RECORD_ITEMS.map((section) => {
        const items = itemsOf(offered, section);
        if (items.length === 0) return null;
        const all = items.every(([code]) => choice[section].includes(code));
        return (
          <fieldset className="field" key={section}>
            <legend>{ITEM_LABELS[section]}</legend>
            <p>
              <Button variant="quiet" size="small" onPress={() => setAll(section, !all)}>
                {all ? "Untick all" : "Tick all"}
                <span className="visually-hidden"> {ITEM_LABELS[section].toLowerCase()}</span>
              </Button>
            </p>
            {items.map(([code, text]) => (
              <div className="field-check" key={code}>
                <input
                  type="checkbox"
                  id={`keep-${section}-${code}`}
                  checked={choice[section].includes(code)}
                  onChange={(event) => toggleItem(section, code, event.target.checked)}
                />
                <label htmlFor={`keep-${section}-${code}`}>{text}</label>
              </div>
            ))}
            {section === "works" && offered.works_omitted ? (
              <p className="hint">
                Your {offered.works_omitted} older works are not offered, to keep what agents are
                given short.
              </p>
            ) : null}
          </fieldset>
        );
      })}
      <p className="document-actions">
        <Button type="submit" variant="primary" isPending={busy}>
          Keep the ticked facts
        </Button>{" "}
        <Button variant="quiet" isDisabled={busy} onPress={onCancel}>
          Cancel
        </Button>
      </p>
    </form>
  );
}
