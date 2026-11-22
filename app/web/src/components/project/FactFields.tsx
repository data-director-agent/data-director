/**
 * The values of one project fact, as a person sets them: whether a file goes in, whether a
 * sensitive field or file may be published and how precisely, a funder, a required repository,
 * the licence, what the plan commits to share, or a standard, vocabulary or format chosen
 * (docs/specs/projects.md, invariant 28).
 *
 * When a person changes a proposal, its kind and subject stay as proposed, since a decision is on
 * that fact; when they state a fact of their own, they choose the kind, and the subject is taken
 * from the value that names it (the file's path, the funder's name and so on).
 */

import { useId } from "react";

import {
  FACT_KINDS,
  FILE_DECISIONS,
  type FactKind,
  PRECISIONS,
  type ProjectFact,
  SENSITIVITY_DECISIONS,
  STANDARD_KINDS,
  SUBJECT_OF,
} from "../../project/facts";
import {
  FILE_DECISION_LABELS,
  KIND_LABELS,
  PRECISION_LABELS,
  SENSITIVITY_LABELS,
  STANDARD_KIND_LABELS,
} from "./factWording";

type Setter = (slot: keyof ProjectFact, value: string | string[] | undefined) => void;

function TextValue({
  label,
  hint,
  slot,
  fact,
  set,
  required = false,
}: {
  label: string;
  hint?: string;
  slot: keyof ProjectFact;
  fact: ProjectFact;
  set: Setter;
  required?: boolean;
}) {
  const id = useId();
  const value = fact[slot];
  return (
    <div className="field">
      <label htmlFor={id}>
        {label} {required ? "(required)" : "(optional)"}
      </label>
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      <input
        id={id}
        type="text"
        required={required}
        aria-describedby={hint ? `${id}-hint` : undefined}
        value={Array.isArray(value) ? value.join(", ") : (value ?? "")}
        onChange={(event) => set(slot, event.target.value)}
      />
    </div>
  );
}

function Choice<T extends string>({
  label,
  slot,
  options,
  labels,
  fact,
  set,
  optional = false,
}: {
  label: string;
  slot: keyof ProjectFact;
  options: readonly T[];
  labels: Record<T, string>;
  fact: ProjectFact;
  set: Setter;
  optional?: boolean;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={(fact[slot] as string | undefined) ?? ""}
        onChange={(event) => set(slot, event.target.value || undefined)}
      >
        {optional && <option value="">Not said</option>}
        {options.map((option) => (
          <option key={option} value={option}>
            {labels[option]}
          </option>
        ))}
      </select>
    </div>
  );
}

function KindValues({ fact, set, isNew }: { fact: ProjectFact; set: Setter; isNew: boolean }) {
  switch (fact.fact_kind) {
    case "file_inclusion":
      return (
        <>
          {isNew && (
            <TextValue
              label="The file's path"
              hint="As the inventory gives it, such as data/readings.csv."
              slot="fact_file_path"
              fact={fact}
              set={set}
              required
            />
          )}
          <Choice
            label="Whether it is deposited"
            slot="file_decision"
            options={FILE_DECISIONS}
            labels={FILE_DECISION_LABELS}
            fact={fact}
            set={set}
          />
        </>
      );
    case "sensitivity":
      return (
        <>
          {isNew && (
            <TextValue
              label="The sensitive field or file"
              hint="A field name, such as lat, or a file's path."
              slot="sensitive_subject"
              fact={fact}
              set={set}
              required
            />
          )}
          <Choice
            label="Whether it may be published"
            slot="sensitivity_decision"
            options={SENSITIVITY_DECISIONS}
            labels={SENSITIVITY_LABELS}
            fact={fact}
            set={set}
          />
          <Choice
            label="At what precision"
            slot="location_precision"
            options={PRECISIONS}
            labels={PRECISION_LABELS}
            fact={fact}
            set={set}
            optional
          />
        </>
      );
    case "funder":
      return (
        <>
          <TextValue
            label="The funder's name"
            slot="fact_funder_name"
            fact={fact}
            set={set}
            required
          />
          <TextValue
            label="Its ROR identifier"
            hint="Such as https://ror.org/02b5d8509."
            slot="fact_funder_ror"
            fact={fact}
            set={set}
          />
          <TextValue
            label="Its Crossref Funder ID"
            hint="As a DOI link."
            slot="fact_crossref_funder_id"
            fact={fact}
            set={set}
          />
        </>
      );
    case "required_repository":
      return (
        <>
          <TextValue
            label="The repository's name"
            slot="fact_repository_name"
            fact={fact}
            set={set}
            required
          />
          <TextValue
            label="Its re3data identifier"
            hint="Such as r3d100010199."
            slot="fact_re3data_id"
            fact={fact}
            set={set}
          />
          <TextValue
            label="Who requires it"
            hint="Funders, journals or institutions, separated by commas."
            slot="fact_required_by"
            fact={fact}
            set={set}
          />
        </>
      );
    case "licence":
      return (
        <TextValue
          label="The licence"
          hint="An SPDX identifier, such as CC-BY-4.0, or a link to the licence."
          slot="licence_id"
          fact={fact}
          set={set}
          required
        />
      );
    case "sharing_commitment":
      // The quote and the document stay as read: a person corrects what the plan was read to say.
      return (
        <>
          <TextValue label="Where it is shared" slot="commitment_repository" fact={fact} set={set} />
          <TextValue
            label="How openly"
            hint="Such as open, safeguarded or controlled."
            slot="commitment_access"
            fact={fact}
            set={set}
          />
          <TextValue label="Under what licence" slot="commitment_licence" fact={fact} set={set} />
        </>
      );
    case "data_management_plan":
      // Which document is the plan is chosen on the Documents page, not typed here.
      return null;
    case "standard":
      // What it is chosen for stays as proposed; a standard a person states is for the dataset.
      return (
        <>
          <TextValue label="The standard's name" slot="standard_name" fact={fact} set={set} required />
          <TextValue
            label="Its identifier"
            hint="A link, such as its FAIRsharing DOI."
            slot="standard_id"
            fact={fact}
            set={set}
          />
          <Choice
            label="What kind of standard it is"
            slot="standard_kind"
            options={STANDARD_KINDS}
            labels={STANDARD_KIND_LABELS}
            fact={fact}
            set={set}
            optional
          />
        </>
      );
  }
}

export function FactFields({
  fact,
  isNew,
  onChange,
}: {
  fact: ProjectFact;
  isNew: boolean;
  onChange: (fact: ProjectFact) => void;
}) {
  const kindId = useId();
  const set: Setter = (slot, raw) => {
    const value =
      slot === "fact_required_by" && typeof raw === "string"
        ? raw.split(",").map((part) => part.trim()).filter(Boolean)
        : raw;
    const next = { ...fact, [slot]: value } as ProjectFact;
    // A fact a person states is named by the value that names it; a proposal keeps its subject.
    if (isNew && SUBJECT_OF[next.fact_kind] === slot && typeof value === "string") {
      next.fact_subject = value.trim();
    }
    onChange(next);
  };
  const chooseKind = (kind: FactKind) => onChange(blankFact(kind));

  return (
    <div className="fact-fields">
      {isNew && (
        <div className="field">
          <label htmlFor={kindId}>What the fact is about</label>
          <select id={kindId} value={fact.fact_kind} onChange={(event) => chooseKind(event.target.value as FactKind)}>
            {FACT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </select>
        </div>
      )}
      <KindValues fact={fact} set={set} isNew={isNew} />
    </div>
  );
}

/** A fact of `kind` with nothing set but what a decision on it must say. */
export function blankFact(kind: FactKind): ProjectFact {
  switch (kind) {
    case "file_inclusion":
      return { fact_kind: kind, fact_subject: "", file_decision: "exclude" };
    case "sensitivity":
      return { fact_kind: kind, fact_subject: "", sensitivity_decision: "undecided" };
    case "licence":
      return { fact_kind: kind, fact_subject: "licence" };
    default:
      return { fact_kind: kind, fact_subject: "" };
  }
}
