"""
Unit Tests for Column Processing Functions

This module tests the bilingual column name handling introduced in v0.6.0,
which allows users to write CSV headers in either English or Spanish. It also
tests the header row detection logic that enables dual-language header rows
in a single CSV file.

The column mapping is central to Telar's internationalization strategy —
it allows Spanish-speaking users to work entirely in their language while
the build system normalizes everything to English internally.

Version: v1.8.0
"""

import sys
import os
import pytest
import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import (
    normalize_column_names,
    is_header_row,
    COLUMN_NAME_MAPPING,
)
from telar.csv_utils import (
    RESERVED_COLUMN_NAMES, ColumnCollisionError, ReservedColumnError)


class TestNormalizeColumnNames:
    """Tests for normalize_column_names function."""

    def test_normalizes_spanish_story_columns(self):
        """Spanish story column names should be converted to English."""
        df = pd.DataFrame({
            'paso': [1, 2],
            'objeto': ['obj-1', 'obj-2'],
            'pregunta': ['Q1', 'Q2'],
            'respuesta': ['A1', 'A2'],
        })
        result = normalize_column_names(df)
        assert 'step' in result.columns
        assert 'object' in result.columns
        assert 'question' in result.columns
        assert 'answer' in result.columns

    def test_normalizes_spanish_layer_columns(self):
        """Spanish layer column names should be normalized."""
        df = pd.DataFrame({
            'boton_capa1': ['Learn more'],
            'contenido_capa1': ['Content'],
            'boton_capa2': ['Go deeper'],
            'contenido_capa2': ['More content'],
        })
        result = normalize_column_names(df)
        assert 'layer1_button' in result.columns
        assert 'layer1_content' in result.columns
        assert 'layer2_button' in result.columns
        assert 'layer2_content' in result.columns

    def test_backward_compatibility_layer_file(self):
        """Legacy layer1_file columns should map to layer1_content."""
        df = pd.DataFrame({
            'layer1_file': ['path/to/file.md'],
            'layer2_file': ['path/to/file2.md'],
        })
        result = normalize_column_names(df)
        assert 'layer1_content' in result.columns
        assert 'layer2_content' in result.columns

    def test_backward_compatibility_archivo_capa(self):
        """Legacy archivo_capa columns should map to layer_content."""
        df = pd.DataFrame({
            'archivo_capa1': ['archivo.md'],
            'archivo_capa2': ['archivo2.md'],
        })
        result = normalize_column_names(df)
        assert 'layer1_content' in result.columns
        assert 'layer2_content' in result.columns

    def test_normalizes_spanish_object_columns(self):
        """Spanish object column names should be converted to English."""
        df = pd.DataFrame({
            'id_objeto': ['obj-1'],
            'titulo': ['Title'],
            'descripcion': ['Description'],
            'creador': ['Artist'],
        })
        result = normalize_column_names(df)
        assert 'object_id' in result.columns
        assert 'title' in result.columns
        assert 'description' in result.columns
        assert 'creator' in result.columns

    def test_normalizes_spanish_project_columns(self):
        """Spanish project column names should be converted to English."""
        df = pd.DataFrame({
            'orden': [1, 2],
            'id_historia': ['story-1', 'story-2'],
            'titulo': ['Title 1', 'Title 2'],
            'subtitulo': ['Sub 1', 'Sub 2'],
            'firma': ['By Author', 'By Author'],
        })
        result = normalize_column_names(df)
        assert 'order' in result.columns
        assert 'story_id' in result.columns
        assert 'title' in result.columns
        assert 'subtitle' in result.columns
        assert 'byline' in result.columns

    def test_preserves_english_columns(self):
        """English column names should remain unchanged."""
        df = pd.DataFrame({
            'step': [1],
            'object': ['obj-1'],
            'question': ['Q1'],
        })
        result = normalize_column_names(df)
        assert 'step' in result.columns
        assert 'object' in result.columns
        assert 'question' in result.columns

    def test_preserves_unknown_columns(self):
        """Unknown column names should remain unchanged."""
        df = pd.DataFrame({
            'custom_column': ['value'],
            'another_custom': ['value2'],
        })
        result = normalize_column_names(df)
        assert 'custom_column' in result.columns
        assert 'another_custom' in result.columns

    def test_case_insensitive_matching(self):
        """Column name matching should be case-insensitive."""
        df = pd.DataFrame({
            'PASO': [1],
            'Objeto': ['obj-1'],
            'PREGUNTA': ['Q1'],
        })
        result = normalize_column_names(df)
        assert 'step' in result.columns
        assert 'object' in result.columns
        assert 'question' in result.columns


class TestIsHeaderRow:
    """Tests for is_header_row function."""

    def test_detects_english_header_row(self):
        """Should detect English column names as header row."""
        row = ['step', 'object', 'question', 'answer', 'x', 'y', 'zoom']
        assert is_header_row(row) is True

    def test_detects_spanish_header_row(self):
        """Should detect Spanish column names as header row."""
        row = ['paso', 'objeto', 'pregunta', 'respuesta', 'x', 'y', 'zoom']
        assert is_header_row(row) is True

    def test_rejects_data_row(self):
        """Should reject rows with data values."""
        row = [1, 'textile-001', 'What is this?', 'A textile.', 0.5, 0.5, 1.0]
        assert is_header_row(row) is False

    def test_handles_mixed_case(self):
        """Should handle mixed case column names."""
        row = ['Step', 'OBJECT', 'Question', 'answer']
        assert is_header_row(row) is True

    def test_handles_partial_headers(self):
        """Should detect row as header if 80%+ cells are column names."""
        row = ['step', 'object', 'question', 'unknown_col', 'x']
        # 4 of 5 are valid (80%), so this should pass
        assert is_header_row(row) is True

    def test_rejects_low_match_rate(self):
        """Should reject row if less than 80% are column names."""
        row = ['value1', 'value2', 'step', 'value3', 'value4']
        # Only 1 of 5 is valid (20%), should fail
        assert is_header_row(row) is False

    def test_handles_nan_values(self):
        """Should ignore NaN values in calculation."""
        row = ['step', 'object', None, None, 'question']
        # 3 valid of 3 non-empty = 100%
        assert is_header_row(row) is True

    def test_handles_completely_empty_row(self):
        """Should return False for completely empty row."""
        row = [None, None, '', '']
        assert is_header_row(row) is False


class TestABlankCellIsAbsentHoweverTheFileWasRead:
    """The verdict must not depend on how pandas was told to read blanks.

    A sheet read with `keep_default_na=False` — which the glossary and
    object readers do, so an author's term titled `NA` survives — hands this
    function `''` where an inferring read hands it NaN. Counting `''` as a
    populated cell drops a bilingual header row of three names and two blank
    custom columns from 100% to 60%, under the threshold, and the row of
    Spanish aliases is then published as a glossary term.
    """

    HEADER_WITH_BLANK_TAIL = ['id_termino', 'titulo', 'definicion']

    @pytest.mark.parametrize('blank', [None, '', '   ', '\t'])
    def test_a_header_row_padded_with_blanks_is_still_a_header(self, blank):
        row = self.HEADER_WITH_BLANK_TAIL + [blank, blank]

        assert is_header_row(row) is True

    @pytest.mark.parametrize('blank', [None, '', '   '])
    def test_a_data_row_padded_with_blanks_is_still_data(self, blank):
        row = ['encomienda', 'Encomienda', 'A grant of labour.', blank, blank]

        assert is_header_row(row) is False

    # A column can leave the vocabulary; a sheet already published with it
    # cannot. `quoted_in_stories` and its two Spanish spellings shipped for
    # four days in September 2026 and were removed with the glossary
    # acknowledgement, which dropped a four-column header to 3/4 -- under the
    # 0.8 threshold -- so the bilingual Spanish row published as a term.
    @pytest.mark.parametrize('spelling', [
        'quoted_in_stories', 'citado_en_historias', 'citada_en_historias'])
    def test_a_header_naming_a_removed_column_is_still_a_header(self, spelling):
        row = ['id_termino', 'titulo', 'definicion', spelling]

        assert is_header_row(row) is True

    def test_a_term_row_is_not_rescued_by_a_legacy_spelling(self):
        """The spellings widen header detection, never data detection."""
        row = ['encomienda', 'Encomienda', 'Un sistema de trabajo.',
               'otra-historia']

        assert is_header_row(row) is False

    def test_both_readings_of_one_row_agree(self):
        """The same sheet, read either way, gets the same answer."""
        inferred = self.HEADER_WITH_BLANK_TAIL + [None, None]
        literal = self.HEADER_WITH_BLANK_TAIL + ['', '']

        assert is_header_row(inferred) is is_header_row(literal)

    @pytest.mark.parametrize('row', [
        [],
        [None, None, None, None],
        ['', '', '', ''],
        ['  ', None, '', '\n'],
    ])
    def test_a_row_of_nothing_is_not_a_header(self, row):
        """No populated cells is not a header, as it was before."""
        assert is_header_row(row) is False


class TestTheAliasMapIsPinned:
    """The alias map is a contract, not an internal detail.

    A consumer outside this repository reads it: the Compositor accepts the
    same headers and diffs its own registry against this one. A silent
    addition here is a silent divergence there, and a silent removal is a
    column a site's spreadsheet stops being understood by — neither of which
    shows up until someone's build is wrong.

    So the whole map is written out. Changing it means changing this literal,
    in the same commit, where a reviewer sees it.
    """

    EXPECTED = {
        'paso': 'step',
        'objeto': 'object',
        'pregunta': 'question',
        'respuesta': 'answer',
        'boton_capa1': 'layer1_button',
        'boton1': 'layer1_button',
        'contenido_capa1': 'layer1_content',
        'contenido1': 'layer1_content',
        'archivo_capa1': 'layer1_content',
        'boton_capa2': 'layer2_button',
        'boton2': 'layer2_button',
        'contenido_capa2': 'layer2_content',
        'contenido2': 'layer2_content',
        'archivo_capa2': 'layer2_content',
        'inicio_clip': 'clip_start',
        'fin_clip': 'clip_end',
        'bucle': 'loop',
        'texto_alt': 'alt_text',
        'pagina': 'page',
        'página': 'page',
        'page': 'page',
        'layer1_file': 'layer1_content',
        'layer2_file': 'layer2_content',
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
        'año': 'year',
        'ano': 'year',
        'tipo_objeto': 'medium',
        'object_type': 'medium',
        'medium_genre': 'medium',
        'medio_genero': 'medium',
        'temas': 'subjects',
        'materias': 'subjects',
        'materia': 'subjects',
        'destacado': 'featured',
        'fuente': 'source',
        'location': 'source',
        'orden': 'order',
        'id_historia': 'story_id',
        'subtitulo': 'subtitle',
        'subtítulo': 'subtitle',
        'firma': 'byline',
        'private': 'protected',
        'privada': 'protected',
        'privado': 'protected',
        'protegida': 'protected',
        'protegido': 'protected',
        'mostrar_secciones': 'show_sections',
        'id_termino': 'term_id',
        'id_término': 'term_id',
        'título': 'title',
        'definición': 'definition',
        'definicion': 'definition',
        'términos_relacionados': 'related_terms',
        'terminos_relacionados': 'related_terms',
    }

    def test_the_map_is_exactly_this(self):
        assert COLUMN_NAME_MAPPING == self.EXPECTED

    def test_no_canonical_name_maps_to_itself(self):
        """It is a rename table, so a canonical name needs no entry.

        `page` is the one deliberate exception, present to normalise the
        casing Google Sheets can produce.
        """
        self_referring = {key for key, value in COLUMN_NAME_MAPPING.items()
                          if key == value}

        assert self_referring == {'page'}


class TestAProtectedStoryIsRecognisedInEitherGender:
    """A header this map does not carry publishes the story in the clear.

    `project.py` reads `row.get('protected', '')`. A column the map does not
    rename never becomes `protected`, so the story is never marked, so it
    publishes as an ordinary story. The interlock that refuses such a build
    acts on stories already recognised as protected, so it cannot fire
    either: the failure is upstream of every guard built for it.
    """

    @pytest.mark.parametrize('header', ['private', 'privada', 'privado',
                                        'protegida', 'protegido'])
    def test_it_normalises_to_protected(self, header):
        df = pd.DataFrame({'orden': [1], 'titulo': ['Una historia'],
                           header: ['yes']})

        assert 'protected' in normalize_column_names(df).columns

    def test_protected_itself_needs_no_entry(self):
        """The canonical spelling passes through untouched."""
        df = pd.DataFrame({'orden': [1], 'protected': ['yes']})

        assert 'protected' not in COLUMN_NAME_MAPPING
        assert 'protected' in normalize_column_names(df).columns

    @pytest.mark.parametrize('header', ['privado', 'protegido'])
    def test_the_masculine_forms_read_as_a_header_row(self, header):
        """The bilingual second row has to be skipped, not read as a story.

        `is_header_row` scores a row against the known column names, so a
        spelling missing from the map lowers the score of every row carrying
        it and can drop a real header row under the threshold.
        """
        row = ['orden', 'titulo', 'subtitulo', header]

        assert is_header_row(row) is True


class TestTwoColumnsCannotClaimOneName:
    """Renaming an alias onto a column that already exists loses a value.

    pandas keeps both, so `row.get('protected')` returns a Series and the
    truth test at the far end raises "The truth value of a Series is
    ambiguous" — which says nothing about the spreadsheet the author has to
    fix, and does not say which of the two columns the build read.

    There is no safe guess available. For `protected` the two answers are
    publish and do not publish.
    """

    @pytest.mark.parametrize('columns', [
        ['orden', 'titulo', 'privado', 'protected'],
        ['orden', 'titulo', 'protected', 'privado'],
        ['orden', 'titulo', 'protegido', 'protected'],
    ])
    def test_an_alias_beside_the_canonical_name_is_refused(self, columns):
        df = pd.DataFrame([[1, 'X', 'yes', '']], columns=columns)

        with pytest.raises(ColumnCollisionError):
            normalize_column_names(df)

    def test_two_aliases_of_one_name_are_refused(self):
        df = pd.DataFrame([[1, 'X', 'yes', '']],
                          columns=['orden', 'titulo', 'privado', 'privada'])

        with pytest.raises(ColumnCollisionError):
            normalize_column_names(df)

    def test_the_message_names_both_columns(self):
        """The author can only act on the column names, so they are the message."""
        df = pd.DataFrame([[1, 'X', 'yes', '']],
                          columns=['orden', 'titulo', 'privado', 'protected'])

        with pytest.raises(ColumnCollisionError) as raised:
            normalize_column_names(df)

        assert 'privado' in str(raised.value)
        assert 'protected' in str(raised.value)

    def test_the_message_names_the_way_out_of_a_published_sheet(self):
        """A Compositor site's owner is looking at a file they never edit.

        An objects sheet written to the documented shape carries
        `medium_genre` as a column and `medium` in the extras tail, so the
        refusal lands on a file the Compositor wrote. Telling that author
        to remove a column is telling them to hand-edit generated output;
        the remedy that fits is to publish the site again.
        """
        df = pd.DataFrame([[1, 'X', 'oil', 'oil']],
                          columns=['id_objeto', 'titulo', 'medium_genre',
                                   'medium'])

        with pytest.raises(ColumnCollisionError) as raised:
            normalize_column_names(df)

        message = str(raised.value)
        assert 'Compositor' in message
        assert 'publish it again' in message
        # Not a claim that the exporter fix has reached them yet.
        assert 'a current Compositor' in message

    def test_an_ordinary_sheet_is_untouched(self):
        df = pd.DataFrame([[1, 'X', 'yes']],
                          columns=['orden', 'titulo', 'privado'])

        assert list(normalize_column_names(df).columns) == [
            'order', 'title', 'protected']

    def test_a_sheet_with_no_aliases_at_all_is_untouched(self):
        df = pd.DataFrame([[1, 'X']], columns=['order', 'title'])

        assert list(normalize_column_names(df).columns) == ['order', 'title']


class TestCaseAndSpacingDoNotGetPastTheCollisionRefusal:
    """Two spellings of one header are one header.

    Every lookup downstream reads a header case-folded and trimmed, so
    `Note` beside `note` is the same column written twice. pandas keeps both
    labels, `row.get('note')` returns a Series, and a caller that lowercased
    its headers first left the two indistinguishable before the refusal could
    see them. The refusal folds the spellings itself, so it holds whatever
    the caller did to the headers on the way in.
    """

    @pytest.mark.parametrize('columns', [
        ['term_id', 'Note', 'note'],
        ['term_id', 'note', 'NOTE'],
        ['term_id', 'note', ' note '],
        ['term_id', 'Title', 'title'],
    ])
    def test_two_spellings_of_one_header_are_refused(self, columns):
        df = pd.DataFrame([['a'] * len(columns)], columns=columns)

        with pytest.raises(ColumnCollisionError):
            normalize_column_names(df)

    def test_the_message_names_both_spellings(self):
        df = pd.DataFrame([['a', 'b', 'c']], columns=['term_id', 'Note', 'note'])

        with pytest.raises(ColumnCollisionError) as raised:
            normalize_column_names(df)

        message = str(raised.value)
        assert "'Note'" in message
        assert "'note'" in message

    @pytest.mark.parametrize('columns', [
        ['protected', 'Protegido'],
        ['Protected', 'privado'],
        ['PRIVADO', 'protegido'],
    ])
    def test_an_alias_still_collides_however_it_is_spelled(self, columns):
        df = pd.DataFrame([['a'] * len(columns)], columns=columns)

        with pytest.raises(ColumnCollisionError):
            normalize_column_names(df)

    @pytest.mark.parametrize('columns', [
        ['Title'],
        ['Title', 'Note'],
        ['term_id', 'Title', 'definition'],
    ])
    def test_one_spelling_of_each_header_is_untouched(self, columns):
        df = pd.DataFrame([['a'] * len(columns)], columns=columns)

        assert list(normalize_column_names(df).columns) == columns


class TestASheetCannotWriteTelarsOwnBookkeeping:
    """`_metadata` is the one key the build writes into a record itself.

    `csv_to_json` prepends a synthetic first element carrying viewer
    warnings and the LaTeX flag, and every consumer finds it by that key
    alone — the shared story-steps include, four places in story.html, five
    JavaScript modules, and the encryptor's sentinel harvest. A sheet that
    declares the same column produces a row every one of them skips: the
    step vanishes from the published story, the step count drops to match,
    and nothing looks wrong.
    """

    def _frame(self, header):
        return pd.DataFrame(columns=header.split(','))

    def test_a_reserved_column_is_refused(self):
        with pytest.raises(ReservedColumnError) as raised:
            normalize_column_names(self._frame('step,title,_metadata'))

        assert '_metadata' in str(raised.value)

    def test_the_refusal_names_the_column_to_rename(self):
        """The only part of this an author can act on."""
        with pytest.raises(ReservedColumnError) as raised:
            normalize_column_names(self._frame('step,title,_metadata'))

        assert 'Rename the column' in str(raised.value)

    @pytest.mark.parametrize('header', ['step,_METADATA', 'step, _metadata ',
                                        'step,_Metadata'])
    def test_case_and_spacing_do_not_get_past_it(self, header):
        with pytest.raises(ReservedColumnError):
            normalize_column_names(self._frame(header))

    def test_an_ordinary_sheet_is_untouched(self):
        frame = normalize_column_names(self._frame('step,title,notes,metadata'))

        assert list(frame.columns) == ['step', 'title', 'notes', 'metadata']

    def test_the_reserved_set_is_pinned(self):
        """Spelled out rather than read from the module.

        A test parametrised over the set it is pinning passes when the set
        is emptied, because zero entries make zero cases.
        """
        assert set(RESERVED_COLUMN_NAMES) == {'_metadata'}

    def test_nothing_is_added_to_the_sheet_or_taken_out_of_it(self):
        """The fix refuses; it does not insert a marker or strip a column.

        A marker has to be removed again later, and the remover is what
        deletes an author's line when the marker is forged. A stripper
        deletes the author's own column on a name match. Refusing leaves
        the file exactly as written and says what to change.
        """
        before = self._frame('step,title,notes')
        after = normalize_column_names(before)

        assert list(after.columns) == list(before.columns)
