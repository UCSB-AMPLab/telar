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

Version: v0.8.0-beta
"""

import pandas as pd


# Bilingual column name mapping (Spanish -> English)
# Supports bilingual story CSV headers (v0.6.0+)
COLUMN_NAME_MAPPING = {
    # Story step columns (Spanish -> English)
    'paso': 'step',
    'objeto': 'object',
    'pregunta': 'question',
    'respuesta': 'answer',
    'boton_capa1': 'layer1_button',
    'contenido_capa1': 'layer1_content',  # v0.6.3+ preferred name
    'archivo_capa1': 'layer1_content',    # backward compatibility
    'boton_capa2': 'layer2_button',
    'contenido_capa2': 'layer2_content',  # v0.6.3+ preferred name
    'archivo_capa2': 'layer2_content',    # backward compatibility
    # x, y, zoom are the same in both languages

    # English column backward compatibility (layer1_file -> layer1_content)
    'layer1_file': 'layer1_content',
    'layer2_file': 'layer2_content',

    # Objects columns (Spanish -> English) - for IIIF auto-populator support
    'id_objeto': 'object_id',
    'titulo': 'title',
    'descripcion': 'description',
    'url_fuente': 'source_url',
    'creador': 'creator',
    'periodo': 'period',
    'medio': 'medium',
    'dimensiones': 'dimensions',
    'ubicacion': 'source',  # v0.8.0: renamed from 'location' to 'source'
    'credito': 'credit',
    'miniatura': 'thumbnail',
    # v0.8.0 gallery filtering columns
    'año': 'year',
    'ano': 'year',  # without tilde
    'tipo_objeto': 'object_type',
    'temas': 'subjects',
    'materias': 'subjects',  # Dublin Core official Spanish translation
    'materia': 'subjects',
    'destacado': 'featured',
    'fuente': 'source',
    # Backward compatibility: location -> source (v0.8.0 schema change)
    'location': 'source',

    # Project columns (Spanish -> English)
    'orden': 'order',
    'id_historia': 'story_id',
    'subtitulo': 'subtitle',
    'firma': 'byline',
    'private': 'protected',
    'privada': 'protected',
    'protegida': 'protected',

    # Glossary columns (Spanish -> English)
    'id_termino': 'term_id',
    'id_término': 'term_id',
    'título': 'title',
    'definición': 'definition',
    'definicion': 'definition',
    'términos_relacionados': 'related_terms',
    'terminos_relacionados': 'related_terms',
}


def sanitize_dataframe(df):
    """
    Remove Christmas tree emoji from all string fields in dataframe.
    This prevents accidental Christmas Tree Mode triggering from user data.

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


def normalize_column_names(df):
    """
    Normalize column names to English using bilingual mapping.
    Supports both English and Spanish column headers (v0.6.0+).

    Args:
        df: pandas DataFrame with potentially Spanish column names

    Returns:
        DataFrame: DataFrame with normalized (English) column names
    """
    # Create a mapping for this dataframe's columns
    rename_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in COLUMN_NAME_MAPPING:
            rename_map[col] = COLUMN_NAME_MAPPING[col_lower]
            print(f"  [INFO] Normalized column '{col}' -> '{COLUMN_NAME_MAPPING[col_lower]}'")

    # Rename columns if any mappings found
    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def is_header_row(row_values):
    """
    Check if a row contains header names (English or Spanish).

    Args:
        row_values: List of cell values from a row

    Returns:
        bool: True if row appears to be a header row
    """
    # Get all valid column names (English and Spanish)
    valid_names = set(COLUMN_NAME_MAPPING.keys()) | set(COLUMN_NAME_MAPPING.values())

    # Also include common column names not in the mapping
    valid_names.update(['x', 'y', 'zoom', 'order', 'story_id', 'title', 'subtitle',
                        'byline', 'object_id', 'description', 'source_url', 'creator',
                        'period', 'medium', 'dimensions', 'location', 'source', 'credit',
                        'thumbnail', 'year', 'object_type', 'subjects', 'featured',
                        'protected'])

    # Count how many cells match known column names
    matches = 0
    total = 0
    for val in row_values:
        if pd.notna(val):
            val_lower = str(val).lower().strip()
            total += 1
            if val_lower in valid_names:
                matches += 1

    # If 80%+ of non-empty cells are column names, it's a header row
    return total > 0 and (matches / total) >= 0.8
