# The agents
Data Director is a team of agents. You converse with one of them, the Data Director, and it
asks the others for you. Each of the others is a specialist with a name for its role, such as
the Standards Librarian or the Policy Adviser, and helps with one or two steps of
[the workflow](workflow.md). You can also open any of them yourself and run it directly
([Running an agent](running-an-agent.md)).

Every agent works the same way:

- **It advises; you decide.** No agent chooses a repository, a licence, an access level or a
  standard for you, and nothing it suggests is adopted until you confirm it.
- **It shows its sources.** Each result cites the records it rests on, and the harness checks
  that it does.
- **It says when it cannot help.** Rather than guess, an agent abstains and says why. You can
  then ask a data steward ([Understanding outcomes](outcomes.md)).
- **Most use an AI model, which your deployment can turn off.** Each section below says what the
  agent sends to the model. Fixed rules make the decisions that matter; the model explains,
  suggests or reads text, and the agent checks what it returns. Which agents run, and what may
  reach a hosted model, are set by your institution's data stewards
  ([The policy and the profile](../steward-guide/policy-and-profile.md)).

All the agents are alpha software: they are being built in the open and will change. Which of
them you see depends on which ones your deployment has registered. The developer documentation
for each one is in its README, under **Packages → Agents**.

## The Data Director

The agent you converse with. It asks the others for you.

### Data Director (`orchestrator.model`)

The Data Director is the assistant you talk to, at every step from planning to deposit. Describe your project in your own words and it works out where you are, suggests the next step and follows you if you want something else.

- **You give it:** messages, answers to its short questions (you may skip any), and the files and documents you add to the project.
- **You get back:** a reply, questions, and the advice of specialist agents it asks for you, reported with their sources. It also suggests names for an unnamed project and each conversation.
- **It will not:** decide for you. You choose the repository, licence and access level. It gives no legal or ethics advice and does not change which files are in the dataset (use Edit inventory). Steps no agent covers yet are named as such, with general background only.
- **AI model:** it uses a model by default. It sends your messages, recent conversation, project notes and the specialists' results; a deployment can turn off only the conversation titles, since it needs a model to converse.
- **It pauses** the sharing steps if the data may identify people or consent is unsettled, and points you to your institution's ethics and data protection staff. You can continue provisionally, for planning only.

## Phase 1: Pre-collection setup

### Standards Librarian (`advisor.standards`)

The Standards Librarian suggests standard vocabularies, ontologies and file formats for your data: when you select vocabularies at setup, when you choose open formats to collect your data in, and when you prepare your data in open formats.

- **You give it** a short description of your dataset: title, description, keywords, themes, file types, and column names and types. Before you collect anything, the file types you plan to use are enough. It never needs your data values.
- **You get back** a short list from the FAIRsharing registry, each tied to the dataset or one column (for example ISO 8601 for a date column), with a reason and any doubt. Each is offered as a proposal in your project; nothing is adopted until you confirm it.
- **It will not** choose for you. Its ranking matches words, and it tells vocabularies from ontologies by their names, so check its picks against your field's practice.
- **The AI model** is on by default. It explains each pick, flags doubts and may search the registry for more; the agent checks what it adds against the registry's records. The model is sent your description, keywords, themes, file types and column names and types, not data values. A deployment can turn it off, and fixed rules then work alone.
- **It abstains** when there is nothing to search on, the registry cannot be reached or returns nothing, or no record scores well enough. Ask your data steward then.

### Storage Adviser (`advisor.storage`)

The Storage Adviser helps you plan where to keep your data while you work on them, how they are backed up, and who can reach them.

- **You give it** about how much data you expect, whether it involves personal data, and whether people outside your institution need access. It never needs your data.
- **You get back** the storage services your institution has listed, the most suitable first, with what each offers and anything to check before choosing it, the services it leaves out for your data and why, and the questions a storage and backup plan answers.
- **It will not** recommend storage your institution has not listed, such as a personal cloud account or a portable drive, and it does not set anything up. It does not advise on anonymisation.
- **The AI model** is on by default. It writes a short summary beside the advice and changes none of it. It is sent what you said about your data and the advice, never data. A deployment can turn it off, and the rules' own summary is used instead.
- **It abstains** when your institution has listed no storage, and refers you to a data steward when your data involve personal data and none of the listed services is approved for them.

## Phase 2: Governance and constraints

### Policy Adviser (`advisor.policy`)

The Policy Adviser shows what the data and open access policies of your funders, journals and institution ask of you. It works where policies are checked, and where a repository a policy requires is named.

**You give it** the funders, journals and institution behind your project, and optionally your discipline, kinds of data and publication date. You can add a policy web address or attach your institution's policy or award letter.

**You get back** the matching policy records from FAIRsharing and Jisc Open Policy Finder, and what each asks (depositing data, a repository, a licence), with a quote. It flags where policies differ, and asks which organisation you mean when a name is ambiguous.

**It will not** decide which policy applies, give legal advice or confirm that you comply. Check each result against the policy itself.

By default it uses an AI model, sent the policy records and text it finds plus your discipline, kinds of data and publication date, never the data. A deployment can turn the model off; the adviser then reads only the registries' fields. It abstains when no organisation is named, no record is found or a registry cannot be reached, which does not mean no policy exists: ask a data steward to check.

### Data Management Planner (`advisor.dmp`)

An early-stage (alpha) planner for three steps: describing your project before you collect data, reviewing your data management plan, and, at the governance step, comparing what the plan promised to share with what you now plan to publish.

**Describing your project.** This is the first planning step. Tell Data Director what the project is for and the data you expect to collect, or attach your proposal, case for support or award letter.

- **You get back** what the project is for, its field of study, when it runs and each kind of data you expect to produce, as project facts. Each one read from a document shows the passage it comes from. You confirm, correct or reject each on the project page, and it says what is still needed. The README that plans your documentation and your Data Management Plan are then drafted from what you confirmed, rather than asking again.
- **It will not** say what your project should collect or judge the research design. A model's reading of your document can be wrong: check each fact against its passage. Without a model it reads no document and proposes only what you said.

**Reviewing your plan.** Attach your plan to the project, or write one here and approve it, and ask for a review. If you mark an attached document as your plan, the checker reviews that document. If you haven't, it reviews the plan you approved here. Failing both, it reviews the document you attached last.

- **You get back**, for each of six core requirements of a plan (after Science Europe's: data collection, documentation and quality, storage and backup, legal and ethics, sharing and preservation, responsibilities and resources), whether a model read the plan as answering it specifically enough, only in part or in general terms, or not at all, with the plan's words the finding rests on and a short reason saying what to add. The model judges the plan against good practice from UKRI and the UK Data Service (specific and justified, proportionate, clear on repositories, retention and metadata, realistic about costs, transparent about what will not be shared, with named owners and a plan for keeping it up to date), and says where the plan does not reflect a decision made in the project, such as the licence or repository.
- **It will not** change your plan, or say whether it meets your funder's own template. A model's reading can be wrong: check each finding against your plan. The review needs a model; a deployment that has turned the model off gets no review, and the checker says so.

**Comparing what you share with what the plan promised.**

- **You give it** your attached plan, or a list of the outputs the plan committed to share, plus the outputs you plan to share now.
- **You get back**, for an attached plan, each sharing commitment it finds with the passage it rests on. You confirm, correct or reject each; nothing is compared until you have. Then it lists every difference (an output missing, unplanned, or a different repository, access level or licence), each flagged for you to review.
- **It will not** enforce the plan or decide who is right; not sharing, once reviewed, is a valid outcome. It checks nothing else in the plan, such as timing or costs.
- **AI model:** on by default. It reads your attached plan and helps match renamed outputs and two spellings of one licence or repository, seeing only the plan text or only what the rules could not match. Each judgement is shown with its reason so you can overrule it. A deployment can turn the model off; the checker then compares exact text and asks you for the commitments.
- **It stops and asks** when there is nothing to compare or a plan is too vague to name an output.

### Research Ethics Adviser (`advisor.ethics`)

The Research Ethics Adviser helps you spot data that may be personal or sensitive, and prompts you about consent and embargo. It works at two steps: identifying sensitive data, and confirming whether an embargo is needed.

- **You give it:** the names of your dataset's fields or columns, whether the data involve people, and whether you intend an embargo. A title and description are optional.
- **You get back:** a list of fields whose names suggest sensitive data, each with the kind of data it may be and why it was flagged, plus questions you need to answer or confirm, such as whether ethics approval and consent cover sharing.

It reads field names only, never your data values, so a field it does not flag may still hold sensitive data. It does not check free text, images or audio, and it does not know your participants' consent or the law that applies. It never says data are safe to share. It does not decide, or suggest, how sensitive data should be treated, for example by anonymising it. That is for you, with your institution's ethics and data protection staff.

By default an AI model reads the field names, as well as a keyword list, and may add flags. It never removes one. Only the field names and your answers about people and embargo go to the model, not the title, description or data. A hosted model is outside your institution, and field names can themselves reveal something about participants. A deployment can turn the model off, or use a local one.

It asks for more input if you give neither field names nor an answer about people.

## Phase 3: Repository selection

### Repository Librarian (`advisor.repository`)

Helps you find where to deposit your data, at the repository selection phase: which repositories suit it, whether they assign persistent identifiers, their access, fees and certificates.

You give it your field of study, kinds of data, the access you decided on earlier, your institution, and any repository a funder, journal or institution requires, or that you want to ask about. You get a description of each required repository, or a shortlist of up to five from the re3data registry. Each shows what it meets and misses, from re3data, DataCite and FAIRsharing.

It does not choose for you, and certification does not affect the ranking. Where a registry is silent about a fee or access rule it says "not stated", so check with the repository. It does not know your funder's or journal's rules; ask your data steward.

By default an AI model writes the short explanation of each repository. It is sent your field, kinds of data, access need and institution name, plus registry text about the repositories, never your data. The model does not pick or judge repositories, and a deployment can turn it off. It abstains when it has nothing to look up.

## Phase 4: Data preparation and metadata creation

### File Archivist (`advisor.files`)

The File Archivist helps when you clean and version your data files, the "preparation: files" step of the workflow, before you deposit.

**What you give it.** The project's file inventory, the list that the inventory tool writes for your dataset's folder: each file's name, size, checksum and detected type. It never opens or receives the files themselves.

**What you get back.**
- A list of every file with the format it appears to be and whether that format is open. A file it cannot place is marked unknown and not open.
- A short list of files worth a look before deposit, such as notes or interview files, tables with coordinate columns, material from other sources, agreements, system or configuration files, empty files and exact copies, and files whose content does not match their name. Each comes with a question for you.
- A short plain-language summary.

**What it will not do.** It does not read file contents, so a file it does not list may still hold personal data, sensitive locations or someone else's material. The listed files are prompts for you or a data steward, not findings. It does not convert, rename, delete or check that files open.

**AI model.** By default a model writes the summary from the findings, which are file names, formats and the reasons for each prompt, never contents. The model changes none of the findings, and a deployment can turn it off so the rules write the summary.

**When it stops.** If the inventory lists no files, it says so and asks you to run the inventory tool first.

### Documentation Editor (`advisor.documentation`)

The Documentation Editor helps you prepare a README and a data dictionary for your dataset, at the documentation step of preparing data for deposit. It works from your project's file inventory and, where there is one, your approved metadata record.

It also drafts a Data Management Plan (alpha), before you collect data. The plan follows six core requirements, after Science Europe's, under a section of project details. It places what people in the project decided, such as the funder, the repository, the licence and how sensitive data are handled, and asks you for the rest, first as questions and then, once you have answered, as the plan for you to approve. It writes no text of its own: a model, if one is configured, only suggests answers from documents you attached, such as your grant application. It needs no file inventory.

- **What you give it:** the inventory of your files, and ideally the approved metadata record. You can also attach field notes or a protocol, and answer its questions.
- **What you get back:** first, a short note asking what only you can say, such as methods, definitions, units and missing value codes. Once you have answered what you can, it writes the README and a data dictionary. The dictionary marks each value as read from the inventory, given by you, or still unknown. Anything it cannot know is left as a clearly marked gap and asked as a question.
- **What it will not do:** it does not open your data files, and it does not make up definitions, units, people, dates, places or citations. It may suggest an answer beside a question, but a suggestion only becomes part of the document if you save it as your answer.
- **AI model:** by default a model writes the README's connecting prose and suggests answers. It is sent the file names, formats and sizes, the table fields with summary values from the inventory, the record's title, creators, funders, abstract and licence, your answers, and any documents you attached. It is not sent your data. A deployment can turn the model off, and the editor then drafts from templates alone.
- **When it stops:** it declines if there is no file inventory, or if you ask for a data dictionary and no file has fields. Read any prose a model wrote before you approve it.

### Metadata Librarian (`advisor.metadata`)

Drafts the metadata record for your dataset at the "prepare metadata" steps, following the standard of the repository you chose (for now always DataCite), covering every property it asks for.

- **You give it:** the chosen repository, your file inventory and, if recorded, your answers and ORCID details.
- **You get back:** a draft to review before submission. It fills in only what it can know: the resource is a dataset, file formats and sizes, and your name, ORCID iD, current employer, keywords and grants where you kept them. Other values stay empty, each with a question. For where the data were collected, it first asks whether, and at what precision, the place may be published.
- **It will not:** invent creators, dates, licences, funders or places, take terms from a controlled vocabulary or convert between schemas.
- **AI model:** by default a model suggests a title, description, keyword and language beside the questions, never in the record. It sees the repository's requirements, the question texts and the files' names, types, sizes and field names, never your data, answers or ORCID details. A deployment can turn it off.

It abstains if no repository has been chosen or the repository needs a schema other than DataCite.

## Phase 5: Deposit and submit

### Rights and Licensing Adviser (`advisor.rights`)

An alpha adviser for the deposit steps where you choose a licence and an access level.

- **You give it:** any of the reuse you want to allow (in your own words if you like), whether the data are sensitive, a licence your funder or journal requires, and whether the data include third-party content.
- **You get back:** a short list of licences that fit that reuse (only the required one if you name it), the four access levels with when each applies, and questions to settle, such as who to ask about sensitive data.
- **It will not:** choose for you, give legal advice, check what your funder or repository requires, or judge whether data are sensitive. It offers five licences.
- **AI model:** on by default. It reads your words about reuse and tailors the questions, and can only order licences from its own list. It is sent those words, any required licence, whether there is third-party content and the licence list, not whether the data are sensitive. A deployment can turn it off; the adviser then understands four fixed reuse choices only.
- **It stops** and asks for more if you give it nothing. Check any reading of your wishes with your data steward.

### Linking Adviser (`advisor.linking`)

Helps you link your dataset to related publications, people, organisations and grants, when you prepare a deposit and when you add links after publication.

- **You give it:** identifiers as you have them: DOIs, ORCID iDs, ROR ids and grant numbers.
- **You get back:** for each one, whether it is well formed, its standard web form and a suggestion for recording it in your metadata. Where your deployment allows lookups, DOIs, ORCID iDs and ROR ids are looked up and the title or name shown, so you can check it is what you meant.
- **It will not:** register any link (you and the repository do that), confirm that a grant number exists, or recognise other identifiers such as arXiv ids. Its relation suggestions are defaults, so confirm each one.
- **AI model:** by default a model writes only a short summary, from the findings (each identifier as you gave it and what was found). It cannot change them. A deployment can turn it off, and fixed rules then write the summary.
- **When it holds back:** with no identifiers it asks for some. An unrecognised one is marked unknown for you to record by hand. A failed lookup is reported, and the form check stands.

### Metadata Reviewer (`advisor.quality`)

The Metadata Reviewer helps at the validation step of depositing data. It checks whether an existing metadata record for your dataset is complete.

- **What you give it:** a metadata record with any of an identifier, title, description, licence, creators and keywords.
- **What you get back:** a completeness score from 0 to 100 per cent, one finding for each of the six items saying whether it is present and how serious a gap would be, and a short plain-language summary that starts with what to add first.
- **What it will not do:** it checks that each item is filled in, not that it is correct. It does not look up your identifier or licence, does not change the record, and never says the record is ready to publish. A person still reviews it. The criteria and weights are a simple demonstration, not a community standard.
- **Use of an AI model:** by default a model writes the summary only. It is sent the record you gave and the findings. It cannot change the score or any finding, and if its summary names a DOI, ORCID iD or web address that is not in your record, the plain rule-based summary is used instead. A deployment can turn the model off, and then you get the rule-based summary.
- **When it abstains:** if the record is empty on all six items, it says there is nothing to review.

## Phase 6: Post-publication

### FAIR Assessor (`advisor.fairness`)

The FAIR Assessor checks a dataset's metadata against a short list of FAIR-related checks; for example, is the identifier a DOI, and does every creator have an ORCID iD. It is optional and advisory. It serves the "check FAIRness" and "retrofit" steps after publication, and can also give feedback on your project's draft metadata record at any time.

You give it the metadata of a published dataset or, in a project, the draft record. You get back what is already met first, a count of met checks for each of Findable, Accessible, Interoperable and Reusable, the one or two most useful next steps, and a recommendation for each check not met. For a draft it shows what is newly met since the approved version. Checks the repository fills in at deposit are left until then.

It gives no FAIR score and does not look anything up, so it cannot tell whether what you gave it is true. It changes no record.

By default it uses an AI model to tailor each recommendation; rules decide whether a check is met. The metadata you give is sent to the model, and a deployment can turn the model off, leaving standard wording. It abstains if there is no identifier or title, or no readable draft.
