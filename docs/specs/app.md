# The app

## Intent and scope

The app (`app/`) is the Data Director that people use. The Blueprint's presentation layer is a
"web app providing a chat interface and feedback mechanism" over an application layer that
orchestrates requests and coordinates the agents
([§9.2, §9.3](../blueprint/09-reference-architecture.md#92-presentation-layer)). A person talks to
one Data Director; the specialist agents support it. So the app opens on a conversation with the
orchestrator, and every agent's own pages (what it does, its stored runs) sit one step away. A person runs an
agent by asking for it in a conversation; there is no form to run one directly.

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
6. **The conversation names agents; their run identifies them exactly.** Each reply and each
   delegated child is headed by the agent's name, not its version or model, which are on the
   agent page. Every delegated child opens its run inside its own card in the conversation, at
   every width, drawn by the run view's components, and the run shows `agent_id@agent_version`.
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
    its `project_id` and the inventory its project holds. The shell always names the project:
    it starts a conversation only from a project's workspace (rule 27). A body that names none is
    still accepted, for clients other than the shell. The shell names the open conversation in the
    address (`/projects/{id}/conversation?conversation=`), so a reload or a link reopens it in its
    own project and a message sent afterwards continues it. The app gives the conductor the same project store, so a turn's runs belong to the
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
    shows as a chip, never as its text. **Make an inventory**, offered beside **Add an inventory** in
    the project's panel and page and not under the message box, opens a
    dialog for a researcher who has none: one sentence on what an inventory is and that the data
    stay on their computer, then two routes as tabs, **In this browser** and **With the command**.
    Where the deployment serves the browser scanner's bundle at `inventory-bundle/`, the dialog
    opens on the first, **Describe a folder in this browser**
    (`components/inventory/DescribeFolder.tsx`, `src/scan/`), under which a **Use the command
    instead** button selects the second; where it does not, the command is the only route and
    shows without tabs, and while the dialog is finding out it shows neither. The browser tab
    stays mounted (inert) while the other is shown, so a scan goes on. On it, the researcher chooses a folder
    (`showDirectoryPicker` where the browser has it, else `<input webkitdirectory>`; dropping one
    is a shortcut), and `dd-inventory` describes it under Pyodide in a Web Worker with no network
    (`@data-director/inventory`, Browser scanner). Each stage is announced once and the files are
    counted on a progress bar; Cancel ends the worker, as does closing the dialog. A folder
    holding a file of 4 GB or more is described only after advice that the command suits it
    better, since the browser's memory grows on files that large and the page can be killed
    when it runs short (`LargeFileNotice.tsx`; measurements in `inventory/browser/README.md`). The inventory
    it makes is handed on as `<folder>-inventory.json`, so it goes through the check above
    unchanged. The section credits the PRONOM signatures as their licence asks and links to the
    bundle's `NOTICES.md`. The second route, the backup, is the command, for data on a server or a cluster or
    a very large dataset: a tab per operating system (the browser's own selected) with the
    commands that install uv and run `dd-inventory`, each with a copy button, and at the end the
    file picker, whose file is added to the project as if chosen with **Add an inventory**. The command's text is
    `@data-director/inventory`'s `making.json`, which the user guide's *Making an inventory* page
    renders too (`docs/hooks_inventory.py`), so the two cannot drift; the dialog names no agent and
    holds no policy (`MakeInventoryDialog.test.tsx`, `DescribeFolder.test.tsx`, and
    `app/web/e2e/scan.spec.ts`, which scans a folder holding a canary and checks that no request
    carries it). The release image and the VM deploy build the bundle from the same commit and serve
    it (`docker/release.Dockerfile`, `deploy/deploy.sh`), and their smoke test checks it is served
    (`scripts/smoke_image.py`). An app on the researcher's own machine whose operator named
    folders it may read (`DD_INVENTORY_FOLDERS`, [Projects](projects.md)) begins the dialog with
    **Describe a folder on this computer** (`components/inventory/DescribeServerFolder.tsx`,
    `src/scan/serverFolders.ts`), shown where `GET /api/about` says `server_folders`: the
    researcher opens a listed folder and its subfolders by name (`GET /api/folders`), and
    `POST /api/folders/inventory` describes the one chosen with `dd-inventory` and answers the
    inventory, which is handed on as `<folder>-inventory.json` to the same check and stored by
    nothing else (`DescribeServerFolder.test.tsx`, `app/tests/test_folder_scan.py`). The
    transcript shows the chip on the turn where the project's inventory changed, read from the
    `project_inventory` the conductor gave that turn (`app/tests/test_app.py`,
    `app/web/src/components/conversation/ConversationHome.test.tsx`).
    An inventory may also be added to a project without a conversation: the project's page and the
    workspace's Project panel offer **Add an inventory** (**Replace the inventory** where the project
    holds one) beside **Make an inventory**. The file goes through the same check as one attached to
    a message, and only **Add this inventory** sends it, to `POST /api/projects/{id}/inventory`; a
    refusal is said and the check stays open, and cancelling stores nothing
    (`app/web/src/components/inventory/AddInventory.test.tsx`).
    A chip whose whole inventory the page can read, the one attached and the one the project holds
    now (`GET /api/projects/{id}/inventory`), has a **View inventory** button. It opens a dialog
    that says this is everything Data Director keeps and agents are shown, then what the inventory
    amounts to and leaves out, where possible personal data was found (by file, with no value, and
    saying whether nothing was found or the inventory was never checked; such files are marked and
    counted in their closed folders, `app/web/src/components/inventory/PersonalData.test.tsx`), its
    formats, its files as folders with a search, and the columns of its tables. A chip for an inventory the project has since replaced has no button, because
    only the latest is served. The facts come from `@data-director/inventory`
    ([System and boundaries](system.md)); the dialog only lays them out. Folders are drawn only
    while open and a search draws at most 200 matches, so an inventory of thousands of files
    stays usable; checkboxes and folders work by keyboard and are named for screen readers
    (`app/web/src/components/inventory/InventoryView.test.tsx`, `app/web/e2e/shell.spec.ts`).
    Beside the project's chip, **Edit inventory** opens the same editor on the inventory the
    project holds. Under **Update with a new scan**, the researcher chooses which folder a new
    scan is of: the folder the inventory was made from, one of its folders, or a folder it does
    not have yet, which is added beside the others (naming, the first time, the folder it already
    has). The scan is a folder described there in the browser, where the deployment serves the
    scanner (**Describe a folder in this browser**, as in Make an inventory), or the file
    `dd-inventory` wrote; while the browser describes it, which folder it is of cannot change
    (`app/web/src/components/inventory/DescribeFolder.test.tsx`, `app/web/e2e/scan.spec.ts`).
    Only that folder is replaced (`withPart`); what the researcher stated is carried by
    path, with what the scan added, changed and removed, and the files they had described that
    it no longer lists ([Projects](projects.md)). **Save as the project's inventory** sends
    the result to `POST /api/projects/{id}/inventory`, which adds it as the project's latest; the
    store records which inventory it revises ([Projects](projects.md))
    (`app/web/src/components/inventory/InventoryEditor.test.tsx`, `app/tests/test_app.py`).
    A supporting document is attached in the same way: a turn may carry `documentation`, an
    object giving its `name`, `media_type` and `text`, which the server adds to the
    conversation's project before the turn runs ([Projects](projects.md)). With one, the message
    may be blank and the server supplies a sentence saying a document was attached; a turn may
    carry an inventory and a document together, and if the project refuses either, the turn is
    refused, nothing runs and neither is kept. The shell's one **Attach a file** button, and a
    drop on the message form, take a `.json` file as an inventory and a `.txt`, `.md`, `.docx`
    or `.pdf` file as a document, unless the agent directory says the profile refuses attached documents
    (`attached_documents`, [Projects](projects.md)): then they take only an inventory, say why a
    document is not taken, and the server refuses a turn that carries one. They take one file at
    a time: of several chosen or dropped together, the first is opened and the others are named
    as not attached, on the form and in the polite live region; a document checked while another
    is attached replaces it, which its dialog says before the researcher attaches it and the live
    region says after, and so does an inventory (#1170,
    `app/web/src/components/conversation/useAttachments.test.tsx`). A Word document or PDF
    is refused in the browser if it is over 1 MB, and otherwise sent to
    `POST /api/documentation/extract`, which reads its text inside the deployment and keeps
    nothing; the dialog then shows that text and says where it was read from, and the turn sends
    the file, not the text, which the server reads again ([Projects](projects.md)).
    `GET /api/projects/{id}/documentation/{digest}?original` serves the file a document was read
    from. A text or Markdown document is read in the browser, refused there if it is empty or over 256 KB,
    and first opened to be checked: a dialog shows its name, size and text, says that it will be
    stored in the project, which of the deployment's agents read its text and what for, as each
    card's `reads_attached` declares, and that the others are told only its name, type and size
    and cannot use its text ([Agents](agents.md), invariant 12; #1326), and
    that it must be about the data, never the data themselves nor anything that identifies a
    person. The dialog also shows what `POST /api/documentation/check` finds in the text:
    possible personal data, by the inventory command's detector, and secrets, by detect-secrets'
    named plugins, each by kind and never by value, in or out of a project, keeping nothing.
    Where something is found, the button reads **Attach anyway** and is enabled only once the
    researcher ticks that they have checked the document; the turn's `documentation` then names
    the kinds in `confirmed`. The server checks the text again: a document whose findings are
    not all confirmed is refused with `409` `documentation-held`, listing the kinds, nothing runs
    and nothing is kept, and the log names the document and the kinds only. A Word document's or
    PDF's text is checked as plain text, in the dialog and again by the server on the text it
    reads from the file, never on text the client sends (#473,
    `app/tests/test_documentation_hold.py`,
    `app/web/src/components/conversation/DocumentReviewDialog.test.tsx`). Nothing is attached
    until the researcher presses **Attach this document** or **Attach anyway**; closing the
    dialog any other way discards it. The checked document shows as a chip with its name and
    size and a button to remove it, never as its text, and so does each document a turn's
    `project_documentation` gained on the transcript. `GET /api/projects/{id}/documentation`
    lists a project's documents and `GET /api/projects/{id}/documentation/{digest}` serves one's
    text (`app/tests/test_app.py`,
    `app/web/src/components/conversation/ConversationHome.test.tsx`,
    `app/web/src/components/conversation/Transcript.test.tsx`, `app/web/e2e/shell.spec.ts`).
20. **The profile page shows only what the session holds.** `/profile`, reached from the name in
    the banner, shows the name and iD the identity provider gave at sign-in, how the person is
    known and when the session ends, and says that nothing more is kept but the facts a person
    chooses, in a project, from their public record. It makes no request to the provider and the
    app asks for no wider scope (`app/web/src/components/profile/ProfilePage.test.tsx`). It points
    to the Settings page (rule 30) for the person's own AI account and preferences.
21. **A reply's questions are answered one at a time in a form, and may be ignored.** A reply's
    `reply_questions` are drawn beneath the reply. On the latest turn each question is a fieldset
    whose legend is the question and whose description is its help: a choice question as radio
    buttons, or checkboxes where several may be chosen, each option a card the whole of which can
    be clicked (the control stays visible and ticked beside an accent bar), with "Something else"
    and a text box where the question allows an answer in words; a short text question as a
    one-line text box, which offers the question's suggested answers (`question_suggestions`) in a
    list narrowed to those containing what is typed, the answer always being the text in the box;
    a long text question as a text area. Each text box counts the characters left against the limit
    the harness holds an answer to and never cuts what is typed or pasted: an answer over the limit
    is kept whole and refused with a message saying by how much. A lone
    question is answered and sent in place. A series shows one question at a time, saying in
    words which of how many it is beside a progress bar, with Back, Skip and Next; Next with
    nothing entered says to answer or skip. After the last question it lists the answers to check,
    each with a button to change it, and Send answers, which needs at least one answer. Moving to
    another question moves the focus to its legend, and to the list's heading at the end. On
    earlier turns the questions are read-only, each answer marked with an icon and words, never by
    colour alone, and a skipped question says so. A new reply that asks is announced in the polite
    live region. Sending sends the answers in words as `message_text` beside `reply_answers`:
    Markdown, each question asked in bold followed by its answer (several options chosen as a list)
    or by `_Skipped_`, with the question's and the researcher's words escaped so that they read as
    written; the transcript renders such a message as Markdown, and a typed one as typed. The
    server refuses answers the harness's `answer_problem` rejects, and nothing runs. The message
    box stays usable, so the researcher may type instead (`app/tests/test_app.py`,
    `app/web/src/components/conversation/QuestionSeries.test.tsx`, `e2e/shell.spec.ts`).
22. **The policy page shows the profile the gate holds runs to.** `/policy`, in the main navigation
    and linked from each place that names the policy, is drawn from `GET /api/policy`: the
    profile's reference, description, digest and orchestrator, each agent it enables with the
    action class it assigns, and the action classes that need approval. What happens to each
    agent's runs here is read from `GET /api/agents`, never worked out in the shell, and an agent
    the profile enables that the deployment does not reach is named by its identifier. The page
    also shows the line drawn at each Blueprint step (#448): `delegated` to the enabled agents
    serving it, as their class allows; `must_approve`, referred to a data steward, when a serving
    agent's class needs approval; `never_delegated` when a person decides it (`Step.person_decides`,
    C2); or `not_offered`, out of scope or served by no enabled agent. The server works each step
    out from the profile and the agents' `serves`, with no profile key of its own; the shell draws
    it. The Governance row of the current state panel links to it (`app/tests/test_app.py`,
    `app/web/src/components/policy/PolicyPage.test.tsx`).

23. **A draft's questions are answered on its card or its documents page, in the researcher's own words.** While a
    drafted version is its document's latest, its card in the conversation puts the questions no
    recorded answer has answered in one form, titled with how many remain, in two groups. Those
    with a model's suggested answer come first, all at once, in a fieldset "Suggested answers to
    check": each box starts with the suggestion and is described by what it fills and by a line
    saying who suggested it, a model or the researcher in another document or a decision
    ([Drafting documents](drafting.md), invariant 11), or, once changed, what the suggestion was,
    with a button to put it
    back. One "Accept N suggested answers" button records every box not left blank, as it then
    reads; nothing a model suggested is recorded until a person presses it. Those with no
    suggestion follow, three at a time, in a fieldset "Only you can answer these", each a blank text
    box labelled by the question and described by what it fills, saved with "Save answers", which
    never sends a suggestion; blank boxes are left as they are. Each box counts the characters left
    against the server's `answer_max_length` and never cuts the text; an answer over it is kept
    whole and refused with a message, with nothing sent. A box holding text not yet saved says
    "Not saved yet" in words, and the browser asks before the page is left or reloaded while any
    does. Beneath the form, the card lists the latest version's answered questions with the answers
    the project log holds, so they are there after a reload; each has a "Change" button that puts
    the question back in the form with its saved answer, and saving records a new answer, which
    stands. Each question links to a new
    conversation ("Talk this through", `/?question={document_id}/{question_id}`) whose message box
    holds, unsent, a request for help with it; the address then drops the question, and the answer
    is still recorded on the draft. Saving sends the answers to
    `POST /api/projects/{id}/documents/{document_id}/answers`, whose body never names who answered:
    the server records them for the person signed in, refuses a malformed body with nothing
    recorded, and answers `409` for a version no longer the latest or a question it does not ask.
    The card then draws the documents the server read back and says in a status how many answers
    were recorded. The project's documents page has one Questions section per version, saying how
    many are answered: on the latest version it holds the same form, with the answered questions
    folded beneath it, each with its answer and "Change"; an earlier version's questions are
    listed only, each with the answer recorded, or saying in words that none is, with the
    suggestion while it is unanswered ([Drafting documents](drafting.md),
    `app/tests/test_document_answers.py`,
    `app/web/src/components/project/DocumentQuestions.test.tsx`,
    `app/web/src/components/conversation/DocumentCard.test.tsx`,
    `app/web/src/components/project/ProjectPage.test.tsx`,
    `app/web/src/components/conversation/useAskAbout.test.tsx`, `e2e/shell.spec.ts`).
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
    The admin service is not the app and is outside this rule: it shows an operator every
    person's runs, on the VM's loopback only ([Policy and identity](policy-and-identity.md),
    "The admin service").
25. **A new project's conversation opens with the intake, and the researcher may always pass it
    by.** While a project's intake is pending ([Orchestration](orchestration.md), invariant 20),
    its workspace (`/projects/{id}/conversation`) opens with Data Director's card before any turn.
    The new-project workflow (rule 27) opens that workspace, so a new project's card is the first
    thing in it. The card holds a greeting and the next question, drawn as in rule 21. It is announced in the polite live region and has a
    "Skip these questions" button.
    - `GET /api/projects/{id}/intake` reads the next question, or says the intake is complete or
      dismissed. It carries `state`, `next` (the next question's id, or null), every question
      asked from the project's entry point with its current `answer_values` and, for a question one
      of whose answers says something at once, its `notices` by answer value, and the project's
      `progress` (`dd_harness.intake.describe`). The card shows a notice as soon as its answer is
      chosen and keeps showing it once recorded; it changes no step.
    - `POST /api/projects/{id}/intake/{question_id}` records an answer (`{"answer_values": […]}`).
      It answers with the next question, or, once the intake is complete, with the phase the
      project starts at and the suggested step, both from the project summary. The suggested step
      is one an enabled agent serves wherever its phase has one ([Orchestration](orchestration.md),
      invariant 19), so **Start with …** does not open on a step Data Director cannot help with.
      Before the project's first turn, the card's ending then offers "Start with" the suggested
      step and "Not now". Start closes the card and sends the researcher's opening turn, which
      names that step, by the ordinary turn path, so the conversation begins with Data
      Director's guidance on it. Not now closes the card and sends nothing. Asked again from the
      tracker, or once a turn exists, the ending offers only Close.
    - `POST /api/projects/{id}/intake/dismiss` records a dismissal.

    Neither body names who answered: the server records the answer for the person signed in. A
    malformed body is refused with a 400, and an answer the harness rejects with a 409; nothing is
    recorded in either case. The message box stays usable throughout. A turn sent while the
    intake is pending leaves it pending, and does not count as an answer. A question with only a model's
    suggestion (`suggested_values`), and the entry question while its entry point is a model's, are asked with that answer chosen and a note that Data Director
    took it from what the researcher wrote; Next records it as the researcher's own answer, and
    Skip leaves the suggestion unrecorded as an answer. A question with neither is asked with
    nothing chosen ([Orchestration](orchestration.md), invariant 20). The card does not yet
    show suggestions, and a model's entry point still completes the entry question rather than
    leaving the intake pending until it is confirmed, TODO(#908). The intake is a card
    of the project, not a turn: no orchestrator runs for it, and the history holds none of it. Its
    answers reach the orchestrator through the project's entry point and step states. The phase
    tracker offers "Answer the setup questions again", which shows the card with the current
    answers chosen and records only an answer that changed. The card reads the intake again after
    each turn, as the workspace reads the project's progress, and when asked again from the
    tracker; a read after a turn changes what the card holds, never whether it is open. An
    entry point Data Director worked out from what the researcher said (`entry_source` `model`) is shown chosen, with a note saying it is
    Data Director's; Next records it as the researcher's own, and nothing records it otherwise
    (`IntakeCard.test.tsx`, `useIntake.test.tsx`). The card's Skip passes one question
    by for that visit only, recording nothing, so it is asked again when the workspace next opens;
    "Skip these questions" records the dismissal. The card's questions are drawn by
    `ChoiceQuestion.tsx`, as a reply's are (`app/tests/test_intake_routes.py`,
    `app/web/src/components/conversation/IntakeCard.test.tsx`).
26. **Researcher facts are chosen on the project's page, with nothing ticked.** The project's page
    lists **People** beside the repository, the disclosure and the deposit package (rule 32). Under
    each member it shows the record they kept and, on the signed-in person's own entry, a button
    to withdraw it; records kept by people no longer members are listed apart. **Bring in facts from your ORCID record** reads their public record and offers
    each section, and each affiliation, work and funding, as a checkbox, none ticked, with a
    button to tick or untick all of a group; **Keep the ticked facts** sends only what is ticked,
    by section and put-code, and the page then shows what the server kept. The panel says that the
    facts go to the project's agents, and to a hosted model only where the deployment allows it,
    and that an email address is never read
    (`app/web/src/components/project/PeoplePanel.test.tsx`, `app/tests/test_researcher_facts.py`,
    [Projects](projects.md), invariant 27).
27. **The shell opens on the person's projects, and a project is started on purpose.** Where the
    app keeps projects, `/` is the Projects page: the person's projects, as `GET /api/projects`
    lists them, each with **Open conversations**. A person with no project is told in a sentence
    what a project keeps, and given **New project** as the page's one action. The shell's
    addresses are:
    - `/`: the Projects page;
    - `/projects/{id}`: the project's documents (rule 2);
    - `/projects/{id}/conversation`: the project's workspace, with the open conversation
      (`?conversation=`) and run (`?run=`) as query parameters.

    Opening a project's workspace address makes that project the active one. An address from
    before this rule, `/?conversation={id}`, is replaced by the conversation's project address,
    and `/projects` by `/`, so old links still open. Where the app keeps no projects, `/` is the
    conversation, as before.

    **New project**, on the Projects page and in the project switcher, opens a dialog with one
    optional field, the project's name, and **Create project** and **Cancel**. Creating sends
    `POST /api/projects`, whose body is `{}` or `{"title": …}`. The server creates the project
    for the person signed in, with the route as its cause (`caused_by: "POST /api/projects"`),
    and answers `201` with the project's summary as `GET /api/projects` lists it. A title is
    checked as `PUT /api/projects/{id}/title` checks one, and a blank title is none. A body that
    is not an object, or that has any other field, is refused with a 400. A title the harness
    refuses is refused with a 400 too, and nothing is created in either case. Where the app keeps
    no projects, the route answers 404, as every project route does there. Once the project is
    created, it becomes active and the shell goes to its workspace, where the intake card shows
    (rule 25). A project created this way is listed on the Projects page before it holds
    anything; one the server created for a conversation that named no project is listed once it
    does (`app/tests/test_app.py`). A refusal or failure is said in the dialog, which keeps what
    was typed (`app/web/src/components/project/NewProjectDialog.tsx`). Not built yet: the
    addresses and landing page, TODO(#764).
28. **An owner deletes a project after typing its name, and restores it from the Projects
    page.** The project's page has **Delete project**, which opens a dialog saying that the
    project leaves every list for everyone working on it and takes no new work, that nothing is
    erased, that a package already built or downloaded is not recalled, and until which day the
    project can be restored, from the summary's `restore_days`. Its **Delete project** button is
    enabled only once the owner has typed the project's title, or its identifier while it has
    none. The server checks the same name (`DELETE /api/projects/{id}`, body `{"title": …}`) and
    refuses any other with a 400, so the guard holds for any client. Once deleted, the shell
    goes to the Projects page, which lists the project under **Recently deleted**
    (`GET /api/projects/deleted`), with when and by whom it was deleted, until when it can be
    restored, and **Restore** (`POST /api/projects/{id}/restore`). The section is not shown
    while there is nothing in it ([Projects](projects.md), invariants 22 to 25;
    `app/web/src/components/project/DeleteProject.tsx`, `ProjectsPage.test.tsx`,
    `app/tests/test_project_deletion.py`).
29. **A proposed fact becomes a fact only when a person decides it on the project's page.** The
    project's page lists **Project facts** beside the researchers. It shows what check agents
    proposed, each with what it would decide in one sentence, why it was proposed and which agent
    proposed it, and offers **Confirm it as proposed**, **Change it, then record my version** and
    **Reject it**, with an optional reason that no agent is given. Under **Decided** each fact that
    stands can be changed or removed, and **State a fact nobody proposed** records one of the
    person's own, named by the value that names it. After each decision the panel shows what the
    server read back. A proposal that has moved on is read again with a warning, and a member
    deciding whether sensitive data is published, or the licence, is told only an owner may
    (`app/web/src/components/project/FactsPanel.test.tsx`, `app/tests/test_project_facts.py`,
    [Projects](projects.md), invariant 28).
30. **A person's own settings are on the Settings page.** `/settings`, reached from the cog
    labelled **Settings** in the banner on every page and from the profile page, holds what a
    person sets for themselves, in tabs (**AI account**, **Appearance**, **Dates and times** and
    **Starting up**); what the deployment allows for everyone stays on the Policy page.
    Where the deployment offers it, the first tab holds the person's own AI account, which it reads from and
    sends to the model broker alone ([A person's own model account](model-accounts.md),
    `app/web/src/components/settings/ModelAccount.test.tsx`, `app/web/e2e/settings.spec.ts`).
    The other tabs are the **Preferences**: the colour scheme (light, dark, or matching the device), text
    size, spacing, animation (matching the device, reduced or shown), the icon that stands for the
    person beside "You" in the conversation (another member keeps the default person icon), the style dates and numbers
    are written in and the 12- or 24-hour clock, and whether a visit returns to the project used
    last or starts with none chosen. Each applies at once and is kept in that browser only, one
    `localStorage` key each, and none reaches the server (`app/web/src/preferences.ts`,
    `app/web/src/components/settings/Preferences.test.tsx`,
    `app/web/src/components/settings/SettingsPage.test.tsx`, `app/web/e2e/settings.spec.ts`).
    Every date, time and number the app shows is written through `app/web/src/format.ts`, so that
    it follows them.
31. **A person deletes a conversation from the list beside it, and restores it from the
    project's page.** Each conversation in the workspace's list has a delete button named by its
    title, which opens a dialog saying that the conversation leaves every list for everyone
    working on its project, that nothing is erased, and until which day it can be restored, from
    the project's `restore_days`; **Delete conversation** deletes it
    (`DELETE /api/conversations/{id}`) and, if it was open, the workspace starts afresh. The
    project's page lists the project's deleted conversations under **Recently deleted**, beneath
    its conversations (`GET /api/conversations/deleted`), with when each was deleted, until when
    it can be restored, and **Restore** (`POST /api/conversations/{id}/restore`); the section is
    not shown while there is nothing in it. Only whoever started the conversation, or the
    project's owner, may do either ([Projects](projects.md), invariants 29 to 31;
    `app/web/src/components/conversation/DeleteConversation.tsx`,
    `app/web/src/components/project/DeletedConversations.tsx`,
    `app/tests/test_conversation_deletion.py`).
32. **A project's members are on its People tab, which offers what the server allows.**
    `/projects/{id}/people` lists each member by ORCID iD, headed by the name they kept from
    their own ORCID record in the project, else the name on their public ORCID record, which the
    server reads for the page and does not keep ([Projects](projects.md), Roles), with their role
    and since when, and the facts they kept (rule 26). The former Researchers and Members tabs'
    paths, `/projects/{id}/researchers` and `/projects/{id}/members`, open it.
    The server says what the person may do (`may_manage`, and each member's `removable` and
    `role_changeable`, and `may_leave`), and the tab offers only that: an owner adds a person by
    ORCID iD and chooses their role, makes a member an owner or an owner a member, and removes a
    member; any member may leave, except the last owner. Removing and leaving each ask first, and
    after leaving the page goes to the Projects page. A refusal is said in the page's status, and
    what was typed stays. The tab says what members see of one another's work. In a project's
    conversations each turn is headed by its sender's name, or "You" for the reader's own
    (`app/web/src/components/project/PeoplePanel.test.tsx`,
    `app/tests/test_project_members.py`; [Projects](projects.md), Roles).

## Boundaries and contracts

- **Depends on** the harness (`dd_harness`) and the SDK only. Workspace-level dependency rules
  are in [System and boundaries](system.md).
- **Listings have threads of their own.** `GET /api/projects`, `/api/conversations` and
  `/api/runs` read and filter stored work before they page, so their cost grows with what is
  stored. They run in a pool of `DD_APP_LISTING_THREADS` threads (8), with `DD_APP_LISTING_QUEUE`
  more allowed to wait (16); past that a listing is answered `503` with a `listing-busy` problem
  and `Retry-After`. A turn or a run start, which uses the shared pool, is never queued behind a
  listing (#1258; [configuration](../guide/operations/configuration.md)).
- **Turn locks.** A conversation's turn holds the conversation's lock from reading its history
  until the turn is stored, and a turn that finds it held is refused with `TurnConflictError`
  before anything runs (orchestration invariant 4). The lock is the run store's
  (`Governance.turn_locks`, opened by `dd_harness.settings.conversation_locks` beside
  `DD_RUNS_DIR`: a file lock on files, an advisory lock on PostgreSQL;
  [Storage](storage.md), "Turn locks"), not the app process's, so several app processes or
  replicas over one store, as #520 allows, run one turn of a conversation at a time
  (`app/tests/test_concurrent_turns.py`). This is option (b) of #983. A conversation started in an app
  that keeps no projects is remembered by that process alone (`Governance._started`) until its
  first turn is stored; a deployment keeps projects, where a conversation is recorded in its
  project as it starts.
- **API types.** The shell's types for the server's responses are generated. Each route answers
  through a Pydantic `ResponseBody` model declared beside it (`app/src/dd_app/responses.py`), and
  `python -m dd_app.responses` prints the JSON Schema of every such model. In `app/web`,
  `npm run gen:api` turns that schema into `src/api/generated/responses.ts` with
  json-schema-to-typescript (`scripts/gen-api-types.mjs`); run it after changing a response model,
  and commit the result. The file is checked in, and the "mypy and generated schemas" CI job fails
  when it is not what the models generate. A key the server sometimes leaves out is optional
  (`x?: T`); one it always sends, perhaps as null, is required. An object whose shape the core
  contract defines (an envelope, a `Question`, a `Principal`) is named in
  `dd_app.contract_shapes` by its TypeScript type, which the generated file imports from where the
  shell already defines it: `@data-director/agent-view`, `src/api/contract.ts` or the domain
  folder that reads it. The domain folders' `api.ts` and `types.ts` re-export the generated types,
  and keep by hand only request bodies, the forms the shell converts a response into, and what the
  app's models do not describe. The tests check each golden fixture in `app/web/fixtures`, which
  `check_fixture` rewrites from real responses, against its route's model; and
  `src/fixtures.typecheck.ts`, which `npm run typecheck` compiles, checks the fixtures against
  what the generated types leave to hand-written ones (the contract shapes, the contract classes
  the app sends as they are, and the model broker's account). A field renamed in a response model
  therefore fails `npm run typecheck`, once the types are regenerated, until the shell is updated.
  The generated file is left out of the size and duplication checks, as other generated code is,
  and knip takes it as an entry, so a type the shell does not read yet is not reported unused.
- **Web source layout and import rules.** In `app/web/src`, the domain folders (`api`, `run`,
  `manifest`, `conversation`, `flow`, `session`, `project`, `feedback`, `policy`,
  `model-account`, `scan`) hold types and API clients, `api` the generated API types and the
  contract shapes they name, `scan` the browser scanner's client, and
  reading an inventory is `@data-director/inventory`'s (`inventory/browser/`);
  `components/` holds the interface, one folder per feature, with the shared kit in
  `components/ui/`. Four rules are checked: no file depends on itself through other files
  (dependency-cruiser, `.dependency-cruiser.cjs`, in `npm run lint`); the kit imports no feature
  component; a domain folder imports no component; and a feature folder imports another only
  through an allow-list, `FEATURE_IMPORTS`, each entry with its reason (eslint-plugin-boundaries,
  in `eslint.config.js`, with a test in `src/architecture.test.ts` that planted violations are
  reported, because the plugin does nothing without its TypeScript resolver). The allow-list
  started as the imports between features in November 2026. Three pairs import each other
  (`conversation` and `workspace`, `agent` and `capabilities`, `journey` and `project`);
  TODO(#494) untangle the first two.
- **Conversations and delegation** are specified in [Orchestration](orchestration.md); the app
  supplies the conductor's callback and the conversation API over it. Which agent is the
  orchestrator is a profile key ([Policy and identity](policy-and-identity.md)). A person's
  conversations are listed beside the open one by the title the harness derives, with the date and
  turn count beside it, and the open one marked as current; the app writes no title, since it
  calls no model.
- **Signing in, whom a run acts for, and model credentials** are in
  [Policy and identity](policy-and-identity.md). The app never holds a model key: no agent runs in
  its process, so there is nothing in it to call a model. A person adding their own model account
  sends the key from the browser straight to the model broker with an enrolment ticket; the app
  issues the ticket and never sees the key ([A person's own model account](model-accounts.md),
  `app/tests/test_model_account.py`).
- **Run events to the browser** are AG-UI ([Transport and tracing](transport.md)). What is
  streamed is the **conversation turn**, since that is how a person starts a run: one stream per
  turn. The turn's own conductor run (the orchestrator's, or the agent the turn names) is the
  AG-UI run, with the conversation as its thread, and its stages and checks' reports are what the
  run view draws. Each child the turn delegates to travels in the same stream as `SUBAGENT_*`
  events (started, with the child's agent and invocation; finished, with its outcome), with no
  stages of its own. The run view lists children in the activity log, and a child's full record
  is read back from the run store. Cancelling a turn cancels its own run; a child already running
  carries on and is stored, as any cancelled run is. One stream per child was rejected because
  the browser would have to open and pair several streams for one turn, while a child's grant and
  lifetime belong to its parent's run. `POST /api/runs`, which runs one agent and answers when it
  has ended, is kept for scripting and tests; the browser does not call it.
  `POST /api/conversations/{id}/turns/stream` serves the stream. Its body is an AG-UI
  `RunAgentInput`, as `HttpAgent` posts it: `runId` names the run, `threadId` (if given) must be
  the conversation, and `forwardedProps` is the turn's body, checked as
  `POST /api/conversations/{id}/turns` checks it; `messages` is not read, since the server builds
  the history from the stored turns. A turn refused before the stream opens (a malformed body,
  a conversation the person may not read, a `runId` already streaming) is answered with a problem,
  as the other routes answer; one refused once it is open (it no longer follows the latest turn,
  or goes to an agent other than the orchestrator) is `RUN_ERROR` alone. A refusal that names
  which it is carries its Problem Details slug as `RUN_ERROR`'s `code`: `turn-conflict` for a turn
  that no longer follows the latest, on which the shell reads the conversation again and puts the
  message back in the box, as for a `409` before the stream opens (#391).
  `POST /api/conversations/{id}/turns/{runId}/cancel` cancels the person's own turn while its
  stream is open (`202`), and answers `404` for any other; the stream ends with a cancelled
  `RUN_FINISHED` and the run is stored as `run-cancelled` ([Transport and tracing](transport.md),
  Cancelling). `POST /api/conversations/{id}/turns`, which answers when the turn has ended, is
  kept beside it for scripting and tests; the browser does not call it.
- **The shell reads a run's stream through `@ag-ui/client`**, one way for a live run and a recorded
  one: an `HttpAgent` posts the turn to its stream route, and a `CassetteAgent` replays a cassette
  from `app/web/cassettes`, all at once or paced (`run/transport.ts`, `run/cassette.ts`). Tests and
  fixtures provide their own through a React context, as they do for the API. The shell reads the
  raw events and the run reducer checks them, keeping an unrecognised or malformed event as such:
  `runAgent`'s own checks would fail a cancelled run, whose stopped stage the harness leaves open,
  TODO(#1007). A refusal before the stream opens is raised as the JSON route's would be (a
  conflict, a gateway error, no response), so the page says why in the same words; a turn the
  stream refuses with `RUN_ERROR` before `RUN_STARTED` ran nothing, and its message goes back to
  the message box as any refused turn's does.
- **A turn's run is drawn live** in the transcript, below the message sent, from the reducer's
  state and nothing else (`components/run/LiveRun.tsx`): the plan's stages, each with a word for
  its state, a finished check told as passed or failed by its report, and **Cancel the run**
  while it runs. Cancel asks the server to cancel the run and reads on until the stream says it
  was cancelled. A run that finished is then shown as a turn, read back from the server, and
  focus returns to the message box. One that was cancelled, failed after it started, or was
  interrupted (the stream closed before the run ended, so no finish is invented) keeps its place
  with a screen of its own until the next message, and focus moves to that screen's heading; the
  conversation is read back beside it, and once the server has stored the turn the message is not
  shown twice. Events of a type or `CUSTOM` name the shell does not know are counted in one
  collapsed "Unrecognised events (n)" group; a malformed event is shown as an error, and the run
  carries on. A stored run (a delegated child's card, or `?run=`) shows its outcome only: a
  child has no stages of its own.
  While the agent stage runs, the shell shows what the stream says it is doing, so a long turn
  never looks stalled (`components/run/AgentActivity.tsx`). The running stage counts its time
  by the page's clock, since the stream carries none; the count is hidden from screen readers,
  which hear the stage start once. Under the Agent stage, each delegated child and each tool call
  is listed as it starts and as it ends, the latest five shown and earlier ones counted, and each
  start is announced once. After 20 seconds with no new event, a line says the agent is still
  working; it claims nothing the stream has not said. The orchestrator's own model calls are not
  streamed, TODO(#159).
- **A turn that failed says so in plain words** (`components/conversation/Transcript.tsx`): that
  Data Director could not answer, that nothing was changed and what the message attached is kept
  in the project, and to try again or tell whoever runs Data Director. The agent's own statement,
  which may name an exception, is kept behind a closed disclosure for operators, never shown as
  the reply. The latest turn, if it failed, offers **Try again**, which sends its message again
  as a new turn (`app/web/src/components/conversation/Transcript.test.tsx`).
- **The activity log** (`components/workspace/ActivityLog.tsx`) lists each step of each run this
  tab has streamed, as it happens, newest run first, from the same reducer state
  (`run/activity.tsx`): steps, checks' reports, tool calls and delegated children, each child
  linked to its record. Below them it tabulates every stored run the person may read
  (`GET /api/runs`, newest first, a page at a time, `components/workspace/RecordedRuns.tsx`), with
  its outcome and a link to its record, leaving out those shown step by step above; it reads them
  again as each run here ends. The server keeps a run's record, not its events, so the steps are
  shown only for what this tab has seen since it was opened, and the page says so; the recorded
  runs outlast a reload, another tab and signing in again (#1330). It is not a live region: the
  run view says the run's progress once, through the announcer.
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
  their version. The decision form chooses nothing for the person:
  approve, edit and reject start unchosen. While the latest version is undecided, the reader says
  how many gaps it has (a README's placeholders, a data dictionary's unknown cells, a metadata
  record's empty fields) and how many of its questions are open, in a bar held at the foot of the
  window with a button to the decision, and again beside the button that records it. The counts are
  the version's questions and the answers recorded to them (one question per gap,
  [Drafting](drafting.md), invariant 5), never read from its prose. Approving a version with any gap
  as it is asks again in a dialog that names the count, since an approval is final and the deposit
  package takes it; rejecting, or editing and approving, does not, and keeps its reason rule (#1282).
  The list holds documents only.
- **A project's pages are tabs.** Beneath the breadcrumb, each of a project's pages is a tab with
  an address of its own: Documents (`/projects/{id}`), Researchers (`/researchers`), Members
  (`/members`), Project facts
  (`/facts`), Repository (`/repository`), Use of generative AI (`/ai-use`), Deposit package
  (`/deposit`) and the Journey map (`/journey`), each under `/projects/{id}`, then the project's
  Conversations. Each is there before any document is drafted. A link to one of the first five
  from when they were entries in the documents list (`?doc=repository` and the like) is sent on
  to its tab, replacing the history entry (`app/web/src/components/project/ProjectPanelPage.test.tsx`).
  The Repository tab (`GET /api/projects/{id}/repository`) shows the repository chosen last, as
  the harness resolved it from the pinned re3data export and the deployment's requirement sets,
  with nothing looked up live: its re3data record and, from its override, where to deposit; the
  requirement sets by version; what it accepts (media types, the largest file and item, licences),
  each only where a set states it; what Data Director assumes (that the package is checked against
  those sets alone and deposited by hand), with the warnings and the sets' `unconfirmed` items;
  the documents and metadata they ask for; and the sets' `guidance`, the pages the values came
  from. It also offers a way to choose one there (below); with none chosen it says so, and that a
  shortlist can be asked for in the project's conversations. Whether a package meets them is the
  deposit check's to say. The Deposit package tab checks the project against its chosen repository's
  requirements ([Deposit](deposit.md)) when the person asks, and lists what must be fixed and
  what is worth fixing, each in the harness's words. It offers to build the package only after
  a check the project passed, and then a link to download the zip by its digest. A decision made
  since the check withdraws that offer until the project is checked again. That a build is
  running, and what a check or a build did, is said once in a live region that is in the panel
  from the start. A check leaves focus on the button pressed; a build removes it, so focus moves
  to the built package, or to the callout that says why there is none, which brings it into view.
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
  new reply's announcement says what the turn drafted. The project pane lists the project's
  documents with their latest versions' states, the conversation's own first, and a proposed
  version waits on the researcher there with a link to its review. A decision is made only on the
  documents page.
- **FAIR feedback is read from the project's `FairnessReport` runs.** The shell recognises the
  class, not the agent. `GET /api/projects/{id}/runs?payload=<class>` lists the succeeded runs
  in the project whose payload is of the class the shell names, newest first, turns and
  delegated children alike, from the conversations the person may read; the server names no
  class (`app/tests/test_project_runs_by_class.py`). The project pane shows how many checks of
  each of F, A, I and R the latest report meets, what is new since the report before, the next
  steps and whether the metadata record has changed since; a question goes in the message box,
  unsent. The pane draws it only where an agent's manifest names `FairnessReport` as its
  payload. The project's FAIR feedback tab (`/projects/{id}/fair`) shows every check and each
  report stored in the project, and a run card lays a report out the same way. No score is
  shown: every view names the run that gave the report and says it is not a FAIRness evaluation
  (R4, [FAIR feedback](../ui/fair-feedback.md)).
- **A repository is chosen from the shortlist on the turn that made it.** A run whose payload is a
  `RepositoryOptions`, on the turn or among its delegated children, is a card on that turn listing
  each candidate by the re3data record it rests on: the `grounded_on` entry that is a re3data
  identifier, named by the evidence citing it from a pinned `re3data:export:YYYY-MM`. The shell
  recognises the class, not the agent. Choosing one sends only that identifier
  (`PUT /api/projects/{id}/repository`); the server records it for the person signed in, the
  harness reads the repository's name and declared standards from the pinned export, and the card
  shows what the choice resolved to: the requirement sets used, the documents and metadata a
  deposit needs, and each warning of what is not checked ([Deposit](deposit.md)). The project
  pane names the repository chosen last; each of its warnings waits on the researcher there, to
  be asked about in the conversation. Choosing another from a shortlist changes
  it, as a new choice, and the last one counts. An identifier no pinned registry holds is refused
  with nothing recorded (`app/tests/test_repository_choice.py`,
  `app/web/src/components/conversation/RepositoryShortlist.test.tsx`).
- **A repository can also be chosen on the project's Repository tab, without a shortlist.** The
  tab's combo box offers the deployment's suggestions until something is typed: the
  repositories its profile names as its institution's (`institution_repositories`), then those it
  has an override for, then those `suggested.yaml` lists (`app/config/repositories/README.md`).
  Typing searches the pinned re3data export and, for repositories re3data does not list, the
  pinned DataCite snapshot (`GET /api/repositories?q=…`) by name or additional name, or by the
  repository's own identifiers: its re3data or DataCite identifier, its re3data DOI or its URL.
  Each match says which registry it is from (`registry`). An institution's ROR is not one, since
  it names an organisation, not a repository. The same text always finds the same repositories,
  in the same order. **Choose repository** sends only the identifier (`repository_id`), as a
  shortlist's card does, and the last choice counts (`app/tests/test_repository_search.py`,
  `app/web/src/components/project/ProjectPanelPage.test.tsx`).
- **The phases** come from the SDK's process flow, served by the app and joined in the shell to
  each manifest's `serves` ([Orchestration](orchestration.md)), so the shell keeps no copy of the
  flow. The shell shows them as "Your data journey", in a researcher's words: each phase has a
  short `name` and a one-sentence `summary`, and each step a `label` and a `prompt`, a first-person
  opening for a conversation about it, all carried by the process flow beside the Blueprint's own
  wording, which the orchestrator reasons over. The journey names
  no agent and no requirement, since a researcher works through the conversation and needs to see
  only the whole route. In a project it shows where the project is, as the harness derives it
  from the project log (`GET /api/projects/{id}/progress`, [Orchestration](orchestration.md),
  invariant 18): how many steps of each phase are done or skipped, each step's state, and the step
  suggested next. The researcher may choose their entry point and mark any step done or skipped,
  or open it again (`PUT .../progress/entry`, `PUT .../progress/steps/{step_id}`); the server
  records it acting for the person signed in and answers with the progress derived anew. The
  shell computes no state and no suggestion of its own.
- **The journey map** draws a project's journey whole, at `/projects/{id}/journey`, after the
  Blueprint's §8 figures: each phase a line of stops, the entry points pinned to the phases they
  join at, the intake's decision points as diamonds before the steps they can skip, with the
  answer given, a band across the map saying every action is recorded (linking to the activity
  log), and the last phase looping back rather than ending. Like the strip it names no agent and
  no requirement, and computes no state: each stop's state, the word that decided it
  (`reasons`) and the decision points (`decisions`) are the harness's, in the progress it
  serves. Each stop is a button that says its state in words. A step out of scope says "Not in
  this version", or, where the intake's answer skipped it as the branch not taken, that it is
  skipped, struck through like any skipped step; opening one (`?step=`) shows what
  the step is, its state and why, a link to the document or page that produced it, the marks the
  researcher may make, and **Ask Data Director about this**, which opens the conversation with a
  question about the step in the message box, unsent (`/?ask={step_id}`), so the researcher's
  own word starts the turn. **Waiting on you** picks out the steps whose document awaits the
  researcher's decision and the decision points not yet answered; the strip shows the same count
  and leads with a button-styled link to the map, and names the suggested step's phase. Each card
  on the projects page shows the journey at a glance, linking to the map, and a **Journey map**
  link beside **Open conversations**
  (`app/web/src/flow/journey.test.ts`, `app/web/src/components/journey/JourneyPage.test.tsx`).
- **A conversation can be started from a step.** In a project, each in-scope step not done or
  skipped, and the suggested step beside the suggestion, offers "Start a conversation". It closes
  the open conversation and puts the step's `prompt` in the message box for the researcher to
  edit and send; a message already being written or attached is replaced only once they confirm.
  An empty conversation offers up to three prompts the same way: the suggested step's first, then
  the open steps after it in the flow, leaving out optional and out-of-scope steps; with nothing
  suggested it offers none, and once the box holds a message the offer gives way to it. Nothing
  is sent or recorded until the researcher sends, and the turn then takes the ordinary path
  (`app/web/src/components/conversation/ConversationHome.test.tsx`).
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
- **The footer links to the operator's privacy notice, if there is one.** The app holds a
  person's name, ORCID iD, conversations and projects for its operator, who decides why and how
  and so owes them a privacy notice. `GET /api/about` gives its address as `privacy_notice_url`
  (`null` when none is set), from `DD_PRIVACY_NOTICE_URL`, which `apply` writes from
  `privacy_notice` in `deployment.yaml` and removes when that is unset. The address is an
  absolute `https` URL: anything else stops the app at start-up, so a wrong setting never becomes
  a link. With none set the footer shows no such link. It does not fall back to the project's notice,
  which covers only the documentation site and the project's work on GitHub, and so would
  mislead. The footer's project navigation (About, Contribute) does link that notice, labelled
  "Project privacy notice" so that it is not taken for the operator's. The address is deliberately not in the profile: it is not policy, and a change to it
  must not change the profile's digest, which every stored run records.
- **Problem reports** go to one repository, named in the app's configuration, as an issue of type
  Bug, Feature or Task with the label `area: app`; a Bug also carries `user report`, so that a
  report from a person using the app is easy to find and to pick out on the project board. The
  person needs no GitHub account. The app
  files them as a GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` and
  `DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`; `DD_FEEDBACK_GITHUB_APP_INSTALLATION_ID` is optional
  and otherwise found from the repository) or with a token (`DD_FEEDBACK_GITHUB_TOKEN`, or
  `_FILE`), never both (`app/src/dd_app/github_auth.py`).

## Rationale

- **A shell drawn from manifests.** The earlier app was built around one agent, so each new agent
  needed new page code. Drawing from the manifest makes the shell general, and the multi-agent
  fixture keeps it so.
- **Conversation first, within a project.** The Blueprint puts the chat interface first, and a
  person should not have to choose an agent before saying what they need. In a project's
  workspace the conversation is at the centre, and nothing else has to be chosen first.
- **Projects first, on arrival and in the navigation.** The project is the unit of work
  ([Projects](projects.md)): its conversations, inventory, documents and decisions belong to it.
  So a person lands on their projects (`/`), the Projects page is the first item in the main
  navigation, and a project's own pages are marked as under it, except its journey map. **Journey
  map** follows Projects in the main navigation: `/journey` opens the active project's map in its
  place (so Back skips it), or lists the person's projects to choose one when none is active, and
  a project's map is marked as under it. Each of a project's pages starts with the same block: a
  breadcrumb (Projects › the project's name) and tabs for its **Documents**, **Journey map** and
  **Conversations**, the page shown marked as current, so the documents and the map are one press
  apart. Starting a project is one press
  and an optional name, and it lets Data Director speak first: the intake (rule 25) places the
  project in the process flow before the researcher types anything. A returning researcher sees
  every project and what waits in each (documents to review) before choosing where to work. A
  project left unnamed is listed by its first conversation's title.
- **One project at a time.** The shell works in one active project: the workspace header names it
  switches to another or to **New project**, and links to the project's page (**Project details**), the left-hand list shows only its
  conversations, **New conversation** starts another thread in it, and the right panel describes
  it. The workspace's address names its project, so a link opens the right one. Opening a
  project from the Projects page, or its documents page, makes it active; switching closes the
  open conversation. Which project is active is a convenience of the browser, kept in
  `localStorage`, and a remembered project the server no longer lists is dropped.
- **The conversation at the centre of a workspace.** Above it, whom the work acts for and whose
  policy applies, then the Blueprint's six phases as a strip, like a progress bar, that opens to
  each phase's steps and the agents serving them. On the left, the person's conversations, so
  that another is one press away; on the right, the project pane.
- **The project pane holds what a conversation needs, not a summary of the project.** The
  project's pages show it in full, and the header and phase strip already name the project and
  draw the journey, so the pane repeats none of them. From the top: what waits on the researcher
  (documents to review, fact proposals to decide, repository warnings, unanswered setup
  questions), each with the one thing to do about it; where the project stands, the step under way
  and the one suggested next; what Data Director is working from, the facts that shape its answers
  (funder, required repository, sensitive data, licence, sharing commitment, standard), each marked
  confirmed, proposed or not known, and the repository chosen; the inventory and documents, the
  conversation's own first; and the guardrails, closed until opened. What waits comes first
  because it is what a person must act on (`docs/ui/best-practices.md` §1, §2); the facts sit
  beside the chat so that a wrong one is seen before an answer built on it is relied on (§4). The
  pane decides nothing: a button goes to the project page where the decision is made, or puts a
  question in the message box, unsent. Approval before an agent acts and the pause for personal
  data are drawn as not built (#72, #39); the guardrails link to what the policy delegates at each
  step.
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

- **Turn locks in the app's memory, with one app process the only supported deployment** (option
  (a) of #983). It is the smallest change, but it fails silently: a second process over the same
  store, started by hand or by scaling a Compose service, lets two turns of one conversation
  interleave and fork it, and the app cannot reliably tell that another process shares its store.

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
- **Arriving on the conversation, with the first message starting a project.** Nobody had to make
  a project before saying what they needed. But a project did not exist until the researcher had
  typed, so Data Director could not speak first, and the intake had no project to belong to.
  Researchers also met projects only afterwards, as something the app had made for them, although
  projects are what keep their inventory, documents and decisions.
- **Projects only when none is active, else the active project's workspace.** It saves a press
  for someone working in one project. But what a person sees on arrival would depend on what
  their browser remembered, and the documents waiting in other projects would stay out of view.
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
- **Layout stability.** Nothing moves under the pointer as what a page reads arrives (#1328). The
  workspace and a project's page are drawn whole once the reads they make on load have landed or
  failed, with one status line, as tall as the window, until then (`ui/PageLoading.tsx`); the
  banner keeps a row for who is signed in at narrow widths while it is read; and a dialog whose
  body grows after it opens, such as the document check, fills the window's height, so its
  buttons stay put. `app/web/e2e/stability.spec.ts` measures, at 1280 and 320 CSS pixels, that
  loading the workspace, a project's page and the document check shifts the layout by no more
  than 0.05 (every shift not caused by input, summed) and moves neither **Next** nor an
  **Attach** button.
- **Live regions.** The frame mounts two, once, so they are in the page from load: a polite log
  (`aria-live="polite"`, `aria-atomic="false"`) and an assertive one for errors
  (`components/ui/Announcer.tsx`). Components speak through `useAnnounce()`; a lint rule stops
  anything else setting `aria-live`. A run's progress is drawn from the reducer's state
  (`run/announce.ts`): each step is said once when it starts, a failed check when its report
  arrives, and the end; `RUN_ERROR`, a malformed event and an interrupted stream are assertive.
- **Colour scheme.** Light by default whatever the system prefers; the person's choice of dark,
  or of matching the device, is remembered in that browser (`shell.spec.ts`, `settings.spec.ts`).
  Reduced motion follows the device unless the person's preferences say otherwise.
- **Privacy.** No font or other asset is fetched from a third party; the typeface is self-hosted.
  The browser scanner reads a chosen folder in the browser and sends only the inventory, after
  the researcher has checked it; its bundle comes from the app's own origin.
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
  reach the app can file a public issue as the project's bot. The browser scanner's worker script
  is sent `default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'`
  (`dd_app.worker_policy`, and the preview server in `app/web/vite.config.ts`), so it can neither
  fetch nor send anything: the page hands it the bundle's bytes. Every file under
  `/inventory-bundle/` is sent `Cache-Control: no-cache` (`dd_app.worker_policy`), so a browser
  revalidates its copy and never pairs one release's lock with another's wheel. A delegation grant is a bearer token, so the
  app warns at start-up when it is not bound to a loopback address. TODO(#17): authenticate
  callers.

## Open questions

- TODO(#411): end-to-end journeys in a browser against the real server; the Playwright suite
  answers `/api` from fixtures.
- TODO(#244): whether the shell's tests feed `CONFORMANCE.md`; until then they carry no
  requirement marker and C6 rests on review.
- TODO(#69): keyboard, axe and reflow journeys for the live run view, with Cancel (#950).
  Streaming a reply's text is TODO(#159).
- TODO(#72, #73): the review gate, and how the conversation docks once there is a working
  surface. A suspended child's card says it is waiting for review.
- TODO(#160): the project's current phase in the workspace.
- TODO(#761): the Projects page as the landing page and the new-project workflow (rule 27).
- TODO(#67): no agent declares limits, reliability or data handling yet.
- TODO(#141): listing runs and conversations reads the whole run store; an index by principal
  comes with the run record (#653).
- TODO(#188): the report limits are provisional and counted for the whole process, not per
  person.
- TODO(#254): integers in a payload arrive as floats over A2A.
