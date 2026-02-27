"""
Migration from v0.8.0-beta to v0.8.1-beta.

Changes:
- Spanish-language spreadsheet support (glosario tab routing, instrucciones skip)
- Updated demo content merging with v0.8.0 object fields
- Bilingual glossary CSV fallback in generate_collections and glossary module

Version: v0.8.1-beta
"""

from typing import List, Dict
import os
from .base import BaseMigration


class Migration080to081(BaseMigration):
    """Migration from v0.8.0 to v0.8.1 - Onboarding & demo content release."""

    from_version = "0.8.0-beta"
    to_version = "0.8.1-beta"
    description = "Spanish spreadsheet support, updated demo content, glossary fallbacks"

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
        if self._update_config_version("0.8.1-beta", today):
            changes.append(f"Updated _config.yml: version 0.8.1-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        # Note: .github/workflows/ files are NOT included here
        # (GitHub Actions security restriction - must be done manually)
        framework_files = {
            # Spanish spreadsheet support + glossary routing
            'scripts/fetch_google_sheets.py': 'Glossary tab routing, instrucciones skip',
            # Bilingual glossary CSV fallback
            'scripts/generate_collections.py': 'Glossary CSV bilingual fallback',
            'scripts/telar/glossary.py': 'Glosario.csv fallback support',
            # Demo content v0.8.0 field support
            'scripts/telar/demo.py': 'Demo objects with v0.8.0 metadata fields',
            # Language files (may have minor updates)
            '_data/languages/en.yml': 'English strings',
            '_data/languages/es.yml': 'Spanish strings',
            # Documentation
            'README.md': 'Updated README',
            'CHANGELOG.md': 'Updated changelog',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                full_path = os.path.join(self.repo_root, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path}")
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
        """English manual steps for v0.8.1 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

No further actions needed. Your site will automatically use the new features when it rebuilds.''',
            },
            {
                'description': '''**If you work with your site locally:**

No new dependencies are required. Simply rebuild your site:

```
python3 scripts/csv_to_json.py
python3 scripts/generate_collections.py
bundle exec jekyll build
```''',
            },
            {
                'description': '''**What's new (no action required):**

1. **Spanish glossary tabs**: If your Google Sheet has a `glosario` tab, it will now be recognized and fetched correctly
2. **Demo content**: Demo objects now display with full gallery metadata (year, type, subjects) if you have demo content enabled
3. **Template update**: The Google Sheets template has been simplified from 8 to 6 tabs. If you'd like the latest template, visit https://bit.ly/telar-template''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.8.1 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

No se requieren acciones adicionales. Tu sitio usará automáticamente las nuevas funciones cuando se reconstruya.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

No se requieren nuevas dependencias. Simplemente reconstruye tu sitio:

```
python3 scripts/csv_to_json.py
python3 scripts/generate_collections.py
bundle exec jekyll build
```''',
            },
            {
                'description': '''**Novedades (no requieren acción):**

1. **Pestañas de glosario en español**: Si tu hoja de Google tiene una pestaña `glosario`, ahora se reconocerá y descargará correctamente
2. **Contenido de demostración**: Los objetos de demostración ahora se muestran con metadatos completos de la galería (año, tipo, temas) si tienes el contenido de demostración activado
3. **Actualización de plantilla**: La plantilla de Google Sheets se ha simplificado de 8 a 6 pestañas. Si deseas la plantilla más reciente, visita https://bit.ly/telar-template''',
            },
        ]
