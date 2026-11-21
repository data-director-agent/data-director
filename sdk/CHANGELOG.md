# Changelog

## [0.2.0-alpha.5](https://github.com/data-director-agent/data-director/compare/sdk-v0.2.0-alpha.4...sdk-v0.2.0-alpha.5) (2026-11-21)


### Features

* add project intake questions as Blueprint data ([#736](https://github.com/data-director-agent/data-director/issues/736)) ([e3c3869](https://github.com/data-director-agent/data-director/commit/e3c38696dccca4a44c9315d024e543f4a681c9e8))
* **advisor-dmp:** Read sharing commitments from an attached plan ([#1200](https://github.com/data-director-agent/data-director/issues/1200)) ([72bf7d3](https://github.com/data-director-agent/data-director/commit/72bf7d31d4a7042848e3c6e387a9c8b27cb32b64))
* **advisor-documentation:** ask the README's general information as separate questions ([#674](https://github.com/data-director-agent/data-director/issues/674)) ([9c12949](https://github.com/data-director-agent/data-director/commit/9c12949321dece45f25d6773f40a73354ee8bb79))
* **advisor-documentation:** Ask the researcher first, then write the README ([#1291](https://github.com/data-director-agent/data-director/issues/1291)) ([dcd5c6d](https://github.com/data-director-agent/data-director/commit/dcd5c6d7375daadf9018332374baf334b12b2d00))
* **advisor-documentation:** call a model by default, with structured replies ([#918](https://github.com/data-director-agent/data-director/issues/918)) ([20924d1](https://github.com/data-director-agent/data-director/commit/20924d13c613968c74a10f1a0c8e3a912f53db78))
* **advisor-metadata:** ask about every empty value and let a model suggest some ([#1049](https://github.com/data-director-agent/data-director/issues/1049)) ([0f44172](https://github.com/data-director-agent/data-director/commit/0f44172d9a08719534d3dccb9f8360d334c066f7))
* **advisor-policy:** read Jisc Open Policy Finder and let a model search and quote ([#964](https://github.com/data-director-agent/data-director/issues/964)) ([a50b2dc](https://github.com/data-director-agent/data-director/commit/a50b2dc28dc3b4d1b90612e5e1dab7de90a69e05))
* **advisor-policy:** read policies' own text and keep only quotes found in it ([#965](https://github.com/data-director-agent/data-director/issues/965)) ([dc4a0e6](https://github.com/data-director-agent/data-director/commit/dc4a0e6950613151e7c3c4ca8c8423b04ce4d5e7))
* **agents:** Make every advisor model-backed by default ([#1236](https://github.com/data-director-agent/data-director/issues/1236)) ([d8a2d4e](https://github.com/data-director-agent/data-director/commit/d8a2d4e32498eedf4bf91e19863130a6c176e487))
* **agents:** suggest drafted answers from a researcher's attached documents ([#1131](https://github.com/data-director-agent/data-director/issues/1131)) ([7ccf414](https://github.com/data-director-agent/data-director/commit/7ccf414c044c0e4eaf295bbb98731f11a5fe49d1))
* **agents:** Turn every advisor's model on by default ([#1234](https://github.com/data-director-agent/data-director/issues/1234)) ([0ecb9b4](https://github.com/data-director-agent/data-director/commit/0ecb9b45034437832bcb36d58dd558221f0f43f8))
* **app:** add your own AI account from the profile page ([#818](https://github.com/data-director-agent/data-director/issues/818)) ([ad98bfc](https://github.com/data-director-agent/data-director/commit/ad98bfc372874ca74346dafd1a8ae789afadb1d2))
* **app:** attach a supporting document to a conversation turn ([#707](https://github.com/data-director-agent/data-director/issues/707)) ([1e40b77](https://github.com/data-director-agent/data-director/commit/1e40b777d0749d54092c4b0cdc2c169eef8342b7))
* **app:** Attach Word and PDF documents, read inside the deployment ([#1183](https://github.com/data-director-agent/data-director/issues/1183)) ([1a53004](https://github.com/data-director-agent/data-director/commit/1a53004e0198e139c210112c2fcf98ebddec8d3e))
* **app:** draw each project's data journey as a map ([#1002](https://github.com/data-director-agent/data-director/issues/1002)) ([655dd6f](https://github.com/data-director-agent/data-director/commit/655dd6f7171c62a2f6178e204be8b6a2dbcd01ff))
* **app:** edit inventories to describe files and revise them ([#747](https://github.com/data-director-agent/data-director/issues/747)) ([427ffe5](https://github.com/data-director-agent/data-director/commit/427ffe588622f5c6af50334056dae7b3c6cfba41))
* **app:** let researchers rename projects and the orchestrator name untitled ones ([#678](https://github.com/data-director-agent/data-director/issues/678)) ([1c3d875](https://github.com/data-director-agent/data-director/commit/1c3d875eb0339328bb0556c1997d02ad99f117e7))
* **app:** say what to do after downloading the deposit package ([#742](https://github.com/data-director-agent/data-director/issues/742)) ([f2d9ad2](https://github.com/data-director-agent/data-director/commit/f2d9ad2b060516d979d82b347e25f5f6c8c04425))
* **app:** Show each Blueprint step's autonomy on the policy page ([#1237](https://github.com/data-director-agent/data-director/issues/1237)) ([7386a08](https://github.com/data-director-agent/data-director/commit/7386a0804711e5b76d941ac6757571c5450feffa))
* **app:** show the intake card before a new project's first turn ([#776](https://github.com/data-director-agent/data-director/issues/776)) ([9f03a8b](https://github.com/data-director-agent/data-director/commit/9f03a8b1fa2b06e66fc8ce0da9dd02481b772ed0))
* **app:** start a conversation from a step of the data journey ([#1000](https://github.com/data-director-agent/data-director/issues/1000)) ([b9265a9](https://github.com/data-director-agent/data-director/commit/b9265a9dfb9fa3f13e540cd24db3e4746ddf2568))
* **app:** start a conversation from a step of the data journey ([#1011](https://github.com/data-director-agent/data-director/issues/1011)) ([61ddce3](https://github.com/data-director-agent/data-director/commit/61ddce3221d5a6cc87587385a81f6d6c9b985ef2))
* **broker:** add the model broker service that holds people's own model keys ([#815](https://github.com/data-director-agent/data-director/issues/815)) ([ffc48a3](https://github.com/data-director-agent/data-director/commit/ffc48a37b3e1676f3ddeafcc57a0da4353af41c2))
* **broker:** forward the openai chat completions format ([#832](https://github.com/data-director-agent/data-director/issues/832)) ([#842](https://github.com/data-director-agent/data-director/issues/842)) ([d38a1bb](https://github.com/data-director-agent/data-director/commit/d38a1bb2e24442b8f8ea96b2d4cc9bd13f7af300))
* Deposit a draft to the Zenodo sandbox through its API with the researcher's account ([#1297](https://github.com/data-director-agent/data-director/issues/1297)) ([2d3cf96](https://github.com/data-director-agent/data-director/commit/2d3cf96b45505bee705242b06c26d74004c5c876))
* **harness:** carry a steward's model map in the grant ([#859](https://github.com/data-director-agent/data-director/issues/859)) ([ce17ba0](https://github.com/data-director-agent/data-director/commit/ce17ba0a1d7a21c852ba5acdc7b153a08b2e0c87))
* **harness:** emit a structured security event log ([#911](https://github.com/data-director-agent/data-director/issues/911)) ([652ca49](https://github.com/data-director-agent/data-director/commit/652ca49264ea77010c32d63e8ec5fcf05ecbb284))
* **harness:** enforce the profile's model_accounts key ([#820](https://github.com/data-director-agent/data-director/issues/820)) ([3229145](https://github.com/data-director-agent/data-director/commit/3229145163e9ccf90cdc8176417373e9ed22f05a))
* **harness:** estimate model energy and cost per run, and benchmark over PostgreSQL ([#1086](https://github.com/data-director-agent/data-director/issues/1086)) ([6ab94f2](https://github.com/data-director-agent/data-director/commit/6ab94f2c1470ba17f15b0ca2cc14f7bdb7991d90))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** Pause the deposit check for a person's decisions before packaging ([#1249](https://github.com/data-director-agent/data-director/issues/1249)) ([a497435](https://github.com/data-director-agent/data-director/commit/a497435d2d5fbd9a74d859c6fdab4543b78404d1))
* **harness:** reach MCP servers through a tool gateway ([#1146](https://github.com/data-director-agent/data-director/issues/1146)) ([611b628](https://github.com/data-director-agent/data-director/commit/611b62826fe685b2d8a173f1e7306605949b29f7))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** record intake answers and derive step states from them ([#768](https://github.com/data-director-agent/data-director/issues/768)) ([7e98d8e](https://github.com/data-director-agent/data-director/commit/7e98d8eb44d9ae7ce6bde70f65d879d051518fef))
* **harness:** refuse an agent that bypasses the model broker when own accounts are on ([#847](https://github.com/data-director-agent/data-director/issues/847)) ([7b0c630](https://github.com/data-director-agent/data-director/commit/7b0c630c59d3346642cc0f7fe4859c0923b7c5d5))
* **harness:** stream run stages, check reports and cancellation over ag-ui ([#709](https://github.com/data-director-agent/data-director/issues/709)) ([6a48a7f](https://github.com/data-director-agent/data-director/commit/6a48a7f9e210fc29d96d0e59d0b680f6fddc61e5))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **inventory:** flag possible personal data where the command finds it ([#1122](https://github.com/data-director-agent/data-director/issues/1122)) ([3901653](https://github.com/data-director-agent/data-director/commit/39016531293c04534067555da3153759307dca54))
* **inventory:** one inventory of several folders, each updated on its own ([#846](https://github.com/data-director-agent/data-director/issues/846)) ([44a27f7](https://github.com/data-director-agent/data-director/commit/44a27f7c7887c00f2e2ec874d7b25e880de677b6))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* let researchers give agents facts from their public ORCID record ([#760](https://github.com/data-director-agent/data-director/issues/760)) ([c312d78](https://github.com/data-director-agent/data-director/commit/c312d7882b157942a08ddbda905b85cad90bd6aa))
* **orchestrator:** Tell the model the kinds of files the inventory lists ([#1290](https://github.com/data-director-agent/data-director/issues/1290)) ([a15edf4](https://github.com/data-director-agent/data-director/commit/a15edf444a413b2fa26303e94f92357c6caa16de))
* own model accounts with openai and openai-compatible endpoints ([#844](https://github.com/data-director-agent/data-director/issues/844)) ([d5469df](https://github.com/data-director-agent/data-director/commit/d5469dfd4275eb3900f4a59499ff24825326f813))
* route a declared model to the one a person's own provider serves ([#880](https://github.com/data-director-agent/data-director/issues/880)) ([d55cad3](https://github.com/data-director-agent/data-director/commit/d55cad3afaf9a8cba850b6d1fe094a0e3ed77183))
* **sdk:** add a model seam that model-backed agents call ([#774](https://github.com/data-director-agent/data-director/issues/774)) ([312cc00](https://github.com/data-director-agent/data-director/commit/312cc003932fd33190390e934c415bc08572170f))
* **sdk:** follow Blueprint §8 in the intake and warn on sensitive data ([#836](https://github.com/data-director-agent/data-director/issues/836)) ([ebb8f1f](https://github.com/data-director-agent/data-director/commit/ebb8f1f300e60a0dc9fcdcbce6893758722470ea))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** load pinned agent skills into a persona's system prompt ([#1105](https://github.com/data-director-agent/data-director/issues/1105)) ([f0a5fdc](https://github.com/data-director-agent/data-director/commit/f0a5fdc8959a1bd53b175fe28a4c4982fa8e85d2))
* **sdk:** model providers beyond anthropic for the advisors ([#835](https://github.com/data-director-agent/data-director/issues/835)) ([8adfa87](https://github.com/data-director-agent/data-director/commit/8adfa870e8a277dd017f165ba16d8709ffa382ca))
* **sdk:** record the model a card declared when the model map routes a call ([#879](https://github.com/data-director-agent/data-director/issues/879)) ([351a45c](https://github.com/data-director-agent/data-director/commit/351a45c1fa2aefabcc283bb79b45c766e61b297e))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* **sdk:** Register the SPDX licence record canonicalisation ([#1186](https://github.com/data-director-agent/data-director/issues/1186)) ([6c9b6f0](https://github.com/data-director-agent/data-director/commit/6c9b6f004703694dab8c1ce18321158fe4c1a9d8))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))
* **sdk:** tool calling in the model seam, so the orchestrator runs on any provider ([#837](https://github.com/data-director-agent/data-director/issues/837)) ([d88acfc](https://github.com/data-director-agent/data-director/commit/d88acfc5f50852ad397a7f0f214b4bc77c821d75))
* Track inventory revisions and draft versions in project messages ([#1295](https://github.com/data-director-agent/data-director/issues/1295)) ([51d960f](https://github.com/data-director-agent/data-director/commit/51d960faa116c55c1da590d71c446d866f2e08c3))
* **web:** add @data-director/agent-view for agent cards and payloads ([#679](https://github.com/data-director-agent/data-director/issues/679)) ([d76df18](https://github.com/data-director-agent/data-director/commit/d76df183dca573f99527a82c95bf39341650d939))


### Bug Fixes

* **harness:** Give the orchestrator the chosen repository and decided facts ([#1209](https://github.com/data-director-agent/data-director/issues/1209)) ([34c6f67](https://github.com/data-director-agent/data-director/commit/34c6f6777d172e78ef8e2b5637beb5d0ed324c75))
* **harness:** stop A2A callers reading back other people's tasks ([#730](https://github.com/data-director-agent/data-director/issues/730)) ([6d415c6](https://github.com/data-director-agent/data-director/commit/6d415c660abb318b37d4c38798fcab0875964d2d))
* **orchestration:** record the entry point Data Director works out ([#706](https://github.com/data-director-agent/data-director/issues/706)) ([7781b37](https://github.com/data-director-agent/data-director/commit/7781b3738ba64bdda89af7d225ba0e1d4a970438))
* **sdk:** Retry a registry download the server fails ([#1177](https://github.com/data-director-agent/data-director/issues/1177)) ([2c09088](https://github.com/data-director-agent/data-director/commit/2c0908848aa8d4218cc596ed1f7135994d319fc7))


### Performance Improvements

* speed up the schema check and drop repeated work per run ([#1029](https://github.com/data-director-agent/data-director/issues/1029)) ([67dc128](https://github.com/data-director-agent/data-director/commit/67dc128af2ff5c3a756acb65325fa9a433a64a8e))


### Documentation

* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
* Encourage reusable, composable agent assets ([#1231](https://github.com/data-director-agent/data-director/issues/1231)) ([6a29033](https://github.com/data-director-agent/data-director/commit/6a290332e1290fab30da456d5532e1f36976ab25))

## [0.2.0-alpha.4](https://github.com/data-director-agent/data-director/compare/sdk-v0.2.0-alpha.3...sdk-v0.2.0-alpha.4) (2026-11-07)


### Features

* **agents:** ask the researcher about each gap in a drafted document ([#602](https://github.com/data-director-agent/data-director/issues/602)) ([bf91107](https://github.com/data-director-agent/data-director/commit/bf911077a941a6a4199d1c0b293d2d26533b4cf7))
* **agents:** draft a readme from the project's approved metadata record ([#617](https://github.com/data-director-agent/data-director/issues/617)) ([281cc59](https://github.com/data-director-agent/data-director/commit/281cc594db577a1517294e429a88b1e35f063d81))
* **agents:** suggest data dictionary definitions and units as questions ([#638](https://github.com/data-director-agent/data-director/issues/638)) ([05f1330](https://github.com/data-director-agent/data-director/commit/05f133061b033ba066088a10eed9c784a77c0228))
* **harness:** keep project documentation from hosted models unless the profile allows it ([#634](https://github.com/data-director-agent/data-director/issues/634)) ([a47d148](https://github.com/data-director-agent/data-director/commit/a47d1486706ceaa081b947fe69c3fea17d6ae02b))
* **harness:** redraft a project document as its next version ([#639](https://github.com/data-director-agent/data-director/issues/639)) ([3d40d7f](https://github.com/data-director-agent/data-director/commit/3d40d7fb16f2b0edc62ed51610c6a420f1de9273))
* track project progress from process flow logs ([#628](https://github.com/data-director-agent/data-director/issues/628)) ([fc5be95](https://github.com/data-director-agent/data-director/commit/fc5be95bdfe9a3d66c4ed023a04765199973db1a))


### Performance Improvements

* **ci:** parallelize CI jobs and improve test assertions ([#621](https://github.com/data-director-agent/data-director/issues/621)) ([c0a53da](https://github.com/data-director-agent/data-director/commit/c0a53da72790e3db30fbf98688948562b7cc7882))

## [0.2.0-alpha.3](https://github.com/data-director-agent/data-director/compare/sdk-v0.2.0-alpha.2...sdk-v0.2.0-alpha.3) (2026-11-06)


### Features

* **app:** ask categorical questions as clickable choices ([#586](https://github.com/data-director-agent/data-director/issues/586)) ([57b4e9f](https://github.com/data-director-agent/data-director/commit/57b4e9f0d7e5dedea4b9e45201de64365c04b90b))
* **app:** show the phases as a plain-language data journey ([df64bb0](https://github.com/data-director-agent/data-director/commit/df64bb0e12f13210f7a5c55d24bfd6cff55c4db5))
* **app:** show the phases as a plain-language data journey ([ab98cf6](https://github.com/data-director-agent/data-director/commit/ab98cf69959982c18ea60a76df5cdeb2146e2e42))
* **sdk:** show the data management plan steps as out of scope ([631f442](https://github.com/data-director-agent/data-director/commit/631f442c5ee6bfeb3f73813bda88ac648901df60))
* **sdk:** show the data management plan steps as out of scope ([7109c17](https://github.com/data-director-agent/data-director/commit/7109c1790d13d84cbdfe54668ad0cfc2803fb2df))

## [0.2.0-alpha.2](https://github.com/data-director-agent/data-director/compare/sdk-v0.2.0-alpha.1...sdk-v0.2.0-alpha.2) (2026-11-06)


### Features

* **app:** give each earlier conversation a title ([#542](https://github.com/data-director-agent/data-director/issues/542)) ([0202dfa](https://github.com/data-director-agent/data-director/commit/0202dfaf94cbb60f951299d138c12877600e7e2f))
* **harness:** disclose the generative AI behind each approved document ([#479](https://github.com/data-director-agent/data-director/issues/479)) ([31c0e31](https://github.com/data-director-agent/data-director/commit/31c0e31ae6465c954ecad99c91bc34e3a3193d54)), closes [#476](https://github.com/data-director-agent/data-director/issues/476)
* **sdk:** prepare every agent's built sources with one command ([#508](https://github.com/data-director-agent/data-director/issues/508)) ([3c76b2b](https://github.com/data-director-agent/data-director/commit/3c76b2ba0edb97ca58bc25910d4ac67224db0262)), closes [#507](https://github.com/data-director-agent/data-director/issues/507)

## [0.2.0-alpha.1](https://github.com/data-director-agent/data-director/compare/sdk-v0.2.0-alpha...sdk-v0.2.0-alpha.1) (2026-11-05)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.10.0; agents declaring 0.9.x are reported as incompatible until rebuilt.
* **sdk:** an agent card that declares R1 to R12 in `serves` is refused; name the steps instead.

### Features

* **agents:** draft the metadata record, README and data dictionary as project documents ([#436](https://github.com/data-director-agent/data-director/issues/436)) ([076d604](https://github.com/data-director-agent/data-director/commit/076d6047d4bb0b9f6411b5ca2755a7ab0a96f69a))
* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))
* **app:** attach a folder's inventory in the chat ([#463](https://github.com/data-director-agent/data-director/issues/463)) ([12470f8](https://github.com/data-director-agent/data-director/commit/12470f86a9c7fd7508d5e084c97f0d2895d9a573))
* **harness:** give a drafter its project's facts and record its draft ([#454](https://github.com/data-director-agent/data-director/issues/454)) ([4dba1b6](https://github.com/data-director-agent/data-director/commit/4dba1b604142acd9b9ac5c3dbe0a81441f396215))
* **harness:** record the repository a researcher chose ([#405](https://github.com/data-director-agent/data-director/issues/405)) ([6b5f52f](https://github.com/data-director-agent/data-director/commit/6b5f52f32b263dff1d101f9cfcb8bfda7a131582))
* **inventory:** inventory a dataset's files where they live ([#393](https://github.com/data-director-agent/data-director/issues/393)) ([2238ce6](https://github.com/data-director-agent/data-director/commit/2238ce657e8158931229f4339cafc83a857bbb03))
* **sdk:** add the core document payload class ([#379](https://github.com/data-director-agent/data-director/issues/379)) ([2d58112](https://github.com/data-director-agent/data-director/commit/2d581126c2fb92adfcbe9a629c5b9433ec4ae8f1))
* **sdk:** let an agent serve steps of the process flow, not requirements ([#307](https://github.com/data-director-agent/data-director/issues/307)) ([5d8a535](https://github.com/data-director-agent/data-director/commit/5d8a535900518241e1963ad0ac5deac886256314))
* **sdk:** reload an agent when its files change ([#304](https://github.com/data-director-agent/data-director/issues/304)) ([917391d](https://github.com/data-director-agent/data-director/commit/917391d07dc31d5f2709ad08808844a24d46dff7))


### Bug Fixes

* **orchestrator:** stop offering to create a data management plan ([#271](https://github.com/data-director-agent/data-director/issues/271)) ([f115f78](https://github.com/data-director-agent/data-director/commit/f115f784f556ee813768409525df9939818f6c54))


### Documentation

* **harness:** say why agent replies are not streamed ([#335](https://github.com/data-director-agent/data-director/issues/335)) ([192f24e](https://github.com/data-director-agent/data-director/commit/192f24ef4d51e211a5a03cc26d0310533dac7b56))
* replace decision records with living specs ([#434](https://github.com/data-director-agent/data-director/issues/434)) ([a19caba](https://github.com/data-director-agent/data-director/commit/a19caba60b1f1fc0049c0a68c29feb2354b97db5))

## [0.2.0-alpha](https://github.com/data-director-agent/data-director/compare/sdk-v0.1.0...sdk-v0.2.0-alpha) (2026-10-23)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.9.0; agents declaring 0.8.x are reported as incompatible.

### Features

* **agents:** a model-backed orchestrator that routes from the manifest ([#161](https://github.com/data-director-agent/data-director/issues/161)) ([021f470](https://github.com/data-director-agent/data-director/commit/021f4707cebc72310917ec4e16ff9cbdd85ce264))
* **agents:** route by the blueprint's three entry points ([#162](https://github.com/data-director-agent/data-director/issues/162)) ([92aa06a](https://github.com/data-director-agent/data-director/commit/92aa06a3dc69d11066fe6dd4c1903af956bed69a))
* **ci:** code coverage for the unit tests, with Codecov reporting and badges ([#90](https://github.com/data-director-agent/data-director/issues/90)) ([b0f611e](https://github.com/data-director-agent/data-director/commit/b0f611e1187db9d110cadb52cf791c9444e99d12))
* **harness:** verify a person's OpenID Connect identity token ([#182](https://github.com/data-director-agent/data-director/issues/182)) ([69e3ea5](https://github.com/data-director-agent/data-director/commit/69e3ea5527549adb20d8e8209788414449ed897b))
* **sdk:** a model key stays with the agent that calls the model ([#157](https://github.com/data-director-agent/data-director/issues/157)) ([a846b8f](https://github.com/data-director-agent/data-director/commit/a846b8feffdfdf87483b618e86830c79e8d4bfe3))
* **sdk:** record an authenticated principal and the issuer that vouched ([#181](https://github.com/data-director-agent/data-director/issues/181)) ([57650b3](https://github.com/data-director-agent/data-director/commit/57650b3176d6510c8580f3b3fad03ca11bc8b3eb))


### Documentation

* record why the contract is written in LinkML (ADR-0020) ([#44](https://github.com/data-director-agent/data-director/issues/44)) ([a366461](https://github.com/data-director-agent/data-director/commit/a36646154c27954f69a74694d40780930bf38663))
* separate the docs by what they describe ([#58](https://github.com/data-director-agent/data-director/issues/58)) ([#64](https://github.com/data-director-agent/data-director/issues/64)) ([b55f849](https://github.com/data-director-agent/data-director/commit/b55f849b14e0566e3fdf2ffdf7def2a0c570afb0))
