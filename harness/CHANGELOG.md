# Changelog

## [0.2.0-alpha.5](https://github.com/data-director-agent/data-director/compare/harness-v0.2.0-alpha.4...harness-v0.2.0-alpha.5) (2026-11-21)


### Features

* **advisor-dmp:** Read sharing commitments from an attached plan ([#1200](https://github.com/data-director-agent/data-director/issues/1200)) ([72bf7d3](https://github.com/data-director-agent/data-director/commit/72bf7d31d4a7042848e3c6e387a9c8b27cb32b64))
* **advisor-documentation:** Ask the researcher first, then write the README ([#1291](https://github.com/data-director-agent/data-director/issues/1291)) ([dcd5c6d](https://github.com/data-director-agent/data-director/commit/dcd5c6d7375daadf9018332374baf334b12b2d00))
* **advisor-policy:** read policies' own text and keep only quotes found in it ([#965](https://github.com/data-director-agent/data-director/issues/965)) ([dc4a0e6](https://github.com/data-director-agent/data-director/commit/dc4a0e6950613151e7c3c4ca8c8423b04ce4d5e7))
* **agents:** Offer to continue provisionally when consent is unknown ([#1338](https://github.com/data-director-agent/data-director/issues/1338)) ([20a16b7](https://github.com/data-director-agent/data-director/commit/20a16b77d9257e0aac15bb1ba9c5e3e4bc0c6c0f))
* **agents:** suggest drafted answers from a researcher's attached documents ([#1131](https://github.com/data-director-agent/data-director/issues/1131)) ([7ccf414](https://github.com/data-director-agent/data-director/commit/7ccf414c044c0e4eaf295bbb98731f11a5fe49d1))
* **app:** Add a requirement set for the NERC EIDC ([#1251](https://github.com/data-director-agent/data-director/issues/1251)) ([7b81f1c](https://github.com/data-director-agent/data-director/commit/7b81f1cae35796057a241772229946046358cc9c))
* **app:** add your own AI account from the profile page ([#818](https://github.com/data-director-agent/data-director/issues/818)) ([ad98bfc](https://github.com/data-director-agent/data-director/commit/ad98bfc372874ca74346dafd1a8ae789afadb1d2))
* **app:** attach a supporting document to a conversation turn ([#707](https://github.com/data-director-agent/data-director/issues/707)) ([1e40b77](https://github.com/data-director-agent/data-director/commit/1e40b777d0749d54092c4b0cdc2c169eef8342b7))
* **app:** Attach Word and PDF documents, read inside the deployment ([#1183](https://github.com/data-director-agent/data-director/issues/1183)) ([1a53004](https://github.com/data-director-agent/data-director/commit/1a53004e0198e139c210112c2fcf98ebddec8d3e))
* **app:** choose a repository on the project's page ([#932](https://github.com/data-director-agent/data-director/issues/932)) ([e34786c](https://github.com/data-director-agent/data-director/commit/e34786cf7d4883696a89f1f35a56ebe6cf4dbdff))
* **app:** draw each project's data journey as a map ([#1002](https://github.com/data-director-agent/data-director/issues/1002)) ([655dd6f](https://github.com/data-director-agent/data-director/commit/655dd6f7171c62a2f6178e204be8b6a2dbcd01ff))
* **app:** each person sees only their own runs and conversations ([#657](https://github.com/data-director-agent/data-director/issues/657)) ([17a8b75](https://github.com/data-director-agent/data-director/commit/17a8b75f8c0461f0e5bf1abd24705d34e6693faf))
* **app:** edit inventories to describe files and revise them ([#747](https://github.com/data-director-agent/data-director/issues/747)) ([427ffe5](https://github.com/data-director-agent/data-director/commit/427ffe588622f5c6af50334056dae7b3c6cfba41))
* **app:** let people delete and restore a conversation ([#1148](https://github.com/data-director-agent/data-director/issues/1148)) ([795864b](https://github.com/data-director-agent/data-director/commit/795864b5519d14f838516f2a63ea0b54f45cca5f))
* **app:** let researchers rename projects and the orchestrator name untitled ones ([#678](https://github.com/data-director-agent/data-director/issues/678)) ([1c3d875](https://github.com/data-director-agent/data-director/commit/1c3d875eb0339328bb0556c1997d02ad99f117e7))
* **app:** say what to do after downloading the deposit package ([#742](https://github.com/data-director-agent/data-director/issues/742)) ([f2d9ad2](https://github.com/data-director-agent/data-director/commit/f2d9ad2b060516d979d82b347e25f5f6c8c04425))
* **app:** show the intake card before a new project's first turn ([#776](https://github.com/data-director-agent/data-director/issues/776)) ([9f03a8b](https://github.com/data-director-agent/data-director/commit/9f03a8b1fa2b06e66fc8ce0da9dd02481b772ed0))
* **app:** stream a conversation turn over ag-ui, with cancel ([#1005](https://github.com/data-director-agent/data-director/issues/1005)) ([e5f4a0c](https://github.com/data-director-agent/data-director/commit/e5f4a0c2607974460f4fd5b75997dd29363108d3))
* **app:** stream tool calls to the run view as the agent works ([#1273](https://github.com/data-director-agent/data-director/issues/1273)) ([54c6c65](https://github.com/data-director-agent/data-director/commit/54c6c65de35c85ff7308bd3276fe5d36ffe3a048))
* Deposit a draft to the Zenodo sandbox through its API with the researcher's account ([#1297](https://github.com/data-director-agent/data-director/issues/1297)) ([2d3cf96](https://github.com/data-director-agent/data-director/commit/2d3cf96b45505bee705242b06c26d74004c5c876))
* **dev:** keep runs and projects in postgresql in the compose stack ([#711](https://github.com/data-director-agent/data-director/issues/711)) ([5a4bc65](https://github.com/data-director-agent/data-director/commit/5a4bc65b112ea0621b05a59bf9413726965ae48d))
* **harness:** add pagination for listing runs and conversations ([#715](https://github.com/data-director-agent/data-director/issues/715)) ([bc3b541](https://github.com/data-director-agent/data-director/commit/bc3b5411362e31b8dae01eb13fd671bc0e55af43))
* **harness:** carry a steward's model map in the grant ([#859](https://github.com/data-director-agent/data-director/issues/859)) ([ce17ba0](https://github.com/data-director-agent/data-director/commit/ce17ba0a1d7a21c852ba5acdc7b153a08b2e0c87))
* **harness:** emit a structured security event log ([#911](https://github.com/data-director-agent/data-director/issues/911)) ([652ca49](https://github.com/data-director-agent/data-director/commit/652ca49264ea77010c32d63e8ec5fcf05ecbb284))
* **harness:** enforce the profile's model_accounts key ([#820](https://github.com/data-director-agent/data-director/issues/820)) ([3229145](https://github.com/data-director-agent/data-director/commit/3229145163e9ccf90cdc8176417373e9ed22f05a))
* **harness:** estimate model energy and cost per run, and benchmark over PostgreSQL ([#1086](https://github.com/data-director-agent/data-director/issues/1086)) ([6ab94f2](https://github.com/data-director-agent/data-director/commit/6ab94f2c1470ba17f15b0ca2cc14f7bdb7991d90))
* **harness:** Hold each conversation's turn lock in the store ([#1160](https://github.com/data-director-agent/data-director/issues/1160)) ([0613e98](https://github.com/data-director-agent/data-director/commit/0613e980a43ff882e7270ce5d6ff1f30f6c359e9))
* **harness:** keep runs and projects in postgresql ([#708](https://github.com/data-director-agent/data-director/issues/708)) ([3436209](https://github.com/data-director-agent/data-director/commit/3436209f605a7cdcc51a9ab7ded2163391818b06))
* **harness:** Let a profile refuse attached documents altogether ([#1161](https://github.com/data-director-agent/data-director/issues/1161)) ([165cc9b](https://github.com/data-director-agent/data-director/commit/165cc9b2de26d6b30079794cc95c0d28066917ab))
* **harness:** list the projects a person may read from an index ([#724](https://github.com/data-director-agent/data-director/issues/724)) ([140db1f](https://github.com/data-director-agent/data-director/commit/140db1ff9d4b70bced5b36ad154d232dd2683d9d))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** Pause the deposit check for a person's decisions before packaging ([#1249](https://github.com/data-director-agent/data-director/issues/1249)) ([a497435](https://github.com/data-director-agent/data-director/commit/a497435d2d5fbd9a74d859c6fdab4543b78404d1))
* **harness:** reach MCP servers through a tool gateway ([#1146](https://github.com/data-director-agent/data-director/issues/1146)) ([611b628](https://github.com/data-director-agent/data-director/commit/611b62826fe685b2d8a173f1e7306605949b29f7))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** record intake answers and derive step states from them ([#768](https://github.com/data-director-agent/data-director/issues/768)) ([7e98d8e](https://github.com/data-director-agent/data-director/commit/7e98d8eb44d9ae7ce6bde70f65d879d051518fef))
* **harness:** refuse an agent that bypasses the model broker when own accounts are on ([#847](https://github.com/data-director-agent/data-director/issues/847)) ([7b0c630](https://github.com/data-director-agent/data-director/commit/7b0c630c59d3346642cc0f7fe4859c0923b7c5d5))
* **harness:** stream run stages, check reports and cancellation over ag-ui ([#709](https://github.com/data-director-agent/data-director/issues/709)) ([6a48a7f](https://github.com/data-director-agent/data-director/commit/6a48a7f9e210fc29d96d0e59d0b680f6fddc61e5))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **inventory:** one inventory of several folders, each updated on its own ([#846](https://github.com/data-director-agent/data-director/issues/846)) ([44a27f7](https://github.com/data-director-agent/data-director/commit/44a27f7c7887c00f2e2ec874d7b25e880de677b6))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* let researchers give agents facts from their public ORCID record ([#760](https://github.com/data-director-agent/data-director/issues/760)) ([c312d78](https://github.com/data-director-agent/data-director/commit/c312d7882b157942a08ddbda905b85cad90bd6aa))
* **orchestrator:** Tell the model the kinds of files the inventory lists ([#1290](https://github.com/data-director-agent/data-director/issues/1290)) ([a15edf4](https://github.com/data-director-agent/data-director/commit/a15edf444a413b2fa26303e94f92357c6caa16de))
* own model accounts with openai and openai-compatible endpoints ([#844](https://github.com/data-director-agent/data-director/issues/844)) ([d5469df](https://github.com/data-director-agent/data-director/commit/d5469dfd4275eb3900f4a59499ff24825326f813))
* **projects:** let an owner delete and restore a project ([#951](https://github.com/data-director-agent/data-director/issues/951)) ([ee2e964](https://github.com/data-director-agent/data-director/commit/ee2e964f2fc53bad7d7dd0f6bb6ca7d393656804))
* **sdk:** follow Blueprint §8 in the intake and warn on sensitive data ([#836](https://github.com/data-director-agent/data-director/issues/836)) ([ebb8f1f](https://github.com/data-director-agent/data-director/commit/ebb8f1f300e60a0dc9fcdcbce6893758722470ea))
* **sdk:** record the model a card declared when the model map routes a call ([#879](https://github.com/data-director-agent/data-director/issues/879)) ([351a45c](https://github.com/data-director-agent/data-director/commit/351a45c1fa2aefabcc283bb79b45c766e61b297e))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))
* Track inventory revisions and draft versions in project messages ([#1295](https://github.com/data-director-agent/data-director/issues/1295)) ([51d960f](https://github.com/data-director-agent/data-director/commit/51d960faa116c55c1da590d71c446d866f2e08c3))


### Bug Fixes

* **app:** refuse project routes to anyone without a role in the project ([#658](https://github.com/data-director-agent/data-director/issues/658)) ([9dd4c6d](https://github.com/data-director-agent/data-director/commit/9dd4c6d5da045c01b1e9fbc28cf915173b5da01e))
* **app:** Say plainly when a turn fails and offer to try again ([#1155](https://github.com/data-director-agent/data-director/issues/1155)) ([f43a78e](https://github.com/data-director-agent/data-director/commit/f43a78e2d560c18327d258b887b2ff00dee62741))
* **harness:** Give the orchestrator the chosen repository and decided facts ([#1209](https://github.com/data-director-agent/data-director/issues/1209)) ([34c6f67](https://github.com/data-director-agent/data-director/commit/34c6f6777d172e78ef8e2b5637beb5d0ed324c75))
* **harness:** record a refusal before raising and find conversations started elsewhere ([#666](https://github.com/data-director-agent/data-director/issues/666)) ([f00c9b9](https://github.com/data-director-agent/data-director/commit/f00c9b92d8f31757e655817e0f3f960e92551671))
* **harness:** stop A2A callers reading back other people's tasks ([#730](https://github.com/data-director-agent/data-director/issues/730)) ([6d415c6](https://github.com/data-director-agent/data-director/commit/6d415c660abb318b37d4c38798fcab0875964d2d))
* **orchestration:** record the entry point Data Director works out ([#706](https://github.com/data-director-agent/data-director/issues/706)) ([7781b37](https://github.com/data-director-agent/data-director/commit/7781b3738ba64bdda89af7d225ba0e1d4a970438))


### Performance Improvements

* **app:** Move blocking store reads off the event loop ([#1289](https://github.com/data-director-agent/data-director/issues/1289)) ([03acc69](https://github.com/data-director-agent/data-director/commit/03acc697bff951d4b50b4008722dd259e8f3e8b2))
* **app:** scan the run store once to list projects ([#1277](https://github.com/data-director-agent/data-director/issues/1277)) ([7f1c206](https://github.com/data-director-agent/data-director/commit/7f1c206d783237a84d60ce4659f12f0ef509574a))
* **harness:** Decide what a person may read from one query ([#1262](https://github.com/data-director-agent/data-director/issues/1262)) ([916e80e](https://github.com/data-director-agent/data-director/commit/916e80e4e3f9331472f3555427293fd876368d7c))
* **harness:** pool connections in the postgresql backend ([#729](https://github.com/data-director-agent/data-director/issues/729)) ([b416706](https://github.com/data-director-agent/data-director/commit/b416706f81e0a65c7a32c7fc2af6a576d69540f2))
* **harness:** read a project's facts from one snapshot per invocation ([#1045](https://github.com/data-director-agent/data-director/issues/1045)) ([a7209f2](https://github.com/data-director-agent/data-director/commit/a7209f2ea0308ae77b752955b68106a9233769a3))
* **harness:** skip the Postgres borrow check; write a run's artifacts in one transaction ([#1278](https://github.com/data-director-agent/data-director/issues/1278)) ([fdeeb42](https://github.com/data-director-agent/data-director/commit/fdeeb42a7a841d32a48e04782551d1f0b1209420))
* speed up the schema check and drop repeated work per run ([#1029](https://github.com/data-director-agent/data-director/issues/1029)) ([67dc128](https://github.com/data-director-agent/data-director/commit/67dc128af2ff5c3a756acb65325fa9a433a64a8e))


### Documentation

* **agents:** tell coding agents that policy lives in the institutional profile ([#942](https://github.com/data-director-agent/data-director/issues/942)) ([b6f9e04](https://github.com/data-director-agent/data-director/commit/b6f9e046c2fee5bb562549fa37e4b31d9eef6f11))
* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
* **loadtest:** Record the list routes' cost after reading readability in one query ([#1272](https://github.com/data-director-agent/data-director/issues/1272)) ([5982798](https://github.com/data-director-agent/data-director/commit/598279804125d8b6c768815eecf82135451578db))
* **specs:** choose postgresql as the record for runs and projects ([#653](https://github.com/data-director-agent/data-director/issues/653)) ([6a47870](https://github.com/data-director-agent/data-director/commit/6a47870a2dfe01713b0b370418d25c0dade4515d))
* **specs:** settle a second identity provider and the principal it names ([#943](https://github.com/data-director-agent/data-director/issues/943)) ([9ea6fb3](https://github.com/data-director-agent/data-director/commit/9ea6fb31736b38bac713d17f743042ae120b2494))

## [0.2.0-alpha.4](https://github.com/data-director-agent/data-director/compare/harness-v0.2.0-alpha.3...harness-v0.2.0-alpha.4) (2026-11-07)


### Features

* **agents:** ask the researcher about each gap in a drafted document ([#602](https://github.com/data-director-agent/data-director/issues/602)) ([bf91107](https://github.com/data-director-agent/data-director/commit/bf911077a941a6a4199d1c0b293d2d26533b4cf7))
* **agents:** draft a readme from the project's approved metadata record ([#617](https://github.com/data-director-agent/data-director/issues/617)) ([281cc59](https://github.com/data-director-agent/data-director/commit/281cc594db577a1517294e429a88b1e35f063d81))
* **agents:** lead the loop from the files to a package with both orchestrators ([#630](https://github.com/data-director-agent/data-director/issues/630)) ([22f22e2](https://github.com/data-director-agent/data-director/commit/22f22e2f43f9c582fbcb58e5442dd5ad187a5c1f))
* **agents:** write readme prose with a model and answer drafter questions ([#627](https://github.com/data-director-agent/data-director/issues/627)) ([764d6ea](https://github.com/data-director-agent/data-director/commit/764d6ea3393ab54eb53843912ea0423fb9f22747))
* **app:** validate a project and download its deposit package ([#636](https://github.com/data-director-agent/data-director/issues/636)) ([a4e9dce](https://github.com/data-director-agent/data-director/commit/a4e9dce1169f8bca09edc43f63be54ef31e6911b))
* **harness:** implement project validation and deposit package building ([#625](https://github.com/data-director-agent/data-director/issues/625)) ([529fea5](https://github.com/data-director-agent/data-director/commit/529fea59de999f95dbf8a75bb4c69f5c402ea388))
* **harness:** keep project documentation from hosted models unless the profile allows it ([#634](https://github.com/data-director-agent/data-director/issues/634)) ([a47d148](https://github.com/data-director-agent/data-director/commit/a47d1486706ceaa081b947fe69c3fea17d6ae02b))
* **harness:** redraft a project document as its next version ([#639](https://github.com/data-director-agent/data-director/issues/639)) ([3d40d7f](https://github.com/data-director-agent/data-director/commit/3d40d7fb16f2b0edc62ed51610c6a420f1de9273))
* **harness:** resolve a chosen repository from the pinned re3data export ([#633](https://github.com/data-director-agent/data-director/issues/633)) ([6a5d862](https://github.com/data-director-agent/data-director/commit/6a5d862f158f61031adceddd7741bbc8a4e1b3ee))
* track project progress from process flow logs ([#628](https://github.com/data-director-agent/data-director/issues/628)) ([fc5be95](https://github.com/data-director-agent/data-director/commit/fc5be95bdfe9a3d66c4ed023a04765199973db1a))


### Documentation

* point follow-up markers at [#631](https://github.com/data-director-agent/data-director/issues/631) and [#632](https://github.com/data-director-agent/data-director/issues/632) ([#635](https://github.com/data-director-agent/data-director/issues/635)) ([8bf763a](https://github.com/data-director-agent/data-director/commit/8bf763a2b70bd73ed1324609c3c3d123cbe4bb1b))
* split AGENTS.md by package and say "harness", not "workbench" ([#626](https://github.com/data-director-agent/data-director/issues/626)) ([5336385](https://github.com/data-director-agent/data-director/commit/5336385430e05c4dd2be27152620f3a48a453dbb))

## [0.2.0-alpha.3](https://github.com/data-director-agent/data-director/compare/harness-v0.2.0-alpha.2...harness-v0.2.0-alpha.3) (2026-11-06)


### Features

* **app:** add a policy page that shows the rules runs are held to ([2b76eb6](https://github.com/data-director-agent/data-director/commit/2b76eb60e1aebf23211f34f526098068260805c6))
* **app:** add a policy page that shows the rules runs are held to ([40cbdb5](https://github.com/data-director-agent/data-director/commit/40cbdb511a7103f5c8527b04c163cd3176f00f64))
* **app:** ask categorical questions as clickable choices ([#586](https://github.com/data-director-agent/data-director/issues/586)) ([57b4e9f](https://github.com/data-director-agent/data-director/commit/57b4e9f0d7e5dedea4b9e45201de64365c04b90b))

## [0.2.0-alpha.2](https://github.com/data-director-agent/data-director/compare/harness-v0.2.0-alpha.1...harness-v0.2.0-alpha.2) (2026-11-06)


### Features

* **agents:** search every re3data repository from a pinned monthly export ([#489](https://github.com/data-director-agent/data-director/issues/489)) ([4a05699](https://github.com/data-director-agent/data-director/commit/4a056996f5ef9611cd97a03722dfdc38f67ab1b9))
* **app:** give each earlier conversation a title ([#542](https://github.com/data-director-agent/data-director/issues/542)) ([0202dfa](https://github.com/data-director-agent/data-director/commit/0202dfaf94cbb60f951299d138c12877600e7e2f))
* **harness:** disclose the generative AI behind each approved document ([#479](https://github.com/data-director-agent/data-director/issues/479)) ([31c0e31](https://github.com/data-director-agent/data-director/commit/31c0e31ae6465c954ecad99c91bc34e3a3193d54)), closes [#476](https://github.com/data-director-agent/data-director/issues/476)
* **sdk:** prepare every agent's built sources with one command ([#508](https://github.com/data-director-agent/data-director/issues/508)) ([3c76b2b](https://github.com/data-director-agent/data-director/commit/3c76b2ba0edb97ca58bc25910d4ac67224db0262)), closes [#507](https://github.com/data-director-agent/data-director/issues/507)
* **workbench:** serve the workbench on the VM to admins signed in with ORCID ([#563](https://github.com/data-director-agent/data-director/issues/563)) ([e1739ed](https://github.com/data-director-agent/data-director/commit/e1739edad10ede33e23091128f42694c4ca69faa)), closes [#549](https://github.com/data-director-agent/data-director/issues/549)

## [0.2.0-alpha.1](https://github.com/data-director-agent/data-director/compare/harness-v0.2.0-alpha...harness-v0.2.0-alpha.1) (2026-11-05)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.10.0; agents declaring 0.9.x are reported as incompatible until rebuilt.

### Features

* **agents:** add the policy advisor for phase 2 ([#332](https://github.com/data-director-agent/data-director/issues/332)) ([1f23fb4](https://github.com/data-director-agent/data-director/commit/1f23fb4dc2c28c21d931632edc3bf339bbbc586d))
* **agents:** add the repository advisor for phase 3 ([#325](https://github.com/data-director-agent/data-director/issues/325)) ([120a8b6](https://github.com/data-director-agent/data-director/commit/120a8b6cee92965ffe30fbd80ab18c302c01fc91))
* **agents:** draft the metadata record, README and data dictionary as project documents ([#436](https://github.com/data-director-agent/data-director/issues/436)) ([076d604](https://github.com/data-director-agent/data-director/commit/076d6047d4bb0b9f6411b5ca2755a7ab0a96f69a))
* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))
* **app:** approve, edit or reject a proposed document ([#437](https://github.com/data-director-agent/data-director/issues/437)) ([e3ea354](https://github.com/data-director-agent/data-director/commit/e3ea354b621d442c838490ea6d723760fd5d6aa2))
* **app:** attach a folder's inventory in the chat ([#463](https://github.com/data-director-agent/data-director/issues/463)) ([12470f8](https://github.com/data-director-agent/data-director/commit/12470f86a9c7fd7508d5e084c97f0d2895d9a573))
* **app:** sign people in with ORCID and act for each of them ([#326](https://github.com/data-director-agent/data-director/issues/326)) ([4c53421](https://github.com/data-director-agent/data-director/commit/4c534212040fe3b7163a02ec28cb2023936a479f))
* **harness:** give a drafter its project's facts and record its draft ([#454](https://github.com/data-director-agent/data-director/issues/454)) ([4dba1b6](https://github.com/data-director-agent/data-director/commit/4dba1b604142acd9b9ac5c3dbe0a81441f396215))
* **harness:** hold a project's record and its inventory ([#396](https://github.com/data-director-agent/data-director/issues/396)) ([daa5733](https://github.com/data-director-agent/data-director/commit/daa57338c87697345a891056de63f8b84ecb4259))
* **harness:** name a project and record the conversations started in it ([#453](https://github.com/data-director-agent/data-director/issues/453)) ([d314939](https://github.com/data-director-agent/data-director/commit/d314939d73be444b9cdcfeca883d16ebbe535b8f)), closes [#444](https://github.com/data-director-agent/data-director/issues/444)
* **harness:** record the repository a researcher chose ([#405](https://github.com/data-director-agent/data-director/issues/405)) ([6b5f52f](https://github.com/data-director-agent/data-director/commit/6b5f52f32b263dff1d101f9cfcb8bfda7a131582))
* **sdk:** add the core document payload class ([#379](https://github.com/data-director-agent/data-director/issues/379)) ([2d58112](https://github.com/data-director-agent/data-director/commit/2d581126c2fb92adfcbe9a629c5b9433ec4ae8f1))


### Documentation

* **harness:** say why agent replies are not streamed ([#335](https://github.com/data-director-agent/data-director/issues/335)) ([192f24e](https://github.com/data-director-agent/data-director/commit/192f24ef4d51e211a5a03cc26d0310533dac7b56))
* replace decision records with living specs ([#434](https://github.com/data-director-agent/data-director/issues/434)) ([a19caba](https://github.com/data-director-agent/data-director/commit/a19caba60b1f1fc0049c0a68c29feb2354b97db5))

## [0.2.0-alpha](https://github.com/data-director-agent/data-director/compare/harness-v0.1.0...harness-v0.2.0-alpha) (2026-10-23)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.9.0; agents declaring 0.8.x are reported as incompatible.
* **app:** the app shows the standards advisor as unavailable unless dd-standards is running (scripts/run-agents.sh). A deployment must rerun deploy/install.sh, and drop any DD_AGENTS_CONFIG pointing at deploy/agents.yaml.

### Features

* **agents:** a model-backed orchestrator that routes from the manifest ([#161](https://github.com/data-director-agent/data-director/issues/161)) ([021f470](https://github.com/data-director-agent/data-director/commit/021f4707cebc72310917ec4e16ff9cbdd85ce264))
* **app:** issue delegation grants so the orchestrator can run ([#139](https://github.com/data-director-agent/data-director/issues/139)) ([3ab0cf8](https://github.com/data-director-agent/data-director/commit/3ab0cf804efa7c3d61e38ec2b9b79f49500b1dc2))
* **app:** reach the standards advisor over a2a like every other agent ([#158](https://github.com/data-director-agent/data-director/issues/158)) ([2bab330](https://github.com/data-director-agent/data-director/commit/2bab3304b18a58e18940c8e5893006a377e3b1b0))
* **app:** route the app through the conductor, with its own configuration ([#63](https://github.com/data-director-agent/data-director/issues/63)) ([1ac8e53](https://github.com/data-director-agent/data-director/commit/1ac8e5354a595bb8d6d24dd99819f15e3d94223e))
* **ci:** code coverage for the unit tests, with Codecov reporting and badges ([#90](https://github.com/data-director-agent/data-director/issues/90)) ([b0f611e](https://github.com/data-director-agent/data-director/commit/b0f611e1187db9d110cadb52cf791c9444e99d12))
* **harness:** a standalone A2A server for deployments ([#55](https://github.com/data-director-agent/data-director/issues/55)) ([#65](https://github.com/data-director-agent/data-director/issues/65)) ([9fa54fa](https://github.com/data-director-agent/data-director/commit/9fa54fa7e75ec1dae88234c27e0966c947105e80))
* **harness:** a test kit of its own, so harness tests leave workbench/tests ([#62](https://github.com/data-director-agent/data-director/issues/62)) ([bf72812](https://github.com/data-director-agent/data-director/commit/bf728125bd42d20865eaff903daa0370f7b94e48)), closes [#56](https://github.com/data-director-agent/data-director/issues/56)
* **harness:** find agents that start after the registry was built ([#165](https://github.com/data-director-agent/data-director/issues/165)) ([e4465c3](https://github.com/data-director-agent/data-director/commit/e4465c32e7457bf5eab59b393c726916a7796bc6))
* **harness:** verify a person's OpenID Connect identity token ([#182](https://github.com/data-director-agent/data-director/issues/182)) ([69e3ea5](https://github.com/data-director-agent/data-director/commit/69e3ea5527549adb20d8e8209788414449ed897b))
* **sdk:** a model key stays with the agent that calls the model ([#157](https://github.com/data-director-agent/data-director/issues/157)) ([a846b8f](https://github.com/data-director-agent/data-director/commit/a846b8feffdfdf87483b618e86830c79e8d4bfe3))
* **sdk:** record an authenticated principal and the issuer that vouched ([#181](https://github.com/data-director-agent/data-director/issues/181)) ([57650b3](https://github.com/data-director-agent/data-director/commit/57650b3176d6510c8580f3b3fad03ca11bc8b3eb))


### Documentation

* **adr:** sign people in with ORCID through OpenID Connect ([#180](https://github.com/data-director-agent/data-director/issues/180)) ([cf633e7](https://github.com/data-director-agent/data-director/commit/cf633e7724627875243d2b19baee6d941f6fdfdd))
* separate the docs by what they describe ([#58](https://github.com/data-director-agent/data-director/issues/58)) ([#64](https://github.com/data-director-agent/data-director/issues/64)) ([b55f849](https://github.com/data-director-agent/data-director/commit/b55f849b14e0566e3fdf2ffdf7def2a0c570afb0))
