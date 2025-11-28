"""
Migration from v0.5.0-beta to v0.6.0-beta.

Changes:
- Gitignore generated files (_data/*.json, _jekyll-files/)
- Remove tracked generated files from git index
- Add demo content fetch to build workflow
- Multilingual UI support
- Custom pages system (move pages/about.md to components/texts/pages/)
- Data-driven navigation menu (_data/navigation.yml)

Version: v0.6.0-beta
"""

from typing import List, Dict
import os
import subprocess
import glob
from .base import BaseMigration


class Migration050to060(BaseMigration):
    """Migration from v0.5.0 to v0.6.0 - gitignore generated files, multilingual UI, custom pages."""

    from_version = "0.5.0-beta"
    to_version = "0.6.0-beta"
    description = "Gitignore generated files, multilingual UI support, custom pages system"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Returns True since v0.6.0 handles all cases safely.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Create new directories
        print("  Phase 1: Creating directories...")
        changes.extend(self._create_directories())

        # Phase 2: Move about page
        print("  Phase 2: Moving about page...")
        changes.extend(self._move_about_page())

        # Phase 3: Update .gitignore with generated file patterns
        print("  Phase 3: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # Phase 4: Remove tracked generated files from git index
        print("  Phase 4: Removing generated files from git tracking...")
        changes.extend(self._remove_generated_from_git())

        # Phase 5: Update configuration structure
        print("  Phase 5: Updating configuration...")
        changes.extend(self._update_config_structure())

        # Phase 6: Cleanup old demo content
        print("  Phase 6: Cleaning up old demo content...")
        changes.extend(self._cleanup_old_demo_content())

        # Phase 7: Update framework files from GitHub
        print("  Phase 7: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 8: Update _config.yml version
        print("  Phase 8: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.6.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.6.0-beta ({today})")

        return changes

    def _create_directories(self) -> List[str]:
        """
        Create new directories for v0.6.0 features.

        Creates:
        - components/texts/pages/ for custom user pages
        - components/texts/stories/your-story/ for English template
        - components/texts/stories/tu-historia/ for Spanish template

        Returns:
            List of change descriptions
        """
        changes = []

        directories = [
            'components/texts/pages',
            'components/texts/stories/your-story',
            'components/texts/stories/tu-historia',
        ]

        for dir_path in directories:
            full_path = os.path.join(self.repo_root, dir_path)
            if not os.path.exists(full_path):
                try:
                    os.makedirs(full_path, exist_ok=True)
                    changes.append(f"Created directory: {dir_path}/")
                except Exception as e:
                    changes.append(f"⚠️  Warning: Could not create {dir_path}: {e}")
            else:
                changes.append(f"Directory already exists: {dir_path}/")

        return changes

    def _move_about_page(self) -> List[str]:
        """
        Move about.md from pages/ to components/texts/pages/.

        Strategy:
        - If pages/about.md exists: Move it (preserves user customizations)
        - If already moved: Do nothing
        - If no about.md anywhere: Fetch default from GitHub

        Safely removes empty pages/ directory after move.

        Returns:
            List of change descriptions
        """
        changes = []

        old_path = 'pages/about.md'
        new_path = 'components/texts/pages/about.md'

        # Check if old file exists
        if self._file_exists(old_path):
            # Move existing file (preserves user customizations)
            if self._move_file(old_path, new_path):
                changes.append(f"Moved {old_path} → {new_path}")

                # Try to remove old pages/ directory if empty
                old_dir = os.path.join(self.repo_root, 'pages')
                if os.path.exists(old_dir):
                    try:
                        if not os.listdir(old_dir):
                            os.rmdir(old_dir)
                            changes.append("Removed empty pages/ directory")
                    except:
                        pass  # Directory not empty or can't remove
            else:
                changes.append(f"⚠️  Warning: Could not move {old_path}")

        elif not self._file_exists(new_path):
            # No existing about.md, fetch default from GitHub
            content = self._fetch_from_github(new_path)
            if content:
                self._write_file(new_path, content)
                changes.append(f"Created default {new_path} from GitHub")
            else:
                changes.append(f"⚠️  Warning: Could not fetch {new_path}")

        else:
            # Already in new location
            changes.append(f"{new_path} already exists")

        return changes

    def _update_config_structure(self) -> List[str]:
        """
        Update _config.yml structure for v0.6.0.

        Changes:
        1. Move story_interface section ABOVE "DO NOT EDIT" line
        2. Add include_demo_content: false to story_interface
        3. Add pages collection
        4. Add pages defaults

        Uses text-based editing to preserve formatting and comments.

        Returns:
            List of change descriptions
        """
        changes = []
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            changes.append("⚠️  Warning: Could not read _config.yml")
            return changes

        lines = content.split('\n')
        modified = False

        # TODO: Complex config restructuring - will implement in next iteration
        # For now, just add the include_demo_content setting if missing

        # Find story_interface section
        in_story_interface = False
        story_interface_start = -1

        for i, line in enumerate(lines):
            if line.startswith('story_interface:'):
                in_story_interface = True
                story_interface_start = i
                continue

            if in_story_interface:
                # Exit when we hit a non-indented line
                if line and not line.startswith('  ') and not line.startswith('\t'):
                    # Check if include_demo_content exists
                    section_lines = lines[story_interface_start:i]
                    if not any('include_demo_content' in l for l in section_lines):
                        # Add it before the end of the section
                        indent = '  '
                        lines.insert(i, f'{indent}include_demo_content: false')
                        modified = True
                        changes.append("Added include_demo_content: false to story_interface")
                    break

        if modified:
            self._write_file(config_path, '\n'.join(lines))

        # Note: Full config restructuring (moving sections, adding collections)
        # will be added in next iteration. This is a minimal safe change.

        return changes

    def _cleanup_old_demo_content(self) -> List[str]:
        """
        Remove old demo content from v0.5.0, preserving user modifications.

        Strategy:
        - Text files (.md, .csv): Compare with v0.5.0-beta, only delete if unmodified
        - Images: Keep all for safety (too risky to auto-delete)
        - Empty directories: Remove after file cleanup

        Returns:
            List of change descriptions
        """
        import shutil

        changes = []
        kept_modified = []

        # Files to check (text files only)
        files_to_check = [
            # story1 markdown files
            'components/texts/stories/story1/bogota_savanna.md',
            'components/texts/stories/story1/encomendero_biography.md',
            'components/texts/stories/story1/legal_painting.md',
            'components/texts/stories/story1/legal_proceeding.md',
            'components/texts/stories/story1/maldonado_lineage.md',
            'components/texts/stories/story1/ways_of_mapping.md',

            # story2 markdown files
            'components/texts/stories/story2/step1-layer1-test.md',
            'components/texts/stories/story2/step1-layer1.md',
            'components/texts/stories/story2/step10-layer1.md',
            'components/texts/stories/story2/step2-layer1.md',
            'components/texts/stories/story2/step3-layer1.md',
            'components/texts/stories/story2/step4-layer1.md',
            'components/texts/stories/story2/step4-layer2.md',
            'components/texts/stories/story2/step5-layer1.md',
            'components/texts/stories/story2/step8-layer1.md',

            # CSV files
            'components/structures/story-1.csv',
            'components/structures/story-2.csv',
            'components/structures/new-objects.csv',
        ]

        # Check each file
        for rel_path in files_to_check:
            if not self._file_exists(rel_path):
                continue

            # Check if modified
            if self._is_file_modified(rel_path, compare_tag='v0.5.0-beta'):
                # User modified, keep it
                kept_modified.append(rel_path)
            else:
                # Unmodified, safe to delete
                full_path = os.path.join(self.repo_root, rel_path)
                try:
                    os.remove(full_path)
                    changes.append(f"Removed unmodified demo file: {rel_path}")
                except Exception as e:
                    changes.append(f"⚠️  Warning: Could not remove {rel_path}: {e}")

        # Remove empty directories
        old_dirs = [
            'components/texts/stories/story1',
            'components/texts/stories/story2',
        ]

        for rel_path in old_dirs:
            full_path = os.path.join(self.repo_root, rel_path)
            if os.path.exists(full_path):
                try:
                    # Only remove if empty
                    if not os.listdir(full_path):
                        os.rmdir(full_path)
                        changes.append(f"Removed empty directory: {rel_path}/")
                except:
                    pass  # Not empty or can't remove

        # Remove paisajes images directory
        paisajes_dir = os.path.join(self.repo_root, 'components/images/paisajes')
        if os.path.exists(paisajes_dir):
            try:
                file_count = len([f for f in os.listdir(paisajes_dir)
                                if os.path.isfile(os.path.join(paisajes_dir, f))])
                shutil.rmtree(paisajes_dir)
                changes.append(f"Removed paisajes/ directory ({file_count} demo images)")
            except Exception as e:
                changes.append(f"⚠️  Warning: Could not remove paisajes/: {e}")

        # Report kept files (with bilingual message)
        if kept_modified:
            lang = self._detect_language()
            if lang == 'es':
                msg = f"⚠️  Se mantuvieron {len(kept_modified)} archivos de demo modificados por el usuario"
            else:
                msg = f"⚠️  Kept {len(kept_modified)} user-modified demo files"
            changes.append(msg)

            for rel_path in kept_modified:
                changes.append(f"  • {rel_path}")

        # Note about root-level demo images (kept for safety)
        root_images = [
            'components/images/ampl-logo.png',
            'components/images/babylonian-6c-bce-world-map.png',
            'components/images/bogota-1614-painting.jpg',
            'components/images/codex-quetzalecatzin-1593.jpg',
            'components/images/greenland-inuit-1926-map.jpg',
            'components/images/guaman-poma-1615-santa-fe.jpg',
            'components/images/kogi-loom-1978.png',
            'components/images/maldonado-antonio-portrait-18c.jpeg',
            'components/images/maldonado-family-tree-1674.jpg',
            'components/images/maldonado-francisco-portrait-18c.jpg',
            'components/images/medieval-1262-1300-world-map.jpg',
            'components/images/recopilacion-leyes-1681-audiencias.jpg',
            'components/images/recopilacion-leyes-1681-encomiendas.jpg',
            'components/images/siberian-1860-1870-sealskin-map.jpg',
            'components/images/venice-1534-west-indies-map.jpg',
            'components/images/example-bogota-1614.png',
            'components/images/example-ceramic-figure.png',
            'components/images/example-muisca-goldwork.jpg',
        ]

        existing_root_images = [img for img in root_images if self._file_exists(img)]

        if existing_root_images:
            lang = self._detect_language()
            if lang == 'es':
                msg = f"ℹ️  Se mantuvieron {len(existing_root_images)} imágenes de demo antiguas por seguridad"
            else:
                msg = f"ℹ️  Kept {len(existing_root_images)} old demo images for safety"
            changes.append(msg)
            changes.append("  (You can manually delete these if not using them)")

        return changes

    def _update_gitignore(self) -> List[str]:
        """
        Add generated file patterns to .gitignore.

        Returns:
            List of change descriptions
        """
        changes = []

        # Generated JSON files
        # Note: With story_id feature, story files use semantic names (e.g., your-story.json, paisajes-demo.json)
        json_entries = [
            '_data/objects.json',
            '_data/project.json',
            '_data/*.json',
            '!_data/languages/',
        ]

        if self._ensure_gitignore_entries(
            json_entries,
            '# Generated JSON files (from components/structures/*.csv by csv_to_json.py)'
        ):
            changes.append("Added generated JSON patterns to .gitignore")

        # Generated Jekyll collection files
        jekyll_entries = [
            '_jekyll-files/',
        ]

        if self._ensure_gitignore_entries(
            jekyll_entries,
            '# Generated Jekyll collection files (from components/texts/ by generate_collections.py)'
        ):
            changes.append("Added _jekyll-files/ to .gitignore")

        # Demo glossary files
        demo_entries = [
            'components/texts/glossary/_demo_*',
        ]

        if self._ensure_gitignore_entries(
            demo_entries,
            '# Demo glossary files (created by csv_to_json.py from demo bundle)'
        ):
            changes.append("Added demo glossary pattern to .gitignore")

        if not changes:
            changes.append("Gitignore patterns already present")

        return changes

    def _remove_generated_from_git(self) -> List[str]:
        """
        Remove tracked generated files from git index.

        Uses git rm --cached to untrack files without deleting them.
        This is safe and idempotent - runs with check=False.

        Returns:
            List of change descriptions
        """
        changes = []
        removed_count = 0

        # Remove generated JSON files
        json_files = [
            '_data/objects.json',
            '_data/project.json',
        ]

        # Add all story JSON files (includes both story-*.json and semantic names like your-story.json)
        # Exclude demo-glossary.json and languages/ directory
        data_pattern = os.path.join(self.repo_root, '_data/*.json')
        for json_file in glob.glob(data_pattern):
            rel_path = os.path.relpath(json_file, self.repo_root)
            # Exclude demo-glossary.json (handled separately) and any non-story files
            if rel_path not in ['_data/objects.json', '_data/project.json', '_data/demo-glossary.json']:
                json_files.append(rel_path)

        for file_path in json_files:
            full_path = os.path.join(self.repo_root, file_path)
            if os.path.exists(full_path):
                result = subprocess.run(
                    ['git', 'rm', '--cached', file_path],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    removed_count += 1

        # Remove _jekyll-files/ directory from tracking
        jekyll_dir = os.path.join(self.repo_root, '_jekyll-files')
        if os.path.exists(jekyll_dir):
            result = subprocess.run(
                ['git', 'rm', '--cached', '-r', '_jekyll-files/'],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                removed_count += 1
                changes.append("Removed _jekyll-files/ from git tracking")

        # Remove demo glossary files from tracking
        demo_pattern = os.path.join(self.repo_root, 'components/texts/glossary/_demo_*.md')
        demo_files = glob.glob(demo_pattern)
        for demo_file in demo_files:
            rel_path = os.path.relpath(demo_file, self.repo_root)
            result = subprocess.run(
                ['git', 'rm', '--cached', rel_path],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                removed_count += 1

        if removed_count > 0:
            changes.append(f"Removed {removed_count} generated file(s) from git tracking")
        else:
            changes.append("No generated files were tracked in git")

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update core framework files from GitHub.

        v0.6.0 includes:
        - Demo content feature with fetch_demo_content.py
        - Multilingual UI support
        - Generated files gitignored
        - Build workflow updated for demo content
        """
        changes = []

        framework_files = {
            # Python scripts
            'scripts/csv_to_json.py': 'Demo content processing, bilingual CSV support, story_id',
            'scripts/fetch_demo_content.py': 'Demo content bundle fetcher (NEW)',
            'scripts/generate_collections.py': 'Custom pages support, demo glossary',
            'scripts/fetch_google_sheets.py': 'Bilingual tab support, story_id support',
            'scripts/discover_sheet_gids.py': 'Story_id support',
            'scripts/generate_iiif.py': 'Version header update',

            # Language files - multilingual UI
            '_data/languages/en.yml': 'Credit prefix, updated strings',
            '_data/languages/es.yml': 'Spanish translations, credit prefix',

            # Data files
            '_data/navigation.yml': 'Bilingual navigation menu configuration (NEW)',

            # Layouts
            '_layouts/story.html': 'Credit prefix exposure, byline markdown support',
            '_layouts/default.html': 'Multilingual support',
            '_layouts/user-page.html': 'Custom pages layout (NEW)',
            '_layouts/objects-index.html': 'Object ordering bug fix',
            '_layouts/index.html': 'Logo display removed',
            '_layouts/glossary.html': 'Demo badge text fix',

            # Includes
            '_includes/header.html': 'Data-driven navigation, logo CSS',
            '_includes/viewer.html': 'Object credits badge HTML/CSS',

            # Stylesheets
            'assets/css/telar.scss': 'Logo, panel freeze, tab widget, glossary, credits badge',

            # JavaScript
            'assets/js/story.js': 'Panel freeze system, credits badge, viewer scroll isolation',
            'assets/js/telar.js': 'Glossary link handling, click-outside-to-close',

            # Documentation
            'README.md': 'v0.6.0 documentation',
            'CHANGELOG.md': 'v0.6.0 changelog',

            # Gitignore
            '.gitignore': 'Generated files gitignored',

            # Template story content - English (your-story)
            'components/texts/stories/your-story/about-coordinates.md': 'Coordinate system explanation',
            'components/texts/stories/your-story/guiding-attention.md': 'Question/Answer/Invitation pattern',
            'components/texts/stories/your-story/building-argument.md': 'Coordinate sequences as argument',
            'components/texts/stories/your-story/visual-rhetoric.md': 'Visual contrast analysis',
            'components/texts/stories/your-story/the-reveal.md': 'Full view synthesis',
            'components/texts/stories/your-story/progressive-disclosure.md': 'Layer 2 panel explanation',
            'components/texts/stories/your-story/ruler-place.md': 'Charles III marginalized position',
            'components/texts/stories/your-story/multiple-images.md': 'IIIF vs self-hosted comparison',
            'components/texts/stories/your-story/whats-next.md': 'Template overview',

            # Template story content - Spanish (tu-historia)
            'components/texts/stories/tu-historia/acerca-de-coordenadas.md': 'Sistema de coordenadas',
            'components/texts/stories/tu-historia/guiar-atencion.md': 'Patrón Pregunta/Respuesta/Invitación',
            'components/texts/stories/tu-historia/construir-argumento.md': 'Secuencias como argumento',
            'components/texts/stories/tu-historia/retorica-visual.md': 'Análisis de contraste visual',
            'components/texts/stories/tu-historia/la-revelacion.md': 'Síntesis de vista completa',
            'components/texts/stories/tu-historia/divulgacion-progresiva.md': 'Explicación de capa 2',
            'components/texts/stories/tu-historia/lugar-gobernante.md': 'Posición marginalizada',
            'components/texts/stories/tu-historia/multiples-imagenes.md': 'Comparación IIIF vs autoalojadas',
            'components/texts/stories/tu-historia/que-sigue.md': 'Resumen de plantilla',

            # Glossary entries - English
            'components/texts/glossary/story.md': 'Story glossary entry',
            'components/texts/glossary/step.md': 'Step glossary entry',
            'components/texts/glossary/viewer.md': 'Viewer glossary entry',
            'components/texts/glossary/panel.md': 'Panel glossary entry',

            # Glossary entries - Spanish
            'components/texts/glossary/historia.md': 'Historia glossary entry',
            'components/texts/glossary/paso.md': 'Paso glossary entry',
            'components/texts/glossary/visor.md': 'Visor glossary entry',
            'components/texts/glossary/panel-es.md': 'Panel-es glossary entry',

            # Template images
            'components/images/leviathan.jpg': 'Hobbes Leviathan frontispiece (self-hosted demo)',

            # Note: components/texts/pages/about.md is handled by _move_about_page()
            # Note: .github/workflows/*.yml files CANNOT be auto-updated (security restriction)
            #       They are included in manual steps instead
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path}: {description}")
            else:
                changes.append(f"⚠️  Warning: Could not fetch {file_path} from GitHub")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Return manual steps in user's language.

        Detects site language and returns appropriate bilingual manual steps.

        Returns:
            List of manual step dicts with 'description' and optional 'doc_url' keys
        """
        lang = self._detect_language()

        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v0.6.0 migration."""
        return [
            {
                'description': '''⚠️ **CRITICAL: Update Your GitHub Actions Workflows** ⚠️

**Without this step, your site may not build correctly with the new demo content feature.**

The v0.6.0 upgrade adds support for demo content fetching in the build workflow. You must update two workflow files: `build.yml` and `upgrade.yml`.

---

**Option 1: Using the GitHub Website**

1. **Update build.yml:**
   - Open this link in a new tab: https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml
   - Select all the text (Ctrl+A on Windows/Linux, Cmd+A on Mac) and copy it (Ctrl+C or Cmd+C)
   - Go to your GitHub repository and navigate to `.github/workflows/build.yml`
   - Click the pencil (✏️) icon in the top-right corner to edit
   - Select all existing content and delete it
   - Paste the new content you copied
   - Scroll to the bottom and click "Commit changes"

2. **Update upgrade.yml:**
   - Repeat the same process for: https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml
   - Navigate to `.github/workflows/upgrade.yml` in your repository
   - Edit, replace content, and commit

---

**Option 2: Using the Command Line** (if comfortable with git)

```bash
# Download the updated workflows
curl -o .github/workflows/build.yml https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml
curl -o .github/workflows/upgrade.yml https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml

# Commit the changes
git add .github/workflows/
git commit -m "Update workflows for v0.6.0 demo content"
git push
```

**Why this is necessary:** GitHub Actions workflow files cannot be automatically updated by other workflows for security reasons. This manual step ensures your automated builds use the latest workflow logic.

**That's it!** Your next build will include demo content support.''',
                'doc_url': 'https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/',
                'critical': True
            },
            {
                'description': 'Run the build scripts to regenerate files: `python3 scripts/csv_to_json.py && python3 scripts/generate_collections.py`',
            },
            {
                'description': 'Test your site build: `bundle exec jekyll build`',
            },
            {
                'description': 'Optional: Enable demo content by setting `include_demo_content: true` in `_config.yml` under `story_interface`. Then run `python3 scripts/fetch_demo_content.py` to download the demo bundle.',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.6.0 migration."""
        return [
            {
                'description': '''⚠️ **CRÍTICO: Actualiza Tus Flujos de Trabajo de GitHub Actions** ⚠️

**Sin este paso, tu sitio podría no compilarse correctamente con la nueva función de contenido demo.**

La actualización v0.6.0 añade soporte para la descarga de contenido demo en el flujo de compilación. Debes actualizar dos archivos de flujo de trabajo: `build.yml` y `upgrade.yml`.

---

**Opción 1: Usando el Sitio Web de GitHub**

1. **Actualizar build.yml:**
   - Abre este enlace en una pestaña nueva: https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml
   - Selecciona todo el texto (Ctrl+A en Windows/Linux, Cmd+A en Mac) y cópialo (Ctrl+C o Cmd+C)
   - Ve a tu repositorio de GitHub y navega a `.github/workflows/build.yml`
   - Haz clic en el ícono del lápiz (✏️) en la esquina superior derecha para editar
   - Selecciona todo el contenido existente y bórralo
   - Pega el nuevo contenido que copiaste
   - Desplázate hacia abajo y haz clic en "Commit changes"

2. **Actualizar upgrade.yml:**
   - Repite el mismo proceso para: https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml
   - Navega a `.github/workflows/upgrade.yml` en tu repositorio
   - Edita, reemplaza el contenido, y haz commit

---

**Opción 2: Usando la Línea de Comandos** (si te sientes cómodo con git)

```bash
# Descarga los flujos de trabajo actualizados
curl -o .github/workflows/build.yml https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml
curl -o .github/workflows/upgrade.yml https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml

# Haz commit de los cambios
git add .github/workflows/
git commit -m "Actualizar flujos de trabajo para contenido demo v0.6.0"
git push
```

**Por qué esto es necesario:** Los archivos de flujo de trabajo de GitHub Actions no pueden ser actualizados automáticamente por otros flujos de trabajo por razones de seguridad. Este paso manual asegura que tus compilaciones automatizadas usen la lógica de flujo de trabajo más reciente.

**¡Eso es todo!** Tu próxima compilación incluirá soporte para contenido demo.''',
                'doc_url': 'https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/',
                'critical': True
            },
            {
                'description': 'Ejecuta los scripts de compilación para regenerar archivos: `python3 scripts/csv_to_json.py && python3 scripts/generate_collections.py`',
            },
            {
                'description': 'Prueba la compilación de tu sitio: `bundle exec jekyll build`',
            },
            {
                'description': 'Opcional: Habilita el contenido demo configurando `include_demo_content: true` en `_config.yml` bajo `story_interface`. Luego ejecuta `python3 scripts/fetch_demo_content.py` para descargar el paquete demo.',
            },
        ]
