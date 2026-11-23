/**
 * The values of a fact that describes the project before its data are collected, decided at
 * "Describe your project": what it is for, its field of study and when it runs (docs/specs/projects.md,
 * invariant 28). What data it produces is a `data_description`, set in `FactFields`.
 */

import type { ProjectFact } from "../../project/facts";
import { type Setter, TextValue } from "./FactInputs";

export function ProjectFactValues({
  fact,
  set,
}: {
  fact: ProjectFact;
  set: Setter;
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
          long
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
    default:
      return null;
  }
}
