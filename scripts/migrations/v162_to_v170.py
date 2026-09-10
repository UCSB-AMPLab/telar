"""
Migration from v1.6.2 to v1.7.0.

v1.7.0 is a stewardship release: most of what changed is in how a site is
built, upgraded and tested rather than in what a reader sees. Three kinds of
change reach an existing site, and they arrive in that order.

1. Framework files (FRAMEWORK_FILES, installed atomically from the v1.7.0
   tag). The set is exactly the files a site owns that v1.7.0 adds or
   rewrites: the root manifests (`.gitattributes`, `.ruby-version`, `Gemfile`,
   `requirements.txt`, `package.json`, `package-lock.json`, `README.md`,
   `CHANGELOG.md`), the three page layouts and the IIIF URL warning include,
   the rebuilt JavaScript bundles together with the modules they are built
   from, and the build scripts under `scripts/` — including the split of
   `scripts/telar/processors/objects.py` into a package. Nothing is derived at
   run time: the list is written out here so that what a site receives is a
   decision recorded in the release, not whatever a tree walk happens to
   return on the day the upgrade runs.

   Bundles and their sources ship together on purpose. `home-page.js`,
   `object-page.js`, `objects-filter.js`, `objects-index-page.js`,
   `share-panel.js`, `iiif-url-warning.js` and `telar-story.js` are built
   artefacts; the modules under the matching directories are what they are
   built from. A site that received one without the other would either run
   last release's behaviour from a bundle whose sources say otherwise, or
   rebuild into something the layouts do not load. `_apply_framework_files`
   fetches the whole map before writing any of it, so the set installs
   entirely or not at all.

2. Deletions (Phase 2). Two files v1.7.0 removes have to be removed from the
   site as well, because leaving them behind is worse than never having had
   them — see the phase's own comments.

3. `.gitignore` (Phase 3). `generate_collections.py` now records where each
   story renders, in `_data/telar-build/`, so the post-build encryption step
   never has to guess a URL. That directory is generated on every build and
   does not belong in a site's history.

`scripts/upgrade.py` IS delivered, and that is a departure from the
convention every migration since v1.5.0 has documented — that `upgrade.py`,
the `migrations` package, `base.py` and `messages.py` are excluded from
FRAMEWORK_FILES and ship out of band in the verified release tarball. The
convention is intact; the file it named has changed identity. As of v1.7.0
`scripts/upgrade.py` is no longer the upgrade engine. It is a launcher: it
asks GitHub which release is newest, downloads that release's tooling,
verifies it against the published checksum, and runs the engine from a
temporary directory. The engine is `telar_upgrade.py`, and that file — with
the whole of `scripts/migrations/` — still ships only in the tarball and is
still absent from FRAMEWORK_FILES.

Delivering the launcher is the point of this hop. A site's own copy of the
engine knows only the releases that existed when the copy was made: a site
created at v1.4.0 asks its own tooling what is current, is told v1.4.0, and
stays behind while reporting success. A launcher has nothing to be stale
about. Once a site holds it, `_site_runs_the_launcher` in the engine
recognises the marker `telar-upgrade-launcher-v1` in the delivered file, and
`_retire_local_migrations` clears the site's now-unrunnable
`scripts/migrations/` after the upgrade completes — which is why this
migration must not deliver those modules itself, and why the manifest that
accompanies this release deletes them for compositor-driven sites, whose
tree-diff adds files but does not remove them.

Also not delivered, for reasons that have not changed:

  - `tests/` — Telar's own framework tests, which have never been a site's
    to run.
  - `.github/workflows/*` — the upgrade's GITHUB_TOKEN carries no
    `workflows: write`, so a push touching any of them is rejected outright.
    The restriction is as old as v0.6.3. Three workflow files changed in
    v1.7.0 and all three are manual steps below.
  - `_config.yml` — a site's configuration is the site's, and v1.7.0 adds no
    key that needs writing into it.
  - `.gitignore` — edited in place in Phase 3 rather than overwritten, so a
    site's own entries survive.

Fail closed: if the framework install returns any FAILED record, apply()
returns immediately and neither the deletions nor the `.gitignore` edit run.
A site that could not receive the new layouts must not lose the script the
old ones load.

The version stamp (telar.version -> 1.7.0) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed step can
never leave the site stamped as a version it is not running.

Version: v1.7.0
"""

import os
from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus


# Framework files fetched from the v1.7.0 release tag and written atomically
# as one set — see point 1 in the module docstring. Every entry is a file
# v1.7.0 adds or modifies that a site owns; the exclusions are listed in the
# docstring rather than left to be inferred from an absence.
FRAMEWORK_FILES = {
    # Root manifests and documentation.
    '.gitattributes': 'Line-ending and diff rules for the repository',
    '.ruby-version': 'Ruby version Telar builds against (3.2)',
    'Gemfile': 'Ruby dependencies for the Jekyll build',
    'requirements.txt': 'Python dependencies for the build and upgrade scripts',
    'package.json': 'Dependency metadata and build scripts for v1.7.0',
    'package-lock.json': 'Regenerated dependency lockfile matching package.json — always ships with it',
    'README.md': 'Project README, updated for v1.7.0',
    'CHANGELOG.md': 'Release history through v1.7.0',

    # Layouts and includes.
    '_includes/iiif-url-warning.html': 'Warning shown when a IIIF URL cannot be used as given',
    '_layouts/index.html': 'Home page layout — loads the per-page home bundle',
    '_layouts/object.html': 'Object page layout — loads the per-page object bundle',
    '_layouts/objects-index.html': 'Objects index layout — loads the per-page index bundle',

    # JavaScript: built bundles and the modules they are built from.
    'assets/js/README.md': 'How the JavaScript in this directory is organised and rebuilt',
    'assets/js/home-page.js': 'Home page bundle',
    'assets/js/home-page.js.map': 'Source map for the home page bundle',
    'assets/js/iiif-thumbnails/resolve.js': 'Resolves a thumbnail URL from a IIIF manifest',
    'assets/js/iiif-thumbnails/explicit-thumbnails.js': 'Honours thumbnails declared in the spreadsheet',
    'assets/js/iiif-thumbnails/home.js': 'Thumbnail loading for the home page',
    'assets/js/iiif-thumbnails/objects-index.js': 'Thumbnail loading for the objects index',
    'assets/js/iiif-url-warning.js': 'IIIF URL warning bundle',
    'assets/js/iiif-url-warning.js.map': 'Source map for the IIIF URL warning bundle',
    'assets/js/iiif-url-warning/main.js': 'IIIF URL warning entry module',
    'assets/js/object-page.js': 'Object page bundle',
    'assets/js/object-page.js.map': 'Source map for the object page bundle',
    'assets/js/object-page/main.js': 'Object page entry module',
    'assets/js/object-page/image-object.js': 'Image object viewer',
    'assets/js/object-page/video-object.js': 'Video object player',
    'assets/js/object-page/audio-object.js': 'Audio object player',
    'assets/js/object-page/clip-panel.js': 'Clip panel for timed media',
    'assets/js/object-page/copy-feedback.js': 'Feedback shown when a link or citation is copied',
    'assets/js/objects-filter.js': 'Objects filter bundle',
    'assets/js/objects-filter.js.map': 'Source map for the objects filter bundle',
    'assets/js/objects-filter/main.js': 'Objects filter entry module',
    'assets/js/objects-filter/matching.js': 'Whole-word and prefix matching for the objects index search',
    'assets/js/objects-filter/search-index.js': 'Builds the in-page search index for the objects index',
    'assets/js/objects-filter/escape.js': 'Escaping helpers shared by the filter modules',
    'assets/js/objects-index-page.js': 'Objects index page bundle',
    'assets/js/objects-index-page.js.map': 'Source map for the objects index page bundle',
    'assets/js/share-panel.js': 'Share panel bundle',
    'assets/js/share-panel.js.map': 'Source map for the share panel bundle',
    'assets/js/share-panel/main.js': 'Share panel entry module',
    'assets/js/share-panel/warnings.js': 'Warnings the share panel raises about a link',
    'assets/js/telar-story.js': 'Story engine bundle',
    'assets/js/telar-story.js.map': 'Source map for the story engine bundle',
    'assets/js/telar-story/card-pool.js': 'Card pool the story engine reuses while scrolling',
    'assets/js/telar-story/navigation.js': 'Story navigation and deep linking',

    # Build and upgrade scripts.
    'scripts/upgrade.py': 'Upgrade launcher — downloads and runs the newest release\'s verified tooling',
    'scripts/build_local_site.py': 'Local build helper',
    'scripts/check_jekyll_conflicts.py': 'Reads the Jekyll build log and reports two files claiming one destination',
    'scripts/encrypt_protected_stories.py': 'Encrypts protected stories after the build',
    'scripts/generate_collections.py': 'Generates Jekyll collections and records the story page manifest',
    'scripts/generate_iiif.py': 'Generates IIIF tiles and manifests for self-hosted images',
    'scripts/iiif_utils.py': 'Shared IIIF helpers',
    'scripts/process_pdf.py': 'Converts PDF sources into page images',
    'scripts/telar/build_conflicts.py': 'Parses build-log conflicts for the conflict check',
    'scripts/telar/demo.py': 'Demo content handling',
    'scripts/telar/story_pages.py': 'Works out where each story renders',
    'scripts/telar/widgets.py': 'Widget rendering helpers',
    'scripts/telar/processors/stories.py': 'Story spreadsheet processing',
    'scripts/telar/processors/objects/__init__.py': 'Object processing package — replaces processors/objects.py',
    'scripts/telar/processors/objects/christmas_tree.py': 'Object processing: layered image trees',
    'scripts/telar/processors/objects/featured.py': 'Object processing: featured objects',
    'scripts/telar/processors/objects/frame.py': 'Object processing: framing and cropping',
    'scripts/telar/processors/objects/local.py': 'Object processing: self-hosted objects',
    'scripts/telar/processors/objects/remote.py': 'Object processing: remote IIIF objects',
}

# Files v1.7.0 removes, which have to go from the site too — see Phase 2.
REMOVED_FILES = [
    'assets/js/iiif-thumbnails.js',
    'scripts/telar/processors/objects.py',
]

# The generated directory Phase 3 adds to .gitignore, and the single-line
# comment it files the entry under. One line, because _ensure_gitignore_entries
# matches an existing section by exact line equality.
GITIGNORE_ENTRIES = ['_data/telar-build/']
GITIGNORE_SECTION_COMMENT = (
    '# Story page manifest (generate_collections.py records where each story renders)'
)


class Migration162to170(BaseMigration):
    """Migration from v1.6.2 to v1.7.0 — deliver the v1.7.0 framework files including the upgrade launcher, remove two superseded files, and ignore the generated story page manifest."""

    from_version = "1.6.2"
    to_version = "1.7.0"
    description = "v1.7.0 framework files (layouts, bundles, build scripts, upgrade launcher), removal of two superseded files, and the _data/telar-build/ gitignore entry"

    # Pin framework-file fetches to the v1.7.0 release tag, not the moving
    # `main` branch, so this migration always installs v1.7.0 files.
    _TARGET_TAG = "v1.7.0"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        changes: List[ChangeRecord] = []

        # Phase 1: install the v1.7.0 framework files atomically.
        print("  Phase 1: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Fail closed: if the set did not install, remove nothing and edit
        # nothing, so a re-run retries from a clean, well-defined state.
        if any(c.status == ChangeStatus.FAILED for c in framework_changes):
            return changes

        # Phase 2: remove the two files v1.7.0 supersedes (soft-fail).
        print("  Phase 2: Removing superseded files...")
        changes.extend(self._remove_superseded_files(REMOVED_FILES))

        # Phase 3: ignore the generated story page manifest directory.
        print("  Phase 3: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # No version bump here — upgrade.py stamps once after all steps succeed.
        return changes

    # ------------------------------------------------------------------ #
    # Phase 1: framework file fetch (pinned + atomic)
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install the v1.7.0 framework file set from the pinned tag."""
        return self._apply_framework_files(FRAMEWORK_FILES)

    # ------------------------------------------------------------------ #
    # Phase 2: superseded file removal (idempotent, soft-fail)
    # ------------------------------------------------------------------ #

    def _remove_superseded_files(self, paths: List[str]) -> List[ChangeRecord]:
        """Delete each path in *paths* if present.

        Two files, and each is worse to leave than to have never shipped.

        `assets/js/iiif-thumbnails.js` was one script doing the thumbnail work
        for both the home page and the objects index. v1.7.0 splits that work
        into per-page bundles — `home-page.js` and `objects-index-page.js` —
        and the layouts installed in Phase 1 no longer load the old file. Left
        behind it is dead weight a reader still has no reason to download.

        `scripts/telar/processors/objects.py` is the sharper case. v1.7.0
        turns it into the package `scripts/telar/processors/objects/`. A site
        holding both would import the package, because a package wins over a
        module of the same name on the same path — so the file would sit there
        inert, looking like the code that runs, while every edit made to it
        changed nothing.

        Idempotent: a path already absent gets a no-op APPLIED record rather
        than a SKIPPED one; there is nothing wrong to flag. A removal failure
        (permissions, a locked working tree) is deliberately soft. Neither
        file affects a built page once Phase 1 has landed, so a site that
        keeps one a little longer loses nothing but tidiness, and that is not
        worth sinking a completed upgrade over.
        """
        records: List[ChangeRecord] = []

        for rel_path in paths:
            if not self._file_exists(rel_path):
                records.append(ChangeRecord(
                    description=f"No {rel_path} to remove (already absent)",
                    status=ChangeStatus.APPLIED,
                    severity="soft",
                ))
                continue

            try:
                os.remove(os.path.join(self.repo_root, rel_path))
            except OSError as e:
                records.append(ChangeRecord(
                    description=(
                        f"Could not remove {rel_path}: {e}. Non-fatal — delete "
                        "it by hand when convenient. Nothing loads it any more: "
                        "the layouts and scripts installed by this upgrade use "
                        "the files that replaced it."
                    ),
                    status=ChangeStatus.FAILED,
                    severity="soft",
                ))
                continue

            records.append(ChangeRecord(
                description=(
                    f"Removed {rel_path} — superseded by the files installed "
                    "with this upgrade"
                ),
                status=ChangeStatus.APPLIED,
                severity="soft",
            ))

        return records

    # ------------------------------------------------------------------ #
    # Phase 3: .gitignore
    # ------------------------------------------------------------------ #

    def _update_gitignore(self) -> List[ChangeRecord]:
        """Ignore `_data/telar-build/`, the generated story page manifest.

        `generate_collections.py` writes the manifest there on every build so
        the post-build encryption step knows the page each story renders to
        instead of reconstructing a URL from a slug. It is build output, and
        committing it means a diff on every push and a merge conflict on every
        parallel edit.

        Recorded either way. `_ensure_gitignore_entries` returns False both
        when the entry is already there and when the site has no `.gitignore`
        at all, and neither is a problem worth a FAILED record: the first is
        the desired state, and the second is a site whose whole tree is
        tracked by choice.
        """
        added = self._ensure_gitignore_entries(
            GITIGNORE_ENTRIES, section_comment=GITIGNORE_SECTION_COMMENT)

        if added:
            description = (
                "Added _data/telar-build/ to .gitignore — the story page "
                "manifest generate_collections.py writes there is build "
                "output, regenerated on every build"
            )
        else:
            description = (
                "No .gitignore change needed for _data/telar-build/ — already "
                "ignored, or the site has no .gitignore"
            )

        return [ChangeRecord(
            description=description,
            status=ChangeStatus.APPLIED,
            severity="soft",
        )]

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Update `.github/workflows/build.yml` by hand (recommended).** If you upgrade through the Telar Compositor, skip this step and the next two: the Compositor updates the workflow files for you. GitHub does not let an automated upgrade change workflow files, so you need to do this manually: open the current `build.yml` in the Telar repository on GitHub, choose "Copy raw contents", paste it over your copy, and commit. The new workflow reads the Jekyll build log and stops the build when two files claim the same destination, instead of letting one of them win silently. That matters more than it sounds: on a site with protected stories, the page that silently goes missing can be the one a story's encrypted text lands on. The new workflow also pins current versions of the actions it uses.''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/'
            },
            {
                'description': '''**Update `.github/workflows/upgrade.yml` by hand (recommended, not urgent).** Same restriction: GitHub will not let the upgrade change this file for you. Open the current `upgrade.yml` in the Telar repository, choose "Copy raw contents", paste it over yours, and commit. The new workflow runs the upgrade engine directly from the verified tooling it downloads. Your current copy keeps working, because that tooling now starts with a launcher that fetches the newest release on its own, so this is housekeeping rather than a requirement.''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/'
            },
            {
                'description': '''**Update `.github/workflows/telar-tests.yml` by hand (optional).** Same restriction. Only the action versions changed in this release, so your site behaves the same either way. If you want every workflow current, open the current `telar-tests.yml` in the Telar repository, choose "Copy raw contents", paste it over yours, and commit.''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/'
            },
            {
                'description': '''**If you work on your site locally, two things changed.** Telar now needs Ruby 3.2 or newer, and CI builds with 3.2.11. Install a Ruby of at least 3.2 before your next local build. And `scripts/upgrade.py` is now a launcher rather than the upgrade tool itself: run it and it downloads the newest release's verified upgrade tooling and runs that against your site, so your copy never falls behind again, however long it sits between upgrades.''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/'
            },
            {
                'description': '''**What changed for your content.** Carousel items can declare `width` and `height`, and the build then skips opening each image to measure it. Search on the objects index now matches whole words as well as the beginnings of words. Objects with a single page copy their coordinates without a page number. And the build now encrypts a protected story whose identifier contains an underscore at the page Jekyll actually produces for it.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Actualiza `.github/workflows/build.yml` a mano (recomendado).** Si actualizas el sitio con el Compositor de Telar, sáltate este paso y los dos siguientes: el Compositor actualiza los archivos de workflow por ti. GitHub no permite que esta actualización modifique archivos de workflow, así que este paso lo haces tú: copia el `build.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). El workflow nuevo lee el registro que Jekyll deja al construir el sitio y detiene la construcción cuando dos archivos apuntan al mismo destino, en vez de dejar que uno de los dos gane sin avisar. Eso importa más de lo que parece: la página que desaparece en silencio puede ser justo la que debía llevar el texto cifrado de una historia protegida. El workflow nuevo también trae al día las versiones fijadas de las acciones de GitHub.''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/'
            },
            {
                'description': '''**Actualiza `.github/workflows/upgrade.yml` a mano (recomendado, no urgente).** La restricción es la misma: GitHub no permite que la actualización lo modifique por ti. Copia el `upgrade.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). El workflow nuevo ejecuta el motor de actualización que viene en las herramientas verificadas que descarga. Tu copia actual sigue sirviendo, así que es cuestión de orden y no un requisito: las herramientas que descarga ahora empiezan por un lanzador que busca por su cuenta el lanzamiento más reciente.''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/'
            },
            {
                'description': '''**Actualiza `.github/workflows/telar-tests.yml` a mano (opcional).** Aquí rige la misma restricción. En este lanzamiento solo cambiaron las versiones fijadas de las acciones, así que tu sitio se comporta igual lo hagas o no. Si prefieres tener todos los workflows al día, copia el `telar-tests.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio).''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/'
            },
            {
                'description': '''**Si trabajas con tu sitio en tu propio computador, cambiaron dos cosas.** Telar ahora necesita Ruby 3.2 o una versión más nueva, y la integración continua construye el sitio con la 3.2.11. Instala Ruby 3.2 como mínimo antes de la próxima construcción local. Y `scripts/upgrade.py` ya no es la herramienta de actualización sino un lanzador: al ejecutarlo descarga las herramientas verificadas del lanzamiento más reciente y las ejecuta sobre tu sitio. Así tu copia de `scripts/upgrade.py` nunca vuelve a quedarse atrás, por mucho tiempo que pase entre una actualización y otra.''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/'
            },
            {
                'description': '''**Lo que cambió para tu contenido.** Ahora puedes indicar `width` y `height` en los elementos de un carrusel, y así la construcción no tiene que abrir cada imagen para medirla. En el índice de objetos, la búsqueda encuentra palabras completas, además de los comienzos de palabra. En los objetos de una sola página, las coordenadas que copias ya no traen número de página. Y si el identificador de una historia protegida lleva un guion bajo, la construcción ahora cifra el texto de la historia en la página que Jekyll produce realmente para ella.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
