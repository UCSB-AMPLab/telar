"""
Migration from v1.5.4 to v1.6.0.

Code Health release. The runtime and build pipeline are extensively
refactored for signposting and dead-code removal (extracted JS/include
modules, a design-token style layer, consolidated pipeline scripts), and
protected stories move to post-build encryption: the encrypted envelope is
now rendered into a dedicated fragment layout and unlocked client-side,
replacing generation-time encryption. A fallback IIIF tile backend also
lands (canonical width/height tile paths, full/max sizing) for sites that
generated tiles without libvips. This is a runtime/pipeline release — the
story step schema, CSV formats, and `_config.yml` keys are unchanged
(`private`/`privada` are now the documented canonical CSV columns, but
`protected`/`protegida` still alias, so no user data edit is required), so
there are no user-content transforms. Existing stories, objects, and
configuration keep working without edits.

What the upgrade does:

1. Framework files (fetched from the v1.6.0 release tag/branch, not the
   moving `main` branch, and written atomically — all or nothing). Every
   changed layout, include, style, script, and language file is re-fetched:
   the extracted JS/include modules (object grid item, share-panel embed
   controls and site tab, story steps loop, KaTeX loader, Christmas-tree
   decorator, IIIF thumbnail resolution, IIIF URL warning diagnostic,
   object-page theme/video helpers, vendored WaveSurfer loader), the
   protected-story rewrite (post-build encryption script, the story-fragment
   layout, the rewritten unlock script), the fallback IIIF tile backend, the
   design-token style layer, and both language packs (new keys — see the
   manual step).

2. `.gitattributes` — new in v1.6.0 (marks the generated story bundle and
   its sourcemap `linguist-generated`). No prior release shipped this file,
   so there is no established merge precedent for it; this migration treats
   it like a config file rather than a blind framework overwrite — it is
   only written when the site does not already have one, so a site that
   already created its own `.gitattributes` is never clobbered. When one
   already exists, this is recorded as skipped and surfaced as a manual
   step so the user can merge the new linguist markers by hand.

3. Deletions (explicit delete actions, v130 pattern):
   - `_includes/viewer.html` — dead include; the protected-story rewrite and
     earlier extractions left it unreferenced.
   - `assets/js/telar-icons.js` — loaded by nothing; its NOTICE attribution
     moved.

Tests (`tests/`) are NOT part of FRAMEWORK_FILES, matching the unbroken
precedent across the whole v1.4.0-v1.5.4 line: v1.4.0->v1.5.0 added or
changed 15 test files and v1.5.0->v1.5.1 added
`tests/unit/test_protected_story_glossary.py` itself, and neither migration
shipped any of them (verified against `git diff --name-status` on the
public repo's tags). Tests are dev-only tooling for the Telar repo, not part
of a user site's runtime. Consistently, this migration also does NOT delete
`tests/unit/test_protected_story_glossary.py` even though it pins the
removed generation-time encryption and will fail on v1.6.0 code — since
tests never reach a user site in the first place, there is nothing on a
site to delete.

The upgrade engine itself (upgrade.py, the migrations package, base.py,
messages.py) is excluded from FRAMEWORK_FILES for the same reason as every
prior release: it ships out of band (the upgrade workflow's own bootstrap
already runs v1.6.0 code by the time this migration executes), so a running
migration never needs to re-fetch or overwrite its own package. This also
explains why several pre-v1.5.4 migration files show as modified in the
v1.6.0 diff (retroactive `Version:` header backfills) — an engine-internal
change, not a site-facing one.

`.github/workflows/build.yml` gains a required "Encrypt protected stories"
step. GitHub does not allow the upgrade's GITHUB_TOKEN to modify workflow
files, so this migration cannot install it — the long-standing convention
(v0.6.3, v0.8.1, v0.9.1, v1.0.0, v1.5.0, v1.5.3, ...). Without the manual
step, marking any story `private: yes` fails that site's build by design
(the core.py interlock refuses to publish an unprotected private story
rather than fail open). See the manual step below.

The version stamp (telar.version -> 1.6.0) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed fetch can
never leave the site stamped as a version it is not running.

Language packs are framework-owned and fetched wholesale, per the
established convention. A site that customised en.yml or es.yml will have
those edits replaced and should re-apply them after upgrading (see the
manual step).

Version: v1.6.0
"""

import os
from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus


# Framework files fetched from the v1.6.0 release tag/branch and written
# atomically. Grouped by subsystem for the upgrade summary; every entry is a
# file that changed in v1.6.0 and is part of a user site's runtime, build
# pipeline, or template. `.gitattributes` is handled separately (Phase 2,
# additive-only — see the module docstring). `.github/workflows/build.yml`
# is excluded — the upgrade token cannot write workflow files (manual step).
# tests/ and the upgrade engine itself (upgrade.py, migrations/, base.py,
# messages.py) are excluded — see the module docstring.
FRAMEWORK_FILES = {
    # --- Configuration / data ---
    '_data/katex.yml': 'KaTeX configuration (new) — CDN URLs, version, delimiters in one place',
    '_data/languages/en.yml': 'English language pack (new keys — see manual step)',
    '_data/languages/es.yml': 'Spanish language pack (same new keys at parity)',

    # --- Layouts ---
    '_layouts/default.html': 'Default layout — design-token layer completion, header i18n',
    '_layouts/glossary.html': 'Glossary entry layout — dead glossary-shim removal',
    '_layouts/index.html': 'Home layout — object-grid-item and IIIF-thumbnail extraction',
    '_layouts/object.html': 'Object layout — inline algorithm extraction (theme, video embed, viewer coordinates), protected-story re-key',
    '_layouts/objects-index.html': 'Objects index — object-grid-item extraction, shared IIIF thumbnail module',
    '_layouts/story-fragment.html': 'Protected-story fragment layout (new) — rendered envelope, unlocked client-side',
    '_layouts/story.html': 'Story layout — KaTeX loader / Christmas-tree decorator extraction, shared story-steps loop, protected-story re-key',
    '_layouts/upgrade-summary.html': 'Upgrade summary layout — i18n completion',

    # --- Includes ---
    '_includes/header.html': 'Header include — localized fallback menu',
    '_includes/iiif-url-warning.html': 'IIIF URL warning include — diagnostic extracted to a standalone script',
    '_includes/katex.html': 'KaTeX include — reads _data/katex.yml',
    '_includes/object-grid-item.html': 'Objects-index gallery card (new, extracted from index/objects-index layouts)',
    '_includes/panels.html': 'Panels include — Offcanvas reuse guard',
    '_includes/share-embed-controls.html': 'Share-panel embed-size controls (new, extracted from share-panel.html)',
    '_includes/share-panel.html': 'Share panel — local language resolution, extracted embed/site-tab blocks',
    '_includes/share-site-tab.html': 'Share-panel "whole site" tab (new, extracted from share-panel.html)',
    '_includes/story-steps.html': 'Shared story-step loop (new) — used by both story.html and story-fragment.html',
    '_includes/upgrade-alert.html': 'Upgrade alert include — localized success alert',
    '_includes/widgets/accordion.html': 'Accordion widget — comment cleanup',
    '_includes/widgets/bibliography.html': 'Bibliography widget — comment cleanup',
    '_includes/widgets/carousel.html': 'Carousel widget — image src resolved in the widget parser, not the template',
    '_includes/widgets/tabs.html': 'Tabs widget — comment cleanup',

    # --- Styles ---
    '_sass/_embed.scss': 'Embed styles — nav-position breakpoint alignment',
    '_sass/_latex.scss': 'LaTeX styles — KaTeX consolidation',
    '_sass/_layout.scss': 'Layout styles — design-token layer',
    '_sass/_mixins.scss': 'Mixins — design-token layer additions',
    '_sass/_panels.scss': 'Panel styles — Offcanvas/panel fixes',
    '_sass/_responsive.scss': 'Responsive variable system — design-token layer completion',
    '_sass/_share.scss': 'Share styles — embed-controls/site-tab extraction',
    '_sass/_story.scss': 'Story styles — token-layer cleanup',
    '_sass/_viewer.scss': 'Viewer styles — chrome cleanup',
    '_sass/_widgets.scss': 'Widget styles — dead-rule removal, token layer',
    'assets/css/telar.scss': 'Main stylesheet entry — token-layer imports',

    # --- Story JS (bundle loaded by story pages, source modules by object pages) ---
    'assets/js/telar-story.js': 'Rebuilt story bundle (Lenis 1.3.23)',
    'assets/js/telar-story.js.map': 'Story bundle sourcemap',
    'assets/js/telar-story/audio-card.js': 'Audio card — clip-start seek fix on ready',
    'assets/js/telar-story/card-pool.js': 'Card pool — registry/interpolation vocabulary renamed to match lifecycles',
    'assets/js/telar-story/deep-link.js': 'Deep linking — dead fallback removal',
    'assets/js/telar-story/iiif-card.js': 'IIIF card — dead viewer-config fallback removal',
    'assets/js/telar-story/iiif-viewer.js': 'Viewer wrapper — cleanup',
    'assets/js/telar-story/main.js': 'Story bootstrap — cleanup',
    'assets/js/telar-story/navigation.js': 'Button navigation — cleanup',
    'assets/js/telar-story/panels.js': 'Panels — Offcanvas reuse guard',
    'assets/js/telar-story/scroll-engine.js': 'Scroll engine — dead code removal',
    'assets/js/telar-story/state.js': 'Runtime state — title-card state fields declared',
    'assets/js/telar-story/test-hook.js': 'Centring measurement hook — de-staled header comment',
    'assets/js/telar-story/text-card.js': 'Text card — content escaping, dead code removal',
    'assets/js/telar-story/utils.js': 'Utilities — dead code removal',
    'assets/js/telar-story/video-card.js': 'Video card — minor fix',
    'assets/js/telar-story/viewer.js': 'Viewer helpers — cleanup',

    # --- Standalone JS (not bundled) ---
    'assets/js/christmas-tree-decorator.js': 'Christmas Tree Mode warning decorator (new, extracted from story.html)',
    'assets/js/embed.js': 'Embed bootstrap — nav-position breakpoint alignment',
    'assets/js/iiif-thumbnails.js': 'Shared IIIF thumbnail resolution (new) — sorted size pick, direct-URL fallback',
    'assets/js/iiif-url-warning.js': 'IIIF URL mismatch diagnostic (new, extracted from iiif-url-warning.html)',
    'assets/js/katex-loader.js': 'Lazy KaTeX loader for story pages (new, extracted from story.html)',
    'assets/js/object-theme.js': 'Object-page theme contrast helpers (new, extracted)',
    'assets/js/objects-filter.js': 'Objects filter — skip IIIF thumbnail fetch for video/audio objects',
    'assets/js/share-panel.js': 'Share panel — extracted embed-controls/site-tab blocks',
    'assets/js/story-unlock.js': 'Story unlock — rewritten for the rendered protected-story envelope',
    'assets/js/telar.js': 'Site JS — dead code removal',
    'assets/js/video-embed.js': 'Object-page video embed resolution (new, extracted)',
    'assets/js/wavesurfer-loader.js': 'Vendored WaveSurfer loader (new, extracted from object.html)',
    'assets/js/widgets.js': 'Widgets bootstrap — minor fix',

    # --- Build pipeline / telar package (runs in each site's own CI build) ---
    'scripts/build_local_site.py': 'Local build orchestration — pipeline consolidation',
    'scripts/csv_to_json.py': 'CSV-to-JSON conversion — minor fix',
    'scripts/discover_sheet_gids.py': 'Sheet GID discovery — consolidation, dead-code removal',
    'scripts/encrypt_protected_stories.py': 'Post-build protected-story encryption (new)',
    'scripts/fetch_google_sheets.py': 'Google Sheets fetch — minor fix',
    'scripts/generate_collections.py': 'Collection generation — consolidation',
    'scripts/generate_iiif.py': 'IIIF tile generation — fallback tile backend (canonical w,h paths, full/max)',
    'scripts/iiif_utils.py': 'IIIF tiling utility — fallback tile backend support',
    'scripts/process_audio.py': 'Audio processing — ffmpeg requirement dropped; audiowaveform is the only tool',
    'scripts/process_pdf.py': 'PDF processing — minor fix',
    'scripts/telar/__init__.py': 'Package init — minor fix',
    'scripts/telar/core.py': 'Pipeline core — content-gate coverage, protected-story post-build hook',
    'scripts/telar/csv_utils.py': 'CSV utilities — minor fix',
    'scripts/telar/demo.py': 'Demo content handling — minor fix',
    'scripts/telar/encryption.py': 'Protected-story encryption — post-build support',
    'scripts/telar/iiif_metadata.py': 'IIIF metadata — dead-code removal',
    'scripts/telar/markdown.py': 'Markdown processing — consolidation',
    'scripts/telar/media_type.py': 'Media-type detection — uppercase audio-extension fix',
    'scripts/telar/processors/objects.py': 'Object processor — alt_text fix, cleanup',
    'scripts/telar/processors/stories.py': 'Story processor — protected-story frontmatter re-keying',
    'scripts/telar/search.py': 'Search index — minor fix',
    'scripts/telar/widgets.py': 'Widgets — carousel src resolution, comment-rendering fix',

    # --- Documentation / metadata ---
    'assets/js/README.md': 'JS directory README (new) — generated-bundle note',
    'CITATION.cff': 'Citation metadata — contributor addition',
    'NOTICE': 'Third-party notices — telar-icons.js attribution removed',
    'README.md': 'README — contributor credits',
    'package.json': 'Dependency metadata (Lenis 1.3.23 pin)',
}

# .gitattributes is new in v1.6.0 and has no merge helper (unlike .gitignore's
# _ensure_gitignore_entries), so it is handled as its own additive-only phase
# rather than folded into FRAMEWORK_FILES — see the module docstring.
GITATTRIBUTES_PATH = '.gitattributes'

# Deletions explicit in v1.6.0 (v130 pattern) — dead files removed from the
# template that a framework re-fetch alone would not delete.
DELETED_FILES = [
    '_includes/viewer.html',
    'assets/js/telar-icons.js',
]


class Migration154to160(BaseMigration):
    """Migration from v1.5.4 to v1.6.0 — Code Health: signposting, protected-story rewrite, IIIF fallback backend."""

    from_version = "1.5.4"
    to_version = "1.6.0"
    description = "Code Health release — signposting/cleanup, post-build protected-story encryption, IIIF fallback tile backend"

    # Pin framework-file fetches to the v1.6.0 release tag/branch, not the
    # moving `main` branch, so this migration always installs v1.6.0 files.
    _TARGET_TAG = "v1.6.0"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        changes: List[ChangeRecord] = []

        # Phase 1: install framework files atomically from the pinned tag.
        print("  Phase 1: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Fail closed: if any framework file did not install, do not touch
        # .gitattributes or remove the dead files. upgrade.py will see the
        # HARD failure, leave the version unstamped, and a re-run retries
        # cleanly.
        if any(c.status == ChangeStatus.FAILED for c in framework_changes):
            return changes

        # Phase 2: add .gitattributes only if the site doesn't already have one.
        print("  Phase 2: Adding .gitattributes...")
        changes.extend(self._add_gitattributes())

        # Phase 3: remove dead files.
        print("  Phase 3: Removing dead files...")
        changes.extend(self._remove_deleted_files())

        # No version bump here — upgrade.py stamps once after all steps succeed.
        return changes

    # ------------------------------------------------------------------ #
    # Phase 1: framework file fetch (pinned + atomic)
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install every changed v1.6.0 framework file from the pinned tag.

        Delegates to the staged-atomic helper: all files are fetched into
        memory first, and nothing is written unless every fetch succeeds.
        """
        return self._apply_framework_files(FRAMEWORK_FILES)

    # ------------------------------------------------------------------ #
    # Phase 2: .gitattributes (additive-only — never clobber a site's own)
    # ------------------------------------------------------------------ #

    def _add_gitattributes(self) -> List[ChangeRecord]:
        """Write .gitattributes only when the site doesn't already have one.

        No prior release shipped this file, so there is no merge helper for
        it (unlike .gitignore's _ensure_gitignore_entries). Rather than
        overwrite a site-authored .gitattributes through the atomic
        framework-file path, this checks first: if the file is already
        present, it is left untouched and a manual step (below) tells the
        user to merge the new linguist-generated markers by hand. This
        outcome also drives whether get_manual_steps() surfaces that note.
        """
        if self._file_exists(GITATTRIBUTES_PATH):
            self._gitattributes_skipped = True
            return [ChangeRecord(
                description=(
                    f"Skipped {GITATTRIBUTES_PATH} (already exists) — "
                    "see the manual step to merge the new linguist-generated markers"
                ),
                status=ChangeStatus.APPLIED,
                severity="soft",
            )]

        self._gitattributes_skipped = False
        content = self._fetch_from_github(GITATTRIBUTES_PATH, branch=self._TARGET_TAG)
        if content is None:
            return [ChangeRecord(
                description=(
                    f"Could not fetch {GITATTRIBUTES_PATH} from GitHub. "
                    "Non-fatal — add it manually if you want the generated-bundle markers."
                ),
                status=ChangeStatus.FAILED,
                severity="soft",
            )]

        self._write_file(GITATTRIBUTES_PATH, content)
        return [ChangeRecord(
            description=f"Added {GITATTRIBUTES_PATH} — marks the generated story bundle as linguist-generated",
            status=ChangeStatus.APPLIED,
            severity="soft",
        )]

    # ------------------------------------------------------------------ #
    # Phase 3: dead-file cleanup
    # ------------------------------------------------------------------ #

    def _remove_deleted_files(self) -> List[ChangeRecord]:
        """Delete the files removed in v1.6.0, if present."""
        changes: List[ChangeRecord] = []
        for rel_path in DELETED_FILES:
            if self._file_exists(rel_path):
                os.remove(os.path.join(self.repo_root, rel_path))
                changes.append(ChangeRecord(
                    description=f"Removed dead file {rel_path}",
                    status=ChangeStatus.APPLIED, severity="soft",
                ))
        if not changes:
            return [ChangeRecord(
                description="No dead files to remove",
                status=ChangeStatus.APPLIED, severity="soft",
            )]
        return changes

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        steps = [
            {
                'description': '''**Update `.github/workflows/build.yml` by hand (required if you use private stories).** v1.6.0 encrypts private stories in a new build step that GitHub does not allow this upgrade to add for you. Copy the current `build.yml` from the Telar repository over yours (open it on GitHub, use "Copy raw contents", replace the whole file, commit). Until you do, marking any story `private: yes` will fail your build on purpose rather than publish it unprotected. Details: https://telar.org/docs/setup/upgrading/#v160-upgrade-notes''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/#v160-upgrade-notes'
            },
            {
                'description': '''**If you customized the language packs, re-apply your changes.** The upgrade refreshed the framework language packs (`en.yml` / `es.yml`). This release adds several keys — the private-story unlock messages (empty/incorrect key), the embed banner's site-name fallback, audio-player control labels, and widget/glossary strings, among others — which the updated packs already include.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]
        if getattr(self, '_gitattributes_skipped', False):
            steps.append({
                'description': '''**Optional — merge the new `.gitattributes`.** Your site already has a `.gitattributes` file, so the upgrade left it untouched. v1.6.0's template adds two lines marking the generated story bundle as `linguist-generated`, which keeps it out of GitHub's diff view and language statistics:

```
assets/js/telar-story.js linguist-generated
assets/js/telar-story.js.map linguist-generated
```

Add these to your existing file if you'd like the same behaviour.''',
                'doc_url': 'https://telar.org/docs'
            })
        return steps

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        steps = [
            {
                'description': '''**Actualiza `.github/workflows/build.yml` a mano (obligatorio si usas historias privadas).** v1.6.0 cifra las historias privadas en un nuevo paso de construcción que GitHub no permite que esta actualización agregue por ti. Copia el `build.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). Mientras no lo hagas, marcar cualquier historia con `private: yes` hará fallar tu construcción a propósito, en lugar de publicarla sin proteger. Detalles: https://telar.org/guia/configuracion/actualizacion/#notas-de-actualización-a-v160''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/#notas-de-actualización-a-v160'
            },
            {
                'description': '''**Si personalizaste los paquetes de idioma, vuelve a aplicar tus cambios.** La actualización reemplazó los paquetes de idioma del marco (`en.yml` / `es.yml`). Esta versión agrega varias claves — los mensajes de desbloqueo de historias privadas (clave vacía/incorrecta), el nombre de respaldo del sitio en el banner de incrustado, las etiquetas de los controles del reproductor de audio y textos de widgets/glosario, entre otras — que los paquetes actualizados ya incluyen.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
        if getattr(self, '_gitattributes_skipped', False):
            steps.append({
                'description': '''**Opcional — fusiona el nuevo `.gitattributes`.** Tu sitio ya tiene un archivo `.gitattributes`, así que la actualización lo dejó sin tocar. La plantilla de v1.6.0 agrega dos líneas que marcan el paquete de JavaScript generado (`telar-story.js`) como `linguist-generated`, lo que lo excluye de la vista de diferencias de GitHub y de las estadísticas de lenguaje:

```
assets/js/telar-story.js linguist-generated
assets/js/telar-story.js.map linguist-generated
```

Agrégalas a tu archivo existente si quieres el mismo comportamiento.''',
                'doc_url': 'https://telar.org/guia'
            })
        return steps
