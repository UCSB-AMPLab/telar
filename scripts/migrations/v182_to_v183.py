"""
Migration from v1.8.2 to v1.8.3.

v1.8.3 is a patch with two corrections: the build on Ubuntu 26.04 runners,
and image, audio and share paths on a site served at a domain root. Only
framework files change, so this migration installs them and does nothing
else.

Framework files (FRAMEWORK_FILES, installed atomically from the v1.8.3 tag):

  - `Gemfile.lock`, which gains the `x86_64-linux` platform. GitHub's
    Ubuntu 26.04 runners are x86_64 Linux, and bundler runs frozen in the
    build workflow, where it may not add a platform to the lock. With a lock
    that names only `ruby` and `arm64-darwin`, bundler resolves the source
    gems, compiles google-protobuf, and the build fails. With the platform in
    the lock it installs the prebuilt gems. The lock alone carries the
    platform, so a site that kept its old lock would keep failing on those
    runners.

  - The story, share panel and IIIF URL warning bundles with their source
    maps and the modules they are built from, and `_layouts/story.html`,
    which puts the site's `baseurl` in a meta tag. On a site served at a
    domain root (`baseurl: ""`) the story bundle's base path came out as `/`,
    so the addresses of panel images, audio and IIIF tiles began with `//`,
    which a browser reads as another host. The share panel and the IIIF URL
    warning took the first segment of the page address as the site's prefix,
    which on such a site is a story or page name; they now read the meta
    tag. The bundles ship with their sources, as in every release since the
    bundles were introduced, so a site that rebuilds them gets the same
    files.

  - The root documents and dependency manifests that carry the version.

Not delivered:

  - `tests/` — Telar's own test suite, listed in `scripts/dev-only-files.txt`.
  - `scripts/migrations/` and the engine — they ship only in the verified
    release tarball, which `scripts/upgrade.py` downloads.
  - `.github/workflows/*` — the upgrade's GITHUB_TOKEN carries no
    `workflows: write`. No workflow changes in this release.
  - `_config.yml` — the site's own. The engine writes the version stamp.

No configuration key, spreadsheet column or content file changes, so there
are no manual steps.

The version stamp (telar.version -> 1.8.3) is not written here. The engine
applies it once after every migration step and the regeneration succeed.

Version: v1.8.3
"""

from typing import List

from .base import BaseMigration, ChangeRecord


# Fetched from the v1.8.3 tag and written atomically as one set.
FRAMEWORK_FILES = {
    # Root documents and dependency manifests.
    'README.md': 'Project README for v1.8.3',
    'CHANGELOG.md': 'Release history through v1.8.3',
    'package.json': 'The version, and the banners of the rebuilt bundles',
    'package-lock.json': 'Lockfile matching package.json — always ships with it',
    # The build workflow runs bundler frozen, which cannot add a platform to
    # the lock: without x86_64-linux in it, the build on an Ubuntu 26.04
    # runner compiles google-protobuf and fails.
    'Gemfile.lock': 'Resolved Ruby dependencies, with prebuilt gems for x86_64 Linux runners',

    # The story page layout.
    '_layouts/story.html': 'Story layout — puts the site baseurl in a meta tag the share panel and the warning read',

    # The story engine.
    'assets/js/telar-story.js': 'Story bundle, rebuilt from the module below',
    'assets/js/telar-story.js.map': 'Source map for the story bundle',
    'assets/js/telar-story/utils.js': 'Base path is empty, not a slash, at a domain root',

    # The share panel.
    'assets/js/share-panel.js': 'Share panel bundle, rebuilt from the module below',
    'assets/js/share-panel.js.map': 'Source map for the share panel bundle',
    'assets/js/share-panel/main.js': 'Share links take the base path from the layout meta tag',

    # The IIIF URL warning.
    'assets/js/iiif-url-warning.js': 'IIIF URL warning bundle, rebuilt from the module below',
    'assets/js/iiif-url-warning.js.map': 'Source map for the IIIF URL warning bundle',
    'assets/js/iiif-url-warning/main.js': 'The site address takes the base path from the layout meta tag',
}


class Migration182to183(BaseMigration):
    """Migration from v1.8.2 to v1.8.3 — the framework files the patch changes."""

    from_version = "1.8.2"
    to_version = "1.8.3"
    release_date = None  # tag v1.8.3 — fill in at Phase 4
    description = ("v1.8.3 framework files: prebuilt gems on Ubuntu 26.04 runners, and "
                   "image, audio and share paths for a site at a domain root")

    _TARGET_TAG = "v1.8.3"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        print("  Phase 1: Updating framework files...")
        return self._apply_framework_files(FRAMEWORK_FILES)
