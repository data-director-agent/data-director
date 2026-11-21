# Changelog

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

## [0.1.0-alpha.2](https://github.com/data-director-agent/data-director/compare/agent-advisor-repository-v0.1.0-alpha.1...agent-advisor-repository-v0.1.0-alpha.2) (2026-11-06)


### Features

* **agents:** search every re3data repository from a pinned monthly export ([#489](https://github.com/data-director-agent/data-director/issues/489)) ([4a05699](https://github.com/data-director-agent/data-director/commit/4a056996f5ef9611cd97a03722dfdc38f67ab1b9))
* **deploy:** one configuration tool with a doctor for the VM ([#548](https://github.com/data-director-agent/data-director/issues/548)) ([73f1db1](https://github.com/data-director-agent/data-director/commit/73f1db15081ccd20ff660b168d5249b4c30e29af))
* **harness:** disclose the generative AI behind each approved document ([#479](https://github.com/data-director-agent/data-director/issues/479)) ([31c0e31](https://github.com/data-director-agent/data-director/commit/31c0e31ae6465c954ecad99c91bc34e3a3193d54)), closes [#476](https://github.com/data-director-agent/data-director/issues/476)
* **sdk:** prepare every agent's built sources with one command ([#508](https://github.com/data-director-agent/data-director/issues/508)) ([3c76b2b](https://github.com/data-director-agent/data-director/commit/3c76b2ba0edb97ca58bc25910d4ac67224db0262)), closes [#507](https://github.com/data-director-agent/data-director/issues/507)

## [0.1.0-alpha.1](https://github.com/data-director-agent/data-director/compare/agent-advisor-repository-v0.1.0-alpha...agent-advisor-repository-v0.1.0-alpha.1) (2026-11-05)


### Features

* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))


### Bug Fixes

* **agents:** keep repository shortlists to the dataset's discipline ([#457](https://github.com/data-director-agent/data-director/issues/457)) ([a18a61b](https://github.com/data-director-agent/data-director/commit/a18a61b09acd58b1bcf162269d4c82aa4927857b))
* **agents:** keep the shortlist when an institution is named ([#460](https://github.com/data-director-agent/data-director/issues/460)) ([fc270d5](https://github.com/data-director-agent/data-director/commit/fc270d5102427f2c9303e6248602c8f185637e15))
* **agents:** say an empty mandate list is not evidence that none is required ([#455](https://github.com/data-director-agent/data-director/issues/455)) ([dacdaaa](https://github.com/data-director-agent/data-director/commit/dacdaaa82934c2c6e3ccc2186b96e59c21e9f694))


### Documentation

* replace decision records with living specs ([#434](https://github.com/data-director-agent/data-director/issues/434)) ([a19caba](https://github.com/data-director-agent/data-director/commit/a19caba60b1f1fc0049c0a68c29feb2354b97db5))
