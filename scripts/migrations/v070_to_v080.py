"""
Migration from v0.7.0-beta to v0.8.0-beta.

Changes:
- Protected stories with AES-GCM encryption and unlock overlay
- Glossary CSV support (alternative to markdown files)
- Gallery/collection system with browse, search, and sort
- Featured objects on homepage
- Share panel redesign with key sharing
- New collection_interface config section
- Renamed hide_stories/hide_collections to skip_stories/skip_collections

Version: v0.8.0-beta
"""

from typing import List, Dict
import os
import re
from .base import BaseMigration


class Migration070to080(BaseMigration):
    """Migration from v0.7.0 to v0.8.0 - Content & Access release."""

    from_version = "0.7.0-beta"
    to_version = "0.8.0-beta"
    description = "Protected stories, glossary CSV, gallery system, featured objects"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update configuration
        print("  Phase 1: Updating configuration...")
        changes.extend(self._update_configuration())

        # Phase 2: Update .gitignore
        print("  Phase 2: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # Phase 3: Update framework files from GitHub
        print("  Phase 3: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 4: Update version
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.8.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.8.0-beta ({today})")

        return changes

    def _update_configuration(self) -> List[str]:
        """Update _config.yml with new settings."""
        changes = []

        content = self._read_file('_config.yml')
        if not content:
            return changes

        # 1. Add collection_interface section if missing
        if 'collection_interface:' not in content:
            # Insert after story_interface section
            collection_block = """
# Collection Interface Settings
collection_interface:
  browse_and_search: true # Set to false to disable filtering sidebar and search on objects page
  show_link_on_homepage: true # Set to false to hide "View the objects" link from homepage
  show_sample_on_homepage: false # Set to true to show a sample of objects on homepage
  featured_count: 4 # Number of objects to show on homepage (default 4)
"""
            # Find the end of story_interface section
            lines = content.split('\n')
            insert_after = None
            in_story_interface = False
            for i, line in enumerate(lines):
                if line.startswith('story_interface:'):
                    in_story_interface = True
                    continue
                if in_story_interface:
                    if line and not line.startswith(' ') and not line.startswith('\t') and line.strip():
                        insert_after = i
                        break
            if insert_after is not None:
                lines.insert(insert_after, collection_block)
                content = '\n'.join(lines)
                changes.append("Added collection_interface section to _config.yml")

        # 2. Add show_on_homepage to story_interface if missing
        if 'show_on_homepage' not in content:
            content = content.replace(
                'story_interface:\n',
                'story_interface:\n  show_on_homepage: true # Set to false to hide stories section from homepage\n'
            )
            changes.append("Added show_on_homepage to story_interface in _config.yml")

        # 3. Rename hide_stories to skip_stories (preserve value)
        hide_stories_match = re.search(
            r'^(\s*)hide_stories:\s*(true|false)',
            content, re.MULTILINE
        )
        if hide_stories_match:
            indent = hide_stories_match.group(1)
            value = hide_stories_match.group(2)
            content = content.replace(
                hide_stories_match.group(0),
                f'{indent}skip_stories: {value} # (Renamed from hide_stories)'
            )
            changes.append("Renamed hide_stories to skip_stories in _config.yml")

        # 4. Rename hide_collections to skip_collections (preserve value)
        hide_collections_match = re.search(
            r'^(\s*)hide_collections:\s*(true|false)',
            content, re.MULTILINE
        )
        if hide_collections_match:
            indent = hide_collections_match.group(1)
            value = hide_collections_match.group(2)
            content = content.replace(
                hide_collections_match.group(0),
                f'{indent}skip_collections: {value} # (Renamed from hide_collections)'
            )
            changes.append("Renamed hide_collections to skip_collections in _config.yml")

        self._write_file('_config.yml', content)
        return changes

    def _update_gitignore(self) -> List[str]:
        """Add new entries to .gitignore."""
        changes = []

        # search-data.json is generated at build time
        search_entries = [
            'search-data.json',
        ]

        if self._ensure_gitignore_entries(search_entries, '# Generated data'):
            changes.append("Added search-data.json to .gitignore")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        # Note: .github/workflows/ files are NOT included here
        # (GitHub Actions security restriction - must be done manually)
        framework_files = {
            # Glossary CSV
            'scripts/telar/glossary.py': 'Glossary CSV support',
            'scripts/generate_collections.py': 'Glossary CSV generation + frontmatter fields',
            # Protected Stories
            'scripts/telar/encryption.py': 'Protected stories encryption',
            'scripts/telar/processors/project.py': 'Protected column support',
            'scripts/telar/core.py': 'Encryption post-processing',
            '_includes/share-panel.html': 'Share panel redesign',
            '_sass/_share.scss': 'Share panel styles',
            'assets/js/share-panel.js': 'Share panel functionality',
            'assets/js/story-unlock.js': 'Story unlock decryption',
            '_layouts/story.html': 'Unlock overlay integration',
            '_sass/_story.scss': 'Unlock overlay styles',
            '_layouts/index.html': 'Protected story indicator + featured objects',
            # Gallery/Collection System
            'scripts/telar/csv_utils.py': 'Column mapping for materias',
            'scripts/telar/search.py': 'Search data generator',
            'scripts/telar/iiif_metadata.py': 'Updated metadata fallback fields',
            'scripts/telar/processors/objects.py': 'Featured objects selection',
            '_layouts/objects-index.html': 'Browse/search UI layout',
            '_includes/header.html': 'skip_collections rename',
            '_sass/_layout.scss': 'Browse/search, featured objects, protected card styles',
            'assets/js/objects-filter.js': 'Filter/search/sort functionality',
            'assets/js/lunr.min.js': 'Lunr.js search library',
            'assets/js/telar-story/main.js': 'Event-driven init for encrypted stories',
            '_data/languages/en.yml': 'All new strings',
            '_data/languages/es.yml': 'Spanish translations',
            # Dependencies
            'requirements.txt': 'Added cryptography dependency',
            'pytest.ini': 'Updated markers',
            # Tests
            'tests/unit/test_apply_metadata.py': 'Updated for new fields',
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
        """English manual steps for v0.8.0 migration."""
        return [
            {
                'description': '''**Update GitHub Actions workflows:**

Due to GitHub security restrictions, workflow files cannot be updated automatically.
Please manually copy these files from the Telar repository:

1. `.github/workflows/build.yml` - Updated with search data generation step

Download from: https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows'
            },
            {
                'description': '''**If you use GitHub Pages:**

No further actions needed beyond updating the workflow files above. Your site will automatically use the new features when it rebuilds.''',
            },
            {
                'description': '''**If you work with your site locally:**

A new Python dependency is required for protected stories:

```
pip install cryptography>=41.0.0
```

Or install all dependencies:

```
pip install -r requirements.txt
```''',
            },
            {
                'description': '''**New features available (optional):**

1. **Protected stories**: Add `protected` column to project.csv (yes/no) and set `story_key` in _config.yml
2. **Glossary CSV**: Create `components/structures/glossary.csv` as an alternative to individual markdown files
3. **Browse & search**: Automatically enabled on the objects page (disable with `browse_and_search: false` in _config.yml)
4. **Featured objects**: Set `show_sample_on_homepage: true` in _config.yml to show objects on the homepage

See the documentation for details on each feature.''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.8.0 migration."""
        return [
            {
                'description': '''**Actualiza los workflows de GitHub Actions:**

Debido a restricciones de seguridad de GitHub, los archivos de workflow no pueden actualizarse automaticamente.
Por favor copia manualmente estos archivos del repositorio de Telar:

1. `.github/workflows/build.yml` - Actualizado con paso de generacion de datos de busqueda

Descarga de: https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows'
            },
            {
                'description': '''**Si usas GitHub Pages:**

No se requieren acciones adicionales aparte de actualizar los archivos de workflow. Tu sitio usara automaticamente las nuevas funciones cuando se reconstruya.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Se requiere una nueva dependencia de Python para historias protegidas:

```
pip install cryptography>=41.0.0
```

O instala todas las dependencias:

```
pip install -r requirements.txt
```''',
            },
            {
                'description': '''**Nuevas funciones disponibles (opcionales):**

1. **Historias protegidas**: Agrega la columna `protected` a project.csv (yes/no) y configura `story_key` en _config.yml
2. **Glosario CSV**: Crea `components/structures/glossary.csv` como alternativa a archivos markdown individuales
3. **Explorar y buscar**: Se activa automaticamente en la pagina de objetos (desactiva con `browse_and_search: false` en _config.yml)
4. **Objetos destacados**: Configura `show_sample_on_homepage: true` en _config.yml para mostrar objetos en la pagina principal

Consulta la documentacion para detalles sobre cada funcion.''',
            },
        ]
