# Releasing

Tayf is pre-1.0. Releases are tags on `main`; no package is published to an
external registry. A tag creates a GitHub Release with source archives, an
SBOM and signed build provenance.

## Preconditions

Before proposing a tag:

1. `main` is green: full CI matrix, pre-commit, security scan, GitGuardian and
   the Docs workflow.
2. `CHANGELOG.md` has a dated section for the version.
3. `backend/app/api/v1/health.py::APP_VERSION` matches the changelog version.
4. `SECURITY.md` lists the version as supported.
5. `TASK_TRACKER.md` rows for the release are `TESTED` with CI evidence.

Do not tag before these are true. Tags are immutable in practice: moving a
published tag breaks consumers and provenance verification.

## Cut a release

From a clean checkout of `main`:

```bash
git tag -a v0.6.0 -m "Tayf 0.6.0"
git push origin v0.6.0
```

The tag push triggers `.github/workflows/release.yml`:

- `verify` runs the backend suite with the 80% coverage floor and builds the
  frontend.
- `build` creates `.tar.gz` and `.zip` source archives, `SHA256SUMS`, a
  CycloneDX SBOM and GitHub build provenance.
- `softprops/action-gh-release` publishes the artifacts with generated release
  notes.

## Dry run

Use the workflow dispatcher when you only want to validate the build path:

```bash
gh workflow run release.yml --repo tibatechapp-ship-it/tayf --field version=v0.6.0
```

A dispatch run uploads artifacts but never creates a GitHub Release because
`github.ref` is not a `v*` tag.

## Dependency updates

Dependabot security updates stay enabled. Routine version-update PRs are
disabled (`open-pull-requests-limit: 0`) so dependency changes are deliberate
and reviewed in the same PR flow as code. Before a release, confirm the open PR
queue contains only changes intended for that release.

## After the tag

- Watch the run: `gh run list --repo tibatechapp-ship-it/tayf --event push --limit 5`.
- Open the release page and confirm the artifacts, SBOM and generated notes.
- Confirm the Docs workflow still deploys to
  `https://tibatechapp-ship-it.github.io/tayf/`.

## Patch releases

For a fix on an existing release, branch from that tag, land the fix through a
PR, then tag the new patch version from the merge commit. Never edit an
existing tag. Update the supported-version table in `SECURITY.md` when an old
line stops receiving fixes.
