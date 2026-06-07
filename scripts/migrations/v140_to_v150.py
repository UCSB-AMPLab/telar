"""
Migration from v1.4.0 to v1.5.0.

Robustness & Security. This release implements the framework-side hardening
from a security review: the data-processing pipeline, the viewer runtime, the
standalone JS, and the upgrade workflow are all tightened. It is a
runtime/pipeline release — the story step schema, CSV formats, and the
(x, y, zoom) capture contract are unchanged, so there are no user-content
transforms. Existing stories, objects, and configuration keep working without
edits.

What the upgrade does:

1. Framework files (fetched from the v1.5.0 release tag, not the moving `main`
   branch, and written atomically — all or nothing). Every changed runtime,
   pipeline, layout, and language file is re-fetched:

   - Build pipeline (runs in each fork's own GitHub Actions build, so the
     security fixes must land in the fork's scripts/): capped reads and an
     object_id path guard (pipeline_utils.py), a shared media-type leaf module
     (telar/media_type.py), CSV/URL escaping and fetch hygiene across the
     fetch, collection-generation, IIIF, audio, PDF, glossary, search, and
     processor scripts.
   - Viewer runtime: the rebuilt story bundle plus its source modules
     (IIIF step-indexing and same-object plate visibility fixes, deep-link
     timer-ladder cancellation, panel-stack handling, title/attribute escape
     sinks, prefetch dedup, and the YouTube/Drive video-positioning fix).
   - Standalone JS (not part of the bundle): share-panel, story-unlock,
     objects-filter, embed, and telar.js.
   - Vendored WaveSurfer (audio waveforms): wavesurfer.js core + the Regions
     plugin are now bundled under assets/vendor/wavesurfer/ and loaded locally,
     so audio cards no longer fetch the library from a CDN.
   - Styles, layouts, includes, and both language packs (which gain the
     protected-story key-exposure sharing warnings).

2. .gitignore — defensively re-ensures the `!assets/vendor/` negation so the
   newly vendored WaveSurfer files are tracked despite the Bundler `vendor/`
   rule. A site upgraded from v1.4.0 already has this entry (the v1.4.0
   migration added it for OpenSeadragon); the re-ensure is a no-op there and
   only matters for a site that lost it.

Workflow files are deliberately NOT delivered here, and instead surfaced as a
manual step — the long-standing convention (v0.6.3, v0.8.1, v0.9.1, v1.0.0).
The upgrade GITHUB_TOKEN has only `contents`/`issues` write, not
`workflows: write`, so when the upgrade workflow stages its changes
(`git add -- .`) and pushes the upgrade branch, GitHub *rejects the entire
push* if it touches `.github/workflows/*` — that would break the whole upgrade,
not just the workflow file. Two v1.5.0 workflow improvements are therefore
manual: the hardened `.github/workflows/upgrade.yml` (checksum-verified,
isolated tooling) and the `ruby/setup-ruby` SHA-pin in
`.github/workflows/build.yml`. Neither is required for the site to keep
building and deploying; both harden it. See the manual step.

The migration engine itself (upgrade.py, the migrations package, base.py,
messages.py) is delivered out of band by the upgrade workflow, which downloads
the verified, checksum-pinned telar-scripts-v1.5.0.tar.gz and runs it from a
temp copy — the fork's own copy of those files is never relied on at upgrade
time, so they are not in FRAMEWORK_FILES.

The version stamp (telar.version -> 1.5.0) is not written here. It is applied
once by upgrade.py after every migration step succeeds, so a failed fetch can
never leave the site stamped as a version it is not running.

Language packs are framework-owned and fetched wholesale, per the established
convention. A site that customised en.yml or es.yml will have those edits
replaced and should re-apply them after upgrading (see the manual step).

Version: v1.5.0
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus


# Framework files fetched from the v1.5.0 release tag and written atomically.
# Grouped by subsystem for the upgrade summary; every entry is a file that
# changed in v1.5.0 and is part of a user site's runtime, build pipeline, or
# template. Build-pipeline scripts are included because they run from the
# fork's own checkout during its GitHub Actions build, so their security fixes
# must be written into the fork. The upgrade engine (upgrade.py, migrations/,
# base.py, messages.py) is intentionally excluded — it ships via the verified
# release tarball and runs from a temp copy. build.yml is excluded — see the
# module docstring (workflow-token restriction; optional manual SHA-pin merge).
FRAMEWORK_FILES = {
    # --- Build pipeline (runs in each fork's own CI build) ---
    'scripts/pipeline_utils.py': 'Capped reads + object_id path guard (new shared module)',
    'scripts/telar/media_type.py': 'Shared media-type detection leaf module (new)',
    'scripts/discover_sheet_gids.py': 'Sheet GID discovery — capped reads',
    'scripts/fetch_google_sheets.py': 'Google Sheets fetch — capped reads, fetch hygiene',
    'scripts/fetch_demo_content.py': 'Demo content fetch — capped reads',
    'scripts/generate_collections.py': 'Collection generation — media-type module, escaping',
    'scripts/generate_iiif.py': 'IIIF tile generation — hardening',
    'scripts/iiif_utils.py': 'IIIF tiling utility — hardening',
    'scripts/process_audio.py': 'Audio processing — hardening',
    'scripts/process_pdf.py': 'PDF processing — hardening',
    'scripts/telar/core.py': 'Pipeline core — capped reads, escaping',
    'scripts/telar/csv_utils.py': 'CSV utilities — IMAGE_EXTENSIONS, stem index, URL resolver',
    'scripts/telar/encryption.py': 'Protected-story encryption — plaintext-leak fix',
    'scripts/telar/glossary.py': 'Glossary processing — hardening',
    'scripts/telar/markdown.py': 'Markdown — documented content trust model',
    'scripts/telar/search.py': 'Search index — media-type module',
    'scripts/telar/widgets.py': 'Widgets — hardening',
    'scripts/telar/processors/objects.py': 'Object processor — media-type module',
    'scripts/telar/processors/project.py': 'Project processor — hardening',
    'scripts/telar/processors/stories.py': 'Story processor — hardening',

    # --- Vendored audio dependency (no CDN) ---
    'assets/vendor/wavesurfer/wavesurfer.min.js': 'Vendored wavesurfer.js 7.12.7 core (replaces the unpkg load)',
    'assets/vendor/wavesurfer/plugins/regions.min.js': 'Vendored WaveSurfer Regions plugin',
    'assets/vendor/README.md': 'Vendored-asset provenance and verification notes',

    # --- Story JS — bundle loaded by story pages, source modules by object pages ---
    'assets/js/telar-story.js': 'Rebuilt story bundle',
    'assets/js/telar-story.js.map': 'Story bundle sourcemap',
    'assets/js/telar-story/audio-card.js': 'Audio card — vendored WaveSurfer loader',
    'assets/js/telar-story/card-pool.js': 'Card pool — IIIF step-indexing + plate visibility, prefetch dedup',
    'assets/js/telar-story/deep-link.js': 'Deep linking — timer-ladder cancellation on interaction',
    'assets/js/telar-story/iiif-card.js': 'IIIF card — same-object plate visibility',
    'assets/js/telar-story/iiif-viewer.js': 'IIIF viewer wrapper — hardening',
    'assets/js/telar-story/panels.js': 'Panels — panel-stack handling',
    'assets/js/telar-story/scroll-engine.js': 'Scroll engine — hardening',
    'assets/js/telar-story/state.js': 'Runtime state — hardening',
    'assets/js/telar-story/utils.js': 'Utilities — base-path helper',
    'assets/js/telar-story/video-card.js': 'Video card — YouTube/Drive aspect detection + letterbox',
    'assets/js/telar-story/viewer.js': 'Viewer helpers — title/attribute escape sinks',

    # --- Standalone JS (not bundled) ---
    'assets/js/share-panel.js': 'Share panel — documented key-in-embed exposure',
    'assets/js/story-unlock.js': 'Story unlock — hardening',
    'assets/js/objects-filter.js': 'Objects filter — escape sinks',
    'assets/js/embed.js': 'Embed bootstrap — hardening',
    'assets/js/telar.js': 'Site JS — hardening',

    # --- Styles ---
    '_sass/_story.scss': 'Story styles — video letterbox background',
    '_sass/_layout.scss': 'Layout styles — theme-button text colour fix (carried from v1.4.0 hotfix)',

    # --- Layouts and includes ---
    '_layouts/default.html': 'Default layout — hardening',
    '_layouts/index.html': 'Index layout — escaping',
    '_layouts/object.html': 'Object layout — escaping',
    '_layouts/story.html': 'Story layout — escaping',
    '_includes/iiif-url-warning.html': 'IIIF URL warning include — hardening',
    '_includes/katex.html': 'KaTeX include — hardening',
    '_includes/panels.html': 'Panels include — escaping',

    # --- Language packs (wholesale; gain protected-story sharing warnings) ---
    '_data/languages/en.yml': 'English language pack (key-exposure sharing warnings)',
    '_data/languages/es.yml': 'Spanish language pack (key-exposure sharing warnings)',

    # NOTE: .github/workflows/ files (upgrade.yml hardening, build.yml SHA-pin)
    # are NOT delivered — the upgrade token cannot push workflow changes, so
    # including them would make the whole upgrade push fail. Handled as a manual
    # step instead (the v0.6.3/v0.8.1/v0.9.1/v1.0.0 convention).
}


class Migration140to150(BaseMigration):
    """Migration from v1.4.0 to v1.5.0 — robustness & security hardening; runtime/pipeline-only."""

    from_version = "1.4.0"
    to_version = "1.5.0"
    description = "Robustness & security hardening (pipeline, viewer, upgrade workflow); runtime-only"

    # Pin framework-file fetches to the v1.5.0 release tag, not the moving
    # `main` branch, so this migration always installs v1.5.0 files.
    _TARGET_TAG = "v1.5.0"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        changes: List[ChangeRecord] = []

        # Phase 1: install framework files atomically from the pinned tag.
        print("  Phase 1: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Fail closed: if any framework file did not install, do not touch the
        # .gitignore. upgrade.py will see the HARD failure, leave the version
        # unstamped, and a re-run retries cleanly.
        if any(c.status == ChangeStatus.FAILED for c in framework_changes):
            return changes

        # Phase 2: defensively ensure the vendored-asset tree stays tracked so
        # the new WaveSurfer files are committed.
        print("  Phase 2: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # No version bump here — upgrade.py stamps once after all steps succeed.
        return changes

    # ------------------------------------------------------------------ #
    # Phase 1: framework file fetch (pinned + atomic)
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install every changed v1.5.0 framework file from the pinned tag.

        Delegates to the staged-atomic helper: all files are fetched into
        memory first, and nothing is written unless every fetch succeeds.
        """
        return self._apply_framework_files(FRAMEWORK_FILES)

    # ------------------------------------------------------------------ #
    # Phase 2: .gitignore
    # ------------------------------------------------------------------ #

    def _update_gitignore(self) -> List[ChangeRecord]:
        """Re-ensure the `!assets/vendor/` negation.

        The negation must re-include the vendored WaveSurfer files, which the
        existing Bundler `vendor/` rule would otherwise ignore — without it git
        silently skips the new assets and audio cards 404 on the local path. A
        site upgraded from v1.4.0 already has this entry, so this is normally a
        no-op; it only matters for a site that lost or never had it.
        """
        added = self._ensure_gitignore_entries(['!assets/vendor/'])
        description = (
            "Updated .gitignore — re-ensured assets/vendor/ is tracked"
            if added else "Skipped .gitignore (assets/vendor/ already tracked)"
        )
        return [ChangeRecord(description=description, status=ChangeStatus.APPLIED, severity="soft")]

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Recommended — update your GitHub Actions workflow files by hand.** For security, GitHub does not let the automated upgrade modify workflow files, so two v1.5.0 improvements are not applied for you:

- `.github/workflows/upgrade.yml` — the upgrade process is now hardened: it downloads its tooling as a release asset, verifies it against the published checksum, and runs it in isolation. This protects your next upgrade.
- `.github/workflows/build.yml` — the `ruby/setup-ruby` action is now pinned to a specific commit, for supply-chain safety.

To apply them, open each file on GitHub, click "Raw", copy the whole file, and replace the contents of the matching file in your repository:

- https://github.com/UCSB-AMPLab/telar/blob/v1.5.0/.github/workflows/upgrade.yml
- https://github.com/UCSB-AMPLab/telar/blob/v1.5.0/.github/workflows/build.yml

If you skip this, your site keeps building and deploying normally — these changes only harden your workflows.''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/v1.5.0/.github/workflows'
            },
            {
                'description': '''**If you customized the language packs, re-apply your changes.** The upgrade refreshed the framework language packs (`en.yml` / `es.yml`). This release adds the protected-story sharing warnings — the messages shown when a share link or embed code includes the access key — which the updated packs already include.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Recomendado: actualiza a mano tus archivos de flujo de trabajo de GitHub Actions.** Por seguridad, GitHub no deja que la actualización automática modifique los archivos de flujo de trabajo, así que dos mejoras de v1.5.0 no se aplican solas:

- `.github/workflows/upgrade.yml`: el proceso de actualización ahora es más seguro — descarga sus herramientas desde el lanzamiento, las verifica con la suma de control publicada y las ejecuta de forma aislada. Así protege tu próxima actualización.
- `.github/workflows/build.yml`: la acción `ruby/setup-ruby` ahora queda fijada a un commit específico, para mayor seguridad en la cadena de suministro.

Para aplicarlas, abre cada archivo en GitHub, haz clic en **Raw** y copia todo el contenido para reemplazar el del archivo correspondiente en tu repositorio:

- https://github.com/UCSB-AMPLab/telar/blob/v1.5.0/.github/workflows/upgrade.yml
- https://github.com/UCSB-AMPLab/telar/blob/v1.5.0/.github/workflows/build.yml

Si te saltas este paso, tu sitio se sigue construyendo y publicando con normalidad; estos cambios solo refuerzan tus flujos de trabajo.''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/v1.5.0/.github/workflows'
            },
            {
                'description': '''**Si personalizaste los paquetes de idioma, vuelve a aplicar tus cambios.** La actualización reemplazó los paquetes de idioma de Telar (`en.yml` / `es.yml`). Esta versión suma los avisos para compartir historias protegidas —los mensajes que aparecen cuando un enlace o un código de inserción lleva la clave de acceso—, que los paquetes actualizados ya incluyen.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
