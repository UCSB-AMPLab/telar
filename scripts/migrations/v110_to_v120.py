"""
Migration from v1.1.0 to v1.2.0.

Story Structure & UX release:
- Section card TOC on title cards — show_sections flag in project.csv
- Auto ordinal numbers removed from story cards
- Back to Start / Back to Home toggle button
- Deep link parent panel stacking fix
- In-story navigation (navigateToStep, navigateToIntro)

~20 framework files fetched from GitHub, 2 language files fetched,
1 CSV column added (show_sections), version bumped.

Version: v1.2.0
"""

from typing import List, Dict
import csv
import io
import re
from .base import BaseMigration


class Migration110to120(BaseMigration):
    """Migration from v1.1.0 to v1.2.0 - Story Structure & UX."""

    from_version = "1.1.0"
    to_version = "1.2.0"
    description = "Section card TOC, ordinal removal, Back to Start button, deep link fixes"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Update language files from GitHub
        print("  Phase 2: Updating language files...")
        changes.extend(self._update_language_files())

        # Phase 3: Add show_sections column to project.csv
        print("  Phase 3: Updating project CSV...")
        changes.extend(self._update_project_csv())

        # Phase 4: Update version
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("1.2.0", today):
            changes.append(f"Updated _config.yml: version 1.2.0 ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Fetch framework files from GitHub main branch."""
        changes = []

        framework_files = {
            # Layouts
            '_layouts/index.html': 'Homepage (ordinal number removal)',
            '_layouts/story.html': 'Story layout (section TOC, Back to Start button)',
            '_layouts/object.html': 'Object layout (ordinal removal from related stories)',
            # Stylesheets
            '_sass/_story.scss': 'Story styles (TOC, title card layer2 bg, Back to Start)',
            # JavaScript (bundled)
            'assets/js/telar-story.js': 'Bundled story JS',
            'assets/js/telar-story.js.map': 'Source map',
            'assets/js/telar-story/main.js': 'Story entry point (TOC links, Back to Start wiring)',
            'assets/js/telar-story/deep-link.js': 'Deep linking (navigateToStep, navigateToIntro, parent panel fix)',
            'assets/js/telar-story/navigation.js': 'Navigation (onStepChange callback)',
            'assets/js/telar-story/scroll-engine.js': 'Scroll engine (onStepChange callback)',
            # Python scripts
            'scripts/generate_collections.py': 'Collections (show_sections frontmatter, ordinal removal)',
            'scripts/telar/processors/project.py': 'Project processor (show_sections column)',
            'scripts/telar/csv_utils.py': 'CSV utils (mostrar_secciones alias)',
            # Documentation
            'README.md': 'README (v1.2.0 features, bilingual)',
            'CHANGELOG.md': 'CHANGELOG (v1.2.0 release notes)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_language_files(self) -> List[str]:
        """Fetch language files from GitHub (adds sections_heading, back_to_start keys)."""
        changes = []

        language_files = {
            '_data/languages/en.yml': 'English strings (sections_heading, back_to_start added)',
            '_data/languages/es.yml': 'Spanish strings (sections_heading, back_to_start added)',
        }

        for file_path, description in language_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_project_csv(self) -> List[str]:
        """Add show_sections column to project.csv if not already present."""
        changes = []

        # Try English filename first, then Spanish
        csv_path = None
        for candidate in ['telar-content/spreadsheets/project.csv',
                          'telar-content/spreadsheets/proyecto.csv']:
            if self._file_exists(candidate):
                csv_path = candidate
                break

        if not csv_path:
            changes.append("Note: No project.csv found, skipping column addition")
            return changes

        content = self._read_file(csv_path)
        if not content:
            return changes

        # Parse CSV
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        if len(rows) < 1:
            changes.append("Note: project.csv is empty, skipping")
            return changes

        # Check if column already exists
        header = rows[0]
        header_lower = [h.lower().strip() for h in header]
        if 'show_sections' in header_lower or 'mostrar_secciones' in header_lower:
            changes.append("Note: show_sections column already present in project.csv, skipped")
            return changes

        # Detect language from header row
        lang = self._detect_language()

        # Determine column name based on language
        col_name = 'mostrar_secciones' if lang == 'es' else 'show_sections'

        # Find insertion point — after the last existing column
        # (show_sections goes at the end, after protected/private)
        for i, row in enumerate(rows):
            row.append(col_name if i < 2 else '')  # Header rows get column name, data rows get empty

        # Write back
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        self._write_file(csv_path, output.getvalue())

        changes.append(f"Added {col_name} column to {csv_path}")
        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return manual steps in user's language."""
        lang = self._detect_language()
        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v1.2.0 migration."""
        return [
            {
                'description': '''**New features available after upgrade:**

- **Section card table of contents**: To display a navigable TOC on a story's title card, add `show_sections: yes` to the story's row in project.csv (or `mostrar_secciones: si` for Spanish-language sites). The TOC automatically lists every section card in the story, linking to each one. Section cards are steps with an empty object column.

- **Section cards**: Unchanged from v1.1.0 — leave the object column empty for a story step to create a section break. With `show_sections` enabled, these appear as navigable links on the title card.

- **Back to Start button**: Stories now show a "Back to Start" button in the top-left corner once readers scroll past the title card. Clicking it returns to the title card. On the title card itself, the button shows "Back to Home" and links to the homepage.

- **Ordinal numbers removed**: Story cards no longer display auto-generated numbers on the homepage, story pages, or object pages. The homepage placeholder shows the first letter of each story title instead.

- **Deep link fix**: Deep links to layer 2 panels (e.g. `#s3l2`) now correctly open layer 1 underneath, so all parent panels are visible.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v1.2.0 migration."""
        return [
            {
                'description': '''**Nuevas funciones disponibles tras la actualización:**

- **Tabla de contenidos en tarjeta de título**: Para mostrar una tabla de contenidos navegable en la tarjeta de título de una historia, agrega `mostrar_secciones: si` en la fila de la historia en project.csv (o `show_sections: yes` para sitios en inglés). La tabla de contenidos lista automáticamente cada tarjeta de sección en la historia, con un enlace a cada una. Las tarjetas de sección son pasos con la columna de objeto vacía.

- **Tarjetas de sección**: Sin cambios respecto a v1.1.0 — deja vacía la columna de objeto en un paso de la historia para crear un salto de sección. Con `mostrar_secciones` activado, estas aparecen como enlaces navegables en la tarjeta de título.

- **Botón de volver al comienzo**: Las historias ahora muestran un botón "Comienzo" en la esquina superior izquierda una vez que se avanza más allá de la tarjeta de título. Al hacer clic regresa a la tarjeta de título. En la tarjeta de título, el botón muestra "Volver al inicio" y enlaza a la página principal.

- **Números ordinales eliminados**: Las tarjetas de historia ya no muestran números generados automáticamente en la página principal, las páginas de historia ni las páginas de objeto. El marcador de posición en la página principal muestra la primera letra del título de cada historia.

- **Corrección de enlaces directos**: Los enlaces directos a paneles de nivel 2 (ej. `#s3l2`) ahora abren correctamente el nivel 1 debajo, de modo que todos los paneles superiores quedan visibles.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
