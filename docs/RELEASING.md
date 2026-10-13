# Releasing PhonixPBX

Versions follow [Semantic Versioning](https://semver.org/) in PEP 440 form (`1.2.0`,
`1.2.0rc1`, `1.3.0.dev0`). Pushing a tag `v<version>` builds and publishes everything:

- `image.yml` builds the disk images, update bundles and LXC/Incus tarballs, and creates
  the GitHub release with `SHA256SUMS` and the CHANGELOG section as release notes.
- `container.yml` pushes `ghcr.io/phonixpbx/phonix:<version>` and, for final releases,
  `latest`.

Both workflows run `scripts/release.sh check <tag>` first and fail if the tag, the version
files and CHANGELOG.md disagree.

## Before the release

- CI is green on `main`.
- `scripts/i18n.sh update` adds no new strings, and `tests/test_i18n.py` passes.
- The repository secrets `PHONIX_UPDATE_SIGNING_KEY`, `PHONIX_ABUILD_KEY` and
  `PHONIX_ABUILD_KEY_PUB` are set. Without them, the build signs with throwaway keys and
  installed systems reject its update bundles.

## Release

1. Set the version in `pyproject.toml`, `phonix/__init__.py` and the `pkgver` fallback in
   `packaging/apk/phonix/APKBUILD` (apk form, see `apk_version` in `image/lib/common.sh`).
2. Regenerate the golden files, whose headers contain the version:
   `UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_generators.py tests/legacy`
3. Rename `## [Unreleased]` in `CHANGELOG.md` to `## [X.Y.Z] - YYYY-MM-DD` and add the
   link at the bottom.
4. Check with `scripts/release.sh check vX.Y.Z` and `scripts/release.sh notes vX.Y.Z`.
5. Commit with `release: X.Y.Z` and push to `main`.
6. Tag and push the tag:

   ```sh
   git tag -s vX.Y.Z -m "PhonixPBX X.Y.Z"
   git push origin vX.Y.Z
   ```

   The tag must be exactly `v` followed by the version, because the update check in the web
   interface compares the GitHub release tag with the installed version.
7. Check the GitHub release assets and the ghcr.io tags.

## After the release

Start the next development version with a commit `release: start X.Y+1.0 development`:
set `X.Y+1.0.dev0` (`X.Y+1.0_pre0` in the APKBUILD), regenerate the golden files and add
an empty `## [Unreleased]` section to `CHANGELOG.md`.
