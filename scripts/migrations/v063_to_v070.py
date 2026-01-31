"""
Migration from v0.6.3-beta to v0.7.0-beta.

This is a major infrastructure release that adds:
- Test infrastructure (pytest, Playwright, Vitest)
- Modular Python scripts (telar/ package)
- Modular JavaScript (ES modules bundled with esbuild)
- SCSS partials (split from monolithic stylesheet)
- CI workflow consolidation

Changes:
- Split csv_to_json.py into 14-module telar/ package
- Split story.js into 6 ES modules (bundled by esbuild)
- Split telar.scss into 9 SCSS partials
- Added test infrastructure (305 tests total)
- Consolidated CI test workflows
- Added accessibility fixes (WCAG AA compliance)
- Node.js now required for builds (esbuild)

Version: v0.7.0-beta
"""

from typing import List, Dict
import os
import shutil
from .base import BaseMigration


class Migration063to070(BaseMigration):
    """Migration from v0.6.3 to v0.7.0 - Infrastructure & Code Quality release."""

    from_version = "0.6.3-beta"
    to_version = "0.7.0-beta"
    description = "Test infrastructure, modular code, SCSS partials, accessibility fixes"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Create new directories
        print("  Phase 1: Creating directories...")
        changes.extend(self._create_directories())

        # Phase 2: Clean up deprecated files
        print("  Phase 2: Cleaning up deprecated files...")
        changes.extend(self._cleanup_deprecated_files())

        # Phase 3: Update .gitignore
        print("  Phase 3: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # Phase 4: Update framework files from GitHub
        print("  Phase 4: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 5: Update version
        print("  Phase 5: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.7.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.7.0-beta ({today})")

        return changes

    def _create_directories(self) -> List[str]:
        """Create new directories for v0.7.0 structure."""
        changes = []

        directories = [
            # Test infrastructure
            'tests',
            'tests/unit',
            'tests/e2e',
            'tests/js',
            'tests/fixtures',
            # Python package
            'scripts/telar',
            'scripts/telar/processors',
            # JavaScript modules
            'assets/js/telar-story',
            # SCSS partials
            '_sass',
        ]

        for dir_path in directories:
            full_path = os.path.join(self.repo_root, dir_path)
            if not os.path.exists(full_path):
                os.makedirs(full_path, exist_ok=True)
                changes.append(f"Created directory: {dir_path}")

        return changes

    def _cleanup_deprecated_files(self) -> List[str]:
        """Remove deprecated files from v0.6.x."""
        changes = []

        # Individual files to remove
        files_to_remove = [
            'assets/js/story.js',  # Replaced by bundled telar-story.js
            'scripts/requirements.txt',  # Consolidated to root requirements.txt
        ]

        for rel_path in files_to_remove:
            full_path = os.path.join(self.repo_root, rel_path)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    changes.append(f"Removed deprecated file: {rel_path}")
                except Exception as e:
                    changes.append(f"Warning: Could not remove {rel_path}: {e}")

        return changes

    def _update_gitignore(self) -> List[str]:
        """Add new entries to .gitignore for build artifacts."""
        changes = []

        # Entries to add for JavaScript build artifacts
        js_entries = [
            'assets/js/telar-story.js',
            'assets/js/telar-story.js.map',
        ]

        if self._ensure_gitignore_entries(js_entries, '# JavaScript build artifacts'):
            changes.append("Added JavaScript build artifacts to .gitignore")

        # Entries for Python
        python_entries = [
            '__pycache__/',
            '*.py[cod]',
            '.pytest_cache/',
        ]

        if self._ensure_gitignore_entries(python_entries, '# Python'):
            changes.append("Added Python cache entries to .gitignore")

        # Entries for Node.js
        node_entries = [
            'node_modules/',
        ]

        if self._ensure_gitignore_entries(node_entries, '# Node.js'):
            changes.append("Added Node.js entries to .gitignore")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        # Framework files to fetch
        # Note: .github/workflows/ files are NOT included here
        # (GitHub Actions security restriction - must be done manually)
        framework_files = {
            # Layouts
            '_layouts/story.html': 'Story layout (accessibility fixes, telar-story.js)',

            # SCSS partials (new in v0.7.0)
            '_sass/_mixins.scss': 'SCSS mixins (tabs, UV hiding)',
            '_sass/_typography.scss': 'Typography styles',
            '_sass/_panels.scss': 'Layer panel styles',
            '_sass/_widgets.scss': 'Widget component styles',
            '_sass/_story.scss': 'Story step styles',
            '_sass/_layout.scss': 'Page layout styles',
            '_sass/_embed.scss': 'Embed mode styles',
            '_sass/_share.scss': 'Share widget styles',
            '_sass/_viewer.scss': 'IIIF viewer styles',
            'assets/css/telar.scss': 'Main SCSS (now imports partials)',

            # JavaScript modules (new in v0.7.0)
            'assets/js/telar-story/state.js': 'Centralised state object',
            'assets/js/telar-story/utils.js': 'Shared utility functions',
            'assets/js/telar-story/viewer.js': 'Viewer card lifecycle',
            'assets/js/telar-story/panels.js': 'Panel system',
            'assets/js/telar-story/navigation.js': 'Navigation modes',
            'assets/js/telar-story/main.js': 'Entry point',

            # Python telar package (new in v0.7.0)
            'scripts/telar/__init__.py': 'Package init with public API',
            'scripts/telar/config.py': 'Language loading, string interpolation',
            'scripts/telar/csv_utils.py': 'CSV utilities, column normalisation',
            'scripts/telar/images.py': 'Image processing, path validation',
            'scripts/telar/iiif_metadata.py': 'IIIF metadata extraction',
            'scripts/telar/glossary.py': 'Glossary loading and linking',
            'scripts/telar/widgets.py': 'Widget parsing and rendering',
            'scripts/telar/markdown.py': 'Markdown processing',
            'scripts/telar/demo.py': 'Demo content fetching',
            'scripts/telar/core.py': 'Build orchestration',
            'scripts/telar/processors/__init__.py': 'Processors subpackage init',
            'scripts/telar/processors/project.py': 'Project CSV processor',
            'scripts/telar/processors/objects.py': 'Objects CSV processor',
            'scripts/telar/processors/stories.py': 'Story CSV processor',

            # Updated scripts
            'scripts/csv_to_json.py': 'Backward-compatible wrapper',
            'scripts/generate_collections.py': 'Updated imports',
            'scripts/build_local_site.py': 'Added JS build step',
            'scripts/discover_sheet_gids.py': 'Updated version header',
            'scripts/fetch_demo_content.py': 'Updated version header',
            'scripts/fetch_google_sheets.py': 'Updated version header',
            'scripts/generate_iiif.py': 'Updated version header',
            'scripts/upgrade.py': 'Updated version header',

            # Test infrastructure (new in v0.7.0)
            'pytest.ini': 'Pytest configuration',
            'vitest.config.js': 'Vitest configuration',
            'tests/__init__.py': 'Test package init',
            'tests/unit/__init__.py': 'Unit test package init',
            'tests/e2e/__init__.py': 'E2E test package init',
            'tests/e2e/conftest.py': 'Playwright fixtures',
            'tests/unit/test_csv_utils.py': 'CSV utility tests',
            'tests/unit/test_column_processing.py': 'Column processing tests',
            'tests/unit/test_inline_content.py': 'Inline content tests',
            'tests/unit/test_google_sheets.py': 'Google Sheets tests',
            'tests/unit/test_widget_parsing.py': 'Widget parsing tests',
            'tests/unit/test_glossary_links.py': 'Glossary link tests',
            'tests/unit/test_iiif_metadata.py': 'IIIF metadata tests',
            'tests/unit/test_image_processing.py': 'Image processing tests',
            'tests/unit/test_carousel_widget.py': 'Carousel widget tests',
            'tests/unit/test_extract_credit.py': 'Credit extraction tests',
            'tests/unit/test_project_processing.py': 'Project processing tests',
            'tests/unit/test_apply_metadata.py': 'Metadata fallback tests',
            'tests/unit/test_process_widgets.py': 'Widget pipeline tests',
            'tests/unit/test_upgrade_utils.py': 'Upgrade utility tests',
            'tests/e2e/test_story_navigation.py': 'Story navigation E2E tests',
            'tests/e2e/test_embed_mode.py': 'Embed mode E2E tests',
            'tests/e2e/test_panel_interactions.py': 'Panel interaction E2E tests',
            'tests/js/state.test.js': 'State object tests',
            'tests/js/utils.test.js': 'Utility function tests',
            'tests/js/viewer.test.js': 'Viewer function tests',
            'tests/js/panels.test.js': 'Panel function tests',

            # GitHub configuration (non-workflow files can be auto-fetched)
            '.github/dependabot.yml': 'Dependabot configuration for dependency updates',

            # Build configuration
            'package.json': 'Node.js dependencies (esbuild, vitest)',
            'requirements.txt': 'Python dependencies (pytest, playwright)',

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
        """English manual steps for v0.7.0 migration."""
        return [
            {
                'description': '''**Update GitHub Actions workflows:**

Due to GitHub security restrictions, workflow files cannot be updated automatically.
Please manually copy these files from the Telar repository:

1. `.github/workflows/build.yml` - Updated with Node.js setup and JS build step
2. `.github/workflows/upgrade.yml` - Updated version header
3. `.github/workflows/telar-tests.yml` - NEW: Runs Python and JavaScript tests

Download from: https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows'
            },
            {
                'description': '''**If you work with your site locally:**

Node.js is now required to build the JavaScript bundle. Install dependencies:

```
npm install
```

The build script now includes a JavaScript build step:

```
python3 scripts/build_local_site.py
```

Or build JavaScript separately:

```
npm run build:js
```''',
            },
            {
                'description': '''**Optional: Run the test suite locally**

This release includes 305 automated tests. To run them:

**Python tests (235 tests):**
```
python3 -m pytest tests/unit/ -v
```

**JavaScript tests (35 tests):**
```
npm run test:js
```

**E2E tests (35 tests) - requires Playwright:**
```
playwright install chromium
python3 -m pytest tests/e2e/ -v
```''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.7.0 migration."""
        return [
            {
                'description': '''**Actualiza los workflows de GitHub Actions:**

Debido a restricciones de seguridad de GitHub, los archivos de workflow no pueden actualizarse automaticamente.
Por favor copia manualmente estos archivos del repositorio de Telar:

1. `.github/workflows/build.yml` - Actualizado con configuracion de Node.js y paso de build JS
2. `.github/workflows/upgrade.yml` - Version actualizada
3. `.github/workflows/telar-tests.yml` - NUEVO: Ejecuta pruebas de Python y JavaScript

Descarga de: https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows'
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Node.js ahora es necesario para construir el bundle de JavaScript. Instala las dependencias:

```
npm install
```

El script de construccion ahora incluye un paso de build de JavaScript:

```
python3 scripts/build_local_site.py
```

O construye JavaScript por separado:

```
npm run build:js
```''',
            },
            {
                'description': '''**Opcional: Ejecuta las pruebas localmente**

Esta version incluye 305 pruebas automatizadas. Para ejecutarlas:

**Pruebas de Python (235 pruebas):**
```
python3 -m pytest tests/unit/ -v
```

**Pruebas de JavaScript (35 pruebas):**
```
npm run test:js
```

**Pruebas E2E (35 pruebas) - requiere Playwright:**
```
playwright install chromium
python3 -m pytest tests/e2e/ -v
```''',
            },
        ]
