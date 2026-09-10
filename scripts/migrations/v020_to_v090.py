"""Consolidated migration from the pre-v0.9.0 betas to v0.9.0-beta

Eighteen releases shipped between v0.2.0-beta and v0.9.0-beta, each with
its own migration module. A site on any of them reaches v0.9.0-beta
through this single step instead of walking all eighteen.

`from_versions` lists every version this migration absorbs. The
dispatcher pins `from_version` to the one the site is actually on before
calling `check_applicable()`, so the upgrade summary still names the
version the user started from.

The work itself is decided by the tree, not by the version: the
transformations in `transformations.py` each look for what they would
change and do nothing when it is not there. The entry version survives
only where it has to — in `from_versions`, and in bounding the framework
files to the ones the replaced chain would have written from here.

Version: v1.7.0
"""

from datetime import date
from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus, coerce_change, is_hard_failure
from .transformations import TRANSFORMATIONS



# What the owner still has to do by hand once this hop has run.
#
# Four instructions, not the forty-three the chain accumulated. The chain
# gave one per release, so a site entering at 0.2.0-beta was told three
# separate times to replace build.yml, walked through feature tours for
# releases it had never run, and read six variations of "nothing to do"
# from releases that each thought they were the last word.
#
# None of the four is conditional. The hop lands every entry version on the
# same tree, so the work left over is the same work.
MANUAL_STEPS_EN = [
    {
        'description': """**Update your GitHub Actions workflow files**

For security, GitHub does not let an upgrade write to `.github/workflows/`, so this part is yours to do by hand. Until you do, your site keeps building with files that look for the old folders, and your images will not appear.

Copy these three files from the v0.9.0-beta release and replace the ones in your repository (or add them, if you do not have them):

- `.github/workflows/build.yml`
- `.github/workflows/upgrade.yml`
- `.github/workflows/telar-tests.yml`

They are at https://github.com/UCSB-AMPLab/telar/tree/v0.9.0-beta/.github/workflows — open each file, click **Raw**, copy the whole contents, and paste it into the file of the same name in your repository.""",
        'doc_url': 'https://telar.org/docs/setup/upgrading/',
        'critical': True,
    },
    {
        'description': """**Fix old paths in your own pages**

This upgrade moved your content out of `components/` and into `telar-content/`:

- `components/images/` → `telar-content/objects/`
- `components/structures/` → `telar-content/spreadsheets/`
- `components/texts/` → `telar-content/texts/`

Telar takes care of the spreadsheets and the stories. What it cannot fix are the paths you typed yourself: in a page of your own, in an HTML include, or in a link or an image inside a Markdown file. Search the site for `components/` and fix what turns up.""",
    },
    {
        'description': """**If you use Google Sheets, add the new columns**

The upgrade has already added the missing columns to the CSV files in your repository, but it cannot touch your spreadsheet. The next time the site pulls its data from Google Sheets, anything you have not added there is lost again:

- **story tabs:** a `page` column, after `zoom`, for pointing at one page inside a multi-page object
- **objects tab:** `year`, `object_type`, `subjects` and `featured`, for filtering the gallery and choosing what appears on the homepage
- **project tab:** a `private` column, for putting a password on a story

You can also start from an up-to-date template: https://bit.ly/telar-template""",
    },
    {
        'description': """**If you build the site on your own computer**

Install what this version needs and build again:

```
pip install -r requirements.txt
npm install
python3 scripts/csv_to_json.py
python3 scripts/generate_collections.py
python3 scripts/generate_iiif.py
bundle exec jekyll build
```

Tiles are generated much faster with libvips installed (`brew install vips` on macOS, `sudo apt-get install libvips-tools` on Debian or Ubuntu). It still works without libvips, only more slowly.

If you publish through GitHub Pages and do not build on your own computer, you can skip this step, but not the workflow files.""",
    },
]

MANUAL_STEPS_ES = [
    {
        'description': """**Actualiza los flujos de trabajo de GitHub Actions**

Por seguridad, GitHub no deja que una actualización escriba en `.github/workflows/`, así que esta parte te toca hacerla a mano. Mientras no la hagas, el sitio se sigue compilando con archivos que buscan las carpetas viejas y las imágenes no van a aparecer.

Copia estos tres archivos de la versión v0.9.0-beta y reemplaza los que tengas en el repositorio (o agrégalos, si no los tienes):

- `.github/workflows/build.yml`
- `.github/workflows/upgrade.yml`
- `.github/workflows/telar-tests.yml`

Están en https://github.com/UCSB-AMPLab/telar/tree/v0.9.0-beta/.github/workflows — abre cada archivo, haz clic en **Raw**, copia todo el contenido y pégalo en el archivo del mismo nombre en el repositorio.""",
        'doc_url': 'https://telar.org/guia/configuracion/actualizacion/',
        'critical': True,
    },
    {
        'description': """**Corrige las rutas viejas en tus propias páginas**

Esta actualización sacó el contenido de `components/` y lo pasó a `telar-content/`:

- `components/images/` → `telar-content/objects/`
- `components/structures/` → `telar-content/spreadsheets/`
- `components/texts/` → `telar-content/texts/`

De las hojas de cálculo y de las historias se encarga Telar. Lo que no puede arreglar son las rutas que escribiste tú a mano: en una página propia, en un *include* de HTML, o en un enlace o una imagen dentro de un archivo de Markdown. Busca `components/` en el sitio y corrige lo que aparezca.""",
    },
    {
        'description': """**Si usas Google Sheets, agrega las columnas nuevas**

La actualización ya les agregó las columnas que faltaban a los archivos CSV del repositorio, pero no puede tocar tu hoja de cálculo. La próxima vez que el sitio baje los datos de Google Sheets, lo que no hayas agregado allá se pierde otra vez:

- **pestañas de historia:** una columna `page`, después de `zoom`, para señalar una página dentro de un objeto de varias páginas
- **pestaña de objetos:** `year`, `object_type`, `subjects` y `featured`, para filtrar la galería y escoger qué aparece en la página principal
- **pestaña del proyecto:** una columna `private`, para ponerle contraseña a una historia

También puedes partir de una plantilla actualizada: https://bit.ly/telar-template""",
    },
    {
        'description': """**Si compilas el sitio en tu propio computador**

Instala lo que necesita esta versión y vuelve a compilar:

```
pip install -r requirements.txt
npm install
python3 scripts/csv_to_json.py
python3 scripts/generate_collections.py
python3 scripts/generate_iiif.py
bundle exec jekyll build
```

Las teselas se generan mucho más rápido si tienes libvips instalado (`brew install vips` en macOS, `sudo apt-get install libvips-tools` en Debian o Ubuntu). Sin libvips también funciona, solo que más lento.

Si publicas con GitHub Pages y no compilas en tu computador, puedes saltarte este paso, pero no el de los flujos de trabajo.""",
    },
]


DEMO_CONTENT_NOTICE_EN = """**Check the demo files this upgrade left behind**

This upgrade leaves your site at version 0.9.0. It does not delete the demo files Telar ships with — earlier versions of the upgrade did, and this one does not, so that nothing of yours is deleted by mistake.

If you are not using them, delete them. They are in three folders:

- `telar-content/objects/` — demo images, among them `leviathan.jpg` and `ampl-logo.png`
- `telar-content/texts/stories/` — the tutorial stories `your-story/` and `tu-historia/`
- `telar-content/spreadsheets/` — `story-1.csv`, `story-2.csv` and `new-objects.csv`

Before deleting an image, check that it does not appear in `objects.csv` or in any of your stories.

Leaving them is fine too. They take up space, but they do not show on your site unless something uses them."""

DEMO_CONTENT_NOTICE_ES = """**Revisa los archivos de demostración que quedaron en tu sitio**

Esta actualización deja tu sitio en la versión 0.9.0. No borra los archivos de demostración que trae Telar: las versiones anteriores de la actualización sí los borraban, y esta no, para no borrarte por error algo que sea tuyo.

Si no los usas, bórralos. Están en tres carpetas:

- `telar-content/objects/` — imágenes de demostración, entre ellas `leviathan.jpg` y `ampl-logo.png`
- `telar-content/texts/stories/` — las historias de ejemplo `your-story/` y `tu-historia/`
- `telar-content/spreadsheets/` — `story-1.csv`, `story-2.csv` y `new-objects.csv`

Antes de borrar una imagen, revisa que no aparezca en `objects.csv` ni en ninguna de tus historias.

Si prefieres dejarlos, tampoco pasa nada: ocupan espacio, pero no se ven en tu sitio si nada los usa."""


# The versions a site can enter this hop from, in release order. The
# indices in FRAMEWORK_FILES_090 are positions in this list, so this list
# is what gives them their meaning.
ENTRY_VERSIONS = (
    '0.2.0-beta', '0.3.0-beta', '0.3.1-beta', '0.3.2-beta', '0.3.3-beta',
    '0.3.4-beta', '0.4.0-beta', '0.4.1-beta', '0.4.2-beta', '0.4.3-beta',
    '0.5.0-beta', '0.6.0-beta', '0.6.1-beta', '0.6.2-beta', '0.6.3-beta',
    '0.7.0-beta', '0.8.0-beta', '0.8.1-beta',
)




# Each framework file this hop can install, with the index of the last
# LEGACY_STEP that writes it.
#
# The index is what makes the install safe to apply from any entry version.
# A site entering at 0.8.1-beta runs only the final step, which never touches
# _data/themes/*.yml; installing them anyway would overwrite a theme its
# owner had customised. So a path is installed only when some step at or
# after the entry would have written it — which bounds this to exactly the
# files the chain it replaces would have touched.
#
# Derived by reading the steps' file maps and keeping the keys the framework
# repository has actually held. A key is a path because the repository says
# so, not because it looks like one: NOTICE and LICENSE carry neither a slash
# nor a dot, and judging by shape dropped the 43-entry map they belong to.
#
# Absent by design:
#   telar-content/       the site's own writing. The templates among these are
#                        replaced only by _update_template_content(), after it
#                        checks the owner has not edited them.
#   .github/workflows/   GITHUB_TOKEN cannot write these; they are manual steps.
#   scripts/upgrade.py   the updater a site runs is downloaded as a verified
#   scripts/migrations/  release asset and run from a temp dir, so a copy left
#                        in the site is stale weight rather than the real tool.
FRAMEWORK_FILES_090 = {
    '.github/dependabot.yml': ('Dependabot configuration for dependency updates', 14),
    '.gitignore': ('Updated paths and patterns', 17),
    'CHANGELOG.md': ('v0.9.0 changelog', 17),
    'LICENSE': ('Updated license', 17),
    'NOTICE': ('Third-party notices', 17),
    'README.md': ('Updated for v0.9.0', 17),
    '_data/languages/en.yml': ('Viewer keys, coordinate keys, simplified validation, trama warning', 17),
    '_data/languages/es.yml': ('Viewer keys, coordinate keys, simplified validation, trama warning', 17),
    '_data/navigation.yml': ('Updated path references', 17),
    '_data/themes/austin.yml': ('Updated Austin theme (creator attribution)', 5),
    '_data/themes/neogranadina.yml': ('Updated Neogranadina theme (creator attribution)', 5),
    '_data/themes/paisajes.yml': ('Updated Paisajes theme (creator attribution)', 5),
    '_data/themes/santa-barbara.yml': ('Updated Santa Barbara theme (creator attribution)', 5),
    '_data/themes/trama.yml': ('New default theme (Trama)', 17),
    '_includes/footer.html': ('Updated footer include (multilingual, theme attribution)', 5),
    '_includes/header.html': ('skip_collections rename', 15),
    '_includes/iiif-url-warning.html': ('Updated IIIF URL warning (multilingual)', 5),
    '_includes/panels.html': ('Panels (h5→h1 semantic fix)', 12),
    '_includes/share-button.html': ('Share button component', 9),
    '_includes/share-panel.html': ('Share panel redesign', 15),
    '_includes/story-step.html': ('data-page attribute for multi-page objects', 17),
    '_includes/viewer.html': ('Viewer include (removed inline transition styles)', 12),
    '_includes/widgets/accordion.html': ('Added accordion widget template', 5),
    '_includes/widgets/carousel.html': ('Added carousel widget template', 5),
    '_includes/widgets/tabs.html': ('Added tabs widget template', 5),
    '_layouts/default.html': ('Multilingual support', 10),
    '_layouts/glossary-index.html': ('Updated glossary index layout (multilingual)', 5),
    '_layouts/glossary.html': ('Demo badge text fix', 10),
    '_layouts/index.html': ('Simplified validation, Trama fallback, Level 0 IIIF fix, page-aware thumbnails', 17),
    '_layouts/object.html': ('Tify viewer, language key labels, multi-page coordinate picker', 17),
    '_layouts/objects-index.html': ('Thumbnail URL fix (w,h format), Level 0 IIIF fix', 17),
    '_layouts/page.html': ('Updated page layout', 5),
    '_layouts/story.html': ('Tify CDN, page parameter passthrough', 17),
    '_layouts/user-page.html': ('Custom pages layout (NEW)', 10),
    '_sass/_embed.scss': ('Embed mode styles', 14),
    '_sass/_layout.scss': ('Featured object thumbnail CSS fix', 17),
    '_sass/_mixins.scss': ('Renamed hide-uv-controls → hide-viewer-chrome (Tify selectors)', 17),
    '_sass/_panels.scss': ('Layer panel styles', 14),
    '_sass/_share.scss': ('Share panel styles', 15),
    '_sass/_story.scss': ('Unlock overlay styles', 15),
    '_sass/_typography.scss': ('Typography styles', 14),
    '_sass/_viewer.scss': ('Tify styling, black background, multi-page pagination', 17),
    '_sass/_widgets.scss': ('Widget component styles', 14),
    'assets/css/telar.scss': ('Trama fallback chain, updated CSS variable defaults', 17),
    'assets/js/embed.js': ('Embed mode detection and banner', 9),
    'assets/js/lunr.min.js': ('Lunr.js search library', 15),
    'assets/js/objects-filter.js': ('Filter/search/sort functionality', 15),
    'assets/js/share-panel.js': ('Share panel functionality', 15),
    'assets/js/story-unlock.js': ('data-page support for encrypted stories', 17),
    'assets/js/telar-story-bundle.js': ('Bundled story viewer (esbuild output)', 17),
    'assets/js/telar-story.bundle.js': ('Bundled story viewer (esbuild output)', 17),
    'assets/js/telar-story/main.js': ('Event-driven init for encrypted stories', 15),
    'assets/js/telar-story/navigation.js': ('Page parameter passthrough', 17),
    'assets/js/telar-story/panels.js': ('Panel system', 14),
    'assets/js/telar-story/state.js': ('Tify instance comments', 17),
    'assets/js/telar-story/utils.js': ('Shared utility functions', 14),
    'assets/js/telar-story/viewer.js': ('Tify viewer, page-specific manifests', 17),
    'assets/js/telar.js': ('Telar JS (glossary-to-glossary linking)', 12),
    'assets/js/widgets.js': ('Added widgets JavaScript (carousel, tabs, accordion)', 5),
    'docs/README.md': ('Updated docs README', 4),
    'objects.json': ('Updated objects.json endpoint', 5),
    'package.json': ('Node.js dependencies (esbuild, vitest)', 14),
    'pytest.ini': ('Updated markers', 15),
    'requirements.txt': ('Updated dependencies', 17),
    'scripts/README.md': ('Updated architecture description', 17),
    'scripts/build_local_site.py': ('Added JS build step', 14),
    'scripts/csv_to_json.py': ('Backward-compatible wrapper', 14),
    'scripts/discover_sheet_gids.py': ('Updated version header', 14),
    'scripts/fetch_demo_content.py': ('Updated version header', 14),
    'scripts/fetch_google_sheets.py': ('Single published URL (shared_url removed)', 17),
    'scripts/generate_collections.py': ('Custom metadata fields, empty field fix, location fix', 17),
    'scripts/generate_iiif.py': ('libvips backend, PDF detection, refactored imports', 17),
    'scripts/iiif_utils.py': ('Shared IIIF utilities (extracted from generate_iiif.py)', 17),
    'scripts/process_pdf.py': ('PDF-to-IIIF pipeline', 17),
    'scripts/telar/__init__.py': ('Package init with public API', 14),
    'scripts/telar/config.py': ('Language loading, string interpolation', 14),
    'scripts/telar/core.py': ('Content path telar-content/spreadsheets', 17),
    'scripts/telar/csv_utils.py': ('Page column mapping (page/pagina/página)', 17),
    'scripts/telar/demo.py': ('Demo objects with v0.8.0 metadata fields', 16),
    'scripts/telar/encryption.py': ('Protected stories encryption', 15),
    'scripts/telar/glossary.py': ('Content paths telar-content/', 17),
    'scripts/telar/iiif_metadata.py': ('Updated metadata fallback fields', 15),
    'scripts/telar/images.py': ('Content path telar-content/objects', 17),
    'scripts/telar/markdown.py': ('Content path telar-content/texts', 17),
    'scripts/telar/processors/__init__.py': ('Processors subpackage init', 14),
    'scripts/telar/processors/objects.py': ('PDF extension support, content paths', 17),
    'scripts/telar/processors/project.py': ('Protected column support', 15),
    'scripts/telar/processors/stories.py': ('Extension stripping, page validation, content paths', 17),
    'scripts/telar/search.py': ('Search data generator', 15),
    'scripts/telar/widgets.py': ('Widget parsing and rendering', 14),
    'tests/__init__.py': ('Test package init', 14),
    'tests/e2e/__init__.py': ('E2E test package init', 14),
    'tests/e2e/conftest.py': ('Playwright fixtures', 14),
    'tests/e2e/test_embed_mode.py': ('Embed mode E2E tests', 14),
    'tests/e2e/test_panel_interactions.py': ('Panel interaction E2E tests', 14),
    'tests/e2e/test_story_navigation.py': ('Story navigation E2E tests', 14),
    'tests/js/panels.test.js': ('Panel function tests', 14),
    'tests/js/state.test.js': ('State object tests', 14),
    'tests/js/utils.test.js': ('Utility function tests', 14),
    'tests/js/viewer.test.js': ('Viewer function tests', 14),
    'tests/unit/__init__.py': ('Unit test package init', 14),
    'tests/unit/test_apply_metadata.py': ('Updated for new fields', 15),
    'tests/unit/test_carousel_widget.py': ('Carousel widget tests', 14),
    'tests/unit/test_column_processing.py': ('Column processing tests', 14),
    'tests/unit/test_csv_utils.py': ('CSV utility tests', 14),
    'tests/unit/test_extract_credit.py': ('Credit extraction tests', 14),
    'tests/unit/test_glossary_links.py': ('Glossary link tests', 14),
    'tests/unit/test_google_sheets.py': ('Google Sheets tests', 14),
    'tests/unit/test_iiif_metadata.py': ('IIIF metadata tests', 14),
    'tests/unit/test_image_processing.py': ('Updated path assertions', 17),
    'tests/unit/test_inline_content.py': ('Inline content tests', 14),
    'tests/unit/test_process_widgets.py': ('Widget pipeline tests', 14),
    'tests/unit/test_project_processing.py': ('Project processing tests', 14),
    'tests/unit/test_upgrade_utils.py': ('Upgrade utility tests', 14),
    'tests/unit/test_widget_parsing.py': ('Widget parsing tests', 14),
    'vitest.config.js': ('Vitest configuration', 14),
}



class Migration020to090(BaseMigration):
    """Migration from any pre-v0.9.0 beta to v0.9.0-beta."""

    from_version = "0.2.0-beta"
    from_versions = list(ENTRY_VERSIONS)
    to_version = "0.9.0-beta"
    description = "Consolidated upgrade from the pre-v0.9.0 betas"

    # The one tag every framework file now comes from.
    _TARGET_TAG = "v0.9.0-beta"

    def _entry_index(self) -> int:
        """Where the site's version sits in ENTRY_VERSIONS."""
        try:
            return ENTRY_VERSIONS.index(self.from_version)
        except ValueError:
            raise ValueError(
                f"{self.from_version} is not one of the versions this migration "
                f"covers ({', '.join(self.from_versions)})"
            ) from None

    def check_applicable(self) -> bool:
        """Whether this hop covers the version the site is on.

        The steps this replaces answered the same question by polling
        themselves, and the poll could only come back true: fifteen of the
        eighteen returned an unconditional yes, and the selection unions
        every step from the entry onward, so one of them always did. The
        entry version is the whole test.
        """
        return self.from_version in ENTRY_VERSIONS

    def apply(self) -> List[ChangeRecord]:
        """Transform the site's content, install the framework, stamp once.

        The eighteen steps this replaces each decided their work from the
        version they were entered at. Their work was already decided by
        the tree — a step skipped when its source was absent and reported
        "already migrated" when its destination was present — so the
        version was an outer gate around logic that knew the answer. The
        catalogue is that logic with the gate taken off, which is what
        lets one pass stand in for eighteen.

        A hard failure stops before the stamp, so a site that does not
        complete keeps the version it started from and re-enters here.
        """
        records: List[ChangeRecord] = []

        for transformation in TRANSFORMATIONS:
            try:
                changes = transformation(self)
            except Exception as error:
                print(f"  ✗ Error: {error}")
                records.append(ChangeRecord(
                    description=f"{transformation.__name__} aborted: {error}",
                    status=ChangeStatus.FAILED,
                    severity="hard",
                ))
                return records

            step_records = [coerce_change(change) for change in changes]
            records.extend(step_records)

            for record in step_records:
                print(f"  {'✓' if record.status == ChangeStatus.APPLIED else '✗'} "
                      f"{record.description}")

            if any(is_hard_failure(record) for record in step_records):
                print("  ✗ Stopping: this migration did not complete. "
                      "The site is left unchanged.")
                return records

        # The one install, after the content work and before the stamp. The
        # steps rewrote user content in place; the framework files land on
        # top of whatever state that left, which is what a site running
        # v0.9.0-beta is entitled to.
        install = self._apply_framework_files(self._files_for_entry())
        records.extend(install)
        for record in install:
            print(f"  {'✓' if record.status == ChangeStatus.APPLIED else '✗'} "
                  f"{record.description}")

        if any(is_hard_failure(record) for record in install):
            print("  ✗ Stopping: the framework files could not be installed. "
                  "The site is left unchanged.")
            return records

        # The one stamp, written only once every step has completed.
        today = date.today().strftime('%Y-%m-%d')
        if self._stamp_version(self.to_version, today):
            records.append(coerce_change(
                f'Updated _config.yml: version {self.to_version} ({today})'))

        return records

    def _files_for_entry(self):
        """The framework files this entry version's chain would have written.

        A path whose last writer sits before the entry is one the replaced
        chain never touched from here, so writing it would overwrite whatever
        the site's owner has there.

        Absent is a different question from customised. A file the site does
        not have cannot be one the owner has edited, and withholding it
        leaves the site missing something the framework needs —
        scripts/telar/config.py is imported by csv_to_json.py, whose failure
        is a hard failure, so withholding it is the difference between a site
        that upgrades and one that cannot.
        """
        entry = self._entry_index()
        return {path: description
                for path, (description, last_writer) in FRAMEWORK_FILES_090.items()
                if last_writer >= entry or not self._file_exists(path)}

    def _stamp_version(self, version, today):
        """Write the single version stamp this hop is entitled to."""
        return self._update_config_version(version, today)

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """What the owner has to do by hand, in their own language.

        The same four for every entry version, plus the demo-content
        notice. Nothing here is derived from where the site started: this
        hop lands them all on the same tree, so it leaves them all the
        same work.
        """
        if self._detect_language() == 'es':
            steps = list(MANUAL_STEPS_ES)
        else:
            steps = list(MANUAL_STEPS_EN)
        steps.append(self._demo_content_step())
        return steps

    def _demo_content_step(self) -> Dict[str, str]:
        """Tell the owner about the demo files this hop leaves behind.

        The chain removed them, weighing each against whether it was still
        in use and whether the owner had edited it. This hop does not, so
        a site arrives at the floor holding demo images and tutorial
        stories it would otherwise have shed. Keeping too much is the safe
        direction for a migration to be wrong in, and the owner is the one
        who can tell which of it they want.
        """
        if self._detect_language() == 'es':
            return {'description': DEMO_CONTENT_NOTICE_ES}
        return {'description': DEMO_CONTENT_NOTICE_EN}
