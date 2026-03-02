"""
Migration from v0.8.1-beta to v0.9.0-beta.

Changes:
- Content folder restructure (components/ → telar-content/)
- Tify viewer replaces UniversalViewer
- PDF document support with multi-page IIIF
- libvips IIIF tile generation (28x faster)
- Single Google Sheets URL (shared_url removed)
- New default theme (Trama replaces Paisajes)
- Custom metadata fields on object pages

Version: v0.9.0-beta
"""

from typing import List, Dict
import os
import shutil
import subprocess
from .base import BaseMigration


class Migration081to090(BaseMigration):
    """Migration from v0.8.1 to v0.9.0 - Faster Builds, Simpler Setup & Document Support."""

    from_version = "0.8.1-beta"
    to_version = "0.9.0-beta"
    description = "Content restructure, Tify viewer, PDF support, libvips tiles, Trama theme"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Move content directories (components/ → telar-content/)
        print("  Phase 1: Moving content directories...")
        changes.extend(self._move_content_directories())

        # Phase 2: Update .gitignore (path references)
        print("  Phase 2: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # Phase 3: Update _config.yml (theme comment, shared_url cleanup)
        print("  Phase 3: Updating configuration...")
        changes.extend(self._update_configuration())

        # Phase 4: Update framework files from GitHub
        print("  Phase 4: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 5: Scan for broken path references in user content
        print("  Phase 5: Scanning for broken path references...")
        changes.extend(self._scan_broken_references())

        # Phase 6: Update version
        print("  Phase 6: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.9.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.9.0-beta ({today})")

        return changes

    # ------------------------------------------------------------------
    # Phase 1: Move content directories
    # ------------------------------------------------------------------

    def _move_content_directories(self) -> List[str]:
        """
        Move user content from components/ to telar-content/.

        Handles three directory renames:
          components/images/     → telar-content/objects/
          components/structures/ → telar-content/spreadsheets/
          components/texts/      → telar-content/texts/

        Then removes the remaining components/ directory and un-tracks
        old paths from the git index.
        """
        changes = []

        relocations = {
            'components/images': 'telar-content/objects',
            'components/structures': 'telar-content/spreadsheets',
            'components/texts': 'telar-content/texts',
        }

        for src, dest in relocations.items():
            src_full = os.path.join(self.repo_root, src)
            dest_full = os.path.join(self.repo_root, dest)

            if not os.path.exists(src_full):
                if os.path.exists(dest_full):
                    changes.append(f"Already migrated: {dest}/")
                else:
                    changes.append(f"Skipped (not found): {src}/")
                continue

            if os.path.exists(dest_full):
                changes.append(
                    f"⚠️  Warning: Both {src}/ and {dest}/ exist. "
                    f"Skipping move — please merge manually."
                )
                continue

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(dest_full), exist_ok=True)

            # Move entire directory
            shutil.move(src_full, dest_full)
            changes.append(f"Moved {src}/ → {dest}/")

        # Remove remaining components/ directory
        components_dir = os.path.join(self.repo_root, 'components')
        if os.path.exists(components_dir):
            remaining = os.listdir(components_dir)
            if remaining:
                changes.append(
                    f"Note: components/ contained unexpected files: "
                    f"{remaining[:5]}"
                )
            try:
                shutil.rmtree(components_dir)
                changes.append("Removed components/ directory")
            except Exception as e:
                changes.append(f"⚠️  Warning: Could not remove components/: {e}")

        # Un-track old paths from git index
        git_dir = os.path.join(self.repo_root, '.git')
        if os.path.exists(git_dir):
            try:
                result = subprocess.run(
                    ['git', 'rm', '-r', '--cached', '--ignore-unmatch',
                     'components/'],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    changes.append("Removed components/ from git tracking")
            except FileNotFoundError:
                changes.append(
                    "⚠️  Git not available, skipping index cleanup"
                )

        return changes

    # ------------------------------------------------------------------
    # Phase 2: Update .gitignore
    # ------------------------------------------------------------------

    def _update_gitignore(self) -> List[str]:
        """
        Update .gitignore path references from components/ to telar-content/.

        Replaces comment and pattern references. Phase 4 will later overwrite
        the entire file from GitHub, but this ensures correctness if the
        GitHub fetch fails.
        """
        changes = []

        content = self._read_file('.gitignore')
        if not content:
            return changes

        original = content

        # Update path references in comments and patterns
        content = content.replace(
            'components/structures/',
            'telar-content/spreadsheets/'
        )
        content = content.replace(
            'components/texts/',
            'telar-content/texts/'
        )
        content = content.replace(
            'components/images/',
            'telar-content/objects/'
        )

        if content != original:
            self._write_file('.gitignore', content)
            changes.append("Updated .gitignore path references (components/ → telar-content/)")

        return changes

    # ------------------------------------------------------------------
    # Phase 3: Update _config.yml
    # ------------------------------------------------------------------

    def _update_configuration(self) -> List[str]:
        """
        Update _config.yml: theme comment and shared_url cleanup.

        Uses text-based editing to preserve comments and formatting.
        Does NOT change the telar_theme value — users who explicitly set
        a theme keep their choice. The framework's fallback chain handles
        the new default automatically for users with no explicit theme.
        """
        changes = []

        content = self._read_file('_config.yml')
        if not content:
            return changes

        modified = False

        # 1. Update telar_theme comment to list trama first
        old_patterns = [
            '# Options: paisajes, neogranadina, santa-barbara, austin, or custom',
            '# Options: paisajes, neogranadina, santa-barbara, austin or custom',
        ]
        new_comment = '# Options: trama, paisajes, neogranadina, santa-barbara, austin, or custom'

        for old in old_patterns:
            if old in content:
                content = content.replace(old, new_comment)
                changes.append("Updated telar_theme options comment (trama now listed first)")
                modified = True
                break

        # 2. Remove shared_url and its comment if present
        #    shared_url is silently ignored since v0.9.0 but removing keeps
        #    configs clean
        lines = content.split('\n')
        new_lines = []
        i = 0
        removed_shared_url = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check if this is the shared_url line
            if stripped.startswith('shared_url:'):
                removed_shared_url = True
                i += 1
                # Skip trailing blank line after removal
                if i < len(lines) and not lines[i].strip():
                    i += 1
                continue

            # Check if this is a comment immediately preceding shared_url
            # (catches both English and Spanish comments)
            if (stripped.startswith('#')
                    and i + 1 < len(lines)
                    and lines[i + 1].strip().startswith('shared_url:')):
                removed_shared_url = True
                i += 2
                # Skip trailing blank line
                if i < len(lines) and not lines[i].strip():
                    i += 1
                continue

            new_lines.append(line)
            i += 1

        if removed_shared_url:
            content = '\n'.join(new_lines)
            changes.append("Removed shared_url from _config.yml (no longer needed)")
            modified = True

        if modified:
            self._write_file('_config.yml', content)

        return changes

    # ------------------------------------------------------------------
    # Phase 4: Update framework files from GitHub
    # ------------------------------------------------------------------

    def _update_framework_files(self) -> List[str]:
        """
        Update framework files from GitHub repository.

        Fetches ~45 files covering: new scripts (iiif_utils, process_pdf),
        Tify viewer migration, libvips support, PDF pipeline, content path
        updates, Trama theme, and documentation.

        Note: .github/workflows/ files are NOT included here due to the
        GitHub Actions security restriction (GITHUB_TOKEN cannot modify
        workflow files). These are documented as manual steps instead.
        """
        changes = []

        framework_files = {
            # --- New files ---
            'scripts/iiif_utils.py': 'Shared IIIF utilities (extracted from generate_iiif.py)',
            'scripts/process_pdf.py': 'PDF-to-IIIF pipeline',
            '_data/themes/trama.yml': 'New default theme (Trama)',
            'NOTICE': 'Third-party notices',

            # --- Python scripts ---
            'scripts/generate_iiif.py': 'libvips backend, PDF detection, refactored imports',
            'scripts/generate_collections.py': 'Custom metadata fields, empty field fix, location fix',
            'scripts/fetch_google_sheets.py': 'Single published URL (shared_url removed)',
            'scripts/telar/core.py': 'Content path telar-content/spreadsheets',
            'scripts/telar/csv_utils.py': 'Page column mapping (page/pagina/página)',
            'scripts/telar/processors/stories.py': 'Extension stripping, page validation, content paths',
            'scripts/telar/processors/objects.py': 'PDF extension support, content paths',
            'scripts/telar/images.py': 'Content path telar-content/objects',
            'scripts/telar/glossary.py': 'Content paths telar-content/',
            'scripts/telar/markdown.py': 'Content path telar-content/texts',

            # --- Layouts ---
            '_layouts/index.html': 'Simplified validation, Trama fallback, Level 0 IIIF fix, page-aware thumbnails',
            '_layouts/objects-index.html': 'Thumbnail URL fix (w,h format), Level 0 IIIF fix',
            '_layouts/object.html': 'Tify viewer, language key labels, multi-page coordinate picker',
            '_layouts/story.html': 'Tify CDN, page parameter passthrough',

            # --- Includes ---
            '_includes/story-step.html': 'data-page attribute for multi-page objects',

            # --- Stylesheets ---
            '_sass/_mixins.scss': 'Renamed hide-uv-controls → hide-viewer-chrome (Tify selectors)',
            '_sass/_viewer.scss': 'Tify styling, black background, multi-page pagination',
            '_sass/_layout.scss': 'Featured object thumbnail CSS fix',
            'assets/css/telar.scss': 'Trama fallback chain, updated CSS variable defaults',

            # --- JavaScript ---
            'assets/js/telar-story/viewer.js': 'Tify viewer, page-specific manifests',
            'assets/js/telar-story/navigation.js': 'Page parameter passthrough',
            'assets/js/telar-story/state.js': 'Tify instance comments',
            'assets/js/story-unlock.js': 'data-page support for encrypted stories',

            # --- Bundle files (generated by esbuild, text JS) ---
            'assets/js/telar-story-bundle.js': 'Bundled story viewer (esbuild output)',
            'assets/js/telar-story.bundle.js': 'Bundled story viewer (esbuild output)',

            # --- Language files ---
            '_data/languages/en.yml': 'Viewer keys, coordinate keys, simplified validation, trama warning',
            '_data/languages/es.yml': 'Viewer keys, coordinate keys, simplified validation, trama warning',

            # --- Data files ---
            '_data/navigation.yml': 'Updated path references',

            # --- Dependencies ---
            'requirements.txt': 'Updated dependencies',

            # --- Documentation ---
            'README.md': 'Updated for v0.9.0',
            'CHANGELOG.md': 'v0.9.0 changelog',
            'LICENSE': 'Updated license',
            'scripts/README.md': 'Updated architecture description',

            # --- Content directory READMEs ---
            'telar-content/README.md': 'Telar Content directory guide',
            'telar-content/objects/README.md': 'Objects directory guide (images + PDFs)',
            'telar-content/spreadsheets/README.md': 'Spreadsheets directory guide',
            'telar-content/texts/README.md': 'Texts directory guide',

            # --- Demo story files (updated path references) ---
            'telar-content/texts/stories/your-story/multiple-images.md': 'Updated paths',
            'telar-content/texts/stories/tu-historia/multiples-imagenes.md': 'Updated paths',

            # --- .gitignore (full replacement with updated paths) ---
            '.gitignore': 'Updated paths and patterns',

            # --- Tests ---
            'tests/unit/test_image_processing.py': 'Updated path assertions',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path}")
            else:
                changes.append(f"⚠️  Warning: Could not fetch {file_path}")

        return changes

    # ------------------------------------------------------------------
    # Phase 5: Scan for broken path references
    # ------------------------------------------------------------------

    def _scan_broken_references(self) -> List[str]:
        """
        Scan user content for hardcoded components/ path references.

        Prints warnings for each found reference so users know to update
        them manually. Not critical — story CSV and objects CSV references
        are handled automatically by the framework.
        """
        changes = []

        scan_dirs = [
            'telar-content/texts',
            '_layouts',
            '_includes',
        ]

        broken_refs = []

        for scan_dir in scan_dirs:
            full_dir = os.path.join(self.repo_root, scan_dir)
            if not os.path.exists(full_dir):
                continue

            for root, dirs, files in os.walk(full_dir):
                for filename in files:
                    if not filename.endswith(('.md', '.html')):
                        continue

                    filepath = os.path.join(root, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()

                        old_paths = [
                            'components/images/',
                            'components/structures/',
                            'components/texts/',
                        ]

                        for old_path in old_paths:
                            if old_path in content:
                                rel_path = os.path.relpath(filepath, self.repo_root)
                                broken_refs.append((rel_path, old_path))
                    except Exception:
                        continue

        if broken_refs:
            lang = self._detect_language()

            if lang == 'es':
                changes.append(
                    f"⚠️  Se encontraron {len(broken_refs)} referencia(s) a rutas antiguas "
                    f"(components/) en tu contenido:"
                )
            else:
                changes.append(
                    f"⚠️  Found {len(broken_refs)} reference(s) to old paths "
                    f"(components/) in your content:"
                )

            for ref_file, ref_pattern in broken_refs[:10]:
                changes.append(f"  • {ref_file}: {ref_pattern}")
            if len(broken_refs) > 10:
                changes.append(f"  ... and {len(broken_refs) - 10} more")

            if lang == 'es':
                changes.append(
                    "  ℹ️  Actualiza estas referencias manualmente a telar-content/"
                )
            else:
                changes.append(
                    "  ℹ️  Update these references manually to telar-content/"
                )
        else:
            changes.append("No broken path references found in user content")

        return changes

    # ------------------------------------------------------------------
    # Manual steps
    # ------------------------------------------------------------------

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return manual steps in user's language."""
        lang = self._detect_language()

        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v0.9.0 migration."""
        return [
            {
                'description': '''**Update GitHub Actions workflow (required):**

Due to GitHub security restrictions, workflow files cannot be updated automatically.
Please replace your `.github/workflows/build.yml` with the latest version from the Telar repository.

**Important:** v0.9.0 adds `libvips-tools` installation for faster IIIF tile generation and updates all content path references from `components/` to `telar-content/`.

Steps:
1. Go to https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml
2. Click the "Raw" button
3. Copy the entire file contents
4. Replace the contents of `.github/workflows/build.yml` in your repository''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml'
            },
            {
                'description': '''**If you use GitHub Pages:**

After updating the workflow file above, no further actions are needed. Your site will automatically rebuild with the new features.''',
            },
            {
                'description': '''**If you work with your site locally:**

1. **Regenerate IIIF tiles** (recommended — libvips is ~28x faster):

   Install libvips (one-time setup):
   - macOS: `brew install vips`
   - Ubuntu/Debian: `sudo apt-get install libvips-tools`

   Then regenerate tiles:
   ```
   python3 scripts/generate_iiif.py
   ```

   The script automatically uses libvips if available, falling back to the Python library.

2. **Optional — PDF support** (only if you want to add PDF documents):
   ```
   pip install PyMuPDF
   ```

3. **Rebuild your site:**
   ```
   python3 scripts/csv_to_json.py
   python3 scripts/generate_collections.py
   bundle exec jekyll build
   ```''',
            },
            {
                'description': '''**Check for broken path references:**

If you have hardcoded paths like `components/images/`, `components/structures/`, or `components/texts/` in your markdown files, custom pages, or HTML includes, these will break after the directory rename.

The migration script scans for common patterns and warns you, but please also review your custom content. Story CSV and objects CSV references are handled automatically by the framework — this only affects freeform markdown or HTML where you typed paths manually.

**Path mapping:**
- `components/images/` → `telar-content/objects/`
- `components/structures/` → `telar-content/spreadsheets/`
- `components/texts/` → `telar-content/texts/`''',
            },
            {
                'description': '''**What's new in v0.9.0:**

1. **Faster builds**: libvips tile generation is ~28x faster than the Python library
2. **Tify viewer**: Replaces UniversalViewer with a lighter, faster IIIF viewer
3. **PDF support**: Add PDF documents as objects — pages are automatically rendered as IIIF images
4. **Multi-page IIIF**: Story steps can reference specific pages of multi-page objects
5. **Trama theme**: New default theme with a fresh visual identity (your current theme is preserved)
6. **Simpler setup**: Only one Google Sheets URL needed (published_url)
7. **Custom metadata**: Extra columns in objects.csv are automatically displayed on object pages''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.9.0 migration."""
        return [
            {
                'description': '''**Actualiza el workflow de GitHub Actions (obligatorio):**

Debido a restricciones de seguridad de GitHub, los archivos de workflow no pueden actualizarse automáticamente.
Por favor reemplaza tu `.github/workflows/build.yml` con la versión más reciente del repositorio de Telar.

**Importante:** v0.9.0 agrega la instalación de `libvips-tools` para una generación más rápida de mosaicos IIIF y actualiza todas las referencias de rutas de `components/` a `telar-content/`.

Pasos:
1. Ve a https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml
2. Haz clic en el botón "Raw"
3. Copia todo el contenido del archivo
4. Reemplaza el contenido de `.github/workflows/build.yml` en tu repositorio''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml'
            },
            {
                'description': '''**Si usas GitHub Pages:**

Después de actualizar el archivo de workflow, no se requieren más acciones. Tu sitio se reconstruirá automáticamente con las nuevas funciones.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

1. **Regenera los mosaicos IIIF** (recomendado — libvips es ~28 veces más rápido):

   Instala libvips (configuración única):
   - macOS: `brew install vips`
   - Ubuntu/Debian: `sudo apt-get install libvips-tools`

   Luego regenera los mosaicos:
   ```
   python3 scripts/generate_iiif.py
   ```

   El script usa automáticamente libvips si está disponible, con respaldo a la biblioteca de Python.

2. **Opcional — soporte para PDFs** (solo si quieres agregar documentos PDF):
   ```
   pip install PyMuPDF
   ```

3. **Reconstruye tu sitio:**
   ```
   python3 scripts/csv_to_json.py
   python3 scripts/generate_collections.py
   bundle exec jekyll build
   ```''',
            },
            {
                'description': '''**Revisa las referencias a rutas antiguas:**

Si tienes rutas escritas manualmente como `components/images/`, `components/structures/` o `components/texts/` en tus archivos markdown, páginas personalizadas o includes HTML, estas dejarán de funcionar después del cambio de nombre de directorios.

El script de migración busca patrones comunes y te advierte, pero también revisa tu contenido personalizado. Las referencias en los CSV de historias y objetos se manejan automáticamente por el framework — esto solo afecta texto markdown o HTML donde escribiste las rutas manualmente.

**Mapeo de rutas:**
- `components/images/` → `telar-content/objects/`
- `components/structures/` → `telar-content/spreadsheets/`
- `components/texts/` → `telar-content/texts/`''',
            },
            {
                'description': '''**Novedades en v0.9.0:**

1. **Compilaciones más rápidas**: la generación de mosaicos con libvips es ~28 veces más rápida que la biblioteca de Python
2. **Visor Tify**: Reemplaza UniversalViewer con un visor IIIF más ligero y rápido
3. **Soporte para PDFs**: Agrega documentos PDF como objetos — las páginas se renderizan automáticamente como imágenes IIIF
4. **IIIF multi-página**: Los pasos de historias pueden referenciar páginas específicas de objetos con múltiples páginas
5. **Tema Trama**: Nuevo tema predeterminado con una identidad visual renovada (tu tema actual se preserva)
6. **Configuración más simple**: Solo se necesita una URL de Google Sheets (published_url)
7. **Metadatos personalizados**: Las columnas extra en objects.csv se muestran automáticamente en las páginas de objetos''',
            },
        ]
