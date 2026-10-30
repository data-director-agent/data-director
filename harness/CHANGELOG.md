# Changelog

## [0.2.0-alpha.1](https://github.com/data-director-agent/data-director/compare/harness-v0.2.0-alpha...harness-v0.2.0-alpha.1) (2026-10-30)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.10.0; agents declaring 0.9.x are reported as incompatible until rebuilt.

### Features

* **agents:** add the policy advisor for phase 2 ([#332](https://github.com/data-director-agent/data-director/issues/332)) ([1f23fb4](https://github.com/data-director-agent/data-director/commit/1f23fb4dc2c28c21d931632edc3bf339bbbc586d))
* **agents:** add the repository advisor for phase 3 ([#325](https://github.com/data-director-agent/data-director/issues/325)) ([120a8b6](https://github.com/data-director-agent/data-director/commit/120a8b6cee92965ffe30fbd80ab18c302c01fc91))
* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))
* **app:** sign people in with ORCID and act for each of them ([#326](https://github.com/data-director-agent/data-director/issues/326)) ([4c53421](https://github.com/data-director-agent/data-director/commit/4c534212040fe3b7163a02ec28cb2023936a479f))
* **harness:** hold a project's record and its inventory ([#396](https://github.com/data-director-agent/data-director/issues/396)) ([daa5733](https://github.com/data-director-agent/data-director/commit/daa57338c87697345a891056de63f8b84ecb4259))
* **harness:** record the repository a researcher chose ([#405](https://github.com/data-director-agent/data-director/issues/405)) ([6b5f52f](https://github.com/data-director-agent/data-director/commit/6b5f52f32b263dff1d101f9cfcb8bfda7a131582))
* **sdk:** add the core document payload class ([#379](https://github.com/data-director-agent/data-director/issues/379)) ([2d58112](https://github.com/data-director-agent/data-director/commit/2d581126c2fb92adfcbe9a629c5b9433ec4ae8f1))


### Documentation

* **harness:** say why agent replies are not streamed ([#335](https://github.com/data-director-agent/data-director/issues/335)) ([192f24e](https://github.com/data-director-agent/data-director/commit/192f24ef4d51e211a5a03cc26d0310533dac7b56))

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
