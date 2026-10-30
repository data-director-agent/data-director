# advisor.documentation

**Mock, alpha** (`0.1.0a1`): a placeholder for a persona of the agent roster (ADR-0033). It gives
no real advice and is likely to change shape.

The Documentation Editor drafts a README and a data dictionary for a dataset (Blueprint R5). It
serves two steps of the process flow:

| Step | What the mock does |
|---|---|
| `setup.documentation` | Drafts a README outline and a data dictionary from what the researcher has said. |
| `preparation.documentation` | The same, for documentation drafted or reviewed while preparing the deposit. |

## What it does

`DocumentationRequest` gives the dataset's title and, optionally, its description, creators, file
names and field names. The mock abstains with `insufficient_input` when there are neither file
names nor field names.

`DocumentationDraft` holds:

- `readme_sections`: the README's sections in the order of `readme.yaml` (Title, Description,
  Creators, Files, Methods, Variables, Licence, How to cite). A section drafted from the input
  copies it, a list as one line per item, and is `drafted`. A section with no input behind it is
  `needs_researcher` and has no text.
- `dictionary`: one entry per field name. Only the name is filled in; the definition, unit and
  missing value codes are empty, and every entry is `needs_researcher`.
- `limitations`: what the mock does not do.

Its grounding mode is `none`: it cites only its input.

## What it does not do

- It writes no prose of its own and invents nothing. Methods, study design, licence and citation
  are left to the researcher.
- It does not open the files, so it says nothing about their contents, formats or sizes.
- It infers no variable definitions, units or missing value codes.
- It follows no community README template or data dictionary standard, such as CDIF's variable
  descriptions.

The real editor, drafting with a model from the files and the project record (#200, #220), is
TODO(#358).
