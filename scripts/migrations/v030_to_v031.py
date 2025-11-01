"""Migration from v0.3.0-beta to v0.3.1-beta"""

from typing import List, Dict
from .base import BaseMigration


class Migration030to031(BaseMigration):
    """
    Migration from Telar v0.3.0-beta to v0.3.1-beta.

    v0.3.1 Changes (from CHANGELOG):
    - Fixed thumbnail loading bugs
    - Fixed local image viewer bugs
    - Fixed objects gallery thumbnails

    All fixes were in Liquid templates - no file updates needed for existing sites.
    """

    from_version = "0.3.0-beta"
    to_version = "0.3.1-beta"
    description = "Bug fixes in framework templates"

    def check_applicable(self) -> bool:
        """This migration is always applicable - it's just a version bump."""
        return True

    def apply(self) -> List[str]:
        """
        Apply migration from v0.3.0 to v0.3.1.

        v0.3.1 only contained bug fixes in framework templates,
        no user-facing changes or file updates required.
        """
        print("\n📦 Migrating from v0.3.0-beta to v0.3.1-beta...")
        print("   This version contains only template bug fixes.")
        print("   No file updates required for your site.")

        return []

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """No manual steps needed for this migration."""
        return []
