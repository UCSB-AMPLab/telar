"""
Migration from v1.7.0 to v1.8.0.

v1.8.0 is about what a site publishes and what an upgrade tells its owner.
Nine kinds of change reach an existing site, in this order.

1. Framework files (FRAMEWORK_FILES, installed atomically from the v1.8.0
   tag): every file a site owns that the release adds or changes. The
   object page is split into one bundle per media type, the story engine
   gains per-type plates, the glossary gains kinds and an index by kind,
   and the build scripts gain the shared markdown converter, the page and
   glossary generators split out of `generate_collections.py`, and the
   column-collision refusal. Bundles ship with the modules they are built
   from, and `generate_collections.py` with every `telar` module it imports,
   so the set installs whole or not at all. Fail closed: a FAILED record
   here returns before any later phase runs.

2. Removals (Phase 2): the single object-page bundle the three per-type
   bundles replace, with its map and entry module, and the stale root
   `migration.json`, the manifest of the 1.5.4 upgrade, which Jekyll
   publishes as a page.

3. Built-in pages (Phase 1a): one default-content line in `index.md` and
   one in `pages/glossary.md`, where it is still the template's.

4. Colliding columns (Phase 2b): the build now refuses a sheet with two
   columns claiming one name, and a failed regeneration leaves the site at
   1.7.0, so a benign collision is repaired here, before regeneration.

5. `_config.yml` (Phase 3): four `exclude` entries. `telar-content/texts/`
   keeps Jekyll from publishing the sources the build generates pages from;
   the other three keep Telar's own tests out of the site.

6. Page sources (Phase 4): a `layout` or `permalink` that repeats what the
   build supplies is removed. The build ignores both keys, so this is
   tidiness, not safety.

7. Glossary markdown (Phase 5): a `related_terms` written as one scalar
   becomes a list, which is what the glossary layout iterates.

8. Step answers (Phase 6): reported, not changed. Every answer the build
   will cut, or strip of content an answer cannot show, is named in the
   summary before the first build runs.

9. The stale engine (Phase 7): a launcher site's leftover
   `scripts/telar_upgrade.py` and its three helpers are removed.

Phases 3 to 7 are in `v180_sources.py` and `v180_sheets.py`; each is
idempotent, so a run that stops at regeneration and is repeated after the
author fixes the cause completes.

Not delivered:

  - `tests/`, `pytest.ini`, `vitest.config.js` — Telar's own test suite,
    listed in `scripts/dev-only-files.txt`. The command-line route leaves a
    site's copies alone; the Compositor's manifest deletes them.
  - `.github/workflows/*` — the upgrade's GITHUB_TOKEN carries no
    `workflows: write`. The three changed workflows are manual steps.
  - `scripts/telar_upgrade.py`, its three `telar_upgrade_*` helpers and
    `scripts/migrations/` — the engine ships only in the verified release
    tarball, which `scripts/upgrade.py` downloads.
  - `_config.yml`, `index.md`, `pages/glossary.md`, `.gitignore` — the
    site's own, edited in place where the release needs a line in them.

The version stamp (telar.version -> 1.8.0) is not written here. The engine
applies it once after every migration step and the regeneration succeed.

Version: v1.8.0
"""

import ast
import hashlib
import os
import sys
from typing import Dict, List

from .messages import get_message
from .base import BaseMigration, ChangeRecord, ChangeStatus, LAUNCHER_MARKER
from .records import ChangeCategory, category_for_path
from . import v180_sheets, v180_sources


# Fetched from the v1.8.0 tag and written atomically as one set.
FRAMEWORK_FILES = {
    # Root documents and dependency manifests.
    'README.md': 'Project README for v1.8.0',
    'requirements.txt': 'Python dependencies, with pandas bounded to the release the sheet repair was checked against',
    'package.json': 'Build scripts for the three object-page bundles, and the dependencies',
    'package-lock.json': 'Lockfile matching package.json — always ships with it',

    # Data files the build reads at fixed paths.
    '_data/glossary_kinds.yml': 'The glossary entry kinds, read by scripts/telar/glossary_kinds.py',
    '_data/languages/en.yml': 'English language pack',
    '_data/languages/es.yml': 'Spanish language pack',

    # Includes.
    '_includes/footer.html': 'Site footer',
    '_includes/katex.html': 'KaTeX loading for pages with mathematics',
    '_includes/katex-loader.html': 'KaTeX loading on request, for stories and the glossary panel',
    '_includes/panels.html': 'Story panels',
    '_includes/share-panel.html': 'Share panel',
    '_includes/story-step.html': 'One story step',
    '_includes/story-steps.html': 'The steps of a story, with each answer as the build wrote it',
    '_includes/glossary-intro.html': 'Glossary introduction, with or without primary sources',
    '_includes/glossary-kind-entries.html': 'Glossary entries of one kind',
    '_includes/glossary-kind-text.html': 'Text for one glossary kind',
    '_includes/glossary-kinds-used.html': 'The glossary kinds a site uses',
    '_includes/glossary-kinds.html': 'Glossary index grouped by kind',
    '_includes/widgets/glossary.html': 'Glossary widget',
    '_includes/objects/metadata/audio.html': 'Object page metadata: audio',
    '_includes/objects/metadata/image.html': 'Object page metadata: image',
    '_includes/objects/metadata/video.html': 'Object page metadata: video',
    '_includes/objects/tools/audio.html': 'Object page tools: audio',
    '_includes/objects/tools/image.html': 'Object page tools: image',
    '_includes/objects/tools/video.html': 'Object page tools: video',

    # Layouts.
    '_layouts/default.html': 'Default layout',
    '_layouts/glossary-index.html': 'Glossary index layout',
    '_layouts/glossary.html': 'Glossary entry layout',
    '_layouts/object.html': 'Object page layout — loads the bundle for the object\'s media type',
    '_layouts/objects-index.html': 'Objects index layout',
    '_layouts/story.html': 'Story layout',

    # Styles.
    '_sass/_coordinate-panel.scss': 'Coordinate panel styles',
    '_sass/_embed.scss': 'Embedded story styles',
    '_sass/_latex.scss': 'Mathematics styles',
    '_sass/_layout.scss': 'Layout styles',
    '_sass/_mixins.scss': 'Shared mixins',
    '_sass/_panels.scss': 'Panel styles',
    '_sass/_responsive.scss': 'Responsive styles',
    '_sass/_share.scss': 'Share panel styles',
    '_sass/_story.scss': 'Story styles',
    '_sass/_typography.scss': 'Typography',
    '_sass/_viewer.scss': 'Viewer styles',
    '_sass/_widgets.scss': 'Widget styles',
    'assets/css/telar.scss': 'Stylesheet entry point',

    # JavaScript: built bundles, their maps, and the modules they are built from.
    'assets/js/README.md': 'How the JavaScript in this directory is organised and rebuilt',
    'assets/js/home-page.js': 'Home page bundle',
    'assets/js/iiif-url-warning.js': 'IIIF URL warning bundle',
    'assets/js/katex-loader.js': 'Lazy KaTeX loader for story pages and the glossary panel',
    'assets/js/object-theme.js': 'Object page theme helpers',
    'assets/js/story-unlock.js': 'Unlocking protected stories',
    'assets/js/telar.js': 'Site-wide panel and glossary behaviour',
    'assets/js/object-audio.js': 'Object page bundle for audio objects',
    'assets/js/object-audio.js.map': 'Source map for the audio object bundle',
    'assets/js/object-image.js': 'Object page bundle for image objects',
    'assets/js/object-image.js.map': 'Source map for the image object bundle',
    'assets/js/object-video.js': 'Object page bundle for video objects',
    'assets/js/object-video.js.map': 'Source map for the video object bundle',
    'assets/js/object-page/audio-entry.js': 'Entry module of the audio object bundle',
    'assets/js/object-page/audio-object.js': 'Audio object player',
    'assets/js/object-page/boot.js': 'What every object page entry does before it knows its type',
    'assets/js/object-page/clip-panel.js': 'Clip panel for timed media',
    'assets/js/object-page/image-entry.js': 'Entry module of the image object bundle',
    'assets/js/object-page/image-object.js': 'Image object viewer',
    'assets/js/object-page/video-entry.js': 'Entry module of the video object bundle',
    'assets/js/objects-filter.js': 'Objects filter bundle',
    'assets/js/objects-filter.js.map': 'Source map for the objects filter bundle',
    'assets/js/objects-filter/escape.js': 'Escaping helpers shared by the filter modules',
    'assets/js/objects-filter/main.js': 'Objects filter entry module',
    'assets/js/objects-index-page.js': 'Objects index page bundle',
    'assets/js/share-panel.js': 'Share panel bundle',
    'assets/js/share-panel.js.map': 'Source map for the share panel bundle',
    'assets/js/share-panel/main.js': 'Share panel entry module',
    'assets/js/embed.js': 'Embed mode: the banner and its events',
    'assets/js/telar-story.js': 'Story engine bundle',
    'assets/js/telar-story.js.map': 'Source map for the story engine bundle',
    'assets/js/telar-story/audio-card.js': 'Story engine: audio cards',
    'assets/js/telar-story/audio-layout.js': 'Story engine: audio layout',
    'assets/js/telar-story/authoring-frame.js': 'Story engine: the authoring frame',
    'assets/js/telar-story/card-fit.js': 'Story engine: side-card fit',
    'assets/js/telar-story/card-height.js': 'Story engine: card height and card motion',
    'assets/js/telar-story/card-pool.js': 'Story engine: the card pool',
    'assets/js/telar-story/card-scroll.js': 'Story engine: a side card that scrolls inside itself',
    'assets/js/telar-story/deep-link.js': 'Story engine: deep links',
    'assets/js/telar-story/iiif-card.js': 'Story engine: IIIF cards',
    'assets/js/telar-story/ios-device.js': 'Story engine: iOS and iPadOS detection',
    'assets/js/telar-story/iiif-manifest.js': 'Story engine: IIIF manifests',
    'assets/js/telar-story/iiif-viewer.js': 'Story engine: IIIF viewer',
    'assets/js/telar-story/layout-mode.js': 'Story engine: layout mode and its thresholds',
    'assets/js/telar-story/main.js': 'Story engine entry module',
    'assets/js/telar-story/media-arrangement.js': 'Story engine: media arrangement',
    'assets/js/telar-story/navigation.js': 'Story engine: navigation',
    'assets/js/telar-story/panels.js': 'Story engine: panels',
    'assets/js/telar-story/scroll-engine.js': 'Story engine: scrolling',
    'assets/js/telar-story/state.js': 'Story engine: state',
    'assets/js/telar-story/story-input.js': 'Story engine: which input is the reader scrolling the story',
    'assets/js/telar-story/utils.js': 'Story engine: shared helpers',
    'assets/js/telar-story/video-card.js': 'Story engine: video cards',
    'assets/js/telar-story/video-layout.js': 'Story engine: video layout',
    'assets/js/telar-story/viewer.js': 'Story engine: viewer',
    'assets/js/telar-story/plates/audio-plate.js': 'Story engine plate: audio',
    'assets/js/telar-story/plates/base-plate.js': 'Story engine plate: shared base',
    'assets/js/telar-story/plates/framing.js': 'Story engine plate: framing',
    'assets/js/telar-story/plates/iiif-plate.js': 'Story engine plate: IIIF',
    'assets/js/telar-story/plates/media-plate.js': 'Story engine plate: timed media',
    'assets/js/telar-story/plates/video-plate.js': 'Story engine plate: video',

    # Build scripts.
    'scripts/dev-only-files.txt': 'The files a Compositor site does not carry',
    'scripts/encrypt_protected_stories.py': 'Encrypts protected stories after the build',
    'scripts/fetch_demo_content.py': 'Fetches the demo content bundle',
    'scripts/generate_collections.py': 'Generates the Jekyll collections',
    'scripts/generate_iiif.py': 'Generates IIIF tiles and manifests for self-hosted images',
    'scripts/iiif_utils.py': 'Shared IIIF helpers',
    'scripts/process_pdf.py': 'Converts PDF sources into page images',
    'scripts/telar/__init__.py': 'The telar build package',
    'scripts/telar/code_spans.py': 'Finds code spans so glossary links and maths leave them as written',
    'scripts/telar/config.py': 'Site configuration and language strings',
    'scripts/telar/core.py': 'Spreadsheet conversion — refuses a sheet whose columns collide',
    'scripts/telar/csv_utils.py': 'Column names, aliases and the collision refusal',
    'scripts/telar/demo.py': 'Demo content handling',
    'scripts/telar/dev_only_files.py': 'Reads scripts/dev-only-files.txt',
    'scripts/telar/encryption.py': 'Protected story encryption',
    'scripts/telar/frontmatter.py': 'Front matter for the generated collection files — imported by the build',
    'scripts/telar/glossary.py': 'Glossary terms and links',
    'scripts/telar/glossary_kinds.py': 'Glossary entry kinds',
    'scripts/telar/glossary_pages.py': 'Glossary pages for the glossary collection — imported by the build',
    'scripts/telar/images.py': 'Image syntax and captions',
    'scripts/telar/kramdown_blocks.py': 'Reads block structure as kramdown does, for the code span finder — imported by the build',
    'scripts/telar/latex.py': 'Mathematics protection and the shared markdown converter',
    'scripts/telar/markdown.py': 'Panel markdown pipeline',
    'scripts/telar/pages.py': 'User pages for the pages collection — imported by the build',
    'scripts/telar/story_pages.py': 'Works out where each story renders',
    'scripts/telar/theme_colours.py': 'Derived on-colours for theme backgrounds',
    'scripts/telar/widgets.py': 'Widget rendering',
    'scripts/telar/processors/project.py': 'Project spreadsheet processing: story numbers',
    'scripts/telar/processors/stories.py': 'Story spreadsheet processing and the answer limits',
    'scripts/telar/processors/objects/featured.py': 'Object processing: featured objects',
    'scripts/telar/processors/objects/frame.py': 'Object processing: one row per object ID',
    'scripts/telar/processors/objects/local.py': 'Object processing: self-hosted objects',
}

# The single object-page bundle, with its map and entry module, which the
# three per-type bundles replace. The layout installed in Phase 1 loads the
# per-type bundle, so nothing loads these.
REMOVED_FILES = [
    'assets/js/object-page.js',
    'assets/js/object-page.js.map',
    'assets/js/object-page/main.js',
]

# The 1.5.4 upgrade manifest at the site root. It was never read there, and
# Jekyll publishes it as part of the site.
STALE_MANIFEST = 'migration.json'

# The engine a site made from a template before the engine left it. The
# launcher downloads a verified engine for each run, so on a launcher site
# these are dead copies whose version numbers suggest otherwise.
ENGINE_FILES = [
    'scripts/telar_upgrade.py',
    'scripts/telar_upgrade_common.py',
    'scripts/telar_upgrade_regen.py',
    'scripts/telar_upgrade_report.py',
]

# The sha256 of every copy of those files a release put in a site: the
# v1.7.0 engine, and no helper, since no release shipped one. Phase 7
# deletes a file only when its bytes are one of these, so a file a site
# wrote or edited itself stays. Computed from the release tags, and
# recomputed from them by the tests.
RELEASED_ENGINE_SHA256 = {
    'scripts/telar_upgrade.py': {
        '046378e5f279fedc646f7e158a206689ac98838775c3779d13ec0160d792f18e',  # v1.7.0
    },
}

# The modules the engine runs as. A file any of them was loaded from is the
# engine that is running, and is never deleted.
_ENGINE_MODULES = ('__main__', 'telar_upgrade', 'telar_upgrade_common',
                   'telar_upgrade_regen', 'telar_upgrade_report')

# The scripts directory this module was imported from. Compared with the
# site's own before Phase 7 deletes anything.
_ENGINE_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DOCS = 'https://telar.org/docs/setup/upgrading/'
_GUIA = 'https://telar.org/guia/configuracion/actualizacion/'

# Spanish is drafted and reviewed separately; this placeholder marks every
# Spanish field until it is, and the tests detect it.
_ES_PENDING = 'ES-PENDIENTE'


def _running_engine_files() -> set:
    """Every file, resolved, the running engine was started or loaded from."""
    paths = [sys.argv[0]] if sys.argv and sys.argv[0] else []
    for name in _ENGINE_MODULES:
        loaded = getattr(sys.modules.get(name), '__file__', None)
        if loaded:
            paths.append(loaded)
    return {os.path.realpath(path) for path in paths}


def _sha256(path: str) -> str:
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class Migration170to180(BaseMigration):
    """Migration from v1.7.0 to v1.8.0 — the framework files, the removals, and the in-place edits to site-owned files the release needs."""

    from_version = "1.7.0"
    to_version = "1.8.0"
    # Filled from the v1.8.0 tag when it exists; until then the engine
    # stamps the day it runs and says so.
    release_date = None
    description = ("v1.8.0 framework files, removal of the single object-page bundle and "
                   "the stale migration.json, colliding-column repair, the exclude entries, "
                   "and the page, glossary and step-answer checks")

    _TARGET_TAG = "v1.8.0"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        changes: List[ChangeRecord] = []
        lang = self._detect_language()

        print("  Phase 1: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Fail closed: a site without the new layouts and scripts keeps the
        # files the old ones load, and none of its own files are edited for
        # a build that will not run.
        if any(c.status == ChangeStatus.FAILED for c in framework_changes):
            return changes

        print("  Phase 2: Removing superseded files...")
        changes.extend(self._remove_superseded_files(REMOVED_FILES))
        changes.extend(self._remove_stale_manifest())

        for label, phase in self._site_phases():
            print(f"  {label}...")
            changes.extend(phase(self.repo_root, lang))

        print("  Phase 7: Removing the stale upgrade engine...")
        changes.extend(self._remove_stale_engine())
        return changes

    @staticmethod
    def _site_phases():
        return (
            ('Phase 1a: Updating the built-in pages', v180_sources.update_site_pages),
            ('Phase 2b: Checking spreadsheet columns', v180_sheets.repair_colliding_columns),
            ('Phase 3: Updating _config.yml', v180_sources.add_exclude_entries),
            ('Phase 4: Tidying page sources', v180_sources.strip_page_sources),
            ('Phase 5: Checking glossary entries', v180_sources.list_related_terms),
            ('Phase 6: Checking story answers', v180_sheets.report_step_answers),
        )

    # ------------------------------------------------------------------ #
    # Phase 1
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install the v1.8.0 framework file set from the pinned tag."""
        return self._apply_framework_files(FRAMEWORK_FILES)

    # ------------------------------------------------------------------ #
    # Phase 2
    # ------------------------------------------------------------------ #

    def _remove_superseded_files(self, paths: List[str]) -> List[ChangeRecord]:
        """Delete each path in *paths* if present; soft on failure.

        An absent path gets a no-op APPLIED record, since there is nothing
        wrong to flag. A failure to delete is soft: the layouts installed
        in Phase 1 do not load these files, so keeping one costs nothing
        a reader sees.
        """
        lang = self._detect_language()
        records = []
        for rel_path in paths:
            outcome = self._delete(rel_path)
            if outcome is None:
                key, args, status = 'change_nothing_to_remove', (rel_path,), ChangeStatus.APPLIED
            elif outcome is True:
                key, args, status = 'change_removed_superseded', (rel_path,), ChangeStatus.APPLIED
            else:
                key, args = 'change_could_not_remove_superseded', (rel_path, outcome)
                status = ChangeStatus.FAILED
            records.append(ChangeRecord(description=get_message(lang, key, *args),
                                        status=status, severity='soft',
                                        category=category_for_path(rel_path)))
        return records

    def _remove_stale_manifest(self) -> List[ChangeRecord]:
        outcome = self._delete(STALE_MANIFEST)
        if outcome is None:
            return []
        lang = self._detect_language()
        if outcome is True:
            description = get_message(lang, 'v180_removed_stale_manifest')
            status = ChangeStatus.APPLIED
        else:
            description = get_message(lang, 'change_could_not_remove_superseded',
                                      STALE_MANIFEST, outcome)
            status = ChangeStatus.FAILED
        return [ChangeRecord(description=description, status=status, severity='soft',
                             category=ChangeCategory.OTHER)]

    def _delete(self, rel_path: str):
        """True when *rel_path* was deleted, None when it was absent, and
        the OSError when it could not be."""
        if not self._file_exists(rel_path):
            return None
        try:
            os.remove(os.path.join(self.repo_root, rel_path))
        except OSError as error:
            return error
        return True

    # ------------------------------------------------------------------ #
    # Phase 7
    # ------------------------------------------------------------------ #

    def _remove_stale_engine(self) -> List[ChangeRecord]:
        """Delete a launcher site's leftover copy of the released engine.

        Three guards. The site's `scripts/upgrade.py` must assign the
        launcher marker at module level: without the launcher, the site's
        copy of the engine is the only thing it can upgrade with, and a
        comment or string carrying the marker's text does not make a file a
        launcher. No file the running engine was loaded or started from is
        touched, and nothing is touched when this module itself was loaded
        from the site's `scripts/`. And a file goes only when its bytes are
        a copy a release shipped; any other is the site's own, left in
        place and reported. Absent files are a no-op. Soft throughout.
        """
        if not self._site_runs_the_launcher() or self._running_from_the_site():
            return []
        lang = self._detect_language()
        running = _running_engine_files()
        records = []
        for rel_path in ENGINE_FILES:
            path = os.path.join(self.repo_root, rel_path)
            if os.path.isfile(path) and os.path.realpath(path) not in running:
                records.append(self._stale_engine_record(lang, rel_path, path))
        return records

    def _stale_engine_record(self, lang, rel_path, path) -> ChangeRecord:
        # A link is something the site set up, whatever its target holds.
        if os.path.islink(path) or \
                _sha256(path) not in RELEASED_ENGINE_SHA256.get(rel_path, set()):
            description = get_message(lang, 'v180_engine_kept', rel_path)
            status = ChangeStatus.APPLIED
        else:
            outcome = self._delete(rel_path)
            if outcome is True:
                description = get_message(lang, 'v180_engine_removed', rel_path)
                status = ChangeStatus.APPLIED
            else:
                description = get_message(lang, 'v180_engine_not_removed', rel_path, outcome)
                status = ChangeStatus.FAILED
        return ChangeRecord(description=description, status=status, severity='soft',
                            category=ChangeCategory.SCRIPTS)

    def _site_runs_the_launcher(self) -> bool:
        """Whether the site's scripts/upgrade.py assigns LAUNCHER_MARKER to
        the name LAUNCHER_MARKER at module level. Parsed, never run."""
        content = self._read_file('scripts/upgrade.py')
        if not isinstance(content, str):
            return False
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            return False
        return any(isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'LAUNCHER_MARKER'
                           for t in node.targets)
                   and isinstance(node.value, ast.Constant)
                   and node.value.value == LAUNCHER_MARKER
                   for node in tree.body)

    def _running_from_the_site(self) -> bool:
        site_scripts = os.path.realpath(os.path.join(self.repo_root, 'scripts'))
        return site_scripts == os.path.realpath(_ENGINE_SCRIPTS_DIR)

    # ------------------------------------------------------------------ #
    # Manual steps
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Update `.github/workflows/build.yml` by hand (recommended).** GitHub does not let an automated upgrade change workflow files, so you need to do this yourself. Open the current `build.yml` in the Telar repository on GitHub, choose "Copy raw contents", paste it over your copy, and commit. The new workflow checks that the saved copy of your object images still exists before it decides not to rebuild them. GitHub deletes that copy after seven days without use, so until now a site that went quiet for a week could publish a text edit with every image missing, on a run that reported success. It also builds with Node 22, and installs only the tools a build needs.''',
                'audience': 'local',
                'kind': 'action',
                'doc_url': _DOCS,
            },
            {
                'description': '''**Update `.github/workflows/upgrade.yml` (optional).** Your current copy keeps working. The new one reads your site's version the same way the upgrade does, so the upgrade issue and the summary always name the same starting version.''',
                'audience': 'local',
                'kind': 'optional',
                'doc_url': _DOCS,
            },
            {
                'description': '''**`.github/workflows/telar-tests.yml` runs Telar's own tests, not your site's (optional).** You can copy the current version from the Telar repository, or delete it together with `tests/`, `pytest.ini` and `vitest.config.js`: nothing your site builds or publishes uses them.''',
                'audience': 'local',
                'kind': 'optional',
                'doc_url': _DOCS,
            },
            {
                'description': '''**If you keep your stories in a spreadsheet, check the column that marks a story private.** Telar accepted `privada` and `protegida` but not `privado` or `protegido`, and a story marked with one of the two it did not accept was published unencrypted, with no warning, because the build never recognized it as protected. All four spellings work from this release on. If your sheet used either masculine form, treat those stories as having been public until now and decide what to do about it: the next build will encrypt them, but it cannot undo what was already published.''',
                'audience': 'all',
                'kind': 'action',
                'doc_url': 'https://telar.org/docs/site-features/private-stories/',
            },
            {
                'description': '''**If your site reads a Google Sheet, check the upgrade summary for a column to delete.** Telar now stops the build when two columns mean the same thing, such as `medium` and `object_type`. The upgrade fixed your local copy, but the build reads your sheet again, so delete the column the summary names from the sheet itself.''',
                'audience': 'google-sheets',
                'kind': 'action',
                'doc_url': 'https://telar.org/docs/your-data/google-sheets/',
            },
            {
                # Condensed from the approved public CHANGELOG, which does
                # not exist yet; the tests detect this placeholder.
                'description': 'EN-PENDING: condensed from the approved 1.8.0 CHANGELOG',
                'audience': 'all',
                'kind': 'note',
                'doc_url': 'https://telar.org/docs',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {'description': '''**Actualiza `.github/workflows/build.yml` a mano (recomendado).** GitHub no permite que una actualización automática modifique archivos de workflow, así que este paso lo haces tú: copia el `build.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). Antes de decidir que no hace falta volver a generar las imágenes de los objetos, el workflow nuevo comprueba que la copia guardada de esas imágenes todavía exista. GitHub borra esa copia después de siete días sin uso, así que, hasta ahora, un sitio que pasaba una semana sin cambios podía publicar una corrección de texto sin ninguna imagen, en una construcción que además informaba que todo había salido bien. También construye el sitio con Node 22 e instala solo las herramientas que la construcción necesita.''', 'audience': 'local', 'kind': 'action',
             'doc_url': _GUIA},
            {'description': '''**Actualiza `.github/workflows/upgrade.yml` (opcional).** Tu copia actual sigue funcionando. La nueva lee la versión del sitio de la misma forma que la actualización, así que el *issue* de la actualización y el resumen siempre indican la misma versión de partida.''', 'audience': 'local', 'kind': 'optional',
             'doc_url': _GUIA},
            {'description': '''**`.github/workflows/telar-tests.yml` ejecuta las pruebas del propio Telar, no las de tu sitio (opcional).** Puedes copiar la versión actual desde el repositorio de Telar, o borrarlo junto con `tests/`, `pytest.ini` y `vitest.config.js`: ninguno de esos archivos interviene en lo que el sitio construye o publica.''', 'audience': 'local', 'kind': 'optional',
             'doc_url': _GUIA},
            {'description': '''**Si llevas tus historias en una hoja de cálculo, revisa la columna que marca una historia como privada.** Telar aceptaba `privada` y `protegida`, pero no `privado` ni `protegido`, y una historia marcada con una de estas dos últimas quedaba publicada a la vista de todo el mundo, sin ningún aviso, porque la construcción nunca llegó a reconocerla como protegida. Desde este lanzamiento funcionan las cuatro formas. Si en tu hoja usaste alguna de las formas masculinas, da por hecho que esas historias estuvieron públicas hasta ahora y decide qué hacer al respecto: la próxima construcción las cifra, pero no puede deshacer lo que ya se publicó.''', 'audience': 'all', 'kind': 'action',
             'doc_url': 'https://telar.org/guia/funciones/historias-privadas/'},
            {'description': '''**Si tu sitio lee una hoja de cálculo de Google Sheets, revisa si el resumen de la actualización indica alguna columna que haya que borrar.** Telar ahora detiene la construcción cuando dos columnas significan lo mismo, como `medium` y `object_type`. La actualización ya corrigió la copia local, pero la construcción vuelve a leer la hoja, así que borra la columna que indica el resumen directamente en la hoja de cálculo.''', 'audience': 'google-sheets', 'kind': 'action',
             'doc_url': 'https://telar.org/guia/tus-datos/google-sheets/'},
            {'description': _ES_PENDING, 'audience': 'all', 'kind': 'note',
             'doc_url': 'https://telar.org/guia'},
        ]
