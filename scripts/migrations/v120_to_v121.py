"""
Migration from v1.2.0 to v1.2.1.

Demo Content Fetch Tolerance patch:
- scripts/fetch_demo_content.py now tolerates v-prefixed telar.version
  values in _config.yml (e.g. "v1.2.0"), which an earlier Telar Compositor
  upgrade flow wrote into some sites. Without this fix the script silently
  built sites with no demo content. CHANGELOG and README updated.

1 framework file fetched from GitHub, version bumped, no content
transforms, no manual steps required for users (the fix is automatic).

Version: v1.2.1
"""

from typing import List, Dict
from .base import BaseMigration


class Migration120to121(BaseMigration):
    """Migration from v1.2.0 to v1.2.1 - Demo Content Fetch Tolerance."""

    from_version = "1.2.0"
    to_version = "1.2.1"
    description = "Demo content fetch tolerates v-prefixed telar.version values"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Update version
        print("  Phase 2: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("1.2.1", today):
            changes.append(f"Updated _config.yml: version 1.2.1 ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Fetch framework files from GitHub main branch."""
        changes = []

        framework_files = {
            'scripts/fetch_demo_content.py': 'Demo content fetcher (v-prefix tolerance fix)',
            'README.md': 'README (v1.2.1 badges and beta notice, bilingual)',
            'CHANGELOG.md': 'CHANGELOG (v1.2.1 release notes)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return manual steps in user's language."""
        lang = self._detect_language()
        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v1.2.1 migration."""
        return [
            {
                'description': '''**Bug fix applied automatically — no action required.**

This patch updates `scripts/fetch_demo_content.py` so it tolerates v-prefixed `telar.version` values in `_config.yml` (for example `version: "v1.2.0"` instead of `version: "1.2.0"`). An earlier version of the Telar Compositor's upgrade flow wrote v-prefixed strings into some sites, which caused the demo content fetcher to silently fail and build sites with no demo content. The fix is in the framework file you just received from this upgrade — no further steps are needed on your end.

If your `_config.yml` has a v-prefixed version string, you may leave it as-is; the script now handles both forms. If you prefer, you can also remove the leading `v` manually under the `telar:` section to keep the file consistent with current Telar conventions.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v1.2.1 migration."""
        return [
            {
                'description': '''**Corrección aplicada automáticamente — no tienes que hacer nada.**

Esta actualización corrige el script que descarga el contenido de demostración (`scripts/fetch_demo_content.py`) para que ahora acepte valores de `telar.version` en `_config.yml` que empiecen con "v" (por ejemplo, `version: "v1.2.0"` en vez de `version: "1.2.0"`). Una versión anterior del flujo de actualización del Compositor de Telar escribía estos valores con "v" en algunos sitios, y eso hacía que la descarga del contenido de demostración fallara sin avisar — así que esos sitios se construían sin contenido de demostración. La corrección ya está en el archivo de framework que recibiste con esta actualización; no tienes que hacer nada más.

Si tu `_config.yml` tiene una versión con "v", puedes dejarla así: el script ahora reconoce las dos formas. Si prefieres dejar el archivo más consistente con el formato actual de Telar, también puedes quitar la "v" a mano en la sección `telar:`.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
