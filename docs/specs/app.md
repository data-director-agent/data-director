# The app

## Intent and scope

The app (`app/`) is the Data Director that people use. The Blueprint's presentation layer is a
"web app providing a chat interface and feedback mechanism" over an application layer that
orchestrates requests and coordinates the agents
([§9.2, §9.3](../blueprint/09-reference-architecture.md#92-presentation-layer)). A person talks to
one Data Director; the specialist agents support it. So the app opens on a conversation with the
orchestrator, and every agent's own pages (what it does, a form to run it, its stored runs) sit
one step away.

The app is three things:

- a **browser shell** (`app/web`, React and TypeScript) that draws every agent from the manifest
  the harness holds, and later from a generic stream of AG-UI events, and names no agent;
- a **server** (`dd_app`, Starlette) that serves the built shell, runs every request through the
  harness's conductor under the app's own configuration (`app/config/`), and is the conductor's
  callback for an orchestrator's delegations;
- a **problem-report channel** that files what a person reports as a GitHub issue.

It is not the workbench, which is a test bed for engineers who write agents, and it must not
depend on it ([System and boundaries](system.md)). It does not decide policy, route messages,
or run agents. `app/README.md` describes what is built; `docs/ui/best-practices.md` is the design
input, whose evidence is weak, so its items are hypotheses to test, not findings.

## Invariants

1. **The shell names no agent.** No agent identifier, the orchestrator's included, appears in
   `app/web/src`. Adding an agent needs its package, an entry in `app/config/agents.yaml` and a
   profile entry, and no change to the shell. Enforced by review; the shell's tests run against
   `agents-several.json`, five agents of different grounding modes and payload shapes, so a
   shell that assumed one agent fails them.
2. **The shell holds no policy.** Whether an agent may run, which agent is the orchestrator, and
   (once built) whether an action needs review are decided by the harness and sent to the shell,
   which renders them. The server's `GET /api/agents` gives each manifest beside what the
   profile assigns it. A project's documents page (`/projects/{id}`) draws each version's state
   as the project log records it, and takes whether a decision needs a reason from the
   harness's rule in `GET /api/projects/{id}/documents`; the harness alone records a decision,
   and the server gives it the decider from the authenticator, never from the request
   ([Projects](projects.md), `app/tests/test_document_decisions.py`).
3. **The shell does not route.** It never classifies a message or sends it to a sub-agent.
   Each turn is one invocation of the orchestrator through the conductor, and each hand-off a
   child invocation under the conductor's grant
   ([Orchestration](orchestration.md)). A turn to any agent but the one the profile names as
   orchestrator is refused (`app/tests/test_app.py`,
   `test_a_turn_goes_only_to_the_orchestrator_the_profile_names`).
4. **The server builds a turn's history from the stored turns.** A request that supplies a
   history is refused, so the input hash covers what the agent was shown and a browser cannot put
   words in an earlier turn (`app/tests/test_app.py`).
5. **No fallback orchestrator.** When the profile names none, the named agent is unavailable, or
   its card does not declare `delegation` grounding, the home page says which and links to the
   agent directory. Neither the shell nor the server chooses another agent. The reference
   profile, not code, names the default (`app/web/src/components/conversation/ConversationHome.test.tsx`).
6. **Every delegated child is labelled `agent_id@agent_version`** and opens its run inside its
   own card in the conversation, at every width, drawn by the run view's components.
7. **What is undeclared is shown as undeclared.** A limit, reliability or data-handling
   statement an agent has not declared is shown as "Not declared"; a reliability nobody has
   evaluated is shown as unsubstantiated. The shell never fills one with a default.
8. **What is not built is drawn as not built.** A zone with no source yet says "Not built yet"
   and links to the issue that builds it, rather than showing invented data.
9. **The manifest carries no presentation.** It says what an agent does, never how to draw it;
   the shell works out presentation and keeps ownership of grounding, derivation badges and
   evidence links ([Agents](agents.md)). A later per-class renderer may lay out a payload but
   adds nothing to the manifest.
10. **Presentation comes from tokens.** Every colour, size and typeface is a custom property in
    `app/web/src/tokens/neutral.css`; no organisation's branding is built in, so a theme is a new
    token file. Stylelint rejects a literal colour outside the token file (`npm run lint`).
11. **The app runs no agent in its own process.** It reaches every agent over A2A through the
    conductor and imports no agent package and not the workbench
    (`app/tests/test_app_boundary.py`). Its agent list names every in-tree agent; one that is not
    running is shown as unavailable, never replaced by a local copy. Its tests serve agents in
    memory over A2A (`dd_harness.testing`), so they exercise the same wire.
12. **The app's A2A endpoint is no general way in.** It accepts only a delegation agent's
    callback under a live grant and refuses every other request
    (`test_the_app_takes_no_a2a_call_but_a_delegation_callback`).
13. **The shell's fixtures are what the server says.** The shell's tests draw from
    `app/web/fixtures/`, which `app/tests/test_app.py` regenerates from the real server and fails
    on drift.
14. **The app stops at start-up, with one line,** when a setting, a file or the built shell is
    missing or wrong. A stopped agent, the orchestrator included, does not stop it.
15. **A problem report never carries a person's work.** It holds what the person typed, the
    build, and the page's path. The run and conversation they came from are attached only if they
    tick a box, and then only as identifiers, agents, versions and outcomes read from the run
    store: never an input, a payload or evidence (`app/tests/test_feedback.py`).
16. **The server names the build in a report.** It adds the app version, harness version and
    commit to the issue itself; the page shows them but is not trusted for them.
17. **Problem reports are bounded.** Lengths are capped, unknown fields refused, and the number
    filed in a window limited (`app/src/dd_app/feedback.py`, `app/tests/test_feedback.py`).
    Without a credential for GitHub the feature is off, the page says so and links to GitHub, and
    the app still starts.
18. **Each conversation is started in a project.** Where the app keeps projects,
    `POST /api/conversations` starts the conversation in the project its body names
    (`{"project_id": …}`), or in a new project when it names none, acting for the person signed
    in. A project that does not exist, or that the person may not read, is refused with a 404 and
    nothing is started; a body with any other field is refused with a 400. A conversation names
    its `project_id` and the inventory its project holds. The shell names the open conversation
    in the address (`?conversation=`), so a reload or a link reopens it in its own project and a
    message sent afterwards continues it. The app gives the conductor the same project store, so a turn's runs belong to the
    project and a drafter's documents are kept in it ([Projects](projects.md),
    `app/tests/test_app.py`).
19. **An inventory is attached, never pasted into the message.** A turn may carry an `inventory`,
    the file `dd-inventory` writes, which the server adds to the conversation's project before the
    turn runs; with one, the message may be blank and the server supplies a sentence saying an
    inventory was attached. An inventory the project refuses, or one sent to a conversation in no
    project, refuses the turn and nothing runs or is recorded. The shell reads one from a file
    chosen with a button, dropped on the message form, or pasted whole into the message box, and
    first opens it to be checked: a dialog says that this is everything that will be stored and
    sent to agents, that file and folder names and column headings are included and may
    themselves be sensitive, and that agents may show it to a hosted model
    ([Projects](projects.md), rule 8), then lays the inventory out as **View inventory** does
    (below) in the inventory editor: an Include checkbox on every file, folder and column, and,
    behind a **Describe** disclosure on each file, what the researcher may state beside the facts
    the command found (a description, the part the file plays, and a format where the command
    matched several, guessed from the name or matched none), one choice of part for every file
    of a folder, a description for each column, Undo and Redo, a status line counting what
    changed, and a choice to show only the files worth a look ([Projects](projects.md)). The
    editing is `@data-director/inventory`'s `edit` and `applyEdits`; the editor lays it out.
    Nothing is attached until
    the researcher presses **Attach this inventory**; closing the dialog any other way discards
    it. What they untick is removed from the document before it is attached, and so is never
    sent or stored: a folder takes every file beneath it, a limitation that names a file left
    out goes with it, and one limitation is added to `inventory_limitations` that counts the
    files and columns left out without naming them, so that an agent does not take the omission
    for an absence. Removing them is `@data-director/inventory`'s `omit`; the dialog only
    records the choice (`inventory/browser/tests/omit.test.ts`,
    `app/web/src/components/conversation/ConversationHome.test.tsx` and, with the same
    `app/web/fixtures/inventory-left-out.json`, `app/tests/test_app.py`). The checked inventory
    shows as a chip, never as its text. Beside the attach button, **Make an inventory** opens a
    dialog for a researcher who has none: one sentence on what an inventory is and that the data
    stay on their computer, a tab per operating system (the browser's own selected) with the
    commands that install uv and run `dd-inventory`, each with a copy button, and at the end the
    file picker, whose file is attached as if chosen with the button. Its text is
    `@data-director/inventory`'s `making.json`, which the user guide's *Making an inventory* page
    renders too (`docs/hooks_inventory.py`), so the two cannot drift; the dialog names no agent and
    holds no policy. A browser scanner will be its first choice (TODO(#367))
    (`app/web/src/components/inventory/MakeInventoryDialog.test.tsx`). The
    transcript shows the chip on the turn where the project's inventory changed, read from the
    `project_inventory` the conductor gave that turn (`app/tests/test_app.py`,
    `app/web/src/components/conversation/ConversationHome.test.tsx`).
    A chip whose whole inventory the page can read, the one attached and the one the project holds
    now (`GET /api/projects/{id}/inventory`), has a **View inventory** button. It opens a dialog
    that says this is everything Data Director keeps and agents are shown, then what the inventory
    amounts to and leaves out, its formats, its files as folders with a search, and the columns of
    its tables. A chip for an inventory the project has since replaced has no button, because
    only the latest is served. The facts come from `@data-director/inventory`
    ([System and boundaries](system.md)); the dialog only lays them out. Folders are drawn only
    while open and a search draws at most 200 matches, so an inventory of thousands of files
    stays usable; checkboxes and folders work by keyboard and are named for screen readers
    (`app/web/src/components/inventory/InventoryView.test.tsx`, `app/web/e2e/shell.spec.ts`).
    Beside the project's chip, **Edit inventory** opens the same editor on the inventory the
    project holds, and may read a new scan of the same dataset instead, onto which what the
    researcher stated is carried by path, with what the scan added, changed and removed, and the
    files they had described that it no longer lists. **Save as the project's inventory** sends
    the result to `POST /api/projects/{id}/inventory`, which adds it as the project's latest; the
    store records which inventory it revises ([Projects](projects.md))
    (`app/web/src/components/inventory/InventoryEditor.test.tsx`, `app/tests/test_app.py`).
    A supporting document is attached in the same way: a turn may carry `documentation`, an
    object giving its `name`, `media_type` and `text`, which the server adds to the
    conversation's project before the turn runs ([Projects](projects.md)). With one, the message
    may be blank and the server supplies a sentence saying a document was attached; a turn may
    carry an inventory and a document together, and if the project refuses either, the turn is
    refused, nothing runs and neither is kept. The shell's one **Attach a file** button, and a
    drop on the message form, take a `.json` file as an inventory and a `.txt` or `.md` file as a
    document. A document is read in the browser, refused there if it is empty or over 256 KB,
    and first opened to be checked: a dialog shows its name, size and text, says that it will be
    stored in the project, that agents are told its name, type and size but not its text, and
    that it must be about the data, never the data themselves nor anything that identifies a
    person. Nothing is attached until the researcher presses **Attach this document**; closing
    the dialog any other way discards it. The checked document shows as a chip with its name and
    size and a button to remove it, never as its text, and so does each document a turn's
    `project_documentation` gained on the transcript. `GET /api/projects/{id}/documentation`
    lists a project's documents and `GET /api/projects/{id}/documentation/{digest}` serves one's
    text (`app/tests/test_app.py`,
    `app/web/src/components/conversation/ConversationHome.test.tsx`,
    `app/web/src/components/conversation/Transcript.test.tsx`, `app/web/e2e/shell.spec.ts`).
20. **The profile page shows only what the session holds.** `/profile`, reached from the name in
    the banner, shows the name and iD the identity provider gave at sign-in, how the person is
    known and when the session ends, and says that nothing more is kept. It makes no request to
    the provider and the app asks for no wider scope (`app/web/src/components/profile/ProfilePage.test.tsx`).
21. **A reply's questions are answered one at a time in a form, and may be ignored.** A reply's
    `reply_questions` are drawn beneath the reply. On the latest turn each question is a fieldset
    whose legend is the question and whose description is its help: a choice question as radio
    buttons, or checkboxes where several may be chosen, each option a card the whole of which can
    be clicked (the control stays visible and ticked beside an accent bar), with "Something else"
    and a text box where the question allows an answer in words; a short text question as a
    one-line text box; a long text question as a text area that counts the characters left. A lone
    question is answered and sent in place. A series shows one question at a time, saying in
    words which of how many it is beside a progress bar, with Back, Skip and Next; Next with
    nothing entered says to answer or skip. After the last question it lists the answers to check,
    each with a button to change it, and Send answers, which needs at least one answer. Moving to
    another question moves the focus to its legend, and to the list's heading at the end. On
    earlier turns the questions are read-only, each answer marked with an icon and words, never by
    colour alone, and a skipped question says so. A new reply that asks is announced in the polite
    live region. Sending sends the answers in words as `message_text` beside `reply_answers`; the
    server refuses answers the harness's `answer_problem` rejects, and nothing runs. The message
    box stays usable, so the researcher may type instead (`app/tests/test_app.py`,
    `app/web/src/components/conversation/QuestionSeries.test.tsx`, `e2e/shell.spec.ts`).
22. **The policy page shows the profile the gate holds runs to.** `/policy`, in the main navigation
    and linked from each place that names the policy, is drawn from `GET /api/policy`: the
    profile's reference, description, digest and orchestrator, each agent it enables with the
    action class it assigns, and the action classes that need approval. What happens to each
    agent's runs here is read from `GET /api/agents`, never worked out in the shell, and an agent
    the profile enables that the deployment does not reach is named by its identifier
    (`app/tests/test_app.py`, `app/web/src/components/policy/PolicyPage.test.tsx`).

23. **A draft's questions are answered on its card, in the researcher's own words.** While a
    drafted version is its document's latest, its card in the conversation puts the questions no
    recorded answer has answered, three at a time, in a fieldset whose legend says how many
    remain; each is a text box labelled by the question and described by what it fills, and blank
    boxes are left as they are. A question's suggested answer is shown beside its box, says it came
    from a model, and describes the box; it never fills the box by itself, and a "Use suggestion"
    button copies it in for the researcher to keep or change before saving. Saving sends the answers to
    `POST /api/projects/{id}/documents/{document_id}/answers`, whose body never names who answered:
    the server records them for the person signed in, refuses a malformed body with nothing
    recorded, and answers `409` for a version no longer the latest or a question it does not ask.
    The card then draws the documents the server read back and says in a status how many answers
    were recorded. The project's documents page lists each version's questions with the answer
    recorded, or says in words that none is, with the suggestion while it is unanswered
    ([Drafting documents](drafting.md),
    `app/tests/test_document_answers.py`,
    `app/web/src/components/conversation/DocumentQuestions.test.tsx`, `e2e/shell.spec.ts`).
24. **Each person sees only their own runs and conversations.** A run or conversation in a project
    is readable by whoever may read the project ([Projects](projects.md), rule 17); one in no
    project by the principal it acted for, or for a conversation with no turn yet, the person who
    started it. A delegated child belongs where its parent does, since it acts for the same
    principal in the same project. `GET /api/runs` and `GET /api/conversations` list only those,
    newest first, a page at a time: `?limit=` (50 unless given, at most 200) and `?before=` the
    cursor of the page before, with the next page named by a `Link` header with `rel="next"`
    ([Storage](storage.md), "Listing"). The run store chooses what the person may read, so a page
    costs the same whatever the size of the store. A run or conversation the person may not read is answered `404` by
    `GET /api/runs/{id}`, `GET /api/conversations/{id}` and `POST /api/conversations/{id}/turns`,
    as one that does not exist, with nothing run. A problem report attaches only what the reporter
    may read. Ownership is read from the `acting_for` and `project_id` the run store records and
    from the project log, never from a second record. A deployment that turns sign-in on starts
    from an empty run store ([Policy and identity](policy-and-identity.md)), so no run is left
    without an owner (`app/tests/test_sign_in.py`, `app/tests/test_app.py`).
25. **A new project's conversation opens with the intake, and the researcher may always pass it
    by.** While a project's intake is pending ([Orchestration](orchestration.md), invariant 20),
    its conversation opens with Data Director's card before any turn. The card holds a greeting and
    the next question, drawn as in rule 21. It is announced in the polite live region and has a
    "Skip these questions" button.
    - `GET /api/projects/{id}/intake` reads the next question, or says the intake is complete or
      dismissed.
    - `POST /api/projects/{id}/intake/{question_id}` records an answer (`{"answer_values": […]}`).
      It answers with the next question, or, once the intake is complete, with the phase the
      project starts at and the suggested step, both from the project summary.
    - `POST /api/projects/{id}/intake/dismiss` records a dismissal.

    Neither body names who answered: the server records the answer for the person signed in. A
    malformed body is refused with a 400, and an answer the harness rejects with a 409; nothing is
    recorded in either case. The message box stays usable throughout. A turn sent while the
    intake is pending leaves it pending, and does not count as an answer. The intake is a card of
    the project, not a turn: no orchestrator runs for it, and the history holds none of it. Its
    answers reach the orchestrator through the project's entry point and step states. The phase
    tracker offers "Answer the setup questions again", which shows the card with the current
    answers chosen. Not built yet, TODO(#668).

## Boundaries and contracts

- **Depends on** the harness (`dd_harness`) and the SDK only. Workspace-level dependency rules
  are in [System and boundaries](system.md).
- **Web source layout and import rules.** In `app/web/src`, the domain folders (`run`,
  `manifest`, `conversation`, `flow`, `session`, `project`, `feedback`, `policy`) hold types and API
  clients, and reading an inventory is `@data-director/inventory`'s (`inventory/browser/`);
  `components/` holds the interface, one folder per feature, with the shared kit in
  `components/ui/`. Three rules are checked: no file depends on itself through other files
  (dependency-cruiser, `.dependency-cruiser.cjs`, in `npm run lint`); the kit imports no feature
  component; and a domain folder imports no component (eslint-plugin-boundaries, in
  `eslint.config.js`, with a test in `src/architecture.test.ts` that planted violations are
  reported, because the plugin does nothing without its TypeScript resolver). Rules between
  feature folders are not yet set, as several features import each other today;
  TODO(#497) decide them and add them to the dependency-cruiser config.
- **Conversations and delegation** are specified in [Orchestration](orchestration.md); the app
  supplies the conductor's callback and the conversation API over it. Which agent is the
  orchestrator is a profile key ([Policy and identity](policy-and-identity.md)). A person's
  conversations are listed beside the open one by the title the harness derives, with the date and
  turn count beside it, and the open one marked as current; the app writes no title, since it
  calls no model.
- **Signing in, whom a run acts for, and model credentials** are in
  [Policy and identity](policy-and-identity.md). The app never holds a model key: no agent runs in
  its process, so there is nothing in it to call a model.
- **Run events to the browser** are AG-UI ([Transport and tracing](transport.md)). The harness
  streams a run's stages, its checks' reports and cancelling; the app does not serve that stream
  yet. A run is one request that answers when it has ended, so stages are read back, not watched,
  and a run cannot be cancelled. TODO(#69).
- **Outcomes, evidence and the checks' reports** are rendered as the [Contract](contract.md) and
  [Evidence and grounding](grounding.md) define them. A drafted document in a run's result is
  shown as a document: rendered when its media type is `text/markdown`, tables included, and
  otherwise with its line breaks kept, with actions to copy the text and download it as a file.
  The project's documents page lists the documents beside a reader, those waiting for a decision
  first, with the one open named in the address (`?doc=`, and `&v=` for an earlier version). The
  reader previews a document by its media type (Markdown rendered, CSV as a table, JSON
  indented), and its Source tab shows the stored text exactly, since that is what a decision names
  by its digest and what the deposit package holds. Its Versions tab shows each version's
  decision and the lines it changed from the one before. While a person edits, the preview shows
  their version. The list ends with the repository chosen, the statement of how generative AI
  was used and the deposit package, and these are listed before any document is drafted. The
  repository entry (`GET /api/projects/{id}/repository`) shows the repository chosen last, the
  requirement sets by version, the warnings, and the documents and metadata they ask for, as
  the harness resolved them; with none chosen it says to choose one from a shortlist in the
  project's conversations. Whether a package meets them is the deposit check's to say. The
  deposit package entry checks the project against its chosen repository's
  requirements ([Deposit](deposit.md)) when the person asks, and lists what must be fixed and
  what is worth fixing, each in the harness's words. It offers to build the package only after
  a check the project passed, and then a link to download the zip by its digest. A decision made
  since the check withdraws that offer until the project is checked again. What a check or a
  build did is said once in a live region that is in the panel from the start; focus stays on
  the button pressed.
- **A project is named on its page.** The page's heading is the project's title, else its first
  conversation's, else when it was started. **Rename project** opens a dialog with the name to
  edit; saving sends it (`PUT /api/projects/{id}/title`), the server records it for the person
  signed in, and the page reads the name back. The dialog says when the name is one the Data
  Director suggested, and that a person's name is never replaced by the Data Director's
  ([Projects](projects.md), invariant 21).
- **A drafted document is shown on the turn that drafted it.** The workspace reads the project's
  documents (`GET /api/projects/{id}/documents`) when the conversation's project is known and
  again after each turn. A version whose `drafted_by.invocation_id` is the turn's invocation or
  one of its delegated children's is a card on that turn, after the reply and before the
  delegated runs. The card names the document, its version and the state the project log records
  (and says when a later version has replaced it). It has a preview, closed at first, drawn as a
  run's result is, and a link that opens the document on the documents page (`?doc={id}`). The
  new reply's announcement says what the turn drafted. The side bar lists every document of the
  project with its latest version's state and says how many await a decision. A decision is made
  only on the documents page.
- **A repository is chosen from the shortlist on the turn that made it.** A run whose payload is a
  `RepositoryOptions`, on the turn or among its delegated children, is a card on that turn listing
  each candidate by the re3data record it rests on: the `grounded_on` entry that is a re3data
  identifier, named by the evidence citing it from a pinned `re3data:export:YYYY-MM`. The shell
  recognises the class, not the agent. Choosing one sends only that identifier
  (`PUT /api/projects/{id}/repository`); the server records it for the person signed in, the
  harness reads the repository's name and declared standards from the pinned export, and the card
  shows what the choice resolved to: the requirement sets used, the documents and metadata a
  deposit needs, and each warning of what is not checked ([Deposit](deposit.md)). The side bar
  names the repository chosen last, with its warnings; choosing another from a shortlist changes
  it, as a new choice, and the last one counts. An identifier the export does not hold is refused
  with nothing recorded (`app/tests/test_repository_choice.py`,
  `app/web/src/components/conversation/RepositoryShortlist.test.tsx`).
- **The phases** come from the SDK's process flow, served by the app and joined in the shell to
  each manifest's `serves` ([Orchestration](orchestration.md)), so the shell keeps no copy of the
  flow. The shell shows them as "Your data journey", in a researcher's words: each phase has a
  short `name` and a one-sentence `summary`, and each step a `label`, all carried by the process
  flow beside the Blueprint's own wording, which the orchestrator reasons over. The journey names
  no agent and no requirement, since a researcher works through the conversation and needs to see
  only the whole route. In a project it shows where the project is, as the harness derives it
  from the project log (`GET /api/projects/{id}/progress`, [Orchestration](orchestration.md),
  invariant 18): how many steps of each phase are done or skipped, each step's state, and the step
  suggested next. The researcher may choose their entry point and mark any step done or skipped,
  or open it again (`PUT .../progress/entry`, `PUT .../progress/steps/{step_id}`); the server
  records it acting for the person signed in and answers with the progress derived anew. The
  shell computes no state and no suggestion of its own.
- **The agent directory** is read-only and for end users: each agent's name, description, what it
  takes and returns, what powers it and whether this deployment will run it. A person does not run
  or message an agent from it; they work through the conversation. Below that, folded away, is
  what the agent's card declares, field by field (`@data-director/agent-view`, `sdk/browser`), for
  a steward or developer who needs to inspect it. Running one agent directly, its run history and
  the explanation of its grounding, derivations and oversight declarations belong to the
  workbench.
- **The policy page** is read-only and for anyone signed in. A person sees the rules their runs
  are held to, the same `policy_bundle_ref` every stored run records; a steward changes them in
  the profile file, not here (TODO(#225)).
- **What a deployment runs is public.** `GET /api/about`, open without a session, names the
  build (versions and commit), the profile the conductor holds runs to (its id, version, digest
  and orchestrator), and the configured agents it cannot reach, by name only. An operator's
  checks compare these with what was configured. The answer carries no address and no reason an
  agent is missing, because a reason can name an internal address; the signed-in
  `GET /api/agents` gives those.
- **Problem reports** go to one repository, named in the app's configuration, as an issue of type
  Bug, Feature or Task with the label `area: app`. The person needs no GitHub account. The app
  files them as a GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` and
  `DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`; `DD_FEEDBACK_GITHUB_APP_INSTALLATION_ID` is optional
  and otherwise found from the repository) or with a token (`DD_FEEDBACK_GITHUB_TOKEN`, or
  `_FILE`), never both (`app/src/dd_app/github_auth.py`).

## Rationale

- **A shell drawn from manifests.** The earlier app was built around one agent, so each new agent
  needed new page code. Drawing from the manifest makes the shell general, and the multi-agent
  fixture keeps it so.
- **Conversation first.** The Blueprint puts the chat interface first, and a person should not
  have to choose an agent before saying what they need.
- **Projects first in the navigation, the conversation first on arrival.** The project is the unit
  of work ([Projects](projects.md)): its conversations, inventory, documents and decisions belong
  to it, so the projects page (`/projects`) is the first item in the main navigation, and a
  project's own page is marked as under it. A person still lands on the conversation, and their
  first message starts a project, so nobody has to make or choose a project before saying what
  they need. The app starts projects untitled, so the list names each by its first
  conversation's title.
- **One project at a time.** The shell works in one active project: the workspace header names it
  switches to another or to **New project**, and links to the project's page (**Project details**), the left-hand list shows only its
  conversations, **New conversation** starts another thread in it, and the right panel describes
  it. With no project active, the first message starts one, which becomes active. Opening a
  project from the projects page, or its documents page, makes it active; switching closes the
  open conversation. Which project is active is a convenience of the browser, kept in
  `localStorage`, and a remembered project the server no longer lists is dropped.
- **The conversation at the centre of a workspace.** Above it, whom the work acts for and whose
  policy applies, then the Blueprint's six phases as a strip, like a progress bar, that opens to
  each phase's steps and the agents serving them. On the left, the person's conversations, so
  that another is one press away; on the right, an overview of the project: its current state
  (dataset, phase, repository, governance flags), the files attached to it and its documents.
  Only the repository is built; the others await a record of where the project is (#160).
  The activity log spans runs and conversations, so it is a page of its own in the main
  navigation. What the orchestrator is and how far to rely on it is on the agents page, not
  beside every conversation. Evidence belongs beside the claim it supports
  (`docs/ui/best-practices.md` §4), so a delegated run opens in its card. When proposals and a
  review gate exist they take the centre and the conversation docks beside them.
- **What a turn produced, on the turn.** Researchers asked for a README and could not tell that
  one had been drafted: it was inside a closed run card, and the side bar had only a link to the
  documents page. A turn's documents are its result, so they come first; the runs are their
  evidence. The match is by invocation, as the project log records it, so the shell names no
  agent and shows only what became a project document, never a payload that failed its checks.
  Deciding stays on the documents page, with its reason rules and its refusal of a stale
  decision, so that approving is deliberate (`docs/ui/best-practices.md` §2, §8) and done in one
  place.
- **Policy in the profile.** Which agent a person talks to first is a policy choice. The profile
  is what a steward reviews and every run cites; a change to the orchestrator raises its version,
  so stored runs say which orchestrator the rules named.
- **An inventory in the project, not in the message.** Pasted into the message, an inventory of
  a few hundred files filled the transcript and was sent again in the history of every later
  turn, and an orchestrator could pass a changed copy to an agent. Kept by the project, it is
  given to each agent whole by the conductor, covered by the input hash, and shown to the
  researcher as one line (#443).
- **One path to every agent.** Two ways of reaching an agent are two behaviours to keep
  conformant. They did diverge: A2A carries numbers as doubles, so a payload over the wire gave
  `14.0` where the in-process path gave `14`, and the app's tests, using the in-process path,
  never saw it. One path also leaves one agent list for development and deployment.
- **The app files reports itself.** A report is little use without the build it was made on, and
  most researchers have no GitHub account. The token is narrow: a fine-grained token for one
  repository with Issues: write, which can do nothing a model key can.

## Rejected alternatives

- **Gradio, or a chat around a model of the app's own.** The page was built around one agent and
  its tools; the app now has no model of its own and converses with the orchestrator.
- **A UI schema or presentation hints from agents.** It would couple every agent to one shell's
  layout; the manifest declares derivations and the shell works out presentation.
- **A drafted document found in a child run's payload, or announced in the orchestrator's
  reply.** A payload is what the agent returned, not what the project recorded: it may never have
  become a version, and it carries no state. A model's reply may leave the document out, and a
  sentence cannot carry its state or a link to it.
- **Approving a draft from its card in the conversation.** It is fewer steps, but it puts a
  second decision form in the transcript and invites approval without reading.
- **Running an agent in the app's process.** See "One path to every agent". It also needed a
  special rule for model keys in the app's process and a second agent list for deployment.
- **The directory as the home page, with the conversation as one more page.** It makes a person
  choose an agent first.
- **The shell routing messages to sub-agents.** That puts a policy decision in the shell, and its
  hand-offs would not be recorded as delegations on any envelope.
- **A fallback orchestrator: one named in code, the first listed, or the only `delegation`
  agent.** A person would be talking to an agent they did not know had been chosen, and the
  choice would depend on what happens to be registered, not on anything a steward reads.
- **Naming the orchestrator in the app's own configuration** (agent list, environment variable).
  It is policy, which belongs in the profile.
- **Refusing to start unless the orchestrator is running.** One stopped service would stop the
  whole app, including the per-agent pages that still work.
- **The open run in a side column.** The evidence sat away from its turn, the column was empty
  until a run was opened, and on a narrow screen the run replaced the page.
- **The conversation as a strip beneath a working surface.** Until proposals exist nothing fills
  that surface, so the one working part would be the smallest thing on screen.
- **Marking the researcher's current phase from the conversation.** The shell would infer where a
  project stands, which no agent has said and no record holds.
- **A profile setting to switch off direct runs.** Nothing needs it, and the profile loader
  refuses a key nothing enforces.

## Non-functional requirements

- **Accessibility (C6).** The shell targets WCAG 2.2 AA, above the Blueprint's 2.1 baseline.
  Interactive widgets come from React Aria Components. A status is never shown by colour alone.
  CI runs ESLint with `jsx-a11y`, Vitest with axe, and Playwright (`app/web/e2e/shell.spec.ts`):
  axe in light and dark, keyboard-only journeys, and reflow at 320 CSS pixels (400% zoom) without
  horizontal scrolling. Automated checks find only some failures; the rest is human review
  ([Evaluation and conformance](evaluation.md)). Chat content needs particular care
  (`docs/ui/best-practices.md`).
- **Colour scheme.** Light by default whatever the system prefers; the person's choice of dark is
  remembered in that browser (`shell.spec.ts`).
- **Privacy.** No font or other asset is fetched from a third party; the typeface is self-hosted.
  A problem report is public, and the page says so and shows what will be sent beside the form.
- **Security.** The credential for filing reports is a secret the app holds, read from a
  credential file or, for a token, the environment. It is one of two, and configuring both stops
  the app at start-up. A **GitHub App** is preferred: the app holds its private key, signs a
  ten-minute JWT, and exchanges it for an installation token that GitHub limits, at the app's own
  request, to the one repository and to Issues: write. That token lasts an hour and is kept in
  memory only, renewed a minute before it expires, and asked for again once if GitHub refuses it.
  The App itself should be granted Issues: read and write and nothing else, so even its key cannot
  do more. A **fine-grained personal access token** is the alternative; give it no scope beyond
  Issues on the one repository, and note that it belongs to a person and expires. Anyone who can
  reach the app can file a public issue as the project's bot. A delegation grant is a bearer token, so the
  app warns at start-up when it is not bound to a loopback address. TODO(#17): authenticate
  callers.

## Open questions

- TODO(#411): end-to-end journeys in a browser against the real server; the Playwright suite
  answers `/api` from fixtures.
- TODO(#244): whether the shell's tests feed `CONFORMANCE.md`; until then they carry no
  requirement marker and C6 rests on review.
- TODO(#69, #159): streamed turns and replies over AG-UI, the activity log, live regions and
  cancellation.
- TODO(#72, #73): the review gate, and how the conversation docks once there is a working
  surface. A suspended child's card says it is waiting for review.
- TODO(#160): the project's current phase in the workspace.
- TODO(#668): the intake card, its routes and the tracker's way back to it (rule 25).
- TODO(#67): no agent declares limits, reliability or data handling yet.
- TODO(#141): listing runs and conversations reads the whole run store; an index by principal
  comes with the run record (#653).
- TODO(#188): the report limits are provisional and counted for the whole process, not per
  person.
- TODO(#254): integers in a payload arrive as floats over A2A.
