# Releasing

How versions are chosen, how a release is made and what a release does and does not change. The
commit and pull request conventions that drive it are in [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

[release-please](https://github.com/googleapis/release-please) does the work; nobody edits a
version or a changelog by hand. `.github/workflows/release-please.yml` runs on every push to
`main`. Its configuration is `release-please-config.json`, and `.release-please-manifest.json`
records the last released version of each package.

- Each package is versioned on its own: `sdk`, `harness`, `workbench`, `app` and each agent in
  `agents/`. Its component name is in the configuration (`agent-director`, `sdk`, …).
- The [Conventional Commit](https://www.conventionalcommits.org/) subjects of the squash-merged
  pull requests that touch a package's directory decide its next version. A commit that touches
  only the package's tests does not.
- release-please keeps **one** release pull request open for every package with a pending release,
  titled `chore(main): release main`, and rewrites it after every merge to `main`. It changes each
  package's `pyproject.toml` (and `app/web/package.json`), `CHANGELOG.md` and the manifest.
- The workflow also refreshes `uv.lock` on the release branch, because release-please cannot.
- Nothing is tagged or published until the release pull request is merged. Merging it tags each
  package `<component>-v<version>` (for example `harness-v0.2.0-alpha`) and creates a GitHub
  release, marked as a pre-release.

## Version numbers

Every package stays on `0.x` alpha pre-releases (`0.2.0-alpha`, `0.2.0-alpha.1`, …) until the
contract and its schemas are stable. uv reads these as `0.2.0a0`, `0.2.0a1`.

- A breaking change raises the minor version, not the major one; a feature or fix raises the
  alpha number.
- Moving any package to 1.0 is a deliberate decision, made by changing
  `release-please-config.json` in its own pull request, not by a commit's type.

TODO(#260): define the criteria for 1.0.

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

## Archiving in ORDA

Each merged release pull request is also archived in [ORDA](https://orda.shef.ac.uk/), the
University of Sheffield's Figshare repository, so that the software has a DOI. The repository has
one ORDA item. Its DOI, reserved once, always resolves to the latest version and is the one to
cite in general; each release publishes a new version of the item with its own DOI ending `.v<N>`.

- `release-please.yml` calls `.github/workflows/orda.yml` when merging the release pull request
  creates at least one release. One merge makes one version, however many packages it released.
- `orda.yml` zips the merge commit with `git archive` and runs `scripts/orda.py release`, which
  replaces the item's file with the zip and publishes it.
- The item's metadata comes from `CITATION.cff`: title, abstract, authors, keywords, licence and
  references. The description also records the commit and every package's version from
  `.release-please-manifest.json`. Correct the metadata there, not in ORDA, since the next release
  overwrites it. The Figshare categories are set in `scripts/orda.py`.
- If the job fails, run **ORDA** from the Actions tab with the release commit as `ref`. Running it
  again publishes a new version, so check ORDA first.

`uv run scripts/orda.py release --archive <zip> --dry-run` prints the metadata without calling ORDA.

### Setting it up

This is done once, by an ORDA account holder who will own the item.

1. In ORDA, under Applications, create a personal token.
2. Create the item and reserve its DOI. Nothing is public yet.

   ```sh
   ORDA_TOKEN=<token> uv run scripts/orda.py create
   ```

3. In the repository's settings, create an environment named `orda` with the secret `ORDA_TOKEN`
   and the variable `ORDA_ARTICLE_ID` set to the item's ID that `create` printed. Restrict the
   environment to the `main` branch.
4. Add the reserved DOI to `CITATION.cff` as `doi:` in a pull request.
5. To publish the first version without waiting for a release, run **ORDA** from the Actions tab.

Until `ORDA_ARTICLE_ID` is set, `orda.yml` does nothing.

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
`.release-please-manifest.json`, `.github/workflows/release-please.yml`,
`.github/workflows/orda.yml` or `scripts/orda.py`.
