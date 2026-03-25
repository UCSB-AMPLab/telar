"""
Migration from v0.9.4-beta to v1.0.0-beta.

Fluid Multimedia Storytelling release:
- Card-stack architecture replaces split-column layout
- Lenis continuous scroll with magnetic waypoints
- Video support (YouTube, Vimeo, Google Drive) in stories and object pages
- Audio support (WaveSurfer waveform) in stories and object pages
- Inline Lucide SVG icons replace CDN dependencies (Material Symbols, Bootstrap Icons)
- Media type auto-detection and gallery filtering
- Alt text support across stories and objects
- Clip time control (start, end, loop) for video and audio
- Audio build pipeline (ffmpeg, audiowaveform)
- Per-scene card pool with z-index banding

~51 framework files fetched from GitHub, 2 language files fetched,
1 config value updated (max_viewer_cards 10 -> 8), version bumped.

Version: v1.0.0-beta
"""

from typing import List, Dict
import re
from .base import BaseMigration


class Migration094to100(BaseMigration):
    """Migration from v0.9.4 to v1.0.0 - Fluid Multimedia Storytelling."""

    from_version = "0.9.4-beta"
    to_version = "1.0.0-beta"
    description = "Card-stack architecture, video/audio support, Lucide icons, scroll engine"

    # Branch to fetch files from on GitHub
    _GITHUB_BRANCH = "v1.0.0-beta"

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

        # Phase 3: Update _config.yml (max_viewer_cards 10 -> 8)
        print("  Phase 3: Updating configuration...")
        changes.extend(self._update_configuration())

        # Phase 4: Update version
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("1.0.0-beta", today):
            changes.append(f"Updated _config.yml: version 1.0.0-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Fetch framework files from GitHub v1.0.0-beta branch."""
        changes = []

        framework_files = {
            # Layouts
            '_layouts/story.html': 'Card-stack story layout',
            '_layouts/default.html': 'Default layout (CDN links removed)',
            '_layouts/object.html': 'Object page with video/audio support',
            '_layouts/objects-index.html': 'Gallery with media type thumbnails',
            '_layouts/index.html': 'Homepage with media-type-aware thumbnails',
            # Includes
            '_includes/story-step.html': 'Story step with clip and alt data',
            '_includes/panels.html': 'Panels (z-index consolidated)',
            '_includes/share-button.html': 'Share button (Lucide SVG)',
            '_includes/share-panel.html': 'Share panel (Lucide SVGs)',
            # Stylesheets
            '_sass/_story.scss': 'Card-stack story styles',
            '_sass/_viewer.scss': 'Object page viewer styles',
            '_sass/_panels.scss': 'Panel styles',
            '_sass/_share.scss': 'Share button styles',
            '_sass/_embed.scss': 'Embed mode styles',
            '_sass/_layout.scss': 'Layout styles (gallery thumbnails)',
            # JavaScript (standalone)
            'assets/js/telar-icons.js': 'Lucide SVG icon module',
            'assets/js/embed.js': 'Embed mode (Lucide icons)',
            'assets/js/objects-filter.js': 'Gallery filter (media_type/medium)',
            'assets/js/share-panel.js': 'Share panel (Lucide icons)',
            'assets/js/story-unlock.js': 'Password unlock (Lucide icons)',
            # JavaScript (bundled)
            'assets/js/telar-story.js': 'Bundled story JS',
            'assets/js/telar-story.js.map': 'Source map',
            'assets/js/telar-story/main.js': 'Story entry point',
            'assets/js/telar-story/card-pool.js': 'Card pool manager',
            'assets/js/telar-story/card-type.js': 'Card type detection',
            'assets/js/telar-story/iiif-card.js': 'IIIF card module',
            'assets/js/telar-story/text-card.js': 'Text card module',
            'assets/js/telar-story/scroll-engine.js': 'Scroll engine',
            'assets/js/telar-story/video-card.js': 'Video card module',
            'assets/js/telar-story/audio-card.js': 'Audio card module',
            'assets/js/telar-story/navigation.js': 'Navigation module',
            'assets/js/telar-story/state.js': 'Shared state',
            'assets/js/telar-story/viewer.js': 'Viewer module',
            'assets/js/telar-story/utils.js': 'Shared utilities',
            'assets/js/telar-story/panels.js': 'Panel module',
            # Image assets
            'assets/img/background-gris.svg': 'Weave pattern background',
            # Python scripts
            'scripts/process_audio.py': 'Audio build pipeline',
            'scripts/build_local_site.py': 'Local build script (7-step)',
            'scripts/generate_collections.py': 'Collections generator',
            'scripts/generate_iiif.py': 'IIIF tile generator',
            'scripts/telar/core.py': 'CSV-to-JSON core',
            'scripts/telar/csv_utils.py': 'CSV utilities',
            'scripts/telar/processors/objects.py': 'Object processor',
            'scripts/telar/processors/stories.py': 'Story processor',
            'scripts/telar/search.py': 'Search data generator',
            # Package config
            'package.json': 'npm dependencies',
            # Tests
            'tests/js/card-pool.test.js': 'Card pool tests',
            'tests/js/card-type.test.js': 'Card type tests',
            'tests/js/iiif-card.test.js': 'IIIF card tests',
            'tests/js/iiif-lerp.test.js': 'IIIF lerp tests',
            'tests/js/text-card.test.js': 'Text card tests',
            'tests/js/scroll-engine.test.js': 'Scroll engine tests',
            'tests/js/navigation.test.js': 'Navigation tests',
            'tests/js/video-card.test.js': 'Video card tests',
            'tests/js/audio-card.test.js': 'Audio card tests',
            'tests/js/state.test.js': 'State tests',
            'tests/js/utils.test.js': 'Utils tests',
            'tests/unit/test_csv_utils.py': 'CSV utils tests',
            'tests/unit/test_generate_collections.py': 'Collections tests',
            'tests/unit/test_process_audio.py': 'Audio pipeline tests',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path, branch=self._GITHUB_BRANCH)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_language_files(self) -> List[str]:
        """Fetch language files from GitHub (adds clip_picker keys)."""
        changes = []

        language_files = {
            '_data/languages/en.yml': 'English strings (clip_picker keys added)',
            '_data/languages/es.yml': 'Spanish strings (clip_picker keys added)',
        }

        for file_path, description in language_files.items():
            content = self._fetch_from_github(file_path, branch=self._GITHUB_BRANCH)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_configuration(self) -> List[str]:
        """Update max_viewer_cards from 10 to 8 in _config.yml."""
        changes = []

        content = self._read_file('_config.yml')
        if not content:
            changes.append("Warning: _config.yml not found")
            return changes

        # Replace max_viewer_cards: 10 with max_viewer_cards: 8
        # Match any variation of the line (with or without comment)
        new_content, count = re.subn(
            r'(max_viewer_cards:\s*)10(\s*#.*)?$',
            r'\g<1>8     # Max viewers in memory (per-scene pool cap). '
            r'Higher = smoother, more memory. (default: 8, max: 15)',
            content,
            flags=re.MULTILINE
        )

        if count > 0:
            self._write_file('_config.yml', new_content)
            changes.append("Updated _config.yml: max_viewer_cards 10 -> 8")
        else:
            # Already at 8 or different value
            if 'max_viewer_cards' in content:
                changes.append("Note: max_viewer_cards already set (not 10), skipped")
            else:
                changes.append("Note: max_viewer_cards not found in _config.yml")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return manual steps in user's language."""
        lang = self._detect_language()
        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v1.0.0 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

Replace your `.github/workflows/build.yml` with the latest version from the Telar repository. The new workflow adds an audio processing step that runs conditionally when audio files are detected.

Steps:
1. Go to https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml
2. Click the "Raw" button
3. Copy the entire file contents
4. Replace the contents of `.github/workflows/build.yml` in your repository''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml'
            },
            {
                'description': '''**If you work with your site locally:**

Install JavaScript dependencies:

```
npm install
```

This adds lenis (scroll engine), @vimeo/player (video embeds), esbuild (JS bundler), and vitest (test runner).

**Optional — audio support** (only if your site includes audio objects):

```
brew install ffmpeg audiowaveform      # macOS
sudo apt install ffmpeg audiowaveform  # Ubuntu
```

Sites without audio objects do not need these tools.''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v1.0.0 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

Reemplaza tu `.github/workflows/build.yml` con la version mas reciente del repositorio de Telar. El nuevo flujo agrega un paso de procesamiento de audio que se ejecuta condicionalmente cuando se detectan archivos de audio.

Pasos:
1. Ve a https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml
2. Haz clic en el boton "Raw"
3. Copia todo el contenido del archivo
4. Reemplaza el contenido de `.github/workflows/build.yml` en tu repositorio''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml'
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Instala las dependencias de JavaScript:

```
npm install
```

Esto agrega lenis (motor de scroll), @vimeo/player (videos incrustados), esbuild (empaquetador JS) y vitest (ejecutor de pruebas).

**Opcional — soporte de audio** (solo si el sitio incluye objetos de audio):

```
brew install ffmpeg audiowaveform      # macOS
sudo apt install ffmpeg audiowaveform  # Ubuntu
```

Los sitios sin objetos de audio no necesitan estas herramientas.''',
            },
        ]
