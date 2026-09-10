"""Transformations a site needs to reach v0.9.0-beta, decided by what it holds.

v0.9.0-beta is where this stops, because it is the floor the compositor
declares: a site at or above it is picked up there, and the eighteen
migrations above the floor already work. Work belonging to a later
release is not done early here, even where it would be harmless — a hop
that does more than it says cannot be checked against the release it
claims to reach.


The chain these come from asks "which version is this?" and runs the steps
between there and the target. Each step's work is nonetheless decided by the
tree — `_move_content_directories` skips when the source is absent and
reports "Already migrated" when the destination is present — so the version
is an outer gate around logic that already knows the answer.

Removing that gate is what lets one transformation stand in for every source
version. Each function here asks only what the site holds, does nothing when
there is nothing to do, and produces the same result run twice. A site that
half-upgraded and stopped can therefore run again and converge, rather than
being stranded at a version whose files it does not have.

Demo content is not managed here. The chain removed the demo images,
tutorial stories and demo spreadsheets, weighing each against whether it
was still in use and whether the owner had edited it. A site reaching the
floor through this catalogue keeps them, and the migration tells the
owner they are there. Keeping too much is the safe direction for a
migration to be wrong in, and the owner is the one who can tell which of
it they want.

Paths appear here in both their pre- and post-relocation forms where the
relocation may not have happened yet. That is not duplication: a site
entering from 0.6.x has `components/`, one entering from 1.2 has
`telar-content/`, and one transformation serves both.

Version: v1.7.0
"""

import os
import re

import yaml
from typing import Dict, List, Optional

from . import config_merge
from .base import BaseMigration, ChangeRecord, ChangeStatus


# --------------------------------------------------------------------------
# .gitignore
# --------------------------------------------------------------------------

# The union of every entry the chain adds, at the paths they hold after the
# content relocation. Six separate _update_gitignore methods across the
# releases contributed these; one of them existed only to re-ensure an entry
# an earlier one had added.
GITIGNORE_SECTIONS = [
    ('# Generated data files', [
        '_data/*.json',
        '!_data/languages/',
        'search-data.json',
    ]),
    ('# Jekyll build inputs', [
        '_jekyll-files/',
        'telar-content/texts/glossary/_demo_*',
    ]),
    ('# Python', [
        '__pycache__/',
        '*.py[cod]',
        '.pytest_cache/',
    ]),
    ('# Node.js and JavaScript build artifacts', [
        'node_modules/',
        'assets/js/telar-story.js',
        'assets/js/telar-story.js.map',
        'telar-story-bundle.js',
        'telar-story*.bundle.js',
    ]),
    ('# Vendored assets are tracked', [
        '!assets/vendor/',
    ]),
]

# Path references the relocation leaves behind inside .gitignore itself.
GITIGNORE_REWRITES = {
    'components/structures/': 'telar-content/spreadsheets/',
    'components/texts/': 'telar-content/texts/',
    'components/images/': 'telar-content/objects/',
}


def rewrite_gitignore_paths(migration: BaseMigration) -> List[ChangeRecord]:
    """Point .gitignore at the relocated content directories."""
    content = migration._read_file('.gitignore')
    if content is None:
        return []

    updated = content
    for old, new in GITIGNORE_REWRITES.items():
        updated = updated.replace(old, new)

    if updated == content:
        return []

    migration._write_file('.gitignore', updated)
    return [ChangeRecord(
        description='Updated .gitignore path references '
                    '(components/ → telar-content/)',
        status=ChangeStatus.APPLIED, severity='soft')]


def ensure_gitignore_entries(migration: BaseMigration) -> List[ChangeRecord]:
    """Add any missing entry, leaving whatever the site's owner has added.

    .gitignore also arrives as a framework file, which would carry these
    anyway. This runs regardless, because a site whose owner added entries of
    their own should keep them, and because the framework copy is exactly
    what a failed fetch leaves stale.
    """
    records = []
    for section, entries in GITIGNORE_SECTIONS:
        if migration._ensure_gitignore_entries(entries, section_comment=section):
            records.append(ChangeRecord(
                description=f'Updated .gitignore — {section.lstrip("# ")}',
                status=ChangeStatus.APPLIED, severity='soft'))
    return records


# --------------------------------------------------------------------------
# Removals
# --------------------------------------------------------------------------

# Files and directories that are not part of Telar. Removing one is safe
# without asking anything else: nothing in a site references them, and a
# second run finds them already gone.
DEAD_PATHS = [
    'assets/js/openseadragon.min.js',
    'assets/js/scrollama.min.js',
    'assets/images/openseadragon',
    'docs/google_sheets_integration',
    'assets/js/story.js',
    'scripts/requirements.txt',
    'assets/js/telar-story-bundle.js',
    'assets/js/telar-story.bundle.js',
    '.github/dependabot.yml',
    'assets/css/telar.css',
]

# Demo glossary terms Telar does not ship. These are removed only
# when the site's copy still matches the one it shipped with — an owner who
# edited one has made it theirs.
WITHDRAWN_GLOSSARY_TERMS = [
    'colonial-period.md',
    'reduccion.md',
    'resguardo.md',
    'viceroyalty.md',
    'iiif-manifest.md',
    'markdown.md',
]

# Where a term sits now, and where it sat in the release that withdrew
# it. The two differ once the relocation has run, and fetching the
# current path from that release finds nothing — which read as "cannot
# check" and kept every withdrawn term forever.
GLOSSARY_DIRECTORIES = (
    ('telar-content/texts/glossary', 'components/texts/glossary'),
    ('components/texts/glossary', 'components/texts/glossary'),
)

WITHDRAWN_AT = 'v0.6.1-beta'


def remove_dead_paths(migration: BaseMigration) -> List[ChangeRecord]:
    """Delete what is not part of Telar, if it is still present."""
    import shutil

    records = []
    for rel_path in DEAD_PATHS:
        full = os.path.join(migration.repo_root, rel_path)
        if not os.path.exists(full):
            continue
        try:
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
        except OSError as error:
            records.append(ChangeRecord(
                description=f'Could not remove {rel_path}: {error}',
                status=ChangeStatus.FAILED, severity='soft'))
            continue
        records.append(ChangeRecord(
            description=f'Removed {rel_path} — no longer part of Telar',
            status=ChangeStatus.APPLIED, severity='soft'))
    return records


def remove_withdrawn_glossary_terms(migration: BaseMigration) -> List[ChangeRecord]:
    """Delete withdrawn demo glossary terms the owner has not edited.

    A term that cannot be compared is kept. Not being able to tell whether
    someone wrote it is a reason to leave it alone, not a reason to delete
    it.
    """
    records = []
    for directory, withdrawn_from in GLOSSARY_DIRECTORIES:
        for term in WITHDRAWN_GLOSSARY_TERMS:
            rel_path = f'{directory}/{term}'
            if not migration._file_exists(rel_path):
                continue

            original = migration._fetch_from_github(
                f'{withdrawn_from}/{term}', branch=WITHDRAWN_AT)
            if original is None:
                # `is None`, not falsiness: an empty file is content, and
                # reading it as a failed fetch is what stranded 65 of the 71
                # entry points.
                records.append(ChangeRecord(
                    description=f'Kept {rel_path} — could not check whether '
                                'it had been edited',
                    status=ChangeStatus.APPLIED, severity='soft'))
                continue

            current = migration._read_file(rel_path)
            if current is None or current.strip() != original.strip():
                records.append(ChangeRecord(
                    description=f'Kept {rel_path} — edited on this site',
                    status=ChangeStatus.APPLIED, severity='soft'))
                continue

            try:
                os.remove(os.path.join(migration.repo_root, rel_path))
            except OSError as error:
                records.append(ChangeRecord(
                    description=f'Could not remove {rel_path}: {error}',
                    status=ChangeStatus.FAILED, severity='soft'))
                continue
            records.append(ChangeRecord(
                description=f'Removed {rel_path} — withdrawn demo glossary term',
                status=ChangeStatus.APPLIED, severity='soft'))
    return records


# --------------------------------------------------------------------------
# Content relocation
# --------------------------------------------------------------------------

# Where a site's own writing lives. A site built before v0.9.0 keeps it
# under components/; every later one under telar-content/.
RELOCATIONS = {
    'components/images': 'telar-content/objects',
    'components/structures': 'telar-content/spreadsheets',
    'components/texts': 'telar-content/texts',
}

# What components/ may still hold once its content has been relocated:
# the placeholder directories the framework created and never filled,
# each holding the README it shipped with. Both forms of each are listed,
# by content — a directory is empty of the owner's work when everything
# in it is one of these, and holds their work when anything is not.
#
# Names alone are not enough. The framework put a README in every
# placeholder, so a directory that must be *empty* is never empty, and
# components/ would survive on every site that has them, which is every
# site since v0.5.0.
SHIPPED_COMPONENTS_FILES = {
    'README.md': {
        '50739b35a6a1ce4b5e10874f7254db84d1c5c52e7ba5bd47c59d948557254f9f',
        'b2e24690ac32779047863d7aff0d19f3a91a41f124228598dfbf7e3d341e0bea',
    },
    'audio/README.md': {
        '2fe297171f0d25a3dfca049b876a2e534a38e67ae475a0b21a96d42b46c3f390',
        'f24901222851e8548224eae34921118d91d0700bc9a834c7e5e6edf43df88e9d',
    },
    'pdfs/README.md': {
        '01d6b8d5b14a0e89eb041901d2a987e57d47acc7f157d7a7cd3ba3ea949cb50a',
        '76604932b83c5c498743ca0b4eb4715ecfe022b209029bbf47a6d1d6657ec931',
    },
    '3d-models/README.md': {
        '5a2d501f24011d3a3db2116b0974a448febe3bef9c83603716ce49a8db5101e0',
        '73b9147fb138d54084e375f67a31a19be323e10b59466ed55e850d1d27180b54',
    },
}

# The about page moved twice in the chain — into components/texts/pages/,
# then along with everything else. One move goes straight to where it ends.
ABOUT_PAGE = ('pages/about.md', 'telar-content/texts/pages/about.md')


def relocate_content(migration: BaseMigration) -> List[ChangeRecord]:
    """Move a site's writing to telar-content/, if it is still elsewhere.

    Where both source and destination exist the move is refused: two
    directories of someone's work cannot be merged by guesswork, and
    silently preferring one would lose the other.
    """
    import shutil

    records = []
    for source, destination in RELOCATIONS.items():
        source_full = os.path.join(migration.repo_root, source)
        destination_full = os.path.join(migration.repo_root, destination)

        if not os.path.exists(source_full):
            continue

        if os.path.exists(destination_full):
            records.append(ChangeRecord(
                description=f'Both {source}/ and {destination}/ are present. '
                            'Neither was changed — please merge them by hand.',
                status=ChangeStatus.APPLIED, severity='soft'))
            continue

        os.makedirs(os.path.dirname(destination_full), exist_ok=True)
        shutil.move(source_full, destination_full)
        records.append(ChangeRecord(
            description=f'Moved {source}/ → {destination}/',
            status=ChangeStatus.APPLIED, severity='soft'))

    records.extend(_remove_empty_components(migration))
    return records


def _remove_empty_components(migration: BaseMigration) -> List[ChangeRecord]:
    """Remove components/ once nothing of the owner's is left in it."""
    import shutil

    components = os.path.join(migration.repo_root, 'components')
    if not os.path.isdir(components):
        return []

    theirs = sorted(_owner_files_under(components))
    if theirs:
        listed = ', '.join(theirs[:5])
        if len(theirs) > 5:
            listed += f', and {len(theirs) - 5} more'
        return [ChangeRecord(
            description=f'Kept components/ — it still holds {listed}',
            status=ChangeStatus.APPLIED, severity='soft')]

    shutil.rmtree(components)
    return [ChangeRecord(description='Removed the empty components/ directory',
                         status=ChangeStatus.APPLIED, severity='soft')]


def _owner_files_under(components: str) -> List[str]:
    """Everything under components/ that the framework did not put there."""
    theirs = []
    for directory, _, filenames in os.walk(components):
        for filename in filenames:
            full = os.path.join(directory, filename)
            relative = os.path.relpath(full, components)
            shipped = SHIPPED_COMPONENTS_FILES.get(relative)
            if shipped is None or _digest(full) not in shipped:
                theirs.append(relative)
    return theirs


def _digest(path: str) -> Optional[str]:
    import hashlib

    try:
        with open(path, 'rb') as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def relocate_about_page(migration: BaseMigration) -> List[ChangeRecord]:
    """Move the about page to where a current site keeps it."""
    source, destination = ABOUT_PAGE
    if not migration._file_exists(source):
        return []

    if migration._file_exists(destination):
        return [ChangeRecord(
            description=f'Both {source} and {destination} are present. '
                        'Neither was changed — please merge them by hand.',
            status=ChangeStatus.APPLIED, severity='soft')]

    if not migration._move_file(source, destination):
        return [ChangeRecord(description=f'Could not move {source}',
                             status=ChangeStatus.FAILED, severity='soft')]

    records = [ChangeRecord(description=f'Moved {source} → {destination}',
                            status=ChangeStatus.APPLIED, severity='soft')]

    pages = os.path.join(migration.repo_root, 'pages')
    if os.path.isdir(pages) and not os.listdir(pages):
        os.rmdir(pages)
        records.append(ChangeRecord(
            description='Removed the empty pages/ directory',
            status=ChangeStatus.APPLIED, severity='soft'))
    return records


# --------------------------------------------------------------------------
# Image flattening
# --------------------------------------------------------------------------

# Images sat in two subdirectories before v0.5.0 and directly in the images
# directory after it. Both bases are listed because the flattening and the
# relocation are independent of each other: whichever a site meets first,
# the other still finds its work.
IMAGE_DIRECTORIES = (
    'components/images',        # before the relocation
    'telar-content/objects',    # after it
)

# objects/ is read first, so a name it holds is the name that survives.
# A file in additional/ wanting a taken name is suffixed instead, because
# objects.csv points at the objects/ name and renaming that would break
# the reference the spreadsheet depends on.
FLATTENED_SUBDIRECTORIES = ('objects', 'additional')

CONFLICT_SUFFIX = '-2'

# Where a site writes image paths by hand: its stories, and the markdown
# pages at the repository root.
REFERENCE_DIRECTORIES = ('_stories',)

_BASES = '|'.join(re.escape(base) for base in IMAGE_DIRECTORIES)
_SUBDIRECTORIES = '|'.join(FLATTENED_SUBDIRECTORIES)

# The subdirectory segment, with its base kept so that a bare `objects/`
# somewhere else in a path is left alone, and the subdirectory captured so
# that a rename is applied only to the reference it belongs to.
SUBDIRECTORY_SEGMENT = re.compile(rf'({_BASES})/({_SUBDIRECTORIES})/',
                                  re.IGNORECASE)

# An image path as markdown, HTML or CSS writes it. The leading group is
# the syntax around the path; the second group is the path itself, which
# may carry a host, a `../`, or a leading slash.
IMAGE_REFERENCE = re.compile(
    r'(!\[.*?\]\(|<img[^>]+src=["\']|url\(["\']?)'
    r'((?:https?://[^/\s]+(?:/[^\s]*?)?)?(?:\.\./|/)?'
    rf'(?:{_BASES})/(?:{_SUBDIRECTORIES})/[^)\s"\']+)',
    re.IGNORECASE)


def flatten_image_directories(migration: BaseMigration) -> List[ChangeRecord]:
    """Bring images up out of objects/ and additional/, and fix references.

    The two subdirectories became one directory in v0.5.0. A site that has
    already flattened has neither subdirectory and nothing happens here.

    A reference keeps the base directory it was written with: only the
    subdirectory is taken out of it. The relocation that follows moves
    the files without rewriting references, exactly as the chain leaves
    them, and tells the owner to fix any path they hardcoded.
    """
    renamed: Dict[tuple, str] = {}
    # Files left where they are. Their references must be left alone too:
    # flattening a path whose file did not move points it at whatever
    # else holds that name.
    kept: set = set()
    records = []
    moved = 0

    for base in IMAGE_DIRECTORIES:
        for subdirectory in FLATTENED_SUBDIRECTORIES:
            count, subdirectory_records = _flatten_subdirectory(
                migration, base, subdirectory, renamed, kept)
            moved += count
            records.extend(subdirectory_records)

    if moved:
        records.append(ChangeRecord(
            description=f'Moved {moved} image(s) up out of objects/ and '
                        'additional/',
            status=ChangeStatus.APPLIED, severity='soft'))

    records.extend(_rewrite_image_references(migration, renamed, kept))
    return records


def _flatten_subdirectory(migration: BaseMigration, base: str,
                          subdirectory: str,
                          renamed: Dict[tuple, str],
                          kept: set) -> tuple:
    """Move one subdirectory's files up a level, suffixing taken names."""
    source = os.path.join(migration.repo_root, base, subdirectory)
    if not os.path.isdir(source):
        return 0, []

    destination_directory = os.path.join(migration.repo_root, base)
    records = []
    moved = 0

    for filename in sorted(os.listdir(source)):
        full = os.path.join(source, filename)
        if not os.path.isfile(full):
            continue

        target = filename
        destination = os.path.join(destination_directory, target)

        if os.path.exists(destination):
            if _same_file(full, destination):
                # This file, already moved. Its references need no change.
                os.remove(full)
                continue

            if subdirectory == FLATTENED_SUBDIRECTORIES[0]:
                # Renaming this one is not available: objects.csv names it
                # by filename, and the spreadsheet is not rewritten here.
                # Two different images of one name is a question for the
                # owner, not a guess for a migration.
                records.append(ChangeRecord(
                    description=f'Kept {base}/{subdirectory}/{filename} — '
                                f'{base}/{filename} is a different image, '
                                'and the spreadsheet names this one',
                    status=ChangeStatus.APPLIED, severity='soft'))
                kept.add((base, subdirectory, filename))
                continue

            stem, extension = os.path.splitext(filename)
            target = f'{stem}{CONFLICT_SUFFIX}{extension}'
            destination = os.path.join(destination_directory, target)
            if os.path.exists(destination):
                # Overwriting here would destroy whichever image the site
                # already keeps under the suffixed name.
                records.append(ChangeRecord(
                    description=f'Kept {base}/{subdirectory}/{filename} — '
                                f'both {filename} and {target} are taken '
                                f'in {base}/',
                    status=ChangeStatus.APPLIED, severity='soft'))
                kept.add((base, subdirectory, filename))
                continue

        try:
            os.rename(full, destination)
        except OSError as error:
            kept.add((base, subdirectory, filename))
            records.append(ChangeRecord(
                description=f'Could not move {base}/{subdirectory}/'
                            f'{filename}: {error}',
                status=ChangeStatus.FAILED, severity='soft'))
            continue

        moved += 1
        if target != filename:
            renamed[(base, subdirectory, filename)] = target
            records.append(ChangeRecord(
                description=f'Moved {base}/{subdirectory}/{filename} → '
                            f'{base}/{target}, renamed because {filename} '
                            'was taken',
                status=ChangeStatus.APPLIED, severity='soft'))

    if not os.listdir(source):
        try:
            os.rmdir(source)
            records.append(ChangeRecord(
                description=f'Removed the empty {base}/{subdirectory}/ '
                            'directory',
                status=ChangeStatus.APPLIED, severity='soft'))
        except OSError:
            pass

    return moved, records


def _same_file(one: str, other: str) -> bool:
    """Whether two files hold the same bytes, and are two files.

    A link reads as equal to what it points at, and deleting the target
    would leave the survivor pointing at nothing.
    """
    if os.path.islink(one) or os.path.islink(other):
        return False
    try:
        if os.path.getsize(one) != os.path.getsize(other):
            return False
        with open(one, 'rb') as first, open(other, 'rb') as second:
            return first.read() == second.read()
    except OSError:
        return False


def _reference_files(migration: BaseMigration) -> List[str]:
    """Every file a site may have written an image path into."""
    paths = []
    for directory in REFERENCE_DIRECTORIES:
        full = os.path.join(migration.repo_root, directory)
        if not os.path.isdir(full):
            continue
        paths.extend(os.path.join(full, name)
                     for name in sorted(os.listdir(full))
                     if name.endswith('.md'))
    paths.extend(os.path.join(migration.repo_root, name)
                 for name in sorted(os.listdir(migration.repo_root))
                 if name.endswith('.md'))
    return paths


def _flatten_reference(path: str, renamed: Dict[tuple, str],
                       kept: set) -> str:
    """Drop the subdirectory from one path, and follow any rename.

    The rename is looked up under the subdirectory the reference names.
    A file renamed out of additional/ says nothing about the file of the
    same name in objects/, which kept its name and its references — nor
    about one of that name under the other base directory.
    """
    segment = SUBDIRECTORY_SEGMENT.search(path)
    if segment is None:
        return path

    base = segment.group(1)
    subdirectory = segment.group(2).lower()
    tail = path[segment.end():]

    # Only a file sitting directly in the subdirectory is moved, so only
    # its reference is flattened. One naming a directory below it would
    # be pointed at a path that does not exist.
    if '/' in tail:
        return path

    # A query or a fragment is not part of the filename.
    name = re.split(r'[?#]', tail, maxsplit=1)[0]
    if (base, subdirectory, name) in kept:
        return path
    flattened = SUBDIRECTORY_SEGMENT.sub(lambda match: match.group(1) + '/',
                                         path, count=1)
    directory, separator, _ = flattened.rpartition('/')
    target = renamed.get((base, subdirectory, name))
    if target is not None:
        return f'{directory}{separator}{target}{tail[len(name):]}'
    return flattened


def _rewrite_image_references(migration: BaseMigration,
                              renamed: Dict[tuple, str],
                              kept: set) -> List[ChangeRecord]:
    """Point a site's own writing at the flattened paths.

    A path is rewritten whether or not the image is there. A reference to
    a missing image was already broken; leaving it spelt the old way only
    hides that it is now broken in one place rather than two.
    """
    records = []
    rewritten = 0

    for full_path in _reference_files(migration):
        try:
            with open(full_path, encoding='utf-8') as handle:
                content = handle.read()
        except (OSError, UnicodeDecodeError):
            continue

        counted = [0]

        def replace(match):
            counted[0] += 1
            flattened = _flatten_reference(match.group(2), renamed, kept)
            if flattened == match.group(2):
                counted[0] -= 1
            return match.group(1) + flattened

        updated = IMAGE_REFERENCE.sub(replace, content)
        if updated == content:
            continue

        with open(full_path, 'w', encoding='utf-8') as handle:
            handle.write(updated)
        rewritten += counted[0]

    if rewritten:
        records.append(ChangeRecord(
            description=f'Updated {rewritten} image path(s) to the '
                        'flattened directory',
            status=ChangeStatus.APPLIED, severity='soft'))
    return records


# --------------------------------------------------------------------------
# Spreadsheets
# --------------------------------------------------------------------------

SPREADSHEET_DIRECTORIES = (
    'telar-content/spreadsheets',   # after the relocation
    'components/structures',        # before it
)

# A spreadsheet's kind is read from its filename; anything unrecognised is
# a story. Templates are skipped: they ship with every column already.
SPREADSHEET_KINDS = {
    'objects.csv': 'objects', 'objetos.csv': 'objects',
    'project.csv': 'project', 'proyecto.csv': 'project',
    'glossary.csv': 'glossary', 'glosario.csv': 'glossary',
}

TEMPLATE_PREFIXES = ('blank_template', 'plantilla')

# Telar's spreadsheets carry an English header row and a Spanish one, and a
# story spreadsheet may carry only one of the two. A row is a header row
# when its first cell is the kind's first column, and that cell says which
# language the row is written in.
FIRST_COLUMNS = {
    'objects': {'object_id': 'en', 'id_objeto': 'es'},
    'project': {'order': 'en', 'orden': 'es'},
    'glossary': {'term_id': 'en', 'id_termino': 'es', 'id_término': 'es'},
    'story': {'step': 'en', 'paso': 'es'},
}

# Columns the spreadsheets gained between v0.8.0 and v1.2.0. A site whose
# spreadsheets came from an older template is missing them; a site built
# since already has them, under one spelling or another.
EXPECTED_COLUMNS = {
    'story': [{'en': 'page', 'es': 'página'}],
    'objects': [{'en': 'year', 'es': 'año'},
                {'en': 'object_type', 'es': 'tipo_objeto'},
                {'en': 'subjects', 'es': 'temas'},
                {'en': 'featured', 'es': 'destacado'}],
    'project': [{'en': 'private', 'es': 'privada'}],
}

# Every spelling a column has shipped under. A column counts as missing
# only when none of its spellings appears in any header row — `protected`
# and `protegido` are v0.8.1's names for what v1.6.0 documents as
# `private`, and a site still using them has the column.
COLUMN_ALIASES = {
    'page': {'page', 'pagina', 'página'},
    'year': {'year', 'año', 'ano'},
    'object_type': {'object_type', 'tipo_objeto'},
    'subjects': {'subjects', 'temas', 'materias', 'materia'},
    'featured': {'featured', 'destacado'},
    'private': {'private', 'privada', 'protected', 'protegida', 'protegido'},
}

# Header renames. iiif_manifest became source_url in v0.5.0, before the
# spreadsheets carried Spanish headers, so it has only the one spelling.
RENAMED_COLUMNS = {'iiif_manifest': 'source_url'}


def _spreadsheet_files(migration: BaseMigration) -> List[tuple]:
    """Every spreadsheet a site keeps, wherever it keeps them."""
    found = []
    for directory in SPREADSHEET_DIRECTORIES:
        full = os.path.join(migration.repo_root, directory)
        if not os.path.isdir(full):
            continue
        for filename in sorted(os.listdir(full)):
            if not filename.lower().endswith('.csv'):
                continue
            if filename.lower().startswith(TEMPLATE_PREFIXES):
                continue
            found.append((f'{directory}/{filename}',
                          SPREADSHEET_KINDS.get(filename.lower(), 'story'),
                          os.path.join(full, filename)))
    return found


def _read_rows(path: str) -> Optional[List[List[str]]]:
    """A spreadsheet as records, not as lines.

    A cell may hold a newline — the panel content columns routinely do —
    so a record and a line are not the same thing. Splitting on newlines
    put an appended comma inside the user's prose.
    """
    import csv

    try:
        with open(path, newline='', encoding='utf-8') as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    if not any(any(cell.strip() for cell in row) for row in rows):
        return None
    return rows


def _write_rows(path: str, rows: List[List[str]]) -> None:
    import csv

    with open(path, 'w', newline='', encoding='utf-8') as handle:
        csv.writer(handle, lineterminator='\n').writerows(rows)


# An English header row and a Spanish one, in that order. A site may have
# only the one. Nothing below them is a header, whatever it holds: an
# object whose id happens to be `object_id` is a row of the site's data.
HEADER_ROWS = 2


def _first_cell_language(kind: str, row: List[str]) -> Optional[str]:
    if not row:
        return None
    return FIRST_COLUMNS.get(kind, {}).get(row[0].strip().lower())


def _row_language(kind: str, rows: List[List[str]], index: int) -> Optional[str]:
    """The language of a header row, or None when the row is not one.

    Telar's spreadsheets put the English header first and the Spanish
    one under it. A Spanish-first sheet is Spanish-only, so its second
    row is data — an object whose id is legitimately `object_id`, not a
    header that arrived in the wrong order.
    """
    if index >= HEADER_ROWS or index >= len(rows):
        return None
    language = _first_cell_language(kind, rows[index])
    if index == 0:
        return language
    return 'es' if (language == 'es'
                    and _first_cell_language(kind, rows[0]) == 'en') else None


def _is_blank(row: List[str]) -> bool:
    return not any(cell.strip() for cell in row)


def rename_spreadsheet_columns(migration: BaseMigration) -> List[ChangeRecord]:
    """Rename columns that changed name, in the header rows only."""
    records = []
    for relative, kind, path in _spreadsheet_files(migration):
        rows = _read_rows(path)
        if rows is None:
            continue

        renamed = []
        for index in range(min(HEADER_ROWS, len(rows))):
            if _row_language(kind, rows, index) is None:
                continue
            lowered = [cell.strip().lower() for cell in rows[index]]
            for old, new in RENAMED_COLUMNS.items():
                if old not in lowered or new in lowered:
                    continue
                rows[index] = [new if cell.strip().lower() == old else cell
                               for cell in rows[index]]
                renamed.append((old, new))

        if not renamed:
            continue

        _write_rows(path, rows)
        for old, new in renamed:
            records.append(ChangeRecord(
                description=f'Renamed the {old} column to {new} in {relative}',
                status=ChangeStatus.APPLIED, severity='soft'))
    return records


def ensure_spreadsheet_columns(migration: BaseMigration) -> List[ChangeRecord]:
    """Append the columns a spreadsheet is missing, in each row's language.

    A header row is given the column's name in its own language; every
    other row is given an empty cell, so the rows stay the same width.
    """
    records = []
    for relative, kind, path in _spreadsheet_files(migration):
        expected = EXPECTED_COLUMNS.get(kind)
        if not expected:
            continue

        rows = _read_rows(path)
        if rows is None:
            continue

        present = set()
        headers = 0
        for index in range(min(HEADER_ROWS, len(rows))):
            if _row_language(kind, rows, index) is None:
                continue
            headers += 1
            present.update(cell.strip().lower() for cell in rows[index])

        if not headers:
            continue

        missing = [column for column in expected
                   if not COLUMN_ALIASES[column['en']] & present]
        if not missing:
            continue

        for index, row in enumerate(rows):
            if _is_blank(row):
                continue
            language = _row_language(kind, rows, index)
            if language is None:
                row.extend([''] * len(missing))
            else:
                row.extend(column[language] for column in missing)

        _write_rows(path, rows)
        records.append(ChangeRecord(
            description=f'Added {", ".join(c["en"] for c in missing)} to '
                        f'{relative}',
            status=ChangeStatus.APPLIED, severity='soft'))
    return records


# The v0.2.0 project spreadsheet was a list of key-value pairs with a
# STORIES section at the end. Only the stories were ever read, so only the
# stories are carried across.
LEGACY_PROJECT_MARKERS = ('key,value', 'project_title')
LEGACY_PROJECT_HEADER = ['order', 'title', 'subtitle']


def restructure_project_spreadsheet(migration: BaseMigration) -> List[ChangeRecord]:
    """Turn a key-value project spreadsheet into a table of stories."""
    records = []
    for relative, kind, path in _spreadsheet_files(migration):
        if kind != 'project':
            continue

        rows = _read_rows(path)
        if rows is None:
            continue

        flat = '\n'.join(','.join(row) for row in rows)
        if not any(marker in flat for marker in LEGACY_PROJECT_MARKERS):
            continue

        stories = []
        in_stories = False
        for row in rows:
            if len(row) < 2:
                continue
            key, value = row[0].strip(), row[1].strip()
            if key == 'STORIES':
                in_stories = True
                continue
            if in_stories and key.isdigit():
                stories.append([key, value, ''])

        if not stories:
            records.append(ChangeRecord(
                description=f'Kept {relative} — it is in the old key-value '
                            'format but names no stories',
                status=ChangeStatus.APPLIED, severity='soft'))
            continue

        _write_rows(path, [LEGACY_PROJECT_HEADER] + stories)
        records.append(ChangeRecord(
            description=f'Rewrote {relative} as a table of '
                        f'{len(stories)} story/stories',
            status=ChangeStatus.APPLIED, severity='soft'))
    return records


# --------------------------------------------------------------------------
# Configuration and frontmatter
# --------------------------------------------------------------------------

def reinstate_configuration(migration: BaseMigration) -> List[ChangeRecord]:
    """Write the site's settings into the release's _config.yml.

    See config_merge for the three rules that decide each key. The whole
    of the chain's configuration work is here: nothing hunts for a line to
    insert after, so nothing can insert in the wrong place.
    """
    site = migration._read_file('_config.yml')
    if site is None:
        return []

    if config_merge.read_site(site) is None:
        return [ChangeRecord(
            description='Kept _config.yml as it is — it could not be read as '
                        'YAML, so nothing could be moved across safely',
            status=ChangeStatus.APPLIED, severity='soft')]

    template = migration._fetch_from_github('_config.yml')
    if template is None:
        return [ChangeRecord(
            description='Could not fetch _config.yml',
            status=ChangeStatus.FAILED, severity='hard')]

    merged, notes = config_merge.merge(template, site)
    if merged == site:
        return []

    migration._write_file('_config.yml', merged)
    records = [ChangeRecord(
        description="Rewrote _config.yml on the release's, keeping this "
                    "site's own settings",
        status=ChangeStatus.APPLIED, severity='soft')]
    records.extend(ChangeRecord(description=note,
                                status=ChangeStatus.APPLIED, severity='soft')
                   for note in notes)
    return records


# Ordered as a site meets them. Every entry is safe to run against any site,
# including one where it has already run.
TRANSFORMATIONS = [
    # Flattening before the relocation, which is the order a site met them
    # in. Each finds its work under either base, so neither has to run
    # first — but a reference keeps the base it was written with, and the
    # relocation does not rewrite references any more than the chain did.
    flatten_image_directories,
    relocate_content,
    relocate_about_page,
    rewrite_gitignore_paths,
    ensure_gitignore_entries,
    remove_dead_paths,
    remove_withdrawn_glossary_terms,
    # The spreadsheets once they are where they belong.
    restructure_project_spreadsheet,
    rename_spreadsheet_columns,
    ensure_spreadsheet_columns,
    # Configuration last: it is the only one that fetches, so a site
    # that cannot reach the network has done everything else first.
    reinstate_configuration,
]
