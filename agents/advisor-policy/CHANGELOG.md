# Changelog

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

## [0.1.0-alpha.2](https://github.com/data-director-agent/data-director/compare/agent-advisor-policy-v0.1.0-alpha.1...agent-advisor-policy-v0.1.0-alpha.2) (2026-11-06)


### Features

* **deploy:** one configuration tool with a doctor for the VM ([#548](https://github.com/data-director-agent/data-director/issues/548)) ([73f1db1](https://github.com/data-director-agent/data-director/commit/73f1db15081ccd20ff660b168d5249b4c30e29af))
* **harness:** disclose the generative AI behind each approved document ([#479](https://github.com/data-director-agent/data-director/issues/479)) ([31c0e31](https://github.com/data-director-agent/data-director/commit/31c0e31ae6465c954ecad99c91bc34e3a3193d54)), closes [#476](https://github.com/data-director-agent/data-director/issues/476)

## [0.1.0-alpha.1](https://github.com/data-director-agent/data-director/compare/agent-advisor-policy-v0.1.0-alpha...agent-advisor-policy-v0.1.0-alpha.1) (2026-11-05)


### Features

* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))


### Bug Fixes

* **agents:** say an empty mandate list is not evidence that none is required ([#455](https://github.com/data-director-agent/data-director/issues/455)) ([dacdaaa](https://github.com/data-director-agent/data-director/commit/dacdaaa82934c2c6e3ccc2186b96e59c21e9f694))


### Documentation

* replace decision records with living specs ([#434](https://github.com/data-director-agent/data-director/issues/434)) ([a19caba](https://github.com/data-director-agent/data-director/commit/a19caba60b1f1fc0049c0a68c29feb2354b97db5))
