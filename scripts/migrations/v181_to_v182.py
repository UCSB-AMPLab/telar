"""
Migration from v1.8.1 to v1.8.2.

v1.8.2 is a patch that corrects two things the template gave every site.

Phase 1, framework files (FRAMEWORK_FILES, installed atomically from the
v1.8.2 tag): the dev-only list, which names the engine and its
migrations, and the module that reads it; the root documents and
dependency manifests that carry the version.

Phase 2, the glossary (`telar-content/spreadsheets/glossary.csv`):

  - The `telar` entry's definition is an English paragraph, a blank line and
    a Spanish one. Where it is exactly one of the two texts Telar released,
    it becomes the paragraph in the site's language, as the Compositor makes
    it when it creates a site. An edited definition is left alone.
  - The two instruction rows named `/components/texts/glossary/`, where the
    build has not looked since 1.8.0. Where a cell is exactly the released
    text, it becomes the corrected one.

Both edits replace the cell's text in the file as written, so nothing else
in the spreadsheet changes, quoting and line endings included. A site whose
spreadsheets come from Google Sheets has its CSV rewritten by the next
fetch, so it gets a step asking for the same edit in the sheet.

Telar's own test files stay: this route leaves them to the author, who
gets an optional step for `.github/workflows/telar-tests.yml`, a workflow an
automated upgrade cannot change. The released copies of the engine are
removed by the engine itself once the upgrade has succeeded
(`stale_engine.py`), not here.

The version stamp (telar.version -> 1.8.2) is not written here. The engine
applies it once after every migration step and the regeneration succeed.

Version: v1.8.2
"""

from typing import Dict, List, Optional

from .base import BaseMigration, ChangeRecord, ChangeStatus
from .messages import get_message
from .records import ChangeCategory, is_hard_failure


# Fetched from the v1.8.2 tag and written atomically as one set.
FRAMEWORK_FILES = {
    # Root documents and dependency manifests.
    'README.md': 'Project README for v1.8.2',
    'CHANGELOG.md': 'Release history through v1.8.2',
    'package.json': 'The version',
    'package-lock.json': 'Lockfile matching package.json — always ships with it',

    # The dev-only list and its reader.
    'scripts/dev-only-files.txt': 'Names the engine and its migrations',
    'scripts/telar/dev_only_files.py': 'Describes how each route treats the list',
}

GLOSSARY = 'telar-content/spreadsheets/glossary.csv'

# The `telar` entry as released: v0.9.0-beta to v1.5.0, then v1.5.1 on.
# Each is the English paragraph, a blank line, and the Spanish one.
TELAR_ENTRY_RELEASED = (
    (
        'Telar is minimal-computing framework for creating layered IIIF visual narratives for '
        'digital scholarship, public exhibitions, community storytelling, and classroom projects. '
        'Learn more at [Telar.org](https://telar.org)',
        'Telar es un marco de computación mínima para crear narrativas visuales con capas de texto '
        'e imágenes IIIF para humanidades digitales, exposiciones públicas y contextos educativos '
        'y comunitarios. Aprende más en [Telar.org](https://telar.org)',
    ),
    (
        "Telar (Spanish for 'loom') is a minimal-computing framework that weaves together IIIF "
        'images, audio, video, and texts to create layered visual narratives for digital '
        'scholarship, public exhibitions, community storytelling, and classroom projects. Learn '
        'more at [Telar.org](https://telar.org)',
        'Telar es un marco de computación mínima que entreteje imágenes IIIF, audio, video y textos '
        'en narrativas visuales por capas para humanidades digitales, exposiciones públicas, '
        'narrativa comunitaria y proyectos en el salón de clase. Aprende más en '
        '[Telar.org](https://telar.org)',
    ),
)

# The instruction cells of the definition column, as released and as corrected.
INSTRUCTIONS = (
    ('Panel content: write text here, paste markdown, or the name of an .md file in '
     '/components/texts/glossary/ (the .md extension is required)',
     'Panel content: write text here, paste markdown, or the name of an .md file in '
     '/telar-content/texts/glossary/ (the .md extension is required)'),
    ('Contenido del panel: escribe texto aquí, pega markdown, o indica un archivo archivo .md en '
     '/components/texts/glossary/ (la extensión .md es obligatoria)',
     'Contenido del panel: escribe texto aquí, pega markdown, o indica un archivo .md en '
     '/telar-content/texts/glossary/ (la extensión .md es obligatoria)'),
)

WORKFLOW = '.github/workflows/telar-tests.yml'


def _as_cell(value: str) -> str:
    """*value* as a quoted CSV field, the way every Telar release wrote it."""
    return '"' + value.replace('"', '""') + '"'


def _replace_cell(text: str, old: str, new: str) -> Optional[str]:
    """*text* with the field *old* replaced by *new*, or None when *old* is
    not in it exactly once. The field is matched with either line ending,
    since a spreadsheet saved on Windows writes the blank line inside the
    `telar` entry as CRLF; the replacement keeps the file's own."""
    for newline in ('\n', '\r\n'):
        field = _as_cell(old.replace('\n', newline))
        if text.count(field) == 1:
            return text.replace(field, _as_cell(new.replace('\n', newline)))
    return None


class Migration181to182(BaseMigration):
    """Migration from v1.8.1 to v1.8.2 — the glossary's Telar entry and instructions."""

    from_version = "1.8.1"
    to_version = "1.8.2"
    release_date = None
    description = "v1.8.2: the glossary's Telar entry and instructions are corrected"

    _TARGET_TAG = "v1.8.2"

    # Set by phase 2 when it replaces a released `telar` entry.
    _trimmed_telar_entry = False

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        print("  Phase 1: Updating framework files...")
        records = self._apply_framework_files(FRAMEWORK_FILES)
        if any(is_hard_failure(r) for r in records):
            return records
        print("  Phase 2: Correcting the glossary...")
        records += self._correct_glossary()
        return records

    # ------------------------------------------------------------------ #
    # Phase 2
    # ------------------------------------------------------------------ #

    def _correct_glossary(self) -> List[ChangeRecord]:
        text = self._read_file(GLOSSARY)
        if not isinstance(text, str):
            return []
        lang = self._detect_language()
        records = []

        for english, spanish in TELAR_ENTRY_RELEASED:
            matched = _replace_cell(text, english + '\n\n' + spanish,
                                    spanish if lang == 'es' else english)
            if matched is not None:
                text = matched
                self._trimmed_telar_entry = True
                records.append(ChangeRecord(
                    description=get_message(lang, 'change_glossary_telar_one_language', GLOSSARY),
                    status=ChangeStatus.APPLIED, category=ChangeCategory.OTHER))
                break

        corrected = False
        for released, current in INSTRUCTIONS:
            matched = _replace_cell(text, released, current)
            if matched is not None:
                text, corrected = matched, True
        if corrected:
            records.append(ChangeRecord(
                description=get_message(lang, 'change_glossary_instructions', GLOSSARY),
                status=ChangeStatus.APPLIED, category=ChangeCategory.OTHER))

        if records:
            self._write_file(GLOSSARY, text)
        return records

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """The Google Sheets step is listed only after this run trimmed the
        `telar` entry: on a site whose entry was already one language it
        would ask for nothing, and 1.8.2's manifest, built from a migration
        that has not run, does not trim it."""
        lang = self._detect_language()
        steps = self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()
        if not self._trimmed_telar_entry:
            steps = [s for s in steps if s['audience'] != 'google-sheets']
        return steps

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': ('**Delete `.github/workflows/telar-tests.yml` (optional).** It runs '
                                "Telar's own tests, and only in Telar's repositories, so on your "
                                'site it reports a skipped check and nothing else. GitHub does not '
                                'let an automated upgrade change workflow files, so this one is '
                                'yours to delete. The test files themselves can stay: nothing your '
                                'site builds or publishes uses them.'),
                'audience': 'local',
                'kind': 'optional',
                'doc_url': 'https://telar.org/docs/setup/upgrading/',
            },
            {
                'description': ('**Keep one language in the Telar entry of your glossary sheet.** '
                                'The upgrade kept only your site\'s language in the "telar" row of '
                                'glossary.csv, but your site reads its spreadsheets from Google '
                                'Sheets, so the next build brings both paragraphs back. In the '
                                'glossary sheet, delete the paragraph in the other language from '
                                'the definition of the "telar" row.'),
                'audience': 'google-sheets',
                'kind': 'action',
                'doc_url': 'https://telar.org/docs/setup/upgrading/',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': ('**Borra `.github/workflows/telar-tests.yml` (opcional).** Este '
                                'workflow ejecuta las pruebas del propio Telar y solo corre en los '
                                'repositorios de Telar; en tu sitio no hace más que aparecer como '
                                'una verificación omitida. GitHub no permite que una actualización '
                                'automática modifique archivos de workflow, y por eso borrarlo te '
                                'toca a ti. Los archivos de pruebas pueden quedarse: no intervienen '
                                'en nada de lo que el sitio construye o publica.'),
                'audience': 'local',
                'kind': 'optional',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/',
            },
            {
                'description': ('**Deja en un solo idioma la entrada sobre Telar en tu hoja del '
                                'glosario.** La actualización ya quitó el párrafo en el otro idioma '
                                'de la fila «telar» de glossary.csv, pero tu sitio toma las hojas de '
                                'cálculo de Google Sheets, así que la próxima construcción vuelve a '
                                'traer los dos párrafos. En la hoja del glosario, borra de la '
                                'definición de la fila «telar» el párrafo en el otro idioma.'),
                'audience': 'google-sheets',
                'kind': 'action',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/',
            },
        ]
