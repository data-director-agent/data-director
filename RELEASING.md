# Releasing

How versions are chosen, how a release is made and what a release does and does not change. The
commit and pull request conventions that drive it are in [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

[release-please](https://github.com/googleapis/release-please) does the work; nobody edits a
version or a changelog by hand. `.github/workflows/release.yaml` runs on every push to
`main`. Its configuration is `release-please-config.json`, and `.release-please-manifest.json`
records the last released version of each package.

- Each package is versioned on its own: `sdk`, `harness`, `workbench`, `app` and each agent in
  `agents/`. Its component name is in the configuration (`agent-orchestrator-stub`, `sdk`, …).
- The [Conventional Commit](https://www.conventionalcommits.org/) subjects of the squash-merged
  pull requests (the only merge the repository allows; see
  [Merging a pull request](CONTRIBUTING.md#merging-a-pull-request)) that touch a package's directory decide its next version. A commit that touches
  only the package's tests does not.
- release-please keeps **one** release pull request open for every package with a pending release,
  titled `chore(main): release main`, and rewrites it after every merge to `main`. It changes each
  package's `pyproject.toml` (and `app/web/package.json`), `CHANGELOG.md` and the manifest.
- The workflow also refreshes `uv.lock` on the release branch, because release-please cannot.
- Nothing is tagged or published until the release pull request is merged. Merging it tags each
  package `<component>-v<version>` (for example `harness-v0.2.0-alpha`) and creates a GitHub
  release, marked as a pre-release.
- If the merge released `sdk`, `harness` or `inventory`, the workflow then builds that package and publishes
  it to [TestPyPI](https://test.pypi.org/) (see below). If it released `inventory`, that package is
  also published to PyPI. No other package is published to an index.
- If the merge released `app`, the workflow publishes the container image, tagged with the app's
  version (see [Publishing the container image](#publishing-the-container-image)).

## Publishing to TestPyPI

An agent in another repository needs the SDK, and the harness's test kit, from a package index
(ADR-0031). Until the release path is proven, they go to TestPyPI only, and install with:

```sh
pip install --pre --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ data-director-sdk
```

The `publish-testpypi` job uses trusted publishing: TestPyPI trusts
`.github/workflows/release.yaml` running in the `testpypi` environment, and no token is
stored. A version already on TestPyPI is skipped, so running the workflow again is safe.

Set-up, once, by a maintainer:

1. On TestPyPI, add a pending trusted publisher for each of `data-director-sdk`,
   `data-director-harness` and `data-director-inventory`: owner `data-director-agent`, repository `data-director`, workflow
   `release.yaml`, environment `testpypi`.
2. In this repository's settings, create the environment `testpypi`, limited to the `main`
   branch.

## Publishing the inventory to PyPI

The inventory is also published to [PyPI](https://pypi.org/p/data-director-inventory), so that a
researcher can run `uvx data-director-inventory path/to/dataset` without a checkout (#552). The
`publish-pypi` job does this on the same trigger as the TestPyPI job, with the same build, and uses trusted
publishing in the same way: PyPI trusts `.github/workflows/release.yaml` running in the `pypi`
environment. A version already on PyPI is skipped.

Set-up, once, by a maintainer:

1. On PyPI, add a pending trusted publisher for `data-director-inventory`: owner
   `data-director-agent`, repository `data-director`, workflow `release.yaml`, environment `pypi`.
2. In this repository's settings, create the environment `pypi`, limited to the `main` branch,
   with a required reviewer so that a release is published only when a maintainer approves it.

A PyPI release cannot be replaced, only yanked, and its name cannot be reused. The sdk and harness
stay on TestPyPI only; publishing them to PyPI is a separate decision, after the contract reaches
1.0 or sooner (TODO(#260, #277)).

## Publishing the container image

`.github/workflows/images.yml` builds `ghcr.io/data-director-agent/data-director` (the app and
every in-tree agent, from `docker/release.Dockerfile`) for `linux/amd64` and `linux/arm64`, and
smoke-tests each platform before anything is pushed. A push to `main` publishes it as `edge`;
the `images` job of `release.yaml` calls the same workflow when a release includes the app, and
tags it with the app's version. One image serves every package, so its tag follows the app's
version, and every package's version is in its `org.data-director.package-versions` label. It is
pushed with `GITHUB_TOKEN` and needs no secret. [Container images](deploy/README.md#container-images)
says how to run it.

Set-up, once, by a maintainer: after the first push, make the
[package](https://github.com/orgs/data-director-agent/packages/container/package/data-director)
public, and check that it is linked to this repository.

## Version numbers

Every package stays on `0.x` alpha pre-releases (`0.2.0-alpha`, `0.2.0-alpha.1`, …) until the
contract and its schemas are stable. uv reads these as `0.2.0a0`, `0.2.0a1`.

- A breaking change raises the minor version, not the major one; a feature or fix raises the
  alpha number.
- Moving any package to 1.0 is a deliberate decision, made by changing
  `release-please-config.json` in its own pull request, not by a commit's type.

TODO(#260): define the criteria for 1.0.

## Versions packages require of each other

Inside the workspace, uv resolves `data-director-sdk` and the other members to their own
directories and ignores any version. A built wheel keeps the requirement as written, so each
member names a lower bound for every member it needs at run time (`data-director-sdk>=0.2.0a0`);
`scripts/check_boundaries.py` rejects one without a version ([System and boundaries](docs/specs/system.md)).

- The lower bound is the oldest release the package works with. Raise it in the same pull request
  as a change that uses something newer. A release does not move it.
- There is no upper bound yet. release-please raises a minor version for a breaking change, and an
  upper bound such as `<0.3` would stop `uv lock` resolving in the release pull request until
  someone edited it. TODO(#276): decide how upper bounds move with releases before any package is
  published.

## Making a release

Merge the release pull request at a milestone, such as a deployment or a hand-over to testers, not
after every feature.

1. Open the release pull request and read what it holds: the packages, their new versions and the
   changelog entries. A wrong entry is fixed with a commit override (see
   below), not by editing the release pull request.
2. Wait for CI, including the lock-file refresh, to pass.
3. Merge it. Confirm that the tags and GitHub releases exist.

The deployment follows `main` (`deploy/deploy.sh`), not tags, so a release does not change what is
deployed.

## Archiving in Zenodo

Each merged release pull request is also archived in [Zenodo](https://zenodo.org/), so that the
software has a DOI. The repository has one Zenodo record. Its concept DOI always resolves to the
latest version and is the one to cite in general; each release publishes a new version with a DOI
of its own.

- `release.yaml` calls `.github/workflows/zenodo.yml` when merging the release pull request
  creates at least one release. One merge makes one version, however many packages it released.
- `zenodo.yml` zips the merge commit with `git archive` and runs `scripts/zenodo.py release`, which
  makes a new version, replaces its file with the zip and publishes it.
- The record's metadata comes from `CITATION.cff`: title, abstract, authors, keywords, licence and
  references. The description also records the commit and every package's version from
  `.release-please-manifest.json`. Correct the metadata there, not in Zenodo, since the next
  release overwrites it.
- Keep Zenodo's own GitHub integration switched off for this repository. It archives every GitHub
  release, and release-please makes one for each package, so it would duplicate versions.
- If the job fails, run **Zenodo** from the Actions tab with the release commit as `ref`. It
  carries on with a draft the failed run left; once a version is published, running it again
  publishes another, so check Zenodo first.

`uv run scripts/zenodo.py release --archive <zip> --dry-run` prints the metadata without calling
Zenodo.

### Setting it up

This is done once, by a Zenodo account holder who will own the record.

1. In Zenodo, under Applications, create a personal access token with the scopes `deposit:write`
   and `deposit:actions`.
2. Create the draft record and reserve its DOI. Nothing is public yet.

   ```sh
   ZENODO_TOKEN=<token> uv run scripts/zenodo.py create
   ```

   To rehearse first, make a token on [Zenodo Sandbox](https://sandbox.zenodo.org/) and set
   `ZENODO_API=https://sandbox.zenodo.org/api` for `create` and `release`.

3. In the repository's settings, create an environment named `zenodo` with the secret
   `ZENODO_TOKEN` and the variable `ZENODO_RECORD_ID` set to the record ID that `create` printed.
   Restrict the environment to the `main` branch.
4. Add the concept DOI that `create` printed to `CITATION.cff` as `doi:` in a pull request.
5. To publish the first version without waiting for a release, run **Zenodo** from the Actions tab.

Until `ZENODO_RECORD_ID` is set, `zenodo.yml` does nothing.

## When something is wrong

- **A tag is missing.** release-please counts commits from the tag `<component>-v<version>` that
  matches the version in `.release-please-manifest.json`, so every version in the manifest must
  have its tag. Push the missing tag, then run `release-please` from the Actions tab
  (`workflow_dispatch`) to rebuild the release pull request.
- **A commit is wrongly classified.** Edit the description of the merged pull request that produced
  it to add a `BEGIN_COMMIT_OVERRIDE` block giving the intended subject, then run the workflow
  again. See release-please's documentation for the format.
- **A version needs setting directly.** Add a `Release-As: x.y.z` trailer to a commit that touches
  the package.

## Keeping this page current

Change this page in the same pull request as any change to `release-please-config.json`,
`.release-please-manifest.json`, `.github/workflows/release.yaml`,
`.github/workflows/zenodo.yml` or `scripts/zenodo.py`.
