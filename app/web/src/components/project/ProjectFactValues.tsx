/**
 * The values of a fact that describes the project before its data are collected, decided at
 * "Describe your project": what it is for, its field of study, when it runs, and each kind of data
 * it will produce (docs/specs/projects.md, invariant 28).
 */

import type { ProjectFact } from "../../project/facts";
import { type Setter, TextValue } from "./FactInputs";

export function ProjectFactValues({
  fact,
  set,
  isNew,
}: {
  fact: ProjectFact;
  set: Setter;
  isNew: boolean;
}) {
  switch (fact.fact_kind) {
    case "project_summary":
      return (
        <TextValue
          label="What the project is for"
          hint="Its aims and the questions it asks, in a few sentences."
          slot="summary_text"
          fact={fact}
          set={set}
          required
          multiline
        />
      );
    case "field_of_study":
      return (
        <TextValue
          label="The field of study"
          slot="field_name"
          fact={fact}
          set={set}
          required
        />
      );
    case "project_period":
      return (
        <>
          <TextValue
            label="When it starts"
            hint="A year, a month or a day, such as 2027, 2027-03 or 2027-03-01."
            slot="period_start"
            fact={fact}
            set={set}
            required
          />
          <TextValue
            label="When it ends"
            hint="As for the start."
            slot="period_end"
            fact={fact}
            set={set}
          />
        </>
      );
    case "planned_data":
      return (
        <>
          {isNew && (
            <TextValue
              label="A short name for the data"
              hint="Such as interview recordings or soil samples."
              slot="fact_subject"
              fact={fact}
              set={set}
              required
            />
          )}
          <TextValue
            label="What the data will hold"
            slot="planned_description"
            fact={fact}
            set={set}
            required
            multiline
          />
          <TextValue
            label="How they will be collected"
            slot="planned_collection_method"
            fact={fact}
            set={set}
          />
          <TextValue
            label="Their formats"
            slot="planned_format"
            fact={fact}
            set={set}
          />
          <TextValue
            label="How much is expected"
            slot="planned_volume"
            fact={fact}
            set={set}
          />
        </>
      );
    default:
      return null;
  }
}
