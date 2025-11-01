"""Migration from v0.3.0-beta to v0.3.1-beta"""

import os
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

    def upgrade(self) -> bool:
        """
        Apply migration from v0.3.0 to v0.3.1.

        v0.3.1 only contained bug fixes in framework templates,
        no user-facing changes or file updates required.
        """
        print("\n📦 Migrating from v0.3.0-beta to v0.3.1-beta...")
        print("   This version contains only template bug fixes.")
        print("   No file updates required for your site.")

        return True

    def get_automated_changes(self) -> list:
        """No automated changes needed for this migration."""
        return []

    def get_manual_steps(self) -> list:
        """No manual steps needed for this migration."""
        return []
