# Changelog

## [0.3.0-alpha.4](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.3...app-v0.3.0-alpha.4) (2026-10-30)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.10.0; agents declaring 0.9.x are reported as incompatible until rebuilt.
* **sdk:** an agent card that declares R1 to R12 in `serves` is refused; name the steps instead.

### Features

* **agents:** add the policy advisor for phase 2 ([#332](https://github.com/data-director-agent/data-director/issues/332)) ([1f23fb4](https://github.com/data-director-agent/data-director/commit/1f23fb4dc2c28c21d931632edc3bf339bbbc586d))
* **agents:** add the repository advisor for phase 3 ([#325](https://github.com/data-director-agent/data-director/issues/325)) ([120a8b6](https://github.com/data-director-agent/data-director/commit/120a8b6cee92965ffe30fbd80ab18c302c01fc91))
* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))
* **app:** add a favicon ([#315](https://github.com/data-director-agent/data-director/issues/315)) ([b4d54e4](https://github.com/data-director-agent/data-director/commit/b4d54e413ea1ac401be46ee293fa7353c3baa4b1))
* **app:** add Lucide icons to the action buttons ([#267](https://github.com/data-director-agent/data-director/issues/267)) ([4a5ad81](https://github.com/data-director-agent/data-director/commit/4a5ad81406b67191bd10ba772809dfa2624ab5e5))
* **app:** link to the user guide from every page ([#344](https://github.com/data-director-agent/data-director/issues/344)) ([8c6b459](https://github.com/data-director-agent/data-director/commit/8c6b4594885829955a1124c02ba075d83d7dacf1))
* **app:** send the chat message with Ctrl+Enter ([#268](https://github.com/data-director-agent/data-director/issues/268)) ([8212eb4](https://github.com/data-director-agent/data-director/commit/8212eb4c27481dfcb1b1299bfd92d0891ec12547))
* **app:** show that the orchestrator is working on a reply ([#334](https://github.com/data-director-agent/data-director/issues/334)) ([1d1ed80](https://github.com/data-director-agent/data-director/commit/1d1ed80007eb849c5414cc4d5c59bd50954870f9))
* **app:** show what powers each agent, and whether it is local or remote ([#317](https://github.com/data-director-agent/data-director/issues/317)) ([f4e7777](https://github.com/data-director-agent/data-director/commit/f4e7777b2e81fe474761569e9c17074539db2d4b))
* **app:** sign people in with ORCID and act for each of them ([#326](https://github.com/data-director-agent/data-director/issues/326)) ([4c53421](https://github.com/data-director-agent/data-director/commit/4c534212040fe3b7163a02ec28cb2023936a479f))
* **harness:** record the repository a researcher chose ([#405](https://github.com/data-director-agent/data-director/issues/405)) ([6b5f52f](https://github.com/data-director-agent/data-director/commit/6b5f52f32b263dff1d101f9cfcb8bfda7a131582))
* **inventory:** inventory a dataset's files where they live ([#393](https://github.com/data-director-agent/data-director/issues/393)) ([2238ce6](https://github.com/data-director-agent/data-director/commit/2238ce657e8158931229f4339cafc83a857bbb03))
* **sdk:** add the core document payload class ([#379](https://github.com/data-director-agent/data-director/issues/379)) ([2d58112](https://github.com/data-director-agent/data-director/commit/2d581126c2fb92adfcbe9a629c5b9433ec4ae8f1))
* **sdk:** let an agent serve steps of the process flow, not requirements ([#307](https://github.com/data-director-agent/data-director/issues/307)) ([5d8a535](https://github.com/data-director-agent/data-director/commit/5d8a535900518241e1963ad0ac5deac886256314))


### Bug Fixes

* **app:** keep a stored turn from being sent again ([#387](https://github.com/data-director-agent/data-director/issues/387)) ([925c5fb](https://github.com/data-director-agent/data-director/commit/925c5fb74ae8e3ce2cadb51d7f5f30583740da82)), closes [#337](https://github.com/data-director-agent/data-director/issues/337)
* **app:** report agents the local profile omits but the example enables ([#384](https://github.com/data-director-agent/data-director/issues/384)) ([af93775](https://github.com/data-director-agent/data-director/commit/af93775f7d480452756593a42addd7a32a5c6fbd)), closes [#343](https://github.com/data-director-agent/data-director/issues/343)
* **app:** say when the server cannot be reached and log each turn ([#339](https://github.com/data-director-agent/data-director/issues/339)) ([14cc21b](https://github.com/data-director-agent/data-director/commit/14cc21b85def850ade3c7b25bc0022fe1cc1525f)), closes [#337](https://github.com/data-director-agent/data-director/issues/337)
* **orchestrator:** stop offering to create a data management plan ([#271](https://github.com/data-director-agent/data-director/issues/271)) ([f115f78](https://github.com/data-director-agent/data-director/commit/f115f784f556ee813768409525df9939818f6c54))


### Documentation

* **adr:** decide the repository profile and the deposit package ([#386](https://github.com/data-director-agent/data-director/issues/386)) ([fd04883](https://github.com/data-director-agent/data-director/commit/fd04883f40d48509550cad74e27ead1340a9028e))
* **adr:** derive a repository's requirements from its metadata standard ([#402](https://github.com/data-director-agent/data-director/issues/402)) ([e60404f](https://github.com/data-director-agent/data-director/commit/e60404f2a3712fe03b93e6e0b1bc8f8a1929d4e7))
* **adr:** number the repository profile ADR 0038 ([#397](https://github.com/data-director-agent/data-director/issues/397)) ([eb8d193](https://github.com/data-director-agent/data-director/commit/eb8d193cf2fafb0b2379b30dcdb5ba999c27a229)), closes [#197](https://github.com/data-director-agent/data-director/issues/197)
* **app:** point local ORCID sandbox sign-in at ORCID's registration page ([#345](https://github.com/data-director-agent/data-director/issues/345)) ([520ca3e](https://github.com/data-director-agent/data-director/commit/520ca3ee4eaae8041027b9faae8ecfe7d32e9c59))

## [0.3.0-alpha.3](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.2...app-v0.3.0-alpha.3) (2026-10-28)


### Features

* **app:** a design system of tokens and styled controls ([#191](https://github.com/data-director-agent/data-director/issues/191)) ([34c1cd4](https://github.com/data-director-agent/data-director/commit/34c1cd4f1efaff48824ea6b66399035b9d0d920e))
* **app:** make the local profile optional with an example ([#227](https://github.com/data-director-agent/data-director/issues/227)) ([3f76cc3](https://github.com/data-director-agent/data-director/commit/3f76cc307b74c2d228ba832c3058bfbb7a6731c9))
* **app:** report a problem from the app ([#187](https://github.com/data-director-agent/data-director/issues/187)) ([30d8311](https://github.com/data-director-agent/data-director/commit/30d831154b5300f26e5ad9285c1315f546451aa4))
* **app:** show a delegated run's evidence inside its card ([#193](https://github.com/data-director-agent/data-director/issues/193)) ([cb36ce2](https://github.com/data-director-agent/data-director/commit/cb36ce2a466d4bae2b733a2230d241a873aaf463))
* **app:** show the deployed commit in the footer ([#230](https://github.com/data-director-agent/data-director/issues/230)) ([9378ada](https://github.com/data-director-agent/data-director/commit/9378ada19456654a69128032dbee8c3e032e26b8))
* **scripts:** add a guided setup and one-command start for development ([#228](https://github.com/data-director-agent/data-director/issues/228)) ([bc42417](https://github.com/data-director-agent/data-director/commit/bc42417a45d080377438ef579e2df7ac73c687ff))


### Bug Fixes

* **app:** read agent cards off the event loop in /api/agents ([#219](https://github.com/data-director-agent/data-director/issues/219)) ([f2bb8d8](https://github.com/data-director-agent/data-director/commit/f2bb8d8ac0e6204061d4aa2ea6f935df64d54da2))

## [0.3.0-alpha.2](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.1...app-v0.3.0-alpha.2) (2026-10-23)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.9.0; agents declaring 0.8.x are reported as incompatible.
* **app:** the app shows the standards advisor as unavailable unless dd-standards is running (scripts/run-agents.sh). A deployment must rerun deploy/install.sh, and drop any DD_AGENTS_CONFIG pointing at deploy/agents.yaml.

### Features

* **agents:** a model-backed orchestrator that routes from the manifest ([#161](https://github.com/data-director-agent/data-director/issues/161)) ([021f470](https://github.com/data-director-agent/data-director/commit/021f4707cebc72310917ec4e16ff9cbdd85ce264))
* **agents:** route by the blueprint's three entry points ([#162](https://github.com/data-director-agent/data-director/issues/162)) ([92aa06a](https://github.com/data-director-agent/data-director/commit/92aa06a3dc69d11066fe6dd4c1903af956bed69a))
* **app:** a conversation api over the conductor ([#140](https://github.com/data-director-agent/data-director/issues/140)) ([6439d01](https://github.com/data-director-agent/data-director/commit/6439d01533d0cf7faa151cb320934174153693a7)), closes [#130](https://github.com/data-director-agent/data-director/issues/130)
* **app:** a stable page frame and layered stylesheets ([#175](https://github.com/data-director-agent/data-director/issues/175)) ([519b594](https://github.com/data-director-agent/data-director/commit/519b59470acf075c1131a7d96b234a94a6ef26bc))
* **app:** a workspace around the conversation: phases, context panel and status bar ([#167](https://github.com/data-director-agent/data-director/issues/167)) ([35f91c4](https://github.com/data-director-agent/data-director/commit/35f91c4829e4f062304db3a86a71841662db8108))
* **app:** issue delegation grants so the orchestrator can run ([#139](https://github.com/data-director-agent/data-director/issues/139)) ([3ab0cf8](https://github.com/data-director-agent/data-director/commit/3ab0cf804efa7c3d61e38ec2b9b79f49500b1dc2))
* **app:** light theme by default with a dark mode switch ([#168](https://github.com/data-director-agent/data-director/issues/168)) ([aa51a0d](https://github.com/data-director-agent/data-director/commit/aa51a0dc85087c737267412e0d3602ee14f0e36d))
* **app:** make the conversation the home page ([#143](https://github.com/data-director-agent/data-director/issues/143)) ([de56976](https://github.com/data-director-agent/data-director/commit/de569760ebef8fbd1cf919d9b27c815caa3dd5ba))
* **app:** move the agent directory to its own page ([#147](https://github.com/data-director-agent/data-director/issues/147)) ([358be04](https://github.com/data-director-agent/data-director/commit/358be043c84a3ec64af45b2e41e9a2c73744b86a)), closes [#132](https://github.com/data-director-agent/data-director/issues/132)
* **app:** reach the standards advisor over a2a like every other agent ([#158](https://github.com/data-director-agent/data-director/issues/158)) ([2bab330](https://github.com/data-director-agent/data-director/commit/2bab3304b18a58e18940c8e5893006a377e3b1b0))
* **app:** register every in-tree agent ([#117](https://github.com/data-director-agent/data-director/issues/117)) ([8ab7c63](https://github.com/data-director-agent/data-director/commit/8ab7c6347a15c8c28ab2af68e85c400fc29fac71))
* **app:** render Markdown in chat replies ([#173](https://github.com/data-director-agent/data-director/issues/173)) ([1d84d29](https://github.com/data-director-agent/data-director/commit/1d84d29e10437c20e8f5893b70bf4e175b4eb429))
* **app:** show delegated runs beside the conversation ([#164](https://github.com/data-director-agent/data-director/issues/164)) ([c828dc7](https://github.com/data-director-agent/data-director/commit/c828dc7b42e5c546c6f0f405bc8c0ce82affc049)), closes [#135](https://github.com/data-director-agent/data-director/issues/135)
* **deploy:** pull-based deployment to an ubuntu vm ([#142](https://github.com/data-director-agent/data-director/issues/142)) ([7436a46](https://github.com/data-director-agent/data-director/commit/7436a46c32cf75603183acf6e34665d2c5d834d5))
* **harness:** find agents that start after the registry was built ([#165](https://github.com/data-director-agent/data-director/issues/165)) ([e4465c3](https://github.com/data-director-agent/data-director/commit/e4465c32e7457bf5eab59b393c726916a7796bc6))
* **sdk:** a model key stays with the agent that calls the model ([#157](https://github.com/data-director-agent/data-director/issues/157)) ([a846b8f](https://github.com/data-director-agent/data-director/commit/a846b8feffdfdf87483b618e86830c79e8d4bfe3))
* **sdk:** record an authenticated principal and the issuer that vouched ([#181](https://github.com/data-director-agent/data-director/issues/181)) ([57650b3](https://github.com/data-director-agent/data-director/commit/57650b3176d6510c8580f3b3fad03ca11bc8b3eb))


### Documentation

* **adr:** the app's entry point is the orchestrator conversation ([#137](https://github.com/data-director-agent/data-director/issues/137)) ([eba0ec2](https://github.com/data-director-agent/data-director/commit/eba0ec2a3bc1cee44d6f856af38d8354c0474b3b))

## [0.3.0-alpha.1](https://github.com/data-director-agent/data-director/compare/app-v0.2.0-alpha.1...app-v0.3.0-alpha.1) (2026-10-21)


### Features

* **app:** a React shell drawn from each agent's manifest, replacing Gradio (ADR-0024) ([#76](https://github.com/data-director-agent/data-director/issues/76)) ([08f13f3](https://github.com/data-director-agent/data-director/commit/08f13f3074de2caad35214d9a27b046df9c1ca1e))
* **app:** a runnable prototype: run R3, see its outcome, evidence and history ([#75](https://github.com/data-director-agent/data-director/issues/75)) ([#109](https://github.com/data-director-agent/data-director/issues/109)) ([2039d4c](https://github.com/data-director-agent/data-director/commit/2039d4c1fc96c4adddbb65dc8e75619e593c8719))
* **app:** route the app through the conductor, with its own configuration ([#63](https://github.com/data-director-agent/data-director/issues/63)) ([1ac8e53](https://github.com/data-director-agent/data-director/commit/1ac8e5354a595bb8d6d24dd99819f15e3d94223e))
* **ci:** code coverage for the unit tests, with Codecov reporting and badges ([#90](https://github.com/data-director-agent/data-director/issues/90)) ([b0f611e](https://github.com/data-director-agent/data-director/commit/b0f611e1187db9d110cadb52cf791c9444e99d12))
