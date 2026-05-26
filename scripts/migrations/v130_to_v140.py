"""
Migration from v1.3.0 to v1.4.0.

Responsive system overhaul and a custom IIIF viewer. This is a runtime-only
release: the story step schema, CSV formats, and the (x, y, zoom) capture
contract are all unchanged, so there are no user-content transforms. Existing
stories, objects, and configuration keep working without edits.

What the upgrade does:

1. Framework files (fetched fresh from GitHub main). The viewer layer is
   replaced wholesale — Tify (and its Vue dependency) is gone, swapped for a
   vendored OpenSeadragon plus a small Telar-authored wrapper. The responsive
   layer is rebuilt around CSS custom properties and cascade layers, with a new
   layout-mode runtime. Every changed runtime file is re-fetched: the bundled
   and source story JS, the SCSS partials, the three layouts that load the
   viewer, the viewer include, both language packs (which gain six new
   object.viewer.* keys for the viewer chrome and error UI), the IIIF tiling
   utility, and the vendored OpenSeadragon asset.

2. .gitignore — adds a `!assets/vendor/` negation so the newly vendored
   OpenSeadragon bundle is tracked despite the existing Bundler `vendor/` rule,
   plus an ignore for the two stale story-bundle filenames removed below.

3. Stale file cleanup — deletes assets/js/telar-story.bundle.js and
   assets/js/telar-story-bundle.js if present. These predate the current build
   naming scheme, were never referenced, and are removed from the template in
   v1.4.0; a framework re-fetch alone would not delete them.

4. Version bump: telar.version 1.3.0 -> 1.4.0 in _config.yml.

Language packs are framework-owned and fetched wholesale, per the established
convention. A site that customised en.yml or es.yml will have those edits
replaced and should re-apply them after upgrading (see the manual step).

Version: v1.4.0
"""

import os
from typing import Dict, List

from .base import BaseMigration


# Framework files re-fetched wholesale from GitHub main. Grouped by subsystem
# for the upgrade summary; every entry is a file that changed in v1.4.0 and is
# part of a user site's runtime or template.
FRAMEWORK_FILES = {
    # Vendored viewer dependency (no CDN)
    'assets/vendor/openseadragon.min.js': 'Vendored OpenSeadragon 6.0.2 (replaces the Tify CDN load)',
    'assets/vendor/README.md': 'Vendored-asset provenance and verification notes',

    # Story JS — bundle loaded by story pages, source modules loaded by object pages
    'assets/js/telar-story.js': 'Rebuilt story bundle',
    'assets/js/telar-story.js.map': 'Story bundle sourcemap',
    'assets/js/telar-story/iiif-manifest.js': 'IIIF Presentation API v2/v3 manifest parser (new)',
    'assets/js/telar-story/iiif-viewer.js': 'Custom OpenSeadragon viewer wrapper (new, replaces Tify)',
    'assets/js/telar-story/layout-mode.js': 'Responsive layout-mode runtime (new)',
    'assets/js/telar-story/test-hook.js': 'Inert centring measurement hook (new; active only under ?telartest=1)',
    'assets/js/telar-story/card-pool.js': 'Card pool — OSD wrapper integration and centring',
    'assets/js/telar-story/iiif-card.js': 'IIIF card — two-circle centring algorithm',
    'assets/js/telar-story/main.js': 'Story bootstrap — layout-mode routing',
    'assets/js/telar-story/state.js': 'Runtime state — layoutMode/isEmbed/cardOverlayRect',
    'assets/js/telar-story/scroll-engine.js': 'Scroll engine — layout-mode resize subscription',
    'assets/js/telar-story/audio-card.js': 'Audio card — layout-mode resize subscription',
    'assets/js/telar-story/video-card.js': 'Video card — layout-mode resize subscription',
    'assets/js/telar-story/deep-link.js': 'Deep linking — clean-jump navigation fix',
    'assets/js/telar-story/text-card.js': 'Text card — layout-mode reads',
    'assets/js/telar-story/viewer.js': 'Viewer helpers — external multi-page handling',
    'assets/js/telar-story/navigation.js': 'Button navigation',

    # Styles
    'assets/css/telar.scss': 'Main stylesheet entry (imports _responsive)',
    '_sass/_responsive.scss': 'Responsive variable system + cascade layers (new)',
    '_sass/_story.scss': 'Story styles — dvh, safe-area insets, container queries',
    '_sass/_layout.scss': 'Layout styles — cascade layer',
    '_sass/_panels.scss': 'Panel styles — cascade layer, hover scoping',
    '_sass/_share.scss': 'Share styles — cascade layer, hover scoping',
    '_sass/_embed.scss': 'Embed styles — cascade layer, hover scoping',
    '_sass/_viewer.scss': 'Viewer styles — Tify overrides removed, OSD chrome added',
    '_sass/_mixins.scss': 'Mixins — hide-viewer-chrome mixin removed',
    '_sass/_coordinate-panel.scss': 'Coordinate panel styles — hover scoping',
    '_sass/_typography.scss': 'Typography styles — hover scoping',
    '_sass/_widgets.scss': 'Widget styles — hover scoping',

    # Layouts and includes that load or wire the viewer
    '_layouts/story.html': 'Story layout — loads vendored OpenSeadragon, viewer lang keys',
    '_layouts/object.html': 'Object layout — OSD coordinate picker, viewer lang keys',
    '_layouts/default.html': 'Default layout — Bootstrap cascade layer',
    '_includes/viewer.html': 'Viewer include — hover scoping',

    # Language packs (wholesale; gain six object.viewer.* keys)
    '_data/languages/en.yml': 'English language pack (new object.viewer.* keys)',
    '_data/languages/es.yml': 'Spanish language pack (new object.viewer.* keys)',

    # Scripts and docs
    'scripts/iiif_utils.py': 'IIIF tiling utility — post-Tify comments',
    'scripts/README.md': 'Scripts README (OpenSeadragon)',
    'NOTICE': 'Third-party notices (Tify removed, OpenSeadragon added)',
    'README.md': 'README (v1.4.0 badges, dependency credits)',
    'CHANGELOG.md': 'CHANGELOG (v1.4.0 release notes)',
}

# Stale bundle files removed in v1.4.0 — deleted from user sites if present.
STALE_BUNDLE_FILES = [
    'assets/js/telar-story.bundle.js',
    'assets/js/telar-story-bundle.js',
]


class Migration130to140(BaseMigration):
    """Migration from v1.3.0 to v1.4.0 — responsive system + custom IIIF viewer."""

    from_version = "1.3.0"
    to_version = "1.4.0"
    description = "Responsive system overhaul and custom IIIF viewer (Tify removed); runtime-only"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[str]:
        changes: List[str] = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Track the vendored asset tree and ignore the stale bundles
        print("  Phase 2: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # Phase 3: Remove stale bundle files
        print("  Phase 3: Removing stale bundle files...")
        changes.extend(self._remove_stale_bundles())

        # Phase 4: Version bump
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("1.4.0", today):
            changes.append(f"Updated _config.yml: version 1.4.0 ({today})")

        return changes

    # ------------------------------------------------------------------ #
    # Phase 1: framework file fetch
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[str]:
        """Fetch every changed v1.4.0 framework file from GitHub main."""
        changes: List[str] = []

        for file_path, description in FRAMEWORK_FILES.items():
            content = self._fetch_from_github(file_path)
            if content is not None:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} — {description}")
            else:
                changes.append(
                    f"⚠️  Could not fetch {file_path} from GitHub (network or release timing). Update it manually."
                )

        return changes

    # ------------------------------------------------------------------ #
    # Phase 2: .gitignore
    # ------------------------------------------------------------------ #

    def _update_gitignore(self) -> List[str]:
        """Add the vendored-asset negation and the stale-bundle ignore patterns.

        The `!assets/vendor/` negation must re-include the vendored
        OpenSeadragon bundle, which the existing Bundler `vendor/` rule would
        otherwise ignore — without it, git silently skips the new asset and the
        deployed site has no viewer. Appended after the existing rules so the
        negation takes effect.
        """
        added = self._ensure_gitignore_entries(
            ['!assets/vendor/', 'telar-story*.bundle.js', 'telar-story-bundle.js']
        )
        if added:
            return ["Updated .gitignore — track assets/vendor/, ignore stale story bundles"]
        return ["Skipped .gitignore (entries already present)"]

    # ------------------------------------------------------------------ #
    # Phase 3: stale bundle cleanup
    # ------------------------------------------------------------------ #

    def _remove_stale_bundles(self) -> List[str]:
        """Delete the two unreferenced bundle files removed in v1.4.0."""
        changes: List[str] = []
        for rel_path in STALE_BUNDLE_FILES:
            if self._file_exists(rel_path):
                os.remove(os.path.join(self.repo_root, rel_path))
                changes.append(f"Removed stale bundle file {rel_path}")
        if not changes:
            return ["No stale bundle files to remove"]
        return changes

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No action required.** v1.4.0 is a runtime-only upgrade.

Your stories, objects, and configuration keep working without any content changes. The headline improvements:

- **Cross-device IIIF centering fixed** — focal points land correctly across phones, tablets, and desktops, including iPad portrait and landscape phones.
- **Lighter and faster** — Tify (and its Vue dependency) removed; OpenSeadragon is now vendored and loaded locally, so the viewer no longer depends on a CDN.
- **iOS Safari stability** — the URL-bar layout jump is fixed and notch safe-area clearance is added.

One note: the upgrade refreshed the framework language packs (en.yml / es.yml). If you had customised either file, re-apply your changes — the new release adds six `object.viewer.*` keys (pagination labels and error messages for the IIIF viewer) that the updated packs already include.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No se requiere ninguna acción.** v1.4.0 cambia solo el funcionamiento interno de Telar: tus historias, objetos y configuración siguen funcionando sin que tengas que tocar nada.

Las mejoras principales:

- **Centrado IIIF entre dispositivos corregido** — los puntos focales se ubican correctamente en teléfonos, tabletas y computadores, incluidos el iPad en vertical y los teléfonos en horizontal.
- **Más liviano y rápido** — se eliminó Tify (y su dependencia de Vue); ahora OpenSeadragon viene incluido en el repositorio y se carga localmente, así que el visor ya no depende de un CDN.
- **Estabilidad en iOS Safari** — se corrigió el salto del diseño que causaba la barra de direcciones del navegador y se añadió espacio para la muesca de la pantalla.

Un detalle: la actualización reemplazó los paquetes de idioma de Telar (en.yml / es.yml). Si habías personalizado alguno de ellos, vuelve a aplicar tus cambios — esta versión agrega seis claves `object.viewer.*` (etiquetas de paginación y mensajes de error del visor IIIF) que los paquetes actualizados ya incluyen.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
