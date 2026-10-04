"""
CSV Utility Functions

This module deals with the low-level operations that prepare raw CSV data
before the processors for projects, objects, and stories take over. It sits
at the very start of the build pipeline: every CSV file passes through
these functions before reaching the code that understands what an "object"
or a "step" actually means.

The central piece is `COLUMN_NAME_MAPPING`, a dictionary that maps Spanish
column headers to their English equivalents. Telar added bilingual CSV
support in v0.6.0, so a spreadsheet can use either "paso" or "step",
"objeto" or "object", and so on. The mapping also handles backward
compatibility — for example, the old column name "layer1_file" is mapped
to the current "layer1_content". `normalize_column_names()` applies this
mapping to a DataFrame's columns, printing an info line for each rename
so the build log shows what happened.

`is_header_row()` detects duplicate header rows that sometimes appear in
bilingual CSVs (where the first data row repeats the column names in the
other language). It checks whether 80% or more of a row's non-empty cells
match known column names, and if so, the row is skipped during processing.

`sanitize_dataframe()` strips the Christmas tree emoji from all string
columns. This prevents user-entered data from accidentally triggering
Christmas Tree Mode, which is a development/testing feature that injects
fake error objects into the build.

`get_source_url()` resolves an object's image source with backward
compatibility: it checks the `source_url` column first (v0.5.0+ standard),
then falls back to the legacy `iiif_manifest` column (v0.4.x), returning
an empty string if neither is present.

The mapping dictionary has grown with each release. It now covers clip
control columns for video and audio steps (`inicio_clip` → `clip_start`,
`fin_clip` → `clip_end`, `bucle` → `loop`), an accessibility column
(`texto_alt` → `alt_text`), short-form layer button and content names
(`boton1` → `layer1_button`, `contenido1` → `layer1_content`), and the
rename of the gallery classification column from `object_type` to `medium`
— with backward-compatible aliases (`tipo_objeto`, `medium_genre`,
`medio_genero`) so existing spreadsheets continue to work without changes.

Version: v1.8.0
"""

from pathlib import Path

import pandas as pd


# Canonical local image/document extensions, shared by the CSV processors and
# the tile generator. Every list of image extensions in the build derives from
# this one: a processor that recognises a file the tiler never searches for
# produces an object that validates and has no image.
#
# Ordered, because the tiler takes the first extension matching an object id and
# several files can share a stem. The order is the tiler's existing priority, so
# which file a site already tiles does not change.
#
# The Telar Compositor pins its own upload allowlist against this tuple, so the
# name and the literal shape are load-bearing outside this repository: an author
# must not be able to upload a file the build cannot tile, or hold a file in
# their repository that the Compositor refuses. Widening the set here is what
# lets the Compositor widen; renaming it or building it dynamically breaks a
# check that runs at their release gate.
IMAGE_EXTENSIONS_ORDERED = (
    '.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tif', '.tiff', '.pdf',
    '.gif', '.bmp', '.svg',
)

# Membership form, for reference-stripping and on-disk existence checks.
IMAGE_EXTENSIONS = frozenset(IMAGE_EXTENSIONS_ORDERED)

# Rendered by MuPDF rather than decoded by Pillow. Both describe a document
# rather than a grid of pixels, so the build chooses a resolution for them:
# process_pdf.py renders a PDF page at 200 DPI, and iiif_utils rasterises an SVG
# to a fixed longest side. Everything else is decoded at its own size.
PYMUPDF_EXTENSIONS = frozenset({'.pdf', '.svg'})


def build_stem_index(directory):
    """Map filename stem -> list of Path objects for one directory, in a single
    pass. Lets per-object existence checks be O(1) lookups instead of each
    re-scanning the whole directory (the old O(objects x files) behaviour).

    Args:
        directory: Path or str of the directory to index.

    Returns:
        dict[str, list[Path]]: stem -> files with that stem (empty if dir absent).
    """
    index = {}
    d = Path(directory)
    if d.exists():
        for f in d.iterdir():
            if f.is_file():
                index.setdefault(f.stem, []).append(f)
    return index


# Bilingual column name mapping (Spanish -> English)
# Supports bilingual story CSV headers (v0.6.0+)
COLUMN_NAME_MAPPING = {
    # Story step columns (Spanish -> English)
    'paso': 'step',
    'objeto': 'object',
    'pregunta': 'question',
    'respuesta': 'answer',
    'boton_capa1': 'layer1_button',
    'boton1': 'layer1_button',            # short-form used in CSV templates
    'contenido_capa1': 'layer1_content',  # v0.6.3+ preferred name
    'contenido1': 'layer1_content',       # short-form used in CSV templates
    'archivo_capa1': 'layer1_content',    # backward compatibility
    'boton_capa2': 'layer2_button',
    'boton2': 'layer2_button',            # short-form used in CSV templates
    'contenido_capa2': 'layer2_content',  # v0.6.3+ preferred name
    'contenido2': 'layer2_content',       # short-form used in CSV templates
    'archivo_capa2': 'layer2_content',    # backward compatibility
    # Clip control columns (v0.10.0+)
    'inicio_clip': 'clip_start',
    'fin_clip': 'clip_end',
    'bucle': 'loop',
    # Accessibility columns (v1.0.0-beta+)
    'texto_alt': 'alt_text',
    # x, y, zoom are the same in both languages
    'pagina': 'page',
    'página': 'page',
    'page': 'page',  # normalize casing (Google Sheets may use 'Page')

    # English column backward compatibility (layer1_file -> layer1_content)
    'layer1_file': 'layer1_content',
    'layer2_file': 'layer2_content',

    # Objects columns (Spanish -> English) - for IIIF auto-populator support
    'id_objeto': 'object_id',
    'titulo': 'title',
    'descripcion': 'description',
    'descripción': 'description',
    'url_fuente': 'source_url',
    'creador': 'creator',
    'periodo': 'period',
    'medio': 'medium',
    'dimensiones': 'dimensions',
    'ubicacion': 'source',
    'ubicación': 'source',
    'credito': 'credit',
    'crédito': 'credit',
    'miniatura': 'thumbnail',
    # v0.8.0 gallery filtering columns
    'año': 'year',
    'ano': 'year',  # without tilde
    # Old column names remain accepted from user CSVs (documented compat)
    'tipo_objeto': 'medium',
    'object_type': 'medium',
    'medium_genre': 'medium',     # v1.0.0-beta: alternative English name
    'medio_genero': 'medium',     # v1.0.0-beta: alternative Spanish name
    'temas': 'subjects',
    'materias': 'subjects',  # Dublin Core official Spanish translation
    'materia': 'subjects',
    'destacado': 'featured',
    'fuente': 'source',
    # The old column name is still accepted
    'location': 'source',

    # Project columns (Spanish -> English)
    'orden': 'order',
    'id_historia': 'story_id',
    'subtitulo': 'subtitle',
    'subtítulo': 'subtitle',
    'firma': 'byline',
    # Both words in both genders. A header this table does not carry yields
    # nothing to `row.get('protected', '')`, so the story is never marked
    # protected and publishes in the clear — and the interlock that refuses
    # such a build acts on stories already recognised as protected, so it
    # cannot fire either.
    'private': 'protected',
    'privada': 'protected',
    'privado': 'protected',
    'protegida': 'protected',
    'protegido': 'protected',
    'mostrar_secciones': 'show_sections',

    # Glossary columns (Spanish -> English)
    'id_termino': 'term_id',
    'id_término': 'term_id',
    'título': 'title',
    'definición': 'definition',
    'definicion': 'definition',
    'términos_relacionados': 'related_terms',
    'terminos_relacionados': 'related_terms',
}

# Aliases one sheet reads and no other. The table above applies to every
# sheet, and `tipo` is a word an author uses for a column of their own on an
# objects or story sheet — the type of document, say — which the build would
# otherwise rename to a name nothing on that sheet reads. A sheet's reader
# passes its own table as `sheet_aliases`; every other sheet keeps the header
# as the author wrote it.
GLOSSARY_COLUMN_ALIASES = {
    'tipo': 'kind',
}


def sanitize_dataframe(df):
    """
    Remove Christmas tree emoji from all string fields in dataframe.
    This prevents accidental Christmas Tree Mode triggering from user data.

    NOTE: This is NOT an HTML/XSS sanitiser. It does not encode HTML entities
    or otherwise validate field contents. Per-template and per-sink escaping
    (Liquid `jsonify`/`escape`, the JS `escapeHtml` helper) is the primary
    control for HTML safety; this function only strips the one emoji that would
    falsely trigger Christmas Tree Mode.

    As a diagnostic aid it also warns (without modifying anything) when a URL
    column carries a `javascript:` or `data:` scheme, so authors can correct it.

    Args:
        df: pandas DataFrame to sanitize

    Returns:
        DataFrame: Sanitized dataframe (copy of input)
    """
    import re
    # Christmas tree emoji: U+1F384
    tree_emoji = chr(0x1F384)
    tree_pattern = re.compile(re.escape(tree_emoji))
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):  # String columns (works with pandas 2.x and 3.x)
            df[col] = df[col].apply(lambda x: tree_pattern.sub('', str(x)) if pd.notna(x) else x)

    # Warn-only URL-scheme check for columns that feed href/src sinks. We do not
    # strip or rewrite the value — the author owns the fix.
    url_columns = {'source_url', 'iiif_manifest', 'thumbnail', 'image'}
    for col in df.columns:
        if col.lower().strip() not in url_columns:
            continue
        for value in df[col]:
            if not pd.notna(value):
                continue
            stripped = str(value).strip().lower()
            if stripped.startswith('javascript:') or stripped.startswith('data:'):
                print(f"  [WARN] Suspicious URL scheme in '{col}': {str(value).strip()!r} "
                      f"— links/images with javascript:/data: schemes can be unsafe")

    return df


def get_source_url(row):
    """
    Get source URL for an object, checking both source_url and iiif_manifest columns.

    Implements backward compatibility:
    - Checks source_url first (new standard, v0.5.0+)
    - Falls back to iiif_manifest (legacy column, v0.4.x)
    - Returns empty string if neither exists or both are empty

    Args:
        row: pandas Series or dict representing a CSV row

    Returns:
        str: Source URL (or empty string)
    """
    # Check source_url first (new standard)
    source_url = str(row.get('source_url', '')).strip()
    if source_url:
        return source_url

    # Fall back to iiif_manifest (legacy)
    iiif_manifest = str(row.get('iiif_manifest', '')).strip()
    if iiif_manifest:
        return iiif_manifest

    return ''


OBJECT_FIELDS = {
    'object_id', 'title', 'creator', 'period', 'medium', 'dimensions',
    'location', 'credit', 'thumbnail', 'iiif_manifest', 'source_url',
    'source', 'object_warning', 'object_warning_short', 'year',
    'object_type', 'subjects', 'is_featured_sample', '_demo',
    'description', 'featured', 'alt_text',
    # Auto-detected media type and audio metadata. Nothing writes
    # audio_duration: it stays reserved, so a column of that name is not shown
    # as custom metadata, while the Compositor's FRAMEWORK_OBJECT_FIELDS holds
    # it. Its tests/import.server.test.ts reads this set and must agree.
    'media_type', 'audio_duration', 'audio_filesize', 'audio_format',
}


# Columns whose cells are read as the author typed them. pandas infers a
# column's dtype from the whole column, so a cell's meaning would otherwise
# depend on what its neighbours contain: `1` in a numeric column with a blank
# cell arrives as "1.0" and misses the vocabulary a flag is matched against,
# while the same `1` in a column with no blank arrives as "1" and matches; and
# a year typed as 1890 is published as "1890.0" on the strength of a blank
# cell in another row. The two cases differ in where the damage lands — a flag
# fails to match, a year is published wrong — and have the same cause, so they
# have the same remedy.
#
# An object id is the third kind: it is a key, matched across two sheets that
# pandas reads separately and can therefore infer differently from each other,
# so a numeric id could be `1` in one sheet and "1.0" in the other and a step
# would lose the object it names. Read as text, both sides hold what the
# author typed, and a step naming something the site does not have is reported
# by the reference check rather than silently losing its image.
TEXT_COLUMNS = frozenset({'featured', 'year', 'object_id', 'object'})


def text_column_dtypes():
    """The pandas dtype map pinning `TEXT_COLUMNS` to text.

    Keyed on the headers as authors write them, English and Spanish alike,
    because the reader runs before `normalize_column_names()`. pandas ignores
    keys for columns a given sheet does not have.
    """
    headers = set(TEXT_COLUMNS)
    headers.update(alias for alias, canonical in COLUMN_NAME_MAPPING.items()
                   if canonical in TEXT_COLUMNS)
    return {header: str for header in headers}


def normalize_column_names(df, canonical_fields=None, sheet_aliases=None):
    """
    Normalize column names to English using bilingual mapping.
    Supports both English and Spanish column headers (v0.6.0+).

    `canonical_fields` scopes the map to one kind of sheet. The table is
    shared by every spreadsheet the build reads, so a rule written for the
    project sheet also renames a column on the objects sheet: an author's
    own `privado` column — a note that a piece is in a private collection —
    became `protected`, the name the project sheet uses to mean "encrypt
    this story". Nothing reads `protected` on an object, so it landed in
    `extra_metadata`, where the object layout prints the key as the label:
    a Spanish site showing an English heading the author never wrote.

    The set is the canonical names that sheet's own consumer reads, so it
    is derived from the thing it describes rather than listed by hand. A
    rename whose target is not in it is skipped, which leaves the author's
    own header in place — the safe direction, because the name they typed
    is the name they meant. Pass None to apply the whole map, which is the
    behaviour for every sheet not yet scoped.

    `sheet_aliases` adds the aliases only this sheet reads (see
    GLOSSARY_COLUMN_ALIASES) on top of the shared map, refused on the same
    collisions.

    Args:
        df: pandas DataFrame with potentially Spanish column names

    Returns:
        DataFrame: DataFrame with normalized (English) column names
    """
    _refuse_reserved_columns(df)

    # Create a mapping for this dataframe's columns
    mapping = {**COLUMN_NAME_MAPPING, **(sheet_aliases or {})}
    rename_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if (canonical_fields is not None
                and mapping.get(col_lower) not in canonical_fields):
            continue
        if col_lower in mapping:
            rename_map[col] = mapping[col_lower]
            print(f"  [INFO] Normalized column '{col}' -> '{mapping[col_lower]}'")

    _refuse_colliding_renames(df, rename_map)

    # Rename columns if any mappings found
    if rename_map:
        df = df.rename(columns=rename_map)

    return df


class ColumnCollisionError(ValueError):
    """Two of a sheet's columns claim one canonical name."""


# Names the build writes into a record itself, which a spreadsheet must
# therefore not also write. `_metadata` is the synthetic first element
# `csv_to_json` prepends to a story's JSON to carry viewer warnings and the
# LaTeX flag; every consumer -- the shared story-steps include, four places
# in story.html, five JavaScript modules, the encryptor's sentinel harvest
# -- identifies that element by this key alone.
RESERVED_COLUMN_NAMES = frozenset({'_metadata'})


class ReservedColumnError(ValueError):
    """A spreadsheet declares a column name the build reserves for itself."""


def _refuse_reserved_columns(df):
    """Refuse a sheet that writes a name only the build is meant to write.

    A story sheet carrying a column called `_metadata` produces rows with
    that key, and every consumer reads such a row as the synthetic metadata
    element rather than as a step: the step is dropped from the published
    story and the step count drops to match, so nothing looks wrong. The
    author is told nothing.

    The name is load-bearing beyond story steps, so the refusal is not
    narrowed to the sheets the sentinel lives on. `telar/demo.py` collects
    the ids already in `objects.json` by filtering the same key, so an
    objects sheet carrying the column empties that set and the demo merge
    stops seeing the site's own objects -- it adds every demo object,
    including ones whose id the owner is already using.

    Refusing is the whole fix, and the alternatives are worse in a way
    worth recording. Hiding the collision behind a name harder to type only
    raises the cost of forging it -- whatever a spreadsheet cannot produce,
    a CSV committed by hand still can, because the decoder and the parser
    both pass bytes through. Stripping the column instead would delete the
    author's own data on a name match, and a remover is what destroys
    content when its sentinel is forged. This adds nothing to the file and
    removes nothing from it; it stops and says which column to rename.
    """
    reserved = sorted({str(col) for col in df.columns
                       if str(col).lower().strip() in RESERVED_COLUMN_NAMES})
    if not reserved:
        return

    named = ', '.join(repr(col) for col in reserved)
    raise ReservedColumnError(
        f"This spreadsheet has a column Telar uses for itself: {named}. "
        "A row in that column is read as Telar's own bookkeeping rather "
        "than as your content, so the row would disappear from the "
        "published site without any warning. Rename the column and rebuild."
    )


def _refuse_colliding_renames(df, rename_map):
    """Refuse a rename that would put two columns under one name.

    A sheet headed both `privado` and `protected`, or both `fuente` and
    `location`, leaves pandas holding two columns of the same name. Every
    consumer then reads a Series where it expects a value: `row.get('protected')`
    returns both cells, and the truth test at the far end raises
    "The truth value of a Series is ambiguous" — a message that says nothing
    about the spreadsheet the author has to fix.

    Refusing here fails just as closed and names the two columns, which is the
    only part the author can act on. There is no safe way to guess which column
    was meant: for `protected` the two answers are publish and do not publish.

    Two spellings of one header collide on the same terms. Every lookup
    downstream folds case and trims, so `Note` beside `note` is one column
    written twice and pandas holds both under one label again. Grouping the
    sheet's own columns rather than the rename map is what sees it: a caller
    that folded its headers before calling leaves two identical labels, and
    a map keyed by label collapses those into a single entry.
    """
    claimed = {}
    for col in df.columns:
        canonical = rename_map.get(col, str(col).lower().strip())
        claimed.setdefault(canonical, []).append(str(col))

    collisions = []
    for canonical, sources in sorted(claimed.items()):
        if len(sources) > 1:
            collisions.append((canonical, sorted(sources)))

    if collisions:
        detail = '; '.join(
            f"'{canonical}' is claimed by {', '.join(repr(c) for c in cols)}"
            for canonical, cols in collisions)
        raise ColumnCollisionError(
            f"Two columns in this spreadsheet mean the same thing: {detail}. "
            "Keep one of each and remove the other, then rebuild. If this "
            "site is edited in the Compositor, publish it again from there "
            "instead: a current Compositor writes one column for each, and "
            "this file is not one to edit by hand."
        )


# Column spellings a published sheet may still carry after the column itself
# was removed. They are NOT aliases: nothing renames to them and no processor
# reads them. They exist so `is_header_row` still recognises a header row that
# names one, because that check scores a row against the column vocabulary and
# a spelling missing from it drags the whole row's score down.
#
# `quoted_in_stories` and its two Spanish spellings shipped in the 1.8.0 test
# instance and in a Compositor beta between 13 and 17 September 2026, then were
# removed with the glossary acknowledgement. A four-column glossary header
# carrying one of them scores 3/4 -- below the 0.8 threshold -- so the bilingual
# Spanish row was read as a glossary term titled `titulo`. This is why
# this set can only grow: a column
# can leave the vocabulary, but a sheet already published with it cannot.
LEGACY_HEADER_SPELLINGS = frozenset({
    'quoted_in_stories',
    'citado_en_historias',
    'citada_en_historias',
})


def is_header_row(row_values, sheet_aliases=None):
    """
    Check if a row contains header names (English or Spanish).

    Args:
        row_values: List of cell values from a row
        sheet_aliases: The aliases only this sheet reads, whose names count
            as header names here too

    Returns:
        bool: True if row appears to be a header row
    """
    # Get all valid column names (English and Spanish)
    valid_names = set(COLUMN_NAME_MAPPING.keys()) | set(COLUMN_NAME_MAPPING.values())

    # Also include common column names not in the mapping
    valid_names.update(['x', 'y', 'zoom'])

    # And spellings a published sheet may carry for a column since removed.
    valid_names.update(LEGACY_HEADER_SPELLINGS)

    if sheet_aliases:
        valid_names.update(sheet_aliases.keys())
        valid_names.update(sheet_aliases.values())

    # Count how many cells match known column names
    # A blank cell is absent however the file was read. The glossary readers
    # give '' for it and `csv_to_json` gives NaN (both keep `NA` as text),
    # and counting '' as populated made the verdict depend on which reader
    # got there: a bilingual header row of three names padded with two empty
    # custom columns fell from 100% to 60% and was published as data.
    matches = 0
    total = 0
    for val in row_values:
        if pd.isna(val):
            continue
        val_lower = str(val).lower().strip()
        if not val_lower:
            continue
        total += 1
        if val_lower in valid_names:
            matches += 1

    # If 80%+ of non-empty cells are column names, it's a header row.
    # Require at least 3 non-empty cells so a sparse first data row whose two
    # populated cells happen to match column names (e.g. "object", "title") is
    # not mistaken for a header and silently dropped.
    return total >= 3 and (matches / total) >= 0.8
