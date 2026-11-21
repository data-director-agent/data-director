:robot: I have created a release *beep* *boop*
---


<details><summary>sdk: 0.2.0-alpha.5</summary>

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
</details>

<details><summary>harness: 0.2.0-alpha.5</summary>

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
</details>

<details><summary>workbench: 0.2.0-alpha.6</summary>

## [0.2.0-alpha.6](https://github.com/data-director-agent/data-director/compare/workbench-v0.2.0-alpha.5...workbench-v0.2.0-alpha.6) (2026-11-21)


### Features

* **advisor-dmp:** Evaluate reading a free-text plan's sharing commitments ([#1254](https://github.com/data-director-agent/data-director/issues/1254)) ([2cd0ddc](https://github.com/data-director-agent/data-director/commit/2cd0ddcca98df2f9aa7728fd62eafbceaa6ba3f9))
* **advisor-policy:** identify funders in ROR before searching FAIRsharing ([#848](https://github.com/data-director-agent/data-director/issues/848)) ([793dd73](https://github.com/data-director-agent/data-director/commit/793dd730419d782ad784bd230b666f39e5b1aacf))
* **advisor-policy:** read policies' own text and keep only quotes found in it ([#965](https://github.com/data-director-agent/data-director/issues/965)) ([dc4a0e6](https://github.com/data-director-agent/data-director/commit/dc4a0e6950613151e7c3c4ca8c8423b04ce4d5e7))
* Deposit a draft to the Zenodo sandbox through its API with the researcher's account ([#1297](https://github.com/data-director-agent/data-director/issues/1297)) ([2d3cf96](https://github.com/data-director-agent/data-director/commit/2d3cf96b45505bee705242b06c26d74004c5c876))
* **harness:** add pagination for listing runs and conversations ([#715](https://github.com/data-director-agent/data-director/issues/715)) ([bc3b541](https://github.com/data-director-agent/data-director/commit/bc3b5411362e31b8dae01eb13fd671bc0e55af43))
* **harness:** carry a steward's model map in the grant ([#859](https://github.com/data-director-agent/data-director/issues/859)) ([ce17ba0](https://github.com/data-director-agent/data-director/commit/ce17ba0a1d7a21c852ba5acdc7b153a08b2e0c87))
* **harness:** enforce the profile's model_accounts key ([#820](https://github.com/data-director-agent/data-director/issues/820)) ([3229145](https://github.com/data-director-agent/data-director/commit/3229145163e9ccf90cdc8176417373e9ed22f05a))
* **harness:** estimate model energy and cost per run, and benchmark over PostgreSQL ([#1086](https://github.com/data-director-agent/data-director/issues/1086)) ([6ab94f2](https://github.com/data-director-agent/data-director/commit/6ab94f2c1470ba17f15b0ca2cc14f7bdb7991d90))
* **harness:** Let a profile refuse attached documents altogether ([#1161](https://github.com/data-director-agent/data-director/issues/1161)) ([165cc9b](https://github.com/data-director-agent/data-director/commit/165cc9b2de26d6b30079794cc95c0d28066917ab))
* **harness:** reach MCP servers through a tool gateway ([#1146](https://github.com/data-director-agent/data-director/issues/1146)) ([611b628](https://github.com/data-director-agent/data-director/commit/611b62826fe685b2d8a173f1e7306605949b29f7))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** stream run stages, check reports and cancellation over ag-ui ([#709](https://github.com/data-director-agent/data-director/issues/709)) ([6a48a7f](https://github.com/data-director-agent/data-director/commit/6a48a7f9e210fc29d96d0e59d0b680f6fddc61e5))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* own model accounts with openai and openai-compatible endpoints ([#844](https://github.com/data-director-agent/data-director/issues/844)) ([d5469df](https://github.com/data-director-agent/data-director/commit/d5469dfd4275eb3900f4a59499ff24825326f813))
* route a declared model to the one a person's own provider serves ([#880](https://github.com/data-director-agent/data-director/issues/880)) ([d55cad3](https://github.com/data-director-agent/data-director/commit/d55cad3afaf9a8cba850b6d1fe094a0e3ed77183))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))


### Bug Fixes

* **advisor-repository:** Describe repositories the researcher names beside the shortlist ([#1211](https://github.com/data-director-agent/data-director/issues/1211)) ([d88ee91](https://github.com/data-director-agent/data-director/commit/d88ee91e3f9d3f1ce58f70b435a0643908274d55))
* **advisor-repository:** Describe the repository a plan names beside the shortlist ([#1235](https://github.com/data-director-agent/data-director/issues/1235)) ([96ed163](https://github.com/data-director-agent/data-director/commit/96ed16388c196d0554263ca9c2b265ec22402e99))
* **advisor-repository:** match plurals and rank the researcher's country first ([#745](https://github.com/data-director-agent/data-director/issues/745)) ([aa9b1fe](https://github.com/data-director-agent/data-director/commit/aa9b1fe5583312e7e0ac486e83a8bed303379dbc))
* small accessibility and layout fixes in the app, admin and workbench ([#997](https://github.com/data-director-agent/data-director/issues/997)) ([8c3c1ec](https://github.com/data-director-agent/data-director/commit/8c3c1ec3d19f0f16ff1bb797ff015f1db816e3e0))


### Performance Improvements

* **app:** Move blocking store reads off the event loop ([#1289](https://github.com/data-director-agent/data-director/issues/1289)) ([03acc69](https://github.com/data-director-agent/data-director/commit/03acc697bff951d4b50b4008722dd259e8f3e8b2))


### Documentation

* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
</details>

<details><summary>app: 0.3.0-alpha.9</summary>

## [0.3.0-alpha.9](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.8...app-v0.3.0-alpha.9) (2026-11-21)


### Features

* add PID resolver MCP server for DOI, ORCID, and ROR lookups ([#1263](https://github.com/data-director-agent/data-director/issues/1263)) ([1cb258b](https://github.com/data-director-agent/data-director/commit/1cb258b92905c9a1e03688838e734f4de41be8ba))
* **advisor-dmp:** Read sharing commitments from an attached plan ([#1200](https://github.com/data-director-agent/data-director/issues/1200)) ([72bf7d3](https://github.com/data-director-agent/data-director/commit/72bf7d31d4a7042848e3c6e387a9c8b27cb32b64))
* **advisor-documentation:** ask the README's general information as separate questions ([#674](https://github.com/data-director-agent/data-director/issues/674)) ([9c12949](https://github.com/data-director-agent/data-director/commit/9c12949321dece45f25d6773f40a73354ee8bb79))
* **advisor-documentation:** Ask the researcher first, then write the README ([#1291](https://github.com/data-director-agent/data-director/issues/1291)) ([dcd5c6d](https://github.com/data-director-agent/data-director/commit/dcd5c6d7375daadf9018332374baf334b12b2d00))
* **advisor-files:** mark files whose names call for a look before deposit ([#986](https://github.com/data-director-agent/data-director/issues/986)) ([01f38ce](https://github.com/data-director-agent/data-director/commit/01f38ce6673b23f97cdd0d7b37adf4e689d26316))
* **advisor-metadata:** ask about every empty value and let a model suggest some ([#1049](https://github.com/data-director-agent/data-director/issues/1049)) ([0f44172](https://github.com/data-director-agent/data-director/commit/0f44172d9a08719534d3dccb9f8360d334c066f7))
* **advisor-policy:** identify funders in ROR before searching FAIRsharing ([#848](https://github.com/data-director-agent/data-director/issues/848)) ([793dd73](https://github.com/data-director-agent/data-director/commit/793dd730419d782ad784bd230b666f39e5b1aacf))
* **advisor-policy:** read policies' own text and keep only quotes found in it ([#965](https://github.com/data-director-agent/data-director/issues/965)) ([dc4a0e6](https://github.com/data-director-agent/data-director/commit/dc4a0e6950613151e7c3c4ca8c8423b04ce4d5e7))
* **advisor-standards:** let a model choose and search FAIRsharing ([#966](https://github.com/data-director-agent/data-director/issues/966)) ([1b64081](https://github.com/data-director-agent/data-director/commit/1b640813cd115753de477169165a7bdd9bc3ae57))
* **agents:** Make every advisor model-backed by default ([#1236](https://github.com/data-director-agent/data-director/issues/1236)) ([d8a2d4e](https://github.com/data-director-agent/data-director/commit/d8a2d4e32498eedf4bf91e19863130a6c176e487))
* **agents:** Offer to continue provisionally when consent is unknown ([#1338](https://github.com/data-director-agent/data-director/issues/1338)) ([20a16b7](https://github.com/data-director-agent/data-director/commit/20a16b77d9257e0aac15bb1ba9c5e3e4bc0c6c0f))
* **agents:** suggest drafted answers from a researcher's attached documents ([#1131](https://github.com/data-director-agent/data-director/issues/1131)) ([7ccf414](https://github.com/data-director-agent/data-director/commit/7ccf414c044c0e4eaf295bbb98731f11a5fe49d1))
* **app:** add a footer crediting the University of Sheffield and the RDA ([#661](https://github.com/data-director-agent/data-director/issues/661)) ([122f4af](https://github.com/data-director-agent/data-director/commit/122f4af0791cd9f20478665422eb1b4aae6779eb))
* **app:** Add a requirement set for the NERC EIDC ([#1251](https://github.com/data-director-agent/data-director/issues/1251)) ([7b81f1c](https://github.com/data-director-agent/data-director/commit/7b81f1cae35796057a241772229946046358cc9c))
* **app:** add a settings page for the AI account and preferences ([#1138](https://github.com/data-director-agent/data-director/issues/1138)) ([9e7538f](https://github.com/data-director-agent/data-director/commit/9e7538fd036da2530a08098a72390b714a4a2757))
* **app:** Add an icon for the person in conversations ([#1165](https://github.com/data-director-agent/data-director/issues/1165)) ([d6b6561](https://github.com/data-director-agent/data-director/commit/d6b65618352f9e526a2f5316ce5f99df9996da0d))
* **app:** add an inventory from the project page and side bar ([#816](https://github.com/data-director-agent/data-director/issues/816)) ([f8345d4](https://github.com/data-director-agent/data-director/commit/f8345d47a5282708e17ea3288176d5d2c59e96ff))
* **app:** add browser-only preferences to the profile page ([#973](https://github.com/data-director-agent/data-director/issues/973)) ([5a438b2](https://github.com/data-director-agent/data-director/commit/5a438b27a4ff746917952a8d2ee374f93e0ea6dc))
* **app:** Add error pages for missing pages and failed renders ([#1197](https://github.com/data-director-agent/data-director/issues/1197)) ([4d624e0](https://github.com/data-director-agent/data-director/commit/4d624e00ecc304e49b7b327c2753bd30ad16a513))
* **app:** add project links to the footer ([#1022](https://github.com/data-director-agent/data-director/issues/1022)) ([5d5e403](https://github.com/data-director-agent/data-director/commit/5d5e403804e923f290c37a4eeac9bc1b14f3de7d))
* **app:** Add requirement sets for the other NERC EDS data centres ([#1253](https://github.com/data-director-agent/data-director/issues/1253)) ([f73ab7b](https://github.com/data-director-agent/data-director/commit/f73ab7b12f9d51c0d24d3207b3ee48376cb82e49))
* **app:** Add response models and answer the session, run and conversation routes ([#1189](https://github.com/data-director-agent/data-director/issues/1189)) ([3759620](https://github.com/data-director-agent/data-director/commit/3759620de290bff9ef776dd9a7a09f77e375068e))
* **app:** add your own AI account from the profile page ([#818](https://github.com/data-director-agent/data-director/issues/818)) ([ad98bfc](https://github.com/data-director-agent/data-director/commit/ad98bfc372874ca74346dafd1a8ae789afadb1d2))
* **app:** advise the command before describing a folder with a very large file ([#1075](https://github.com/data-director-agent/data-director/issues/1075)) ([1fd3f3c](https://github.com/data-director-agent/data-director/commit/1fd3f3cad2e04cce971dfff19c7a8d1da350741b))
* **app:** announce run progress through one polite and one assertive region ([#1026](https://github.com/data-director-agent/data-director/issues/1026)) ([d38e27c](https://github.com/data-director-agent/data-director/commit/d38e27ca9cf1275d75b819f8c193a36cb3d6c2c8))
* **app:** Answer a draft's questions on the project's documents page ([#1304](https://github.com/data-director-agent/data-director/issues/1304)) ([d8d3a43](https://github.com/data-director-agent/data-director/commit/d8d3a437939e5cf7b43be607744d997cf580eda7))
* **app:** Answer the project routes through response models ([#1190](https://github.com/data-director-agent/data-director/issues/1190)) ([ed7086a](https://github.com/data-director-agent/data-director/commit/ed7086a08529e2c81c590736a2757c965aca8b27))
* **app:** attach a supporting document to a conversation turn ([#707](https://github.com/data-director-agent/data-director/issues/707)) ([1e40b77](https://github.com/data-director-agent/data-director/commit/1e40b777d0749d54092c4b0cdc2c169eef8342b7))
* **app:** Attach Word and PDF documents, read inside the deployment ([#1183](https://github.com/data-director-agent/data-director/issues/1183)) ([1a53004](https://github.com/data-director-agent/data-director/commit/1a53004e0198e139c210112c2fcf98ebddec8d3e))
* **app:** Badge each run on the activity log and fold older runs away ([#1164](https://github.com/data-director-agent/data-director/issues/1164)) ([81bf9a2](https://github.com/data-director-agent/data-director/commit/81bf9a2ea103506ff7392a32eaebf1b4f2558d12))
* **app:** choose a repository on the project's page ([#932](https://github.com/data-director-agent/data-director/issues/932)) ([e34786c](https://github.com/data-director-agent/data-director/commit/e34786cf7d4883696a89f1f35a56ebe6cf4dbdff))
* **app:** create a project from a dialog so the intake shows first ([#916](https://github.com/data-director-agent/data-director/issues/916)) ([b04500f](https://github.com/data-director-agent/data-director/commit/b04500fe9562158191e22398fbddb978a0d7e4f5))
* **app:** create a project without a conversation (POST /api/projects) ([#805](https://github.com/data-director-agent/data-director/issues/805)) ([737a27f](https://github.com/data-director-agent/data-director/commit/737a27f3e423b58bfd91ee95b247e31f8096fd4b))
* **app:** decide the facts agents propose on the project page ([#1098](https://github.com/data-director-agent/data-director/issues/1098)) ([3cea940](https://github.com/data-director-agent/data-director/commit/3cea940f57e974c76c454b1b5d6d5e74f71a90f8))
* **app:** describe a folder in the browser to make an inventory ([#1053](https://github.com/data-director-agent/data-director/issues/1053)) ([1f74cda](https://github.com/data-director-agent/data-director/commit/1f74cda7be9825611b651bf99458e76051955d85))
* **app:** describe a folder in the browser to update an inventory ([#1116](https://github.com/data-director-agent/data-director/issues/1116)) ([b59306d](https://github.com/data-director-agent/data-director/commit/b59306d6274dbf2b96a234f7d8329c9cdcd33ceb))
* **app:** describe a folder on the server on a local install ([#1120](https://github.com/data-director-agent/data-director/issues/1120)) ([201637e](https://github.com/data-director-agent/data-director/commit/201637e7b93f14c9688321e4e58d7f627ba47890))
* **app:** draw a conversation turn live from its stream, with cancel and the activity log ([#1096](https://github.com/data-director-agent/data-director/issues/1096)) ([8596750](https://github.com/data-director-agent/data-director/commit/8596750b238e27ae5a2daca8858dd3485f0d9afa))
* **app:** draw each project's data journey as a map ([#1002](https://github.com/data-director-agent/data-director/issues/1002)) ([655dd6f](https://github.com/data-director-agent/data-director/commit/655dd6f7171c62a2f6178e204be8b6a2dbcd01ff))
* **app:** each person sees only their own runs and conversations ([#657](https://github.com/data-director-agent/data-director/issues/657)) ([17a8b75](https://github.com/data-director-agent/data-director/commit/17a8b75f8c0461f0e5bf1abd24705d34e6693faf))
* **app:** edit inventories to describe files and revise them ([#747](https://github.com/data-director-agent/data-director/issues/747)) ([427ffe5](https://github.com/data-director-agent/data-director/commit/427ffe588622f5c6af50334056dae7b3c6cfba41))
* **app:** Hold an attached document that may hold personal data or secrets ([#1149](https://github.com/data-director-agent/data-director/issues/1149)) ([75709c7](https://github.com/data-director-agent/data-director/commit/75709c7fb11829c007bfba967c1c31e6cd6690d2))
* **app:** label a sandbox deposit as not real beside the draft link ([#1337](https://github.com/data-director-agent/data-director/issues/1337)) ([b45f2d9](https://github.com/data-director-agent/data-director/commit/b45f2d97353eb5903627c58eb4392c79bc8d097e))
* **app:** label bug reports from the app as user reports ([#889](https://github.com/data-director-agent/data-director/issues/889)) ([e9a1654](https://github.com/data-director-agent/data-director/commit/e9a16545067bdf4fe1016be8b5dab26a89560920))
* **app:** let people delete and restore a conversation ([#1148](https://github.com/data-director-agent/data-director/issues/1148)) ([795864b](https://github.com/data-director-agent/data-director/commit/795864b5519d14f838516f2a63ea0b54f45cca5f))
* **app:** let researchers rename projects and the orchestrator name untitled ones ([#678](https://github.com/data-director-agent/data-director/issues/678)) ([1c3d875](https://github.com/data-director-agent/data-director/commit/1c3d875eb0339328bb0556c1997d02ad99f117e7))
* **app:** link from the conversation to the active project's details ([#687](https://github.com/data-director-agent/data-director/issues/687)) ([49fa40a](https://github.com/data-director-agent/data-director/commit/49fa40afc12c245c3be2d599d7f70f652fc7f037))
* **app:** link the banner app name to the home page ([#735](https://github.com/data-director-agent/data-director/issues/735)) ([ec52dff](https://github.com/data-director-agent/data-director/commit/ec52dff89329963cc165c5468f38dd3f3ce1ff10))
* **app:** link the footer to the operator's privacy notice ([#830](https://github.com/data-director-agent/data-director/issues/830)) ([c79ea47](https://github.com/data-director-agent/data-director/commit/c79ea47b59eeb3f0f5d350f8eeefdcbc93d592af))
* **app:** link the workflow user guide from the data journey page ([#1023](https://github.com/data-director-agent/data-director/issues/1023)) ([04c87e8](https://github.com/data-director-agent/data-director/commit/04c87e8310247476aaeb0146fff07e04b1ad7164))
* **app:** link to each provider's key page and spot a key for another provider ([#1127](https://github.com/data-director-agent/data-director/issues/1127)) ([1aec02c](https://github.com/data-director-agent/data-director/commit/1aec02cad90012b0bffb164dab2943ef4a5e507d))
* **app:** list a project's conversations on its documents page ([#934](https://github.com/data-director-agent/data-director/issues/934)) ([92a1fcd](https://github.com/data-director-agent/data-director/commit/92a1fcdcd217e91b70a7f2300f08850c89152529))
* **app:** make choice question options whole-card targets ([#672](https://github.com/data-director-agent/data-director/issues/672)) ([69b705f](https://github.com/data-director-agent/data-director/commit/69b705fca084946ab80ab0897ae3a0b3c4df1dd1))
* **app:** make the journey map reachable from the main navigation ([#1021](https://github.com/data-director-agent/data-director/issues/1021)) ([bf87e09](https://github.com/data-director-agent/data-director/commit/bf87e097c14ad38163b4cba6541615174b3ac284))
* **app:** make the transcript read as a conversation ([#1001](https://github.com/data-director-agent/data-director/issues/1001)) ([f874363](https://github.com/data-director-agent/data-director/commit/f87436362edcfbba6e245c9fc50ea1b9976e04cf))
* **app:** offer to start the conversation when the intake ends ([#959](https://github.com/data-director-agent/data-director/issues/959)) ([1f29b90](https://github.com/data-director-agent/data-director/commit/1f29b9051a0bd9b1c468174894c5bcc01d97635f))
* **app:** open make an inventory on the browser scan, with the command as a tab ([#1111](https://github.com/data-director-agent/data-director/issues/1111)) ([8191e3f](https://github.com/data-director-agent/data-director/commit/8191e3fb662d280a0611292bdc71257aa3f3ed61))
* **app:** Organise the Settings page into tabs ([#1151](https://github.com/data-director-agent/data-director/issues/1151)) ([da64337](https://github.com/data-director-agent/data-director/commit/da643372bc5e65a1582f5ba33e935f77038c8168))
* **app:** redesign the footer with University of Sheffield and RDA logos ([#985](https://github.com/data-director-agent/data-director/issues/985)) ([11a49dd](https://github.com/data-director-agent/data-director/commit/11a49dd94108c49653f370126b2017a8a1dfb2a7))
* **app:** reduce a run's AG-UI events to its state ([#957](https://github.com/data-director-agent/data-director/issues/957)) ([478d72f](https://github.com/data-director-agent/data-director/commit/478d72f56e572a744ab1a0e58d64dbcd923ad3a2))
* **app:** Remove the dark mode switch from the banner ([#1163](https://github.com/data-director-agent/data-director/issues/1163)) ([97da84a](https://github.com/data-director-agent/data-director/commit/97da84a4c7dafe101f7963c8f3eff76582e2c38d))
* **app:** replay and stream runs through the ag-ui client ([#1009](https://github.com/data-director-agent/data-director/issues/1009)) ([b38a8f6](https://github.com/data-director-agent/data-director/commit/b38a8f61b5803e22b8806ccb1180022d9163d975))
* **app:** say that an inventory describes the data, not uploads it ([#676](https://github.com/data-director-agent/data-director/issues/676)) ([426d0e3](https://github.com/data-director-agent/data-director/commit/426d0e3422ac8e3f077948ef0747022fb6a939f3))
* **app:** say what to do after downloading the deposit package ([#742](https://github.com/data-director-agent/data-director/issues/742)) ([f2d9ad2](https://github.com/data-director-agent/data-director/commit/f2d9ad2b060516d979d82b347e25f5f6c8c04425))
* **app:** Show each Blueprint step's autonomy on the policy page ([#1237](https://github.com/data-director-agent/data-director/issues/1237)) ([7386a08](https://github.com/data-director-agent/data-director/commit/7386a0804711e5b76d941ac6757571c5450feffa))
* **app:** show ORCID and GitHub marks beside their sign-in and links ([#663](https://github.com/data-director-agent/data-director/issues/663)) ([0c3e8cb](https://github.com/data-director-agent/data-director/commit/0c3e8cb37b76ec7a3a0badde724b6f99a4f0c3c4))
* **app:** show the intake card before a new project's first turn ([#776](https://github.com/data-director-agent/data-director/issues/776)) ([9f03a8b](https://github.com/data-director-agent/data-director/commit/9f03a8b1fa2b06e66fc8ce0da9dd02481b772ed0))
* **app:** show where possible personal data was found in an inventory ([#1135](https://github.com/data-director-agent/data-director/issues/1135)) ([ac3d6f2](https://github.com/data-director-agent/data-director/commit/ac3d6f214922550167ea08f28417fe4fea496929))
* **app:** start a conversation from a step of the data journey ([#1000](https://github.com/data-director-agent/data-director/issues/1000)) ([b9265a9](https://github.com/data-director-agent/data-director/commit/b9265a9dfb9fa3f13e540cd24db3e4746ddf2568))
* **app:** start a conversation from a step of the data journey ([#1011](https://github.com/data-director-agent/data-director/issues/1011)) ([61ddce3](https://github.com/data-director-agent/data-director/commit/61ddce3221d5a6cc87587385a81f6d6c9b985ef2))
* **app:** stream a conversation turn over ag-ui, with cancel ([#1005](https://github.com/data-director-agent/data-director/issues/1005)) ([e5f4a0c](https://github.com/data-director-agent/data-director/commit/e5f4a0c2607974460f4fd5b75997dd29363108d3))
* **app:** stream tool calls to the run view as the agent works ([#1273](https://github.com/data-director-agent/data-director/issues/1273)) ([54c6c65](https://github.com/data-director-agent/data-director/commit/54c6c65de35c85ff7308bd3276fe5d36ffe3a048))
* **deploy:** serve the browser scanner's bundle from the image and the vm ([#1054](https://github.com/data-director-agent/data-director/issues/1054)) ([2cb0b49](https://github.com/data-director-agent/data-director/commit/2cb0b493fd0b84cce02a7f2558dea07acb7d221e))
* Deposit a draft to the Zenodo sandbox through its API with the researcher's account ([#1297](https://github.com/data-director-agent/data-director/issues/1297)) ([2d3cf96](https://github.com/data-director-agent/data-director/commit/2d3cf96b45505bee705242b06c26d74004c5c876))
* **harness:** add pagination for listing runs and conversations ([#715](https://github.com/data-director-agent/data-director/issues/715)) ([bc3b541](https://github.com/data-director-agent/data-director/commit/bc3b5411362e31b8dae01eb13fd671bc0e55af43))
* **harness:** emit a structured security event log ([#911](https://github.com/data-director-agent/data-director/issues/911)) ([652ca49](https://github.com/data-director-agent/data-director/commit/652ca49264ea77010c32d63e8ec5fcf05ecbb284))
* **harness:** enforce the profile's model_accounts key ([#820](https://github.com/data-director-agent/data-director/issues/820)) ([3229145](https://github.com/data-director-agent/data-director/commit/3229145163e9ccf90cdc8176417373e9ed22f05a))
* **harness:** Hold each conversation's turn lock in the store ([#1160](https://github.com/data-director-agent/data-director/issues/1160)) ([0613e98](https://github.com/data-director-agent/data-director/commit/0613e980a43ff882e7270ce5d6ff1f30f6c359e9))
* **harness:** keep runs and projects in postgresql ([#708](https://github.com/data-director-agent/data-director/issues/708)) ([3436209](https://github.com/data-director-agent/data-director/commit/3436209f605a7cdcc51a9ab7ded2163391818b06))
* **harness:** Let a profile refuse attached documents altogether ([#1161](https://github.com/data-director-agent/data-director/issues/1161)) ([165cc9b](https://github.com/data-director-agent/data-director/commit/165cc9b2de26d6b30079794cc95c0d28066917ab))
* **harness:** list the projects a person may read from an index ([#724](https://github.com/data-director-agent/data-director/issues/724)) ([140db1f](https://github.com/data-director-agent/data-director/commit/140db1ff9d4b70bced5b36ad154d232dd2683d9d))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** Pause the deposit check for a person's decisions before packaging ([#1249](https://github.com/data-director-agent/data-director/issues/1249)) ([a497435](https://github.com/data-director-agent/data-director/commit/a497435d2d5fbd9a74d859c6fdab4543b78404d1))
* **harness:** reach MCP servers through a tool gateway ([#1146](https://github.com/data-director-agent/data-director/issues/1146)) ([611b628](https://github.com/data-director-agent/data-director/commit/611b62826fe685b2d8a173f1e7306605949b29f7))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** record intake answers and derive step states from them ([#768](https://github.com/data-director-agent/data-director/issues/768)) ([7e98d8e](https://github.com/data-director-agent/data-director/commit/7e98d8eb44d9ae7ce6bde70f65d879d051518fef))
* **harness:** stream run stages, check reports and cancellation over ag-ui ([#709](https://github.com/data-director-agent/data-director/issues/709)) ([6a48a7f](https://github.com/data-director-agent/data-director/commit/6a48a7f9e210fc29d96d0e59d0b680f6fddc61e5))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **inventory:** build the pyodide bundle and check it against the command ([#1048](https://github.com/data-director-agent/data-director/issues/1048)) ([21d53ab](https://github.com/data-director-agent/data-director/commit/21d53ab74213232eba79637de550342babbe1ece))
* **inventory:** flag possible personal data where the command finds it ([#1122](https://github.com/data-director-agent/data-director/issues/1122)) ([3901653](https://github.com/data-director-agent/data-director/commit/39016531293c04534067555da3153759307dca54))
* **inventory:** one inventory of several folders, each updated on its own ([#846](https://github.com/data-director-agent/data-director/issues/846)) ([44a27f7](https://github.com/data-director-agent/data-director/commit/44a27f7c7887c00f2e2ec874d7b25e880de677b6))
* **inventory:** run the command in a browser worker over a chosen folder ([#1050](https://github.com/data-director-agent/data-director/issues/1050)) ([cc4dbc6](https://github.com/data-director-agent/data-director/commit/cc4dbc6b8e1514d8c0e8f6fe1466a78467740102))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* let researchers give agents facts from their public ORCID record ([#760](https://github.com/data-director-agent/data-director/issues/760)) ([c312d78](https://github.com/data-director-agent/data-director/commit/c312d7882b157942a08ddbda905b85cad90bd6aa))
* **orchestrator:** Tell the model the kinds of files the inventory lists ([#1290](https://github.com/data-director-agent/data-director/issues/1290)) ([a15edf4](https://github.com/data-director-agent/data-director/commit/a15edf444a413b2fa26303e94f92357c6caa16de))
* own model accounts with openai and openai-compatible endpoints ([#844](https://github.com/data-director-agent/data-director/issues/844)) ([d5469df](https://github.com/data-director-agent/data-director/commit/d5469dfd4275eb3900f4a59499ff24825326f813))
* **projects:** let an owner delete and restore a project ([#951](https://github.com/data-director-agent/data-director/issues/951)) ([ee2e964](https://github.com/data-director-agent/data-director/commit/ee2e964f2fc53bad7d7dd0f6bb6ca7d393656804))
* **sdk:** follow Blueprint §8 in the intake and warn on sensitive data ([#836](https://github.com/data-director-agent/data-director/issues/836)) ([ebb8f1f](https://github.com/data-director-agent/data-director/commit/ebb8f1f300e60a0dc9fcdcbce6893758722470ea))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** load pinned agent skills into a persona's system prompt ([#1105](https://github.com/data-director-agent/data-director/issues/1105)) ([f0a5fdc](https://github.com/data-director-agent/data-director/commit/f0a5fdc8959a1bd53b175fe28a4c4982fa8e85d2))
* **sdk:** record the model a card declared when the model map routes a call ([#879](https://github.com/data-director-agent/data-director/issues/879)) ([351a45c](https://github.com/data-director-agent/data-director/commit/351a45c1fa2aefabcc283bb79b45c766e61b297e))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* Track inventory revisions and draft versions in project messages ([#1295](https://github.com/data-director-agent/data-director/issues/1295)) ([51d960f](https://github.com/data-director-agent/data-director/commit/51d960faa116c55c1da590d71c446d866f2e08c3))
* **web:** add @data-director/agent-view for agent cards and payloads ([#679](https://github.com/data-director-agent/data-director/issues/679)) ([d76df18](https://github.com/data-director-agent/data-director/commit/d76df183dca573f99527a82c95bf39341650d939))
* **web:** set the orchestrator apart on the agents page ([#660](https://github.com/data-director-agent/data-director/issues/660)) ([a7b185c](https://github.com/data-director-agent/data-director/commit/a7b185c94a5b4a6617ec66bd6e2424abb9595d18))


### Bug Fixes

* **advisor-repository:** Describe repositories the researcher names beside the shortlist ([#1211](https://github.com/data-director-agent/data-director/issues/1211)) ([d88ee91](https://github.com/data-director-agent/data-director/commit/d88ee91e3f9d3f1ce58f70b435a0643908274d55))
* **advisor-repository:** Describe the repository a plan names beside the shortlist ([#1235](https://github.com/data-director-agent/data-director/issues/1235)) ([96ed163](https://github.com/data-director-agent/data-director/commit/96ed16388c196d0554263ca9c2b265ec22402e99))
* **advisor-repository:** match plurals and rank the researcher's country first ([#745](https://github.com/data-director-agent/data-director/issues/745)) ([aa9b1fe](https://github.com/data-director-agent/data-director/commit/aa9b1fe5583312e7e0ac486e83a8bed303379dbc))
* **app:** hide HTML comments such as gap markers in rendered Markdown ([#1204](https://github.com/data-director-agent/data-director/issues/1204)) ([82ea64f](https://github.com/data-director-agent/data-director/commit/82ea64f5aeb748977f6fab4663e039e777e455d3))
* **app:** keep one rxjs copy shared with @ag-ui/client ([#1087](https://github.com/data-director-agent/data-director/issues/1087)) ([e2bb61e](https://github.com/data-director-agent/data-director/commit/e2bb61ea37a570303ec92ff08670701c06c866dd))
* **app:** keep the open conversation in the address for reload and linking ([#691](https://github.com/data-director-agent/data-director/issues/691)) ([3b91030](https://github.com/data-director-agent/data-director/commit/3b910304f889aea88f53b5be690cfd0e571b05fc))
* **app:** name and link the project a conversation's run belongs to ([#845](https://github.com/data-director-agent/data-director/issues/845)) ([0085b4b](https://github.com/data-director-agent/data-director/commit/0085b4b4b4fda5270170b40c07dd04be2e6e59a9))
* **app:** Name the repository when GitHub refuses the feedback App ([#1159](https://github.com/data-director-agent/data-director/issues/1159)) ([1c1a524](https://github.com/data-director-agent/data-director/commit/1c1a524ed7ecda810ac904cb6c5d00d59dc5ae61))
* **app:** refuse project routes to anyone without a role in the project ([#658](https://github.com/data-director-agent/data-director/issues/658)) ([9dd4c6d](https://github.com/data-director-agent/data-director/commit/9dd4c6d5da045c01b1e9fbc28cf915173b5da01e))
* **app:** Say plainly when a turn fails and offer to try again ([#1155](https://github.com/data-director-agent/data-director/issues/1155)) ([f43a78e](https://github.com/data-director-agent/data-director/commit/f43a78e2d560c18327d258b887b2ff00dee62741))
* **app:** Say which attached files were not attached and when a document is replaced ([#1205](https://github.com/data-director-agent/data-director/issues/1205)) ([8db2209](https://github.com/data-director-agent/data-director/commit/8db22095ce191846f576f466d752d4e4c7e6e6ba))
* **app:** Show the built deposit package where the person is looking ([#1340](https://github.com/data-director-agent/data-director/issues/1340)) ([c41d887](https://github.com/data-director-agent/data-director/commit/c41d887da9f28326bf5ac1b5e0672c4ab76139c4))
* **app:** show the entry point Data Director worked out on the setup card ([#909](https://github.com/data-director-agent/data-director/issues/909)) ([83e4669](https://github.com/data-director-agent/data-director/commit/83e46690d63810a1f7c837f2b29bb2001180b7ea))
* **app:** State that model-backed agents call through the broker ([#1228](https://github.com/data-director-agent/data-director/issues/1228)) ([49865eb](https://github.com/data-director-agent/data-director/commit/49865eb369ac17b2f68765f2c075c518499f5456))
* **app:** treat a gateway error on a turn as no answer ([#1018](https://github.com/data-director-agent/data-director/issues/1018)) ([d5caeda](https://github.com/data-director-agent/data-director/commit/d5caeda951690bea610716065139da5cb334bd92))
* Block /server-status endpoint from external access via NGINX ([#731](https://github.com/data-director-agent/data-director/issues/731)) ([f904f2b](https://github.com/data-director-agent/data-director/commit/f904f2b248c1544ec869ddd1132b192ed0b3c96b))
* **ci:** downgrade Node to LTS 22 and Python to 3.14 ([#722](https://github.com/data-director-agent/data-director/issues/722)) ([4b38f14](https://github.com/data-director-agent/data-director/commit/4b38f14f4f90c71838e2b01c83caf3b605d1494d))
* **deploy:** wire the harness's model-grant secrets, and test own accounts end to end ([#873](https://github.com/data-director-agent/data-director/issues/873)) ([94d22e9](https://github.com/data-director-agent/data-director/commit/94d22e9298b696b9e7ff0f552196bc8a39cf85fc))
* **harness:** Give the orchestrator the chosen repository and decided facts ([#1209](https://github.com/data-director-agent/data-director/issues/1209)) ([34c6f67](https://github.com/data-director-agent/data-director/commit/34c6f6777d172e78ef8e2b5637beb5d0ed324c75))
* **orchestration:** record the entry point Data Director works out ([#706](https://github.com/data-director-agent/data-director/issues/706)) ([7781b37](https://github.com/data-director-agent/data-director/commit/7781b3738ba64bdda89af7d225ba0e1d4a970438))
* require JSON content-type for state-changing API requests ([#732](https://github.com/data-director-agent/data-director/issues/732)) ([9311d1c](https://github.com/data-director-agent/data-director/commit/9311d1cdb4cc94e2c3a89a6801e680c8af650775))
* small accessibility and layout fixes in the app, admin and workbench ([#997](https://github.com/data-director-agent/data-director/issues/997)) ([8c3c1ec](https://github.com/data-director-agent/data-director/commit/8c3c1ec3d19f0f16ff1bb797ff015f1db816e3e0))


### Performance Improvements

* **app:** Move blocking store reads off the event loop ([#1289](https://github.com/data-director-agent/data-director/issues/1289)) ([03acc69](https://github.com/data-director-agent/data-director/commit/03acc697bff951d4b50b4008722dd259e8f3e8b2))
* **app:** scan the run store once to list projects ([#1277](https://github.com/data-director-agent/data-director/issues/1277)) ([7f1c206](https://github.com/data-director-agent/data-director/commit/7f1c206d783237a84d60ce4659f12f0ef509574a))
* **harness:** Decide what a person may read from one query ([#1262](https://github.com/data-director-agent/data-director/issues/1262)) ([916e80e](https://github.com/data-director-agent/data-director/commit/916e80e4e3f9331472f3555427293fd876368d7c))
* isolate listing routes to prevent thread starvation of turns ([#1288](https://github.com/data-director-agent/data-director/issues/1288)) ([6cfe8eb](https://github.com/data-director-agent/data-director/commit/6cfe8eb6caf0d7f8e4413f0164bc747405f62efa))


### Documentation

* **app:** stream the conversation turn, and drop the unused run form ([#998](https://github.com/data-director-agent/data-director/issues/998)) ([35ef507](https://github.com/data-director-agent/data-director/commit/35ef507b7d9792e50173ba34c50670180899bbb9))
* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
* **deposit:** specify depositing a draft through a repository's API ([#874](https://github.com/data-director-agent/data-director/issues/874)) ([3399bcc](https://github.com/data-director-agent/data-director/commit/3399bccf822ebf8d832f8ebd545f5533b3547d44))
</details>

<details><summary>admin: 0.1.0-alpha.1</summary>

## [0.1.0-alpha.1](https://github.com/data-director-agent/data-director/compare/admin-v0.1.0-alpha.0...admin-v0.1.0-alpha.1) (2026-11-21)


### Features

* **admin:** add a read-only admin service on loopback ([#781](https://github.com/data-director-agent/data-director/issues/781)) ([a98c52a](https://github.com/data-director-agent/data-director/commit/a98c52a3f1ad779acc682050ff9939ab20156c19))
* **admin:** add a spend page from the llm gateway and run telemetry ([#813](https://github.com/data-director-agent/data-director/issues/813)) ([8ba67fe](https://github.com/data-director-agent/data-director/commit/8ba67fe9c9a34796fdfce5236ca80f48a7d341a7))
* **deploy:** add data-director edit for deployment.yaml ([#1115](https://github.com/data-director-agent/data-director/issues/1115)) ([8a2a13d](https://github.com/data-director-agent/data-director/commit/8a2a13db45cbdc7a09fbae66e430dc74c6f217f8))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))


### Bug Fixes

* small accessibility and layout fixes in the app, admin and workbench ([#997](https://github.com/data-director-agent/data-director/issues/997)) ([8c3c1ec](https://github.com/data-director-agent/data-director/commit/8c3c1ec3d19f0f16ff1bb797ff015f1db816e3e0))


### Documentation

* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
</details>

<details><summary>model-broker: 0.1.0-alpha.1</summary>

## [0.1.0-alpha.1](https://github.com/data-director-agent/data-director/compare/model-broker-v0.1.0-alpha.0...model-broker-v0.1.0-alpha.1) (2026-11-21)


### Features

* **app:** add your own AI account from the profile page ([#818](https://github.com/data-director-agent/data-director/issues/818)) ([ad98bfc](https://github.com/data-director-agent/data-director/commit/ad98bfc372874ca74346dafd1a8ae789afadb1d2))
* **broker:** add the model broker service that holds people's own model keys ([#815](https://github.com/data-director-agent/data-director/issues/815)) ([ffc48a3](https://github.com/data-director-agent/data-director/commit/ffc48a37b3e1676f3ddeafcc57a0da4353af41c2))
* **broker:** forward the openai chat completions format ([#832](https://github.com/data-director-agent/data-director/issues/832)) ([#842](https://github.com/data-director-agent/data-director/issues/842)) ([d38a1bb](https://github.com/data-director-agent/data-director/commit/d38a1bb2e24442b8f8ea96b2d4cc9bd13f7af300))
* **broker:** Tag the deployment's gateway calls with the agent that made them ([#1153](https://github.com/data-director-agent/data-director/issues/1153)) ([8d6df18](https://github.com/data-director-agent/data-director/commit/8d6df18bfd7babd4650eaa595dc22accae952fc6))
* Deposit a draft to the Zenodo sandbox through its API with the researcher's account ([#1297](https://github.com/data-director-agent/data-director/issues/1297)) ([2d3cf96](https://github.com/data-director-agent/data-director/commit/2d3cf96b45505bee705242b06c26d74004c5c876))
* **harness:** carry a steward's model map in the grant ([#859](https://github.com/data-director-agent/data-director/issues/859)) ([ce17ba0](https://github.com/data-director-agent/data-director/commit/ce17ba0a1d7a21c852ba5acdc7b153a08b2e0c87))
* **harness:** emit a structured security event log ([#911](https://github.com/data-director-agent/data-director/issues/911)) ([652ca49](https://github.com/data-director-agent/data-director/commit/652ca49264ea77010c32d63e8ec5fcf05ecbb284))
* **harness:** enforce the profile's model_accounts key ([#820](https://github.com/data-director-agent/data-director/issues/820)) ([3229145](https://github.com/data-director-agent/data-director/commit/3229145163e9ccf90cdc8176417373e9ed22f05a))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* own model accounts with openai and openai-compatible endpoints ([#844](https://github.com/data-director-agent/data-director/issues/844)) ([d5469df](https://github.com/data-director-agent/data-director/commit/d5469dfd4275eb3900f4a59499ff24825326f813))
* route a declared model to the one a person's own provider serves ([#880](https://github.com/data-director-agent/data-director/issues/880)) ([d55cad3](https://github.com/data-director-agent/data-director/commit/d55cad3afaf9a8cba850b6d1fe094a0e3ed77183))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))


### Bug Fixes

* **broker:** Log the provider's status when a model call fails ([#1158](https://github.com/data-director-agent/data-director/issues/1158)) ([837c9c7](https://github.com/data-director-agent/data-director/commit/837c9c732831bf0713f0bc21d3cc5de7241a56a9))
</details>

<details><summary>deposit-broker: 0.1.0-alpha.1</summary>

## [0.1.0-alpha.1](https://github.com/data-director-agent/data-director/compare/deposit-broker-v0.1.0-alpha.0...deposit-broker-v0.1.0-alpha.1) (2026-11-21)


### Features

* Deposit a draft to the Zenodo sandbox through its API with the researcher's account ([#1297](https://github.com/data-director-agent/data-director/issues/1297)) ([2d3cf96](https://github.com/data-director-agent/data-director/commit/2d3cf96b45505bee705242b06c26d74004c5c876))
</details>

<details><summary>agent-orchestrator-stub: 0.1.1-alpha.4</summary>

## [0.1.1-alpha.4](https://github.com/data-director-agent/data-director/compare/agent-orchestrator-stub-v0.1.1-alpha.3...agent-orchestrator-stub-v0.1.1-alpha.4) (2026-11-21)


### Features

* **advisor-documentation:** Ask the researcher first, then write the README ([#1291](https://github.com/data-director-agent/data-director/issues/1291)) ([dcd5c6d](https://github.com/data-director-agent/data-director/commit/dcd5c6d7375daadf9018332374baf334b12b2d00))
* Implement entry point intake handling to skip redundant questions ([#770](https://github.com/data-director-agent/data-director/issues/770)) ([10b3483](https://github.com/data-director-agent/data-director/commit/10b3483aefdd38fd15da6b6eefcbcd8aaa646ee6))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))


### Bug Fixes

* **orchestration:** record the entry point Data Director works out ([#706](https://github.com/data-director-agent/data-director/issues/706)) ([7781b37](https://github.com/data-director-agent/data-director/commit/7781b3738ba64bdda89af7d225ba0e1d4a970438))
</details>

<details><summary>agent-orchestrator-model: 0.1.1-alpha.5</summary>

## [0.1.1-alpha.5](https://github.com/data-director-agent/data-director/compare/agent-orchestrator-model-v0.1.1-alpha.4...agent-orchestrator-model-v0.1.1-alpha.5) (2026-11-21)


### Features

* **advisor-dmp:** Read sharing commitments from an attached plan ([#1200](https://github.com/data-director-agent/data-director/issues/1200)) ([72bf7d3](https://github.com/data-director-agent/data-director/commit/72bf7d31d4a7042848e3c6e387a9c8b27cb32b64))
* **advisor-documentation:** Ask the researcher first, then write the README ([#1291](https://github.com/data-director-agent/data-director/issues/1291)) ([dcd5c6d](https://github.com/data-director-agent/data-director/commit/dcd5c6d7375daadf9018332374baf334b12b2d00))
* **agents:** Offer to continue provisionally when consent is unknown ([#1338](https://github.com/data-director-agent/data-director/issues/1338)) ([20a16b7](https://github.com/data-director-agent/data-director/commit/20a16b77d9257e0aac15bb1ba9c5e3e4bc0c6c0f))
* **agents:** suggest drafted answers from a researcher's attached documents ([#1131](https://github.com/data-director-agent/data-director/issues/1131)) ([7ccf414](https://github.com/data-director-agent/data-director/commit/7ccf414c044c0e4eaf295bbb98731f11a5fe49d1))
* **app:** let researchers rename projects and the orchestrator name untitled ones ([#678](https://github.com/data-director-agent/data-director/issues/678)) ([1c3d875](https://github.com/data-director-agent/data-director/commit/1c3d875eb0339328bb0556c1997d02ad99f117e7))
* **app:** Show each Blueprint step's autonomy on the policy page ([#1237](https://github.com/data-director-agent/data-director/issues/1237)) ([7386a08](https://github.com/data-director-agent/data-director/commit/7386a0804711e5b76d941ac6757571c5450feffa))
* **harness:** carry a steward's model map in the grant ([#859](https://github.com/data-director-agent/data-director/issues/859)) ([ce17ba0](https://github.com/data-director-agent/data-director/commit/ce17ba0a1d7a21c852ba5acdc7b153a08b2e0c87))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* Implement entry point intake handling to skip redundant questions ([#770](https://github.com/data-director-agent/data-director/issues/770)) ([10b3483](https://github.com/data-director-agent/data-director/commit/10b3483aefdd38fd15da6b6eefcbcd8aaa646ee6))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* **orchestrator:** Tell the model the kinds of files the inventory lists ([#1290](https://github.com/data-director-agent/data-director/issues/1290)) ([a15edf4](https://github.com/data-director-agent/data-director/commit/a15edf444a413b2fa26303e94f92357c6caa16de))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** model providers beyond anthropic for the advisors ([#835](https://github.com/data-director-agent/data-director/issues/835)) ([8adfa87](https://github.com/data-director-agent/data-director/commit/8adfa870e8a277dd017f165ba16d8709ffa382ca))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))
* **sdk:** tool calling in the model seam, so the orchestrator runs on any provider ([#837](https://github.com/data-director-agent/data-director/issues/837)) ([d88acfc](https://github.com/data-director-agent/data-director/commit/d88acfc5f50852ad397a7f0f214b4bc77c821d75))
* Track inventory revisions and draft versions in project messages ([#1295](https://github.com/data-director-agent/data-director/issues/1295)) ([51d960f](https://github.com/data-director-agent/data-director/commit/51d960faa116c55c1da590d71c446d866f2e08c3))


### Bug Fixes

* **advisor-repository:** Describe repositories the researcher names beside the shortlist ([#1211](https://github.com/data-director-agent/data-director/issues/1211)) ([d88ee91](https://github.com/data-director-agent/data-director/commit/d88ee91e3f9d3f1ce58f70b435a0643908274d55))
* **advisor-repository:** Describe the repository a plan names beside the shortlist ([#1235](https://github.com/data-director-agent/data-director/issues/1235)) ([96ed163](https://github.com/data-director-agent/data-director/commit/96ed16388c196d0554263ca9c2b265ec22402e99))
* **agents:** Point researchers to Edit inventory when they ask in chat to leave files out ([#1208](https://github.com/data-director-agent/data-director/issues/1208)) ([0e6fd23](https://github.com/data-director-agent/data-director/commit/0e6fd23fdacadd6cc4af0d74089809e52f7725b5))
* **harness:** Give the orchestrator the chosen repository and decided facts ([#1209](https://github.com/data-director-agent/data-director/issues/1209)) ([34c6f67](https://github.com/data-director-agent/data-director/commit/34c6f6777d172e78ef8e2b5637beb5d0ed324c75))
* **orchestration:** record the entry point Data Director works out ([#706](https://github.com/data-director-agent/data-director/issues/706)) ([7781b37](https://github.com/data-director-agent/data-director/commit/7781b3738ba64bdda89af7d225ba0e1d4a970438))


### Documentation

* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
</details>

<details><summary>agent-example-hello: 0.1.1-alpha.3</summary>

## [0.1.1-alpha.3](https://github.com/data-director-agent/data-director/compare/agent-example-hello-v0.1.1-alpha.2...agent-example-hello-v0.1.1-alpha.3) (2026-11-21)


### Features

* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))
</details>

<details><summary>agent-advisor-quality: 0.1.1-alpha.2</summary>

## [0.1.1-alpha.2](https://github.com/data-director-agent/data-director/compare/agent-advisor-quality-v0.1.1-alpha.1...agent-advisor-quality-v0.1.1-alpha.2) (2026-11-21)


### Features

* **agents:** Make every advisor model-backed by default ([#1236](https://github.com/data-director-agent/data-director/issues/1236)) ([d8a2d4e](https://github.com/data-director-agent/data-director/commit/d8a2d4e32498eedf4bf91e19863130a6c176e487))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))
</details>

<details><summary>agent-advisor-standards: 0.1.1-alpha.4</summary>

## [0.1.1-alpha.4](https://github.com/data-director-agent/data-director/compare/agent-advisor-standards-v0.1.1-alpha.3...agent-advisor-standards-v0.1.1-alpha.4) (2026-11-21)


### Features

* **advisor-dmp:** Evaluate reading a free-text plan's sharing commitments ([#1254](https://github.com/data-director-agent/data-director/issues/1254)) ([2cd0ddc](https://github.com/data-director-agent/data-director/commit/2cd0ddcca98df2f9aa7728fd62eafbceaa6ba3f9))
* **advisor-standards:** let a model choose and search FAIRsharing ([#966](https://github.com/data-director-agent/data-director/issues/966)) ([1b64081](https://github.com/data-director-agent/data-director/commit/1b640813cd115753de477169165a7bdd9bc3ae57))
* **agents:** Turn every advisor's model on by default ([#1234](https://github.com/data-director-agent/data-director/issues/1234)) ([0ecb9b4](https://github.com/data-director-agent/data-director/commit/0ecb9b45034437832bcb36d58dd558221f0f43f8))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** reach MCP servers through a tool gateway ([#1146](https://github.com/data-director-agent/data-director/issues/1146)) ([611b628](https://github.com/data-director-agent/data-director/commit/611b62826fe685b2d8a173f1e7306605949b29f7))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** model providers beyond anthropic for the advisors ([#835](https://github.com/data-director-agent/data-director/issues/835)) ([8adfa87](https://github.com/data-director-agent/data-director/commit/8adfa870e8a277dd017f165ba16d8709ffa382ca))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))
</details>

<details><summary>agent-advisor-repository: 0.1.0-alpha.3</summary>

## [0.1.0-alpha.3](https://github.com/data-director-agent/data-director/compare/agent-advisor-repository-v0.1.0-alpha.2...agent-advisor-repository-v0.1.0-alpha.3) (2026-11-21)


### Features

* **advisor-repository:** grade repositories by DFG subject and text match ([#743](https://github.com/data-director-agent/data-director/issues/743)) ([dc946bc](https://github.com/data-director-agent/data-director/commit/dc946bc3d4cc4eedee1e2b5b394478077d8e9f94))
* **agents:** Turn every advisor's model on by default ([#1234](https://github.com/data-director-agent/data-director/issues/1234)) ([0ecb9b4](https://github.com/data-director-agent/data-director/commit/0ecb9b45034437832bcb36d58dd558221f0f43f8))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** model providers beyond anthropic for the advisors ([#835](https://github.com/data-director-agent/data-director/issues/835)) ([8adfa87](https://github.com/data-director-agent/data-director/commit/8adfa870e8a277dd017f165ba16d8709ffa382ca))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))


### Bug Fixes

* **advisor-repository:** Describe repositories the researcher names beside the shortlist ([#1211](https://github.com/data-director-agent/data-director/issues/1211)) ([d88ee91](https://github.com/data-director-agent/data-director/commit/d88ee91e3f9d3f1ce58f70b435a0643908274d55))
* **advisor-repository:** Describe the repository a plan names beside the shortlist ([#1235](https://github.com/data-director-agent/data-director/issues/1235)) ([96ed163](https://github.com/data-director-agent/data-director/commit/96ed16388c196d0554263ca9c2b265ec22402e99))
* **advisor-repository:** keep a generalist place on every shortlist, chosen by rule ([#1206](https://github.com/data-director-agent/data-director/issues/1206)) ([4c7c10b](https://github.com/data-director-agent/data-director/commit/4c7c10bd3c46209dad13c850b880ab525ec340fc))
* **advisor-repository:** match plurals and rank the researcher's country first ([#745](https://github.com/data-director-agent/data-director/issues/745)) ([aa9b1fe](https://github.com/data-director-agent/data-director/commit/aa9b1fe5583312e7e0ac486e83a8bed303379dbc))
* **harness:** Give the orchestrator the chosen repository and decided facts ([#1209](https://github.com/data-director-agent/data-director/issues/1209)) ([34c6f67](https://github.com/data-director-agent/data-director/commit/34c6f6777d172e78ef8e2b5637beb5d0ed324c75))


### Documentation

* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
</details>

<details><summary>agent-advisor-policy: 0.1.0-alpha.3</summary>

## [0.1.0-alpha.3](https://github.com/data-director-agent/data-director/compare/agent-advisor-policy-v0.1.0-alpha.2...agent-advisor-policy-v0.1.0-alpha.3) (2026-11-21)


### Features

* add PID resolver MCP server for DOI, ORCID, and ROR lookups ([#1263](https://github.com/data-director-agent/data-director/issues/1263)) ([1cb258b](https://github.com/data-director-agent/data-director/commit/1cb258b92905c9a1e03688838e734f4de41be8ba))
* **advisor-policy:** identify funders in ROR before searching FAIRsharing ([#848](https://github.com/data-director-agent/data-director/issues/848)) ([793dd73](https://github.com/data-director-agent/data-director/commit/793dd730419d782ad784bd230b666f39e5b1aacf))
* **advisor-policy:** read Jisc Open Policy Finder and let a model search and quote ([#964](https://github.com/data-director-agent/data-director/issues/964)) ([a50b2dc](https://github.com/data-director-agent/data-director/commit/a50b2dc28dc3b4d1b90612e5e1dab7de90a69e05))
* **advisor-policy:** read policies' own text and keep only quotes found in it ([#965](https://github.com/data-director-agent/data-director/issues/965)) ([dc4a0e6](https://github.com/data-director-agent/data-director/commit/dc4a0e6950613151e7c3c4ca8c8423b04ce4d5e7))
* **agents:** State the policy adviser's limitations in its payload ([#1184](https://github.com/data-director-agent/data-director/issues/1184)) ([be5752f](https://github.com/data-director-agent/data-director/commit/be5752f1da15c9c00fb33ebbd73dd6beab333933))
* **agents:** Turn every advisor's model on by default ([#1234](https://github.com/data-director-agent/data-director/issues/1234)) ([0ecb9b4](https://github.com/data-director-agent/data-director/commit/0ecb9b45034437832bcb36d58dd558221f0f43f8))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** reach MCP servers through a tool gateway ([#1146](https://github.com/data-director-agent/data-director/issues/1146)) ([611b628](https://github.com/data-director-agent/data-director/commit/611b62826fe685b2d8a173f1e7306605949b29f7))
* **harness:** record facts a person decides and give them to every drafter ([#1093](https://github.com/data-director-agent/data-director/issues/1093)) ([0095d50](https://github.com/data-director-agent/data-director/commit/0095d504e36d271db318bd550ef23b6e2ce7b638))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* **sdk:** give each agent persona an emoji icon ([#1100](https://github.com/data-director-agent/data-director/issues/1100)) ([60e69dd](https://github.com/data-director-agent/data-director/commit/60e69dde27deaea1ff14d60fd1a78ac89f83e71a))
* **sdk:** model providers beyond anthropic for the advisors ([#835](https://github.com/data-director-agent/data-director/issues/835)) ([8adfa87](https://github.com/data-director-agent/data-director/commit/8adfa870e8a277dd017f165ba16d8709ffa382ca))
* **sdk:** record whose model account paid for each call ([#825](https://github.com/data-director-agent/data-director/issues/825)) ([8ce3e5d](https://github.com/data-director-agent/data-director/commit/8ce3e5da293c6086b6edc1eafc46fd34a2fcd60d))
* **sdk:** share the agent kit and add a generator for new agents ([#1016](https://github.com/data-director-agent/data-director/issues/1016)) ([31aae2c](https://github.com/data-director-agent/data-director/commit/31aae2c52dc81c9818519f626a72b8f94be8a6f4))


### Bug Fixes

* **harness:** Give the orchestrator the chosen repository and decided facts ([#1209](https://github.com/data-director-agent/data-director/issues/1209)) ([34c6f67](https://github.com/data-director-agent/data-director/commit/34c6f6777d172e78ef8e2b5637beb5d0ed324c75))


### Documentation

* **architecture:** review where complexity builds up and add ratchets to contain it ([#984](https://github.com/data-director-agent/data-director/issues/984)) ([007271a](https://github.com/data-director-agent/data-director/commit/007271ac88dadf0e8a3eb98ec3cdc2c1a7c7171f))
</details>

<details><summary>inventory: 0.1.0-alpha.5</summary>

## [0.1.0-alpha.5](https://github.com/data-director-agent/data-director/compare/inventory-v0.1.0-alpha.4...inventory-v0.1.0-alpha.5) (2026-11-21)


### Features

* **inventory:** build the pyodide bundle and check it against the command ([#1048](https://github.com/data-director-agent/data-director/issues/1048)) ([21d53ab](https://github.com/data-director-agent/data-director/commit/21d53ab74213232eba79637de550342babbe1ece))
* **inventory:** compare personal-data detectors on a synthetic evaluation set ([#1144](https://github.com/data-director-agent/data-director/issues/1144)) ([d3a0106](https://github.com/data-director-agent/data-director/commit/d3a0106a92ada10abda7842c99b731a409847b60))
* **inventory:** flag possible personal data where the command finds it ([#1122](https://github.com/data-director-agent/data-director/issues/1122)) ([3901653](https://github.com/data-director-agent/data-director/commit/39016531293c04534067555da3153759307dca54))
* **inventory:** one inventory of several folders, each updated on its own ([#846](https://github.com/data-director-agent/data-director/issues/846)) ([44a27f7](https://github.com/data-director-agent/data-director/commit/44a27f7c7887c00f2e2ec874d7b25e880de677b6))


### Bug Fixes

* Address the workshop dry-run findings in ethics, files, metadata and the inventory ([#1248](https://github.com/data-director-agent/data-director/issues/1248)) ([a76b427](https://github.com/data-director-agent/data-director/commit/a76b427355b9e12a5c6b41c828de2809f4067211))
</details>

<details><summary>mcp-pid: 0.1.0-alpha.1</summary>

## [0.1.0-alpha.1](https://github.com/data-director-agent/data-director/compare/mcp-pid-v0.1.0-alpha.0...mcp-pid-v0.1.0-alpha.1) (2026-11-21)


### Features

* add PID resolver MCP server for DOI, ORCID, and ROR lookups ([#1263](https://github.com/data-director-agent/data-director/issues/1263)) ([1cb258b](https://github.com/data-director-agent/data-director/commit/1cb258b92905c9a1e03688838e734f4de41be8ba))
</details>

---
This PR was generated with [Release Please](https://github.com/googleapis/release-please). See [documentation](https://github.com/googleapis/release-please#release-please).