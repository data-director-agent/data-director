# Changelog

## [0.2.0-alpha.2](https://github.com/data-director-agent/data-director/compare/workbench-v0.2.0-alpha.1...workbench-v0.2.0-alpha.2) (2026-10-30)


### Features

* **agents:** add the policy advisor for phase 2 ([#332](https://github.com/data-director-agent/data-director/issues/332)) ([1f23fb4](https://github.com/data-director-agent/data-director/commit/1f23fb4dc2c28c21d931632edc3bf339bbbc586d))
* **agents:** add the repository advisor for phase 3 ([#325](https://github.com/data-director-agent/data-director/issues/325)) ([120a8b6](https://github.com/data-director-agent/data-director/commit/120a8b6cee92965ffe30fbd80ab18c302c01fc91))
* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))
* **inventory:** inventory a dataset's files where they live ([#393](https://github.com/data-director-agent/data-director/issues/393)) ([2238ce6](https://github.com/data-director-agent/data-director/commit/2238ce657e8158931229f4339cafc83a857bbb03))
* **workbench:** act for an example person by default ([#297](https://github.com/data-director-agent/data-director/issues/297)) ([dd0de8d](https://github.com/data-director-agent/data-director/commit/dd0de8d5eb8e40732a5063c63f1ac9223a16e78c))
* **workbench:** open the viewer on chat with the orchestrator ([#316](https://github.com/data-director-agent/data-director/issues/316)) ([bb4c8bb](https://github.com/data-director-agent/data-director/commit/bb4c8bb13a63c9cc68e01702dce8b6bd003e4a58))


### Bug Fixes

* default the explainer and orchestrator to claude sonnet 5.5 ([#298](https://github.com/data-director-agent/data-director/issues/298)) ([1149b72](https://github.com/data-director-agent/data-director/commit/1149b72190f8bc6a4076143e0edd354f45b4c382))


### Documentation

* **adr:** decide the repository profile and the deposit package ([#386](https://github.com/data-director-agent/data-director/issues/386)) ([fd04883](https://github.com/data-director-agent/data-director/commit/fd04883f40d48509550cad74e27ead1340a9028e))
* **adr:** derive a repository's requirements from its metadata standard ([#402](https://github.com/data-director-agent/data-director/issues/402)) ([e60404f](https://github.com/data-director-agent/data-director/commit/e60404f2a3712fe03b93e6e0b1bc8f8a1929d4e7))
* **adr:** number the repository profile ADR 0038 ([#397](https://github.com/data-director-agent/data-director/issues/397)) ([eb8d193](https://github.com/data-director-agent/data-director/commit/eb8d193cf2fafb0b2379b30dcdb5ba999c27a229)), closes [#197](https://github.com/data-director-agent/data-director/issues/197)
* reproduce the published blueprint v1.0 as chaptered markdown ([#286](https://github.com/data-director-agent/data-director/issues/286)) ([15e0094](https://github.com/data-director-agent/data-director/commit/15e00946817f7f132f1f3b8bf52826022d1b43c7))

## [0.2.0-alpha.1](https://github.com/data-director-agent/data-director/compare/workbench-v0.2.0-alpha...workbench-v0.2.0-alpha.1) (2026-10-28)


### Features

* **workbench:** show the agent card in a readable form on the Agents page ([#217](https://github.com/data-director-agent/data-director/issues/217)) ([f5a650c](https://github.com/data-director-agent/data-director/commit/f5a650caa4afb7138353243dfed9bd144e3eff19)), closes [#138](https://github.com/data-director-agent/data-director/issues/138)

## [0.2.0-alpha](https://github.com/data-director-agent/data-director/compare/workbench-v0.1.0...workbench-v0.2.0-alpha) (2026-10-23)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.9.0; agents declaring 0.8.x are reported as incompatible.

### Features

* **agents:** a model-backed orchestrator that routes from the manifest ([#161](https://github.com/data-director-agent/data-director/issues/161)) ([021f470](https://github.com/data-director-agent/data-director/commit/021f4707cebc72310917ec4e16ff9cbdd85ce264))
* **app:** route the app through the conductor, with its own configuration ([#63](https://github.com/data-director-agent/data-director/issues/63)) ([1ac8e53](https://github.com/data-director-agent/data-director/commit/1ac8e5354a595bb8d6d24dd99819f15e3d94223e))
* **ci:** code coverage for the unit tests, with Codecov reporting and badges ([#90](https://github.com/data-director-agent/data-director/issues/90)) ([b0f611e](https://github.com/data-director-agent/data-director/commit/b0f611e1187db9d110cadb52cf791c9444e99d12))
* **harness:** a standalone A2A server for deployments ([#55](https://github.com/data-director-agent/data-director/issues/55)) ([#65](https://github.com/data-director-agent/data-director/issues/65)) ([9fa54fa](https://github.com/data-director-agent/data-director/commit/9fa54fa7e75ec1dae88234c27e0966c947105e80))
* **harness:** a test kit of its own, so harness tests leave workbench/tests ([#62](https://github.com/data-director-agent/data-director/issues/62)) ([bf72812](https://github.com/data-director-agent/data-director/commit/bf728125bd42d20865eaff903daa0370f7b94e48)), closes [#56](https://github.com/data-director-agent/data-director/issues/56)
* **harness:** find agents that start after the registry was built ([#165](https://github.com/data-director-agent/data-director/issues/165)) ([e4465c3](https://github.com/data-director-agent/data-director/commit/e4465c32e7457bf5eab59b393c726916a7796bc6))
* **orchestrator:** default to Claude Haiku 5.5 ([#172](https://github.com/data-director-agent/data-director/issues/172)) ([7aa861c](https://github.com/data-director-agent/data-director/commit/7aa861c269f55743962f6a2d30cb093def03f8b6))
* **sdk:** a model key stays with the agent that calls the model ([#157](https://github.com/data-director-agent/data-director/issues/157)) ([a846b8f](https://github.com/data-director-agent/data-director/commit/a846b8feffdfdf87483b618e86830c79e8d4bfe3))
* **sdk:** record an authenticated principal and the issuer that vouched ([#181](https://github.com/data-director-agent/data-director/issues/181)) ([57650b3](https://github.com/data-director-agent/data-director/commit/57650b3176d6510c8580f3b3fad03ca11bc8b3eb))
* **workbench:** colour agent status chips by state ([#136](https://github.com/data-director-agent/data-director/issues/136)) ([63a05d2](https://github.com/data-director-agent/data-director/commit/63a05d2f899439c808cdcb7d10546a21ac150600))


### Bug Fixes

* **workbench:** report a missing profile, agent list or source list in one line ([#61](https://github.com/data-director-agent/data-director/issues/61)) ([afaaa8c](https://github.com/data-director-agent/data-director/commit/afaaa8c8d2e5eefd5406d83f0683b96140dcfe3c))


### Documentation

* **adr:** the app's entry point is the orchestrator conversation ([#137](https://github.com/data-director-agent/data-director/issues/137)) ([eba0ec2](https://github.com/data-director-agent/data-director/commit/eba0ec2a3bc1cee44d6f856af38d8354c0474b3b))
* explain the system architecture from the top down ([#148](https://github.com/data-director-agent/data-director/issues/148)) ([cac515c](https://github.com/data-director-agent/data-director/commit/cac515c367803f3c6e7ff5ce57a0dca336f96d9a))
* record why the contract is written in LinkML (ADR-0020) ([#44](https://github.com/data-director-agent/data-director/issues/44)) ([a366461](https://github.com/data-director-agent/data-director/commit/a36646154c27954f69a74694d40780930bf38663))
* separate the docs by what they describe ([#58](https://github.com/data-director-agent/data-director/issues/58)) ([#64](https://github.com/data-director-agent/data-director/issues/64)) ([b55f849](https://github.com/data-director-agent/data-director/commit/b55f849b14e0566e3fdf2ffdf7def2a0c570afb0))
* stop naming specific models in prose and examples ([#174](https://github.com/data-director-agent/data-director/issues/174)) ([ab5c074](https://github.com/data-director-agent/data-director/commit/ab5c0741b364c5942a78824033afac6d0f04f183))
* **workbench:** record what RO-Crate is for (ADR-0021) ([#48](https://github.com/data-director-agent/data-director/issues/48)) ([b748203](https://github.com/data-director-agent/data-director/commit/b748203447aa988e0d072ff70c8fd73cff1822ee))
* **workbench:** walk one run through every step ([#45](https://github.com/data-director-agent/data-director/issues/45)) ([ab18167](https://github.com/data-director-agent/data-director/commit/ab18167bb33abb20f2e6580452ff8e421297dbf5))
