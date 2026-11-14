# Changelog

## [0.3.0-alpha.9](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.8...app-v0.3.0-alpha.9) (2026-11-14)


### Features

* **advisor-documentation:** ask the README's general information as separate questions ([#674](https://github.com/data-director-agent/data-director/issues/674)) ([9c12949](https://github.com/data-director-agent/data-director/commit/9c12949321dece45f25d6773f40a73354ee8bb79))
* **app:** add a footer crediting the University of Sheffield and the RDA ([#661](https://github.com/data-director-agent/data-director/issues/661)) ([122f4af](https://github.com/data-director-agent/data-director/commit/122f4af0791cd9f20478665422eb1b4aae6779eb))
* **app:** add an inventory from the project page and side bar ([#816](https://github.com/data-director-agent/data-director/issues/816)) ([f8345d4](https://github.com/data-director-agent/data-director/commit/f8345d47a5282708e17ea3288176d5d2c59e96ff))
* **app:** add your own AI account from the profile page ([#818](https://github.com/data-director-agent/data-director/issues/818)) ([ad98bfc](https://github.com/data-director-agent/data-director/commit/ad98bfc372874ca74346dafd1a8ae789afadb1d2))
* **app:** attach a supporting document to a conversation turn ([#707](https://github.com/data-director-agent/data-director/issues/707)) ([1e40b77](https://github.com/data-director-agent/data-director/commit/1e40b777d0749d54092c4b0cdc2c169eef8342b7))
* **app:** create a project without a conversation (POST /api/projects) ([#805](https://github.com/data-director-agent/data-director/issues/805)) ([737a27f](https://github.com/data-director-agent/data-director/commit/737a27f3e423b58bfd91ee95b247e31f8096fd4b))
* **app:** each person sees only their own runs and conversations ([#657](https://github.com/data-director-agent/data-director/issues/657)) ([17a8b75](https://github.com/data-director-agent/data-director/commit/17a8b75f8c0461f0e5bf1abd24705d34e6693faf))
* **app:** edit inventories to describe files and revise them ([#747](https://github.com/data-director-agent/data-director/issues/747)) ([427ffe5](https://github.com/data-director-agent/data-director/commit/427ffe588622f5c6af50334056dae7b3c6cfba41))
* **app:** let researchers rename projects and the orchestrator name untitled ones ([#678](https://github.com/data-director-agent/data-director/issues/678)) ([1c3d875](https://github.com/data-director-agent/data-director/commit/1c3d875eb0339328bb0556c1997d02ad99f117e7))
* **app:** link from the conversation to the active project's details ([#687](https://github.com/data-director-agent/data-director/issues/687)) ([49fa40a](https://github.com/data-director-agent/data-director/commit/49fa40afc12c245c3be2d599d7f70f652fc7f037))
* **app:** link the banner app name to the home page ([#735](https://github.com/data-director-agent/data-director/issues/735)) ([ec52dff](https://github.com/data-director-agent/data-director/commit/ec52dff89329963cc165c5468f38dd3f3ce1ff10))
* **app:** make choice question options whole-card targets ([#672](https://github.com/data-director-agent/data-director/issues/672)) ([69b705f](https://github.com/data-director-agent/data-director/commit/69b705fca084946ab80ab0897ae3a0b3c4df1dd1))
* **app:** say that an inventory describes the data, not uploads it ([#676](https://github.com/data-director-agent/data-director/issues/676)) ([426d0e3](https://github.com/data-director-agent/data-director/commit/426d0e3422ac8e3f077948ef0747022fb6a939f3))
* **app:** say what to do after downloading the deposit package ([#742](https://github.com/data-director-agent/data-director/issues/742)) ([f2d9ad2](https://github.com/data-director-agent/data-director/commit/f2d9ad2b060516d979d82b347e25f5f6c8c04425))
* **app:** show ORCID and GitHub marks beside their sign-in and links ([#663](https://github.com/data-director-agent/data-director/issues/663)) ([0c3e8cb](https://github.com/data-director-agent/data-director/commit/0c3e8cb37b76ec7a3a0badde724b6f99a4f0c3c4))
* **app:** show the intake card before a new project's first turn ([#776](https://github.com/data-director-agent/data-director/issues/776)) ([9f03a8b](https://github.com/data-director-agent/data-director/commit/9f03a8b1fa2b06e66fc8ce0da9dd02481b772ed0))
* **harness:** add pagination for listing runs and conversations ([#715](https://github.com/data-director-agent/data-director/issues/715)) ([bc3b541](https://github.com/data-director-agent/data-director/commit/bc3b5411362e31b8dae01eb13fd671bc0e55af43))
* **harness:** enforce the profile's model_accounts key ([#820](https://github.com/data-director-agent/data-director/issues/820)) ([3229145](https://github.com/data-director-agent/data-director/commit/3229145163e9ccf90cdc8176417373e9ed22f05a))
* **harness:** keep runs and projects in postgresql ([#708](https://github.com/data-director-agent/data-director/issues/708)) ([3436209](https://github.com/data-director-agent/data-director/commit/3436209f605a7cdcc51a9ab7ded2163391818b06))
* **harness:** list the projects a person may read from an index ([#724](https://github.com/data-director-agent/data-director/issues/724)) ([140db1f](https://github.com/data-director-agent/data-director/commit/140db1ff9d4b70bced5b36ad154d232dd2683d9d))
* **harness:** mint a model grant for each model-backed invocation ([#817](https://github.com/data-director-agent/data-director/issues/817)) ([6042098](https://github.com/data-director-agent/data-director/commit/604209892028330c5eee74f58f04f15485ce4ee1))
* **harness:** record intake answers and derive step states from them ([#768](https://github.com/data-director-agent/data-director/issues/768)) ([7e98d8e](https://github.com/data-director-agent/data-director/commit/7e98d8eb44d9ae7ce6bde70f65d879d051518fef))
* **harness:** stream run stages, check reports and cancellation over ag-ui ([#709](https://github.com/data-director-agent/data-director/issues/709)) ([6a48a7f](https://github.com/data-director-agent/data-director/commit/6a48a7f9e210fc29d96d0e59d0b680f6fddc61e5))
* **harness:** validate agent payloads against their SHACL shapes ([#654](https://github.com/data-director-agent/data-director/issues/654)) ([7406741](https://github.com/data-director-agent/data-director/commit/74067418e35de94175a76c3e9d66601c8875cbf1))
* let agents ask a series of questions answered one at a time ([#739](https://github.com/data-director-agent/data-director/issues/739)) ([5332215](https://github.com/data-director-agent/data-director/commit/5332215e8f050dcf3b61fdccb11b63ad436e6d92))
* let researchers give agents facts from their public ORCID record ([#760](https://github.com/data-director-agent/data-director/issues/760)) ([c312d78](https://github.com/data-director-agent/data-director/commit/c312d7882b157942a08ddbda905b85cad90bd6aa))
* **web:** add @data-director/agent-view for agent cards and payloads ([#679](https://github.com/data-director-agent/data-director/issues/679)) ([d76df18](https://github.com/data-director-agent/data-director/commit/d76df183dca573f99527a82c95bf39341650d939))
* **web:** set the orchestrator apart on the agents page ([#660](https://github.com/data-director-agent/data-director/issues/660)) ([a7b185c](https://github.com/data-director-agent/data-director/commit/a7b185c94a5b4a6617ec66bd6e2424abb9595d18))


### Bug Fixes

* **advisor-repository:** match plurals and rank the researcher's country first ([#745](https://github.com/data-director-agent/data-director/issues/745)) ([aa9b1fe](https://github.com/data-director-agent/data-director/commit/aa9b1fe5583312e7e0ac486e83a8bed303379dbc))
* **app:** keep the open conversation in the address for reload and linking ([#691](https://github.com/data-director-agent/data-director/issues/691)) ([3b91030](https://github.com/data-director-agent/data-director/commit/3b910304f889aea88f53b5be690cfd0e571b05fc))
* **app:** refuse project routes to anyone without a role in the project ([#658](https://github.com/data-director-agent/data-director/issues/658)) ([9dd4c6d](https://github.com/data-director-agent/data-director/commit/9dd4c6d5da045c01b1e9fbc28cf915173b5da01e))
* Block /server-status endpoint from external access via NGINX ([#731](https://github.com/data-director-agent/data-director/issues/731)) ([f904f2b](https://github.com/data-director-agent/data-director/commit/f904f2b248c1544ec869ddd1132b192ed0b3c96b))
* **ci:** downgrade Node to LTS 22 and Python to 3.14 ([#722](https://github.com/data-director-agent/data-director/issues/722)) ([4b38f14](https://github.com/data-director-agent/data-director/commit/4b38f14f4f90c71838e2b01c83caf3b605d1494d))
* **orchestration:** record the entry point Data Director works out ([#706](https://github.com/data-director-agent/data-director/issues/706)) ([7781b37](https://github.com/data-director-agent/data-director/commit/7781b3738ba64bdda89af7d225ba0e1d4a970438))
* require JSON content-type for state-changing API requests ([#732](https://github.com/data-director-agent/data-director/issues/732)) ([9311d1c](https://github.com/data-director-agent/data-director/commit/9311d1cdb4cc94e2c3a89a6801e680c8af650775))

## [0.3.0-alpha.8](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.7...app-v0.3.0-alpha.8) (2026-11-07)


### Features

* **agents:** ask the researcher about each gap in a drafted document ([#602](https://github.com/data-director-agent/data-director/issues/602)) ([bf91107](https://github.com/data-director-agent/data-director/commit/bf911077a941a6a4199d1c0b293d2d26533b4cf7))
* **agents:** draft a readme from the project's approved metadata record ([#617](https://github.com/data-director-agent/data-director/issues/617)) ([281cc59](https://github.com/data-director-agent/data-director/commit/281cc594db577a1517294e429a88b1e35f063d81))
* **agents:** suggest data dictionary definitions and units as questions ([#638](https://github.com/data-director-agent/data-director/issues/638)) ([05f1330](https://github.com/data-director-agent/data-director/commit/05f133061b033ba066088a10eed9c784a77c0228))
* **agents:** write readme prose with a model and answer drafter questions ([#627](https://github.com/data-director-agent/data-director/issues/627)) ([764d6ea](https://github.com/data-director-agent/data-director/commit/764d6ea3393ab54eb53843912ea0423fb9f22747))
* **app:** browse a project's documents in a list and a reader ([#601](https://github.com/data-director-agent/data-director/issues/601)) ([297ebea](https://github.com/data-director-agent/data-director/commit/297ebeace08b97108e7774ce392d18a3e76872c6))
* **app:** check an inventory and leave things out before it is attached ([#605](https://github.com/data-director-agent/data-director/issues/605)) ([d275526](https://github.com/data-director-agent/data-director/commit/d2755264c831a9d566d114a97626f3de9f7450be))
* **app:** show the chosen repository's requirements on the project page ([#642](https://github.com/data-director-agent/data-director/issues/642)) ([b3f0ae1](https://github.com/data-director-agent/data-director/commit/b3f0ae1322e2e4812c206885857ad77709a6fe27))
* **app:** validate a project and download its deposit package ([#636](https://github.com/data-director-agent/data-director/issues/636)) ([a4e9dce](https://github.com/data-director-agent/data-director/commit/a4e9dce1169f8bca09edc43f63be54ef31e6911b))
* **app:** work in one project at a time ([#600](https://github.com/data-director-agent/data-director/issues/600)) ([23a3913](https://github.com/data-director-agent/data-director/commit/23a39136afb1421ae2c3012c3bc53fc11b9d1342))
* **harness:** implement project validation and deposit package building ([#625](https://github.com/data-director-agent/data-director/issues/625)) ([529fea5](https://github.com/data-director-agent/data-director/commit/529fea59de999f95dbf8a75bb4c69f5c402ea388))
* **harness:** keep project documentation from hosted models unless the profile allows it ([#634](https://github.com/data-director-agent/data-director/issues/634)) ([a47d148](https://github.com/data-director-agent/data-director/commit/a47d1486706ceaa081b947fe69c3fea17d6ae02b))
* **harness:** resolve a chosen repository from the pinned re3data export ([#633](https://github.com/data-director-agent/data-director/issues/633)) ([6a5d862](https://github.com/data-director-agent/data-director/commit/6a5d862f158f61031adceddd7741bbc8a4e1b3ee))
* track project progress from process flow logs ([#628](https://github.com/data-director-agent/data-director/issues/628)) ([fc5be95](https://github.com/data-director-agent/data-director/commit/fc5be95bdfe9a3d66c4ed023a04765199973db1a))


### Performance Improvements

* **ci:** parallelize CI jobs and improve test assertions ([#621](https://github.com/data-director-agent/data-director/issues/621)) ([c0a53da](https://github.com/data-director-agent/data-director/commit/c0a53da72790e3db30fbf98688948562b7cc7882))

## [0.3.0-alpha.7](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.6...app-v0.3.0-alpha.7) (2026-11-06)


### Features

* **app:** add a make an inventory dialog beside attach inventory ([#593](https://github.com/data-director-agent/data-director/issues/593)) ([9e65d6f](https://github.com/data-director-agent/data-director/commit/9e65d6f02f61403218af81ba44a4c3380547ff32))
* **app:** add a policy page that shows the rules runs are held to ([2b76eb6](https://github.com/data-director-agent/data-director/commit/2b76eb60e1aebf23211f34f526098068260805c6))
* **app:** ask categorical questions as clickable choices ([#586](https://github.com/data-director-agent/data-director/issues/586)) ([57b4e9f](https://github.com/data-director-agent/data-director/commit/57b4e9f0d7e5dedea4b9e45201de64365c04b90b))
* **app:** put a projects page first in the navigation ([13ddf5c](https://github.com/data-director-agent/data-director/commit/13ddf5c3658c9c492f710a8d18ad02836423e944))
* **app:** put a projects page first in the navigation ([003b270](https://github.com/data-director-agent/data-director/commit/003b270302c5d34efbc94aa8ac8700b51899f518))
* **app:** say that ctrl+enter sends a chat message ([#595](https://github.com/data-director-agent/data-director/issues/595)) ([c9817d0](https://github.com/data-director-agent/data-director/commit/c9817d0c3cec3af3f03872a8a270ff752783e585))
* **app:** show the phases as a plain-language data journey ([df64bb0](https://github.com/data-director-agent/data-director/commit/df64bb0e12f13210f7a5c55d24bfd6cff55c4db5))
* **sdk:** show the data management plan steps as out of scope ([631f442](https://github.com/data-director-agent/data-director/commit/631f442c5ee6bfeb3f73813bda88ac648901df60))
* **sdk:** show the data management plan steps as out of scope ([7109c17](https://github.com/data-director-agent/data-director/commit/7109c1790d13d84cbdfe54668ad0cfc2803fb2df))


### Bug Fixes

* **app:** put the tabindex lint exemption on the reported line ([01d43b8](https://github.com/data-director-agent/data-director/commit/01d43b85c421e1d51b578847cc64bd50d1b6c666))
* **app:** put the tabindex lint exemption on the reported line ([c5e37de](https://github.com/data-director-agent/data-director/commit/c5e37de9e8708595bc3f4d5585d43c9cf62cba9a))

## [0.3.0-alpha.6](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.5...app-v0.3.0-alpha.6) (2026-11-06)


### Features

* **app:** put conversations left, the project right and the activity log on its own page ([0ed2f31](https://github.com/data-director-agent/data-director/commit/0ed2f3118533c0d4d9d20b4c8fa966515f55dd13))
* **app:** put conversations left, the project right and the activity log on its own page ([93477f9](https://github.com/data-director-agent/data-director/commit/93477f92effb6b51701c851ea7e1fc05194d0d29))
* **app:** remove the acting for and policy strip from the workspace ([9e6a3f0](https://github.com/data-director-agent/data-director/commit/9e6a3f04166ca0c0eed03f1446e09e59d28af78c))
* **app:** remove the acting for and policy strip from the workspace ([75d755b](https://github.com/data-director-agent/data-director/commit/75d755b6a6b8b5384b9fd72e7eb4ee23c1d67ba7))
* **app:** serve a project's inventory for the researcher to read ([46d9e8b](https://github.com/data-director-agent/data-director/commit/46d9e8bd570fdfbc3b04299c2272c918ca301175))
* **app:** show an inventory in readable form ([e4461f1](https://github.com/data-director-agent/data-director/commit/e4461f1b6314bcdb938cc9a6f5d3f05b1809886c))
* **app:** show an inventory in readable form ([d38c95d](https://github.com/data-director-agent/data-director/commit/d38c95ddf8a5ded75c85c27f50a23d9e259c6de0))


### Bug Fixes

* **app:** say what an agent is given, not where it sends your data ([6be219e](https://github.com/data-director-agent/data-director/commit/6be219eb3bbdd0a83e1a2861258e2391ebe33595))
* **app:** say what an agent is given, not where it sends your data ([d33153a](https://github.com/data-director-agent/data-director/commit/d33153a95491794cf2589c627dcc408211f89e4a))

## [0.3.0-alpha.5](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.4...app-v0.3.0-alpha.5) (2026-11-06)


### Features

* **agents:** name example.hello the friendly greeter and refresh the template ([#530](https://github.com/data-director-agent/data-director/issues/530)) ([7e796e2](https://github.com/data-director-agent/data-director/commit/7e796e2ca638bb46414ae5fe93e834b007de0f4c))
* **agents:** search every re3data repository from a pinned monthly export ([#489](https://github.com/data-director-agent/data-director/issues/489)) ([4a05699](https://github.com/data-director-agent/data-director/commit/4a056996f5ef9611cd97a03722dfdc38f67ab1b9))
* **app:** add a profile page showing what sign-in holds ([#536](https://github.com/data-director-agent/data-director/issues/536)) ([1e5566f](https://github.com/data-director-agent/data-director/commit/1e5566f6b67ed758487c66b14d96ffdbc63ac0f0))
* **app:** answer a monitor's server-status request ([#526](https://github.com/data-director-agent/data-director/issues/526)) ([f1e5a8b](https://github.com/data-director-agent/data-director/commit/f1e5a8b52e6f0e76f7190db1a0dccf732fdaff5b))
* **app:** file problem reports as a GitHub App ([#531](https://github.com/data-director-agent/data-director/issues/531)) ([1a54c05](https://github.com/data-director-agent/data-director/commit/1a54c05b8f88d02f650f3f14fe31ec61a982a698))
* **app:** give each earlier conversation a title ([#542](https://github.com/data-director-agent/data-director/issues/542)) ([0202dfa](https://github.com/data-director-agent/data-director/commit/0202dfaf94cbb60f951299d138c12877600e7e2f))
* **app:** report the live profile and unavailable agents in /api/about ([#547](https://github.com/data-director-agent/data-director/issues/547)) ([a9635ae](https://github.com/data-director-agent/data-director/commit/a9635ae75c10a5485101609c8dddd2bd6b5c4f34))
* **app:** simplify the agents page for end users ([#545](https://github.com/data-director-agent/data-director/issues/545)) ([c1a8ad5](https://github.com/data-director-agent/data-director/commit/c1a8ad586e1cdc7b98e942df63bf807420e4dc0c))
* **deploy:** declare what an instance runs in deployment.yaml ([#559](https://github.com/data-director-agent/data-director/issues/559)) ([566aa56](https://github.com/data-director-agent/data-director/commit/566aa56066d867d5c138059ab8a2efe7d3664e30))
* **deploy:** one configuration tool with a doctor for the VM ([#548](https://github.com/data-director-agent/data-director/issues/548)) ([73f1db1](https://github.com/data-director-agent/data-director/commit/73f1db15081ccd20ff660b168d5249b4c30e29af))
* **harness:** disclose the generative AI behind each approved document ([#479](https://github.com/data-director-agent/data-director/issues/479)) ([31c0e31](https://github.com/data-director-agent/data-director/commit/31c0e31ae6465c954ecad99c91bc34e3a3193d54)), closes [#476](https://github.com/data-director-agent/data-director/issues/476)
* **sdk:** prepare every agent's built sources with one command ([#508](https://github.com/data-director-agent/data-director/issues/508)) ([3c76b2b](https://github.com/data-director-agent/data-director/commit/3c76b2ba0edb97ca58bc25910d4ac67224db0262)), closes [#507](https://github.com/data-director-agent/data-director/issues/507)


### Bug Fixes

* **app:** call the phases panel data management phases ([#474](https://github.com/data-director-agent/data-director/issues/474)) ([6f3efa8](https://github.com/data-director-agent/data-director/commit/6f3efa81f3249e5c16e57c8157c6f966e064b495))
* **app:** override minimatch to 11.0.1 or later ([#493](https://github.com/data-director-agent/data-director/issues/493)) ([730668b](https://github.com/data-director-agent/data-director/commit/730668b2edb296d9a7d4cbb86d1ebfab31863e97))
* **app:** show agent errors at the top of the agents page ([#528](https://github.com/data-director-agent/data-director/issues/528)) ([fcccff1](https://github.com/data-director-agent/data-director/commit/fcccff10933ff6df345a8aa4949d7433643a1ad0))


### Documentation

* **deploy:** document the data-director command for operators ([55d0d69](https://github.com/data-director-agent/data-director/commit/55d0d6901b56add54627f2286abc72c24d1909ac))
* **deploy:** document the data-director command for operators ([50825e4](https://github.com/data-director-agent/data-director/commit/50825e4ada925fc89de1d76db980970cab268e94))
* **operations:** document setting up sign-in against the ORCID sandbox ([#527](https://github.com/data-director-agent/data-director/issues/527)) ([773a98e](https://github.com/data-director-agent/data-director/commit/773a98ece74c5bdb5e57fdf0f3da90f5b74d58ae))

## [0.3.0-alpha.4](https://github.com/data-director-agent/data-director/compare/app-v0.3.0-alpha.3...app-v0.3.0-alpha.4) (2026-11-05)


### ⚠ BREAKING CHANGES

* **sdk:** the contract version is 0.10.0; agents declaring 0.9.x are reported as incompatible until rebuilt.
* **sdk:** an agent card that declares R1 to R12 in `serves` is refused; name the steps instead.

### Features

* **agents:** add the policy advisor for phase 2 ([#332](https://github.com/data-director-agent/data-director/issues/332)) ([1f23fb4](https://github.com/data-director-agent/data-director/commit/1f23fb4dc2c28c21d931632edc3bf339bbbc586d))
* **agents:** add the repository advisor for phase 3 ([#325](https://github.com/data-director-agent/data-director/issues/325)) ([120a8b6](https://github.com/data-director-agent/data-director/commit/120a8b6cee92965ffe30fbd80ab18c302c01fc91))
* **agents:** draft the metadata record, README and data dictionary as project documents ([#436](https://github.com/data-director-agent/data-director/issues/436)) ([076d604](https://github.com/data-director-agent/data-director/commit/076d6047d4bb0b9f6411b5ca2755a7ab0a96f69a))
* **agents:** sketch every persona of the roster as a served mock ([#364](https://github.com/data-director-agent/data-director/issues/364)) ([e9b81ba](https://github.com/data-director-agent/data-director/commit/e9b81ba0f94af1b7901de8f43704a3000d357933))
* **app:** add a favicon ([#315](https://github.com/data-director-agent/data-director/issues/315)) ([b4d54e4](https://github.com/data-director-agent/data-director/commit/b4d54e413ea1ac401be46ee293fa7353c3baa4b1))
* **app:** add icons to the banner and sign-in controls ([#467](https://github.com/data-director-agent/data-director/issues/467)) ([f52666a](https://github.com/data-director-agent/data-director/commit/f52666a235db415c2f3a3b1a8ca910740efa18a0))
* **app:** add Lucide icons to the action buttons ([#267](https://github.com/data-director-agent/data-director/issues/267)) ([4a5ad81](https://github.com/data-director-agent/data-director/commit/4a5ad81406b67191bd10ba772809dfa2624ab5e5))
* **app:** approve, edit or reject a proposed document ([#437](https://github.com/data-director-agent/data-director/issues/437)) ([e3ea354](https://github.com/data-director-agent/data-director/commit/e3ea354b621d442c838490ea6d723760fd5d6aa2))
* **app:** attach a folder's inventory in the chat ([#463](https://github.com/data-director-agent/data-director/issues/463)) ([12470f8](https://github.com/data-director-agent/data-director/commit/12470f86a9c7fd7508d5e084c97f0d2895d9a573))
* **app:** link to the user guide from every page ([#344](https://github.com/data-director-agent/data-director/issues/344)) ([8c6b459](https://github.com/data-director-agent/data-director/commit/8c6b4594885829955a1124c02ba075d83d7dacf1))
* **app:** send the chat message with Ctrl+Enter ([#268](https://github.com/data-director-agent/data-director/issues/268)) ([8212eb4](https://github.com/data-director-agent/data-director/commit/8212eb4c27481dfcb1b1299bfd92d0891ec12547))
* **app:** show that the orchestrator is working on a reply ([#334](https://github.com/data-director-agent/data-director/issues/334)) ([1d1ed80](https://github.com/data-director-agent/data-director/commit/1d1ed80007eb849c5414cc4d5c59bd50954870f9))
* **app:** show what powers each agent, and whether it is local or remote ([#317](https://github.com/data-director-agent/data-director/issues/317)) ([f4e7777](https://github.com/data-director-agent/data-director/commit/f4e7777b2e81fe474761569e9c17074539db2d4b))
* **app:** sign people in with ORCID and act for each of them ([#326](https://github.com/data-director-agent/data-director/issues/326)) ([4c53421](https://github.com/data-director-agent/data-director/commit/4c534212040fe3b7163a02ec28cb2023936a479f))
* **harness:** give a drafter its project's facts and record its draft ([#454](https://github.com/data-director-agent/data-director/issues/454)) ([4dba1b6](https://github.com/data-director-agent/data-director/commit/4dba1b604142acd9b9ac5c3dbe0a81441f396215))
* **harness:** record the repository a researcher chose ([#405](https://github.com/data-director-agent/data-director/issues/405)) ([6b5f52f](https://github.com/data-director-agent/data-director/commit/6b5f52f32b263dff1d101f9cfcb8bfda7a131582))
* **inventory:** inventory a dataset's files where they live ([#393](https://github.com/data-director-agent/data-director/issues/393)) ([2238ce6](https://github.com/data-director-agent/data-director/commit/2238ce657e8158931229f4339cafc83a857bbb03))
* **sdk:** add the core document payload class ([#379](https://github.com/data-director-agent/data-director/issues/379)) ([2d58112](https://github.com/data-director-agent/data-director/commit/2d581126c2fb92adfcbe9a629c5b9433ec4ae8f1))
* **sdk:** let an agent serve steps of the process flow, not requirements ([#307](https://github.com/data-director-agent/data-director/issues/307)) ([5d8a535](https://github.com/data-director-agent/data-director/commit/5d8a535900518241e1963ad0ac5deac886256314))


### Bug Fixes

* **app:** keep a stored turn from being sent again ([#387](https://github.com/data-director-agent/data-director/issues/387)) ([925c5fb](https://github.com/data-director-agent/data-director/commit/925c5fb74ae8e3ce2cadb51d7f5f30583740da82)), closes [#337](https://github.com/data-director-agent/data-director/issues/337)
* **app:** refuse a turn that does not follow the latest ([#417](https://github.com/data-director-agent/data-director/issues/417)) ([b1fdf80](https://github.com/data-director-agent/data-director/commit/b1fdf8008b15d5a3e472171763525fb9b4641b49)), closes [#337](https://github.com/data-director-agent/data-director/issues/337) [#390](https://github.com/data-director-agent/data-director/issues/390)
* **app:** render a drafted document's markdown in the run card ([#462](https://github.com/data-director-agent/data-director/issues/462)) ([4f8e018](https://github.com/data-director-agent/data-director/commit/4f8e018ff508b9ca65cd683a971c76e21203d067)), closes [#442](https://github.com/data-director-agent/data-director/issues/442)
* **app:** report agents the local profile omits but the example enables ([#384](https://github.com/data-director-agent/data-director/issues/384)) ([af93775](https://github.com/data-director-agent/data-director/commit/af93775f7d480452756593a42addd7a32a5c6fbd)), closes [#343](https://github.com/data-director-agent/data-director/issues/343)
* **app:** say what happens to a run's result instead of promising a review ([#452](https://github.com/data-director-agent/data-director/issues/452)) ([aeca961](https://github.com/data-director-agent/data-director/commit/aeca961f1758c5dd3b3c0aa3a413bdbc713eee71)), closes [#444](https://github.com/data-director-agent/data-director/issues/444)
* **app:** say when the server cannot be reached and log each turn ([#339](https://github.com/data-director-agent/data-director/issues/339)) ([14cc21b](https://github.com/data-director-agent/data-director/commit/14cc21b85def850ade3c7b25bc0022fe1cc1525f)), closes [#337](https://github.com/data-director-agent/data-director/issues/337)
* **orchestrator:** stop offering to create a data management plan ([#271](https://github.com/data-director-agent/data-director/issues/271)) ([f115f78](https://github.com/data-director-agent/data-director/commit/f115f784f556ee813768409525df9939818f6c54))


### Documentation

* **adr:** decide the repository profile and the deposit package ([#386](https://github.com/data-director-agent/data-director/issues/386)) ([fd04883](https://github.com/data-director-agent/data-director/commit/fd04883f40d48509550cad74e27ead1340a9028e))
* **adr:** derive a repository's requirements from its metadata standard ([#402](https://github.com/data-director-agent/data-director/issues/402)) ([e60404f](https://github.com/data-director-agent/data-director/commit/e60404f2a3712fe03b93e6e0b1bc8f8a1929d4e7))
* **adr:** number the repository profile ADR 0038 ([#397](https://github.com/data-director-agent/data-director/issues/397)) ([eb8d193](https://github.com/data-director-agent/data-director/commit/eb8d193cf2fafb0b2379b30dcdb5ba999c27a229)), closes [#197](https://github.com/data-director-agent/data-director/issues/197)
* **app:** point local ORCID sandbox sign-in at ORCID's registration page ([#345](https://github.com/data-director-agent/data-director/issues/345)) ([520ca3e](https://github.com/data-director-agent/data-director/commit/520ca3ee4eaae8041027b9faae8ecfe7d32e9c59))
* replace decision records with living specs ([#434](https://github.com/data-director-agent/data-director/issues/434)) ([a19caba](https://github.com/data-director-agent/data-director/commit/a19caba60b1f1fc0049c0a68c29feb2354b97db5))

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
