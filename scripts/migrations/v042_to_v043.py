"""
Migration from Telar v0.4.2-beta to v0.4.3-beta.

Runtime/tooling update, no configuration or user-content changes:
- generate_iiif.py gains EXIF orientation handling
- story.js gains iPad touch scrolling support
- build.yml gains IIIF regeneration on config changes

Previously this migration was orphaned: it did not subclass BaseMigration, took
a different __init__ signature, returned a dict, and depended on `requests`, so
it was never imported into upgrade.py's MIGRATIONS list. The 0.4.2 -> 0.4.3 step
was therefore skipped for every site. Ported onto BaseMigration and registered
so the chain is continuous.

Version: v0.4.3-beta
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus


# Framework files updated in v0.4.3, fetched from the v0.4.3-beta release tag
# and written atomically.
FRAMEWORK_FILES = {
    'scripts/generate_iiif.py': 'EXIF orientation handling in IIIF generation',
    'assets/js/story.js': 'iPad touch scrolling for stories',
    '.github/workflows/build.yml': 'IIIF regeneration on config changes',
}


class Migration042to043(BaseMigration):
    """Migrate from v0.4.2-beta to v0.4.3-beta."""

    from_version = "0.4.2-beta"
    to_version = "0.4.3-beta"
    description = "EXIF orientation, iPad touch scrolling, IIIF config-change detection"

    # Pin framework fetches to the release tag.
    _TARGET_TAG = "v0.4.3-beta"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        print("  Phase 1: Updating framework files...")
        return self._update_framework_files()

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install the changed v0.4.3 framework files (pinned, atomic)."""
        return self._apply_framework_files(FRAMEWORK_FILES)

    def get_manual_steps(self) -> List[Dict[str, str]]:
        return [
            {
                'description': (
                    'Update your GitHub Actions build workflow file: this update adds smart '
                    'detection so IIIF tiles automatically regenerate when you change '
                    '_config.yml settings. Without it you would need to manually regenerate '
                    'tiles after config changes. GitHub Actions workflow files only take '
                    'effect once committed to your repository, so review the build.yml change '
                    'included in this upgrade and merge it along with the rest of the upgrade.'
                ),
                'doc_url': 'https://telar.org/docs'
            },
        ]
