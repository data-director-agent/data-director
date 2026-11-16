# Interface languages

## Intent and scope

Data Director is for a research community that works in many languages (P12), and its interface
should not exclude someone because it speaks only English (C6). This spec says how the text the
app's interface writes itself is offered in more than one language: the browser shell
(`app/web`) and the two libraries it draws with, `@data-director/agent-view` (`sdk/browser`) and
`@data-director/inventory` (`inventory/browser`). British English is the first language, Spanish
the second (#931).

It answers the Blueprint's open question on language
([§13.2](../blueprint/13-open-questions.md#132-roadmap-for-future-iterations)) for the interface
only. It does not cover:

- what agents write: replies, payloads, drafted documents and their metadata, or the language a
  researcher converses in. Those cross the contract, the agents and the deposit package, and are
  decided separately: TODO(#935);
- the workbench, the admin view and the documentation site, which are for engineers and operators
  and stay in English.

The work that brings the shell to this spec is tracked under #920.

## Invariants

1. **The shell's text comes from a catalogue.** Every string the shell or its libraries write for
   a person to read, including accessible names, descriptions and placeholders, is a message in a
   catalogue, keyed by a stable identifier and never by its English text. The `en-GB` catalogue is
   the source; every other catalogue translates it. Most strings are still written inline: #922
   to #926 move them, and the lint rule in #927 will enforce this.
2. **Codes are never translated.** Outcome statuses, reason codes, grounding modes, derivations,
   problem types, agent identifiers and class names stay as they are, in the interface, in URLs
   and in anything sent to the server. What the shell shows for a code is a catalogue message
   keyed by that code, so a new code without a label is a missing message, which the catalogue
   check (#927) finds.
3. **A missing message falls back to British English.** Languages are named by BCP 47 tags.
   When the active language has no message for a key, the `en-GB` message is shown, never the
   key and never a blank.
4. **The person's choice of language stays in their browser.** The active language is the one
   the person chose in this browser; if they chose none, the first of the browser's preferred
   languages that the deployment offers; otherwise the deployment's default. The choice is kept
   in the browser, as the colour scheme is, and the server stores nothing about it, which keeps
   the profile page's promise that nothing more is kept ([The app](app.md#invariants),
   invariant 20). The chooser comes with #928.
5. **A deployment offers only reviewed languages.** A language is offered once a person has
   approved every message in its catalogue. Which languages a deployment offers, and its default,
   are settings of the app's deployment configuration, not of the institutional profile, which
   governs runs ([Policy and identity](policy-and-identity.md)).
6. **No translation is unreviewed.** A language model may draft a translation for a translator
   to correct (#930), but a draft never reaches a catalogue until a person approves it (#929).
   Nothing is translated by a model while the app runs.
7. **Text the shell did not write is shown as written.** Agent replies, payload values, the text
   of an agent's card, registry records and a server problem's `detail` are shown as they arrive,
   never translated by the shell, and marked with their language where it is known, so that
   assistive technology reads them in the right language (WCAG 2.2 success criterion 3.1.2,
   Language of Parts). For a problem from the server, the shell shows its own message, keyed by
   the problem's type, and the server's `detail` as given beside it. Today it shows the server's
   text alone; #923 to #926 change that.
8. **The page states its language and direction.** The document's `lang` and `dir` follow the
   active language. Styles use logical properties (`inline-start`, not `left`), so that a
   right-to-left language needs no layout of its own.
9. **Formatting belongs to the locale.** Dates, times, numbers, sizes, lists and relative times
   are formatted with `Intl`, and plurals and variable parts with ICU MessageFormat, never by
   joining strings.
10. **The libraries take the host's locale.** `agent-view` and the inventory browser format with
    the locale the host app gives them, and each ships its own catalogues; a host that gives no
    locale gets `en-GB`. A front end that uses them needs no translation of its own for what they
    draw.

## Boundaries and contracts

- Each package owns its catalogues, beside its code. The app owns the active locale and passes it
  to the libraries.
- The server's API does not change: it speaks codes and problem types, and its `title` and
  `detail` remain British English for the people who read logs and the API.
- The harness, the agents and the contract do not change. Nothing a person chooses about the
  interface reaches a run.
- Translations are made in Weblate, which opens pull requests against the catalogues. Those pull
  requests pass the same checks and review as any other change (#929).

## Rationale

- **ICU MessageFormat.** English has two plural forms; Polish has four and Arabic six. ICU
  MessageFormat expresses them, and selection by gender or kind, in one portable syntax that
  Weblate supports and that matches the `Intl` formatting React Aria already uses.
- **Keys are identifiers, not English text.** The British English wording is revised often, for
  plain language and accuracy. Keyed by identifiers, a revision marks the translations for review
  instead of orphaning them, and the same English words can carry two meanings.
- **The choice stays in the browser.** A language is a preference about this screen, like the
  colour scheme. Keeping it in the browser stores no new personal data
  ([Policy and identity](policy-and-identity.md)) and works before sign-in. The cost is that
  another device asks again, or follows its own browser's preference.
- **Reviewed catalogues, not translation at run time.** Text the shell writes explains what the
  harness checks and what it does not; a wrong translation would mislead in exactly the places
  that carry governance. A reviewed catalogue is consistent between screens, can be tested, and
  sends no interface text to a model provider.
- **FormatJS.** `react-intl` with `@formatjs/cli` is a maintained ICU implementation for React.
  It is a runtime dependency behind one module per package, with `intl-messageformat` alone, or
  lookups with `Intl.PluralRules`, as its fallback; it enters the register
  ([Dependencies](dependencies.md)) with #922 and #923.

## Rejected alternatives

- **English text as the key**, as gettext does. Every revision of the source wording would orphan
  its translations, and the shell's wording is revised often.
- **i18next.** It has its own plural and interpolation format, with ICU only by a plugin, and
  Weblate and React Aria both work in ICU.
- **A language preference stored on the server.** It would follow a person between devices, but
  it is personal data the app does not otherwise keep, and the profile page promises it keeps
  none.
- **Translating agent replies and drafted documents in the shell.** What an agent writes is
  evidence of what it did, cited and checked as written. Its language belongs to the conversation
  and the contract (TODO(#935)), not to the interface.
- **Machine translation while the app runs.** It is unreviewed, varies between screens and visits,
  sends interface text to a model provider, and cannot run in offline tests.
- **Crowdin.** It works as well, but it is proprietary; Weblate is open source and hosts open
  projects without charge.
- **Translating the workbench and the admin view.** Their readers are engineers and operators,
  who work with the code, the specs and the logs in English.

## Non-functional requirements

- **Accessibility (C6).** Every offered language meets the app's WCAG 2.2 AA target
  ([The app](app.md#non-functional-requirements)). Translations can be a third longer than
  English; reflow at 320 CSS pixels must still hold, which a pseudo-locale of lengthened text
  checks in CI (#927).
- **Performance.** The shell loads only the active language's catalogue.
- **Tests.** Tests stay offline and assert on structure, not wording, so they pass in any
  language.

## Open questions

- TODO(#935): the conversation language and multilingual metadata.
- TODO(#927): the lint rule, the catalogue check and the pseudo-locale.
- TODO(#928): the language chooser and the deployment's offered languages.
- TODO(#929): connecting the catalogues to Weblate.
- No right-to-left language is planned; invariant 8 keeps the way open for one.
