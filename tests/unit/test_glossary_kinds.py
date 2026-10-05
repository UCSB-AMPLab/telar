"""
Unit Tests for Glossary Entry Kinds

A glossary entry is a key term or a primary source. The kinds are one list,
`_data/glossary_kinds.yml`, which the build reads to resolve what an author
wrote and the layouts read to label the panel and group the glossary page.
These tests hold the build's half: the values it accepts, the column that
carries them in each language, the front matter of a legacy markdown file,
the demo bundle, and the id written into each entry's page.

`tipo` is a common word, so the Spanish column name is renamed on the
glossary sheet only: an objects or story sheet with a `tipo` column keeps
it as the author wrote it.

Version: v1.8.0
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.csv_utils import (ColumnCollisionError, GLOSSARY_COLUMN_ALIASES,
                             OBJECT_FIELDS, is_header_row,
                             normalize_column_names)
from telar.glossary import load_glossary_terms
from telar.glossary_kinds import (_fold, all_kinds, default_kind,
                                  glossary_kinds, kind_text, resolve_kind,
                                  site_kinds)
from telar.glossary_pages import generate_glossary

REPO = Path(__file__).resolve().parents[2]

# The rulings' tables (docs/framework/releases/1.8/1.8.0/design/
# tel-451-glossary-kinds.md), English then Spanish.
ENTITY_VALUES = [
    'entity', 'entities', 'person', 'people', 'character', 'characters',
    'group', 'groups', 'organization', 'organisation', 'organizations',
    'institution', 'institutions', 'community', 'communities', 'family',
    'families', 'corporate body', 'corporate bodies', 'agent', 'agents',
    'entidad', 'entidades', 'persona', 'personas', 'personaje', 'personajes',
    'grupo', 'grupos', 'organización', 'organizaciones', 'institución',
    'instituciones', 'colectivo', 'colectivos', 'comunidad', 'comunidades',
    'familia', 'familias', 'entidad corporativa', 'entidades corporativas',
    'agente', 'agentes',
]
PLACE_VALUES = [
    'place', 'places', 'site', 'sites', 'territory', 'territories',
    'lugar', 'lugares', 'sitio', 'sitios', 'territorio', 'territorios',
]
LANGUAGES = REPO / '_data' / 'languages'


def _catalogue(code):
    return yaml.safe_load((LANGUAGES / f'{code}.yml').read_text(encoding='utf-8'))


def _resolve(catalogue, key_path):
    node = catalogue
    for part in key_path.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class TestTheValuesAnAuthorMayWrite:

    @pytest.mark.parametrize('value', [
        'term', 'término', 'termino', 'key term', 'palabra clave',
        'Term', 'TÉRMINO', 'Key Term', 'Palabra Clave', '  key   term ',
        'key_term', 'palabra_clave',
    ])
    def test_these_are_a_term(self, value, capsys):
        # A term is also what an unknown value falls back to, so the absence
        # of the warning is what shows the value was recognised.
        assert resolve_kind(value) == 'term'
        assert '[WARN]' not in capsys.readouterr().out

    @pytest.mark.parametrize('value', [
        'source', 'fuente', 'primary source', 'fuente primaria',
        'fuente_primaria', 'primary_source', 'Source', 'FUENTE',
        'Primary Source', 'Fuente Primaria', 'fuente-primaria',
    ])
    def test_these_are_a_source(self, value, capsys):
        assert resolve_kind(value) == 'source'
        assert '[WARN]' not in capsys.readouterr().out

    @pytest.mark.parametrize('value', ['', '   ', None, float('nan')])
    def test_a_blank_kind_is_a_term(self, value, capsys):
        assert resolve_kind(value) == 'term'
        assert '[WARN]' not in capsys.readouterr().out

    @pytest.mark.parametrize('value', ENTITY_VALUES + [
        'Entidad Corporativa', 'CORPORATE_BODY', 'Organizacion', 'institucion',
        'Personajes', 'AGENTES'])
    def test_these_are_an_entity(self, value, capsys):
        assert resolve_kind(value) == 'entity'
        assert '[WARN]' not in capsys.readouterr().out

    @pytest.mark.parametrize('value', PLACE_VALUES + ['Territorios', 'LUGAR', 'Sites'])
    def test_these_are_a_place(self, value, capsys):
        assert resolve_kind(value) == 'place'
        assert '[WARN]' not in capsys.readouterr().out

    @pytest.mark.parametrize('value', ['pueblo', 'pueblos', 'pueblo indígena',
                                       'pueblos indígenas', 'town', 'work', 'obra'])
    def test_these_are_no_kind(self, value, capsys):
        """`pueblo` reads as a town in Colombia, and works have no kind."""
        assert resolve_kind(value) == 'term'
        assert '[WARN]' in capsys.readouterr().out

    def test_an_unknown_kind_is_a_term_and_says_so(self, capsys):
        assert resolve_kind('species', where="glossary entry 'quercus'") == 'term'

        out = capsys.readouterr().out
        assert '[WARN]' in out
        assert "'species'" in out
        assert "glossary entry 'quercus'" in out
        # The way out: the values the build does accept.
        for kind_id in ('term', 'source', 'entity', 'place'):
            assert kind_id in out


class TestTheRegistry:

    def test_it_holds_the_core_kinds_in_the_page_order(self):
        assert [kind['id'] for kind in glossary_kinds()] == [
            'term', 'source', 'entity', 'place']

    def test_the_entity_and_place_values_are_the_rulings_lists(self):
        """The design doc's tables, English and Spanish, and nothing else."""
        values = {kind['id']: kind['values'] for kind in glossary_kinds()}
        assert values['entity'] == ENTITY_VALUES
        assert values['place'] == PLACE_VALUES

    def test_only_the_source_kind_names_an_intro(self):
        """The page says it has sources, and no other kind changes the intro."""
        assert {kind['id']: kind.get('intro') for kind in glossary_kinds()} == {
            'term': None, 'source': 'pages.glossary_intro_with_sources',
            'entity': None, 'place': None}

    def test_exactly_one_kind_is_the_default_and_it_is_term(self):
        defaults = [kind for kind in glossary_kinds() if kind.get('default')]
        assert len(defaults) == 1
        assert default_kind() == 'term'

    def test_no_value_names_two_kinds(self):
        seen = {}
        for kind in glossary_kinds():
            for value in [kind['id']] + list(kind['values']):
                other = seen.setdefault(_fold(value), kind['id'])
                assert other == kind['id'], value

    @pytest.mark.parametrize('code', ['en', 'es'])
    @pytest.mark.parametrize('field', ['panel_label', 'section_heading', 'intro'])
    def test_every_key_it_names_is_a_two_part_string_key(self, code, field):
        """The layouts read these as `lang[section][key]`, so a key of any
        other depth resolves to nothing on the page."""
        catalogue = _catalogue(code)
        for kind in glossary_kinds():
            key = kind.get(field)
            if key is None and field == 'intro':
                continue
            assert len(key.split('.')) == 2, key
            assert isinstance(_resolve(catalogue, key), str), f'{code}: {key}'


class TestTheSpanishColumnNameIsTheGlossarysOnly:

    def test_the_glossary_sheet_renames_tipo(self):
        df = pd.DataFrame({'id_termino': ['x'], 'titulo': ['X'], 'tipo': ['fuente']})

        result = normalize_column_names(df, sheet_aliases=GLOSSARY_COLUMN_ALIASES)

        assert 'kind' in result.columns
        assert 'tipo' not in result.columns

    def test_a_story_sheet_keeps_tipo(self):
        df = pd.DataFrame({'paso': [1], 'objeto': ['x'], 'tipo': ['carta']})

        assert 'tipo' in normalize_column_names(df).columns

    def test_an_objects_sheet_keeps_tipo(self):
        df = pd.DataFrame({'id_objeto': ['x'], 'titulo': ['X'], 'tipo': ['carta']})

        result = normalize_column_names(df, OBJECT_FIELDS)

        assert 'tipo' in result.columns
        assert 'kind' not in result.columns

    def test_kind_beside_tipo_on_the_glossary_is_refused(self):
        df = pd.DataFrame({'term_id': ['x'], 'title': ['X'],
                           'kind': ['source'], 'tipo': ['fuente']})

        with pytest.raises(ColumnCollisionError):
            normalize_column_names(df, sheet_aliases=GLOSSARY_COLUMN_ALIASES)

    def test_the_link_map_refuses_it_too(self, tmp_path, monkeypatch):
        """The link map and the page generator read the same file and refuse
        the same sheets."""
        monkeypatch.chdir(tmp_path)
        folder = tmp_path / 'telar-content' / 'spreadsheets'
        folder.mkdir(parents=True)
        (folder / 'glossary.csv').write_text(
            'term_id,title,definition,kind,tipo\nx,X,d,source,fuente\n',
            encoding='utf-8')

        with pytest.raises(ColumnCollisionError):
            load_glossary_terms()

    def test_the_spanish_header_row_of_the_template_is_a_header_row(self):
        """The template's second row names each column in Spanish. With four
        columns, one unrecognised name puts it at 3/4, under the threshold,
        and the row is published as a term titled `titulo`."""
        row = ['id_término', 'titulo', 'definición', 'tipo']

        assert is_header_row(row, sheet_aliases=GLOSSARY_COLUMN_ALIASES) is True

    def test_the_english_header_names_count_as_well(self):
        row = ['term_id', 'title', 'definition', 'kind']

        assert is_header_row(row, sheet_aliases=GLOSSARY_COLUMN_ALIASES) is True


def _site(tmp_path, monkeypatch, csv_text=None, name='glossary.csv'):
    monkeypatch.chdir(tmp_path)
    sheets = tmp_path / 'telar-content' / 'spreadsheets'
    sheets.mkdir(parents=True)
    if csv_text is not None:
        (sheets / name).write_text(csv_text, encoding='utf-8')
    (tmp_path / '_data').mkdir()
    return tmp_path / '_jekyll-files' / '_glossary'


def _front_matter(page_path):
    text = page_path.read_text(encoding='utf-8')
    return yaml.safe_load(text.split('---\n')[1])


class TestTheSheetColumnReachesTheEntrysPage:

    def test_each_entry_carries_its_kind(self, tmp_path, monkeypatch):
        out = _site(tmp_path, monkeypatch,
                    'term_id,title,definition,kind\n'
                    'loom,Loom,A frame.,\n'
                    'letter,Letter,A letter.,Primary source\n'
                    'map,Map,A map.,término\n')

        generate_glossary()

        assert _front_matter(out / 'loom.md')['glossary_kind'] == 'term'
        assert _front_matter(out / 'letter.md')['glossary_kind'] == 'source'
        assert _front_matter(out / 'map.md')['glossary_kind'] == 'term'

    def test_a_sheet_without_the_column_is_all_terms(self, tmp_path, monkeypatch):
        out = _site(tmp_path, monkeypatch,
                    'term_id,title,definition\nloom,Loom,A frame.\n')

        generate_glossary()

        assert _front_matter(out / 'loom.md')['glossary_kind'] == 'term'

    def test_the_spanish_sheet_with_its_instruction_rows(self, tmp_path, monkeypatch):
        """The template's shape: an English header, the Spanish header as a
        second row, and two instruction rows."""
        out = _site(tmp_path, monkeypatch,
                    'id_término,titulo,definición,tipo\n'
                    'term_id,title,definition,kind\n'
                    '# id,# title,# definition,# Optional.\n'
                    '# id,# título,# definición,# Opcional.\n'
                    'carta,Carta,Una carta.,fuente\n')

        generate_glossary()

        assert sorted(p.name for p in out.glob('*.md')) == ['carta.md']
        assert _front_matter(out / 'carta.md')['glossary_kind'] == 'source'

    def test_an_unknown_kind_is_a_term_and_the_build_says_which_entry(
            self, tmp_path, monkeypatch, capsys):
        out = _site(tmp_path, monkeypatch,
                    'term_id,title,definition,kind\nquercus,Quercus,An oak.,species\n')

        generate_glossary()

        assert _front_matter(out / 'quercus.md')['glossary_kind'] == 'term'
        printed = capsys.readouterr().out
        assert '[WARN]' in printed and 'quercus' in printed and "'species'" in printed


class TestLegacyMarkdownFrontMatter:

    def _md_site(self, tmp_path, monkeypatch, files):
        out = _site(tmp_path, monkeypatch)
        texts = tmp_path / 'telar-content' / 'texts' / 'glossary'
        texts.mkdir(parents=True)
        for name, text in files.items():
            (texts / name).write_text(text, encoding='utf-8')
        return out

    @pytest.mark.parametrize('line, expected', [
        ('kind: source', 'source'),
        ('tipo: fuente primaria', 'source'),
        ('Kind: "Primary source"', 'source'),
        ("tipo: 'término'", 'term'),
        ('', 'term'),
    ])
    def test_kind_or_tipo_is_read(self, tmp_path, monkeypatch, line, expected):
        out = self._md_site(tmp_path, monkeypatch, {
            'carta.md': f'---\nterm_id: carta\ntitle: "Carta"\n{line}\n---\n\nUna carta.\n'})

        generate_glossary()

        assert _front_matter(out / 'carta.md')['glossary_kind'] == expected

    def test_an_unknown_kind_warns(self, tmp_path, monkeypatch, capsys):
        out = self._md_site(tmp_path, monkeypatch, {
            'carta.md': '---\nterm_id: carta\ntitle: Carta\nkind: letter\n---\n\nUna carta.\n'})

        generate_glossary()

        assert _front_matter(out / 'carta.md')['glossary_kind'] == 'term'
        assert "[WARN]" in capsys.readouterr().out


class TestDemoTerms:

    def _demo_site(self, tmp_path, monkeypatch, terms):
        out = _site(tmp_path, monkeypatch)
        (tmp_path / '_data' / 'demo-glossary.json').write_text(
            json.dumps(terms), encoding='utf-8')
        return out

    def test_a_demo_term_without_a_kind_is_a_term(self, tmp_path, monkeypatch):
        out = self._demo_site(tmp_path, monkeypatch,
                              [{'term_id': 'viewer', 'title': 'Viewer', 'content': 'x'}])

        generate_glossary()

        assert _front_matter(out / 'viewer.md')['glossary_kind'] == 'term'

    def test_a_demo_term_keeps_the_kind_its_bundle_gives(self, tmp_path, monkeypatch):
        out = self._demo_site(tmp_path, monkeypatch,
                              [{'term_id': 'carta', 'title': 'Carta',
                                'content': 'x', 'kind': 'fuente'}])

        generate_glossary()

        assert _front_matter(out / 'carta.md')['glossary_kind'] == 'source'

    def test_the_bundle_writer_carries_a_kind_only_where_there_is_one(
            self, tmp_path, monkeypatch):
        from telar.demo import _write_demo_glossary
        monkeypatch.chdir(tmp_path)
        (tmp_path / '_data').mkdir()

        _write_demo_glossary({'glossary': {
            'viewer': {'term': 'Viewer', 'content': 'x'},
            'carta': {'term': 'Carta', 'content': 'y', 'kind': 'source'},
        }})

        written = {t['term_id']: t for t in json.loads(
            (tmp_path / '_data' / 'demo-glossary.json').read_text(encoding='utf-8'))}
        assert 'kind' not in written['viewer']
        assert written['carta']['kind'] == 'source'


SPECIES = {'id': 'species', 'label': 'Species', 'heading': 'Species',
           'values': ['taxon', 'especie']}


def _config_site(tmp_path, monkeypatch, kinds, csv_rows=''):
    """A site whose _config.yml declares these glossary kinds."""
    out = _site(tmp_path, monkeypatch,
                'term_id,title,definition,kind\n' + csv_rows if csv_rows else None)
    (tmp_path / '_config.yml').write_text(
        yaml.safe_dump({'telar_language': 'en', 'glossary': {'kinds': kinds}},
                       allow_unicode=True), encoding='utf-8')
    return out


class TestTheSitesOwnKinds:

    def test_a_site_kind_follows_the_core_kinds(self, tmp_path, monkeypatch):
        _config_site(tmp_path, monkeypatch, [SPECIES, {'id': 'ship', 'label': 'Ship',
                                                       'heading': 'Ships'}])

        assert [k['id'] for k in all_kinds()] == [
            'term', 'source', 'entity', 'place', 'species', 'ship']

    @pytest.mark.parametrize('value', ['species', 'Species', 'taxon', 'ESPECIE'])
    def test_its_id_and_values_name_it(self, tmp_path, monkeypatch, value, capsys):
        _config_site(tmp_path, monkeypatch, [SPECIES])

        assert resolve_kind(value) == 'species'
        assert '[WARN]' not in capsys.readouterr().out

    def test_without_values_its_id_still_names_it(self, tmp_path, monkeypatch):
        _config_site(tmp_path, monkeypatch, [{'id': 'ship', 'label': 'Ship',
                                              'heading': 'Ships'}])

        assert resolve_kind('ship') == 'ship'

    def test_a_site_without_the_block_has_the_core_kinds(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / '_config.yml').write_text('telar_language: en\n', encoding='utf-8')

        assert site_kinds() == ()
        assert resolve_kind('species') == 'term'

    @pytest.mark.parametrize('kind, reason', [
        ({'id': 'species', 'heading': 'Species'}, 'no label'),
        ({'id': 'species', 'label': 'Species'}, 'no heading'),
        ({'id': 'species', 'label': '  ', 'heading': 'Species'}, 'no label'),
        ({'id': 'person', 'label': 'Person', 'heading': 'People'}, "'entity'"),
        ({'id': 'species', 'label': 'S', 'heading': 'S', 'values': ['lugar']}, "'place'"),
        ({'id': 'species', 'label': 'S', 'heading': 'S', 'values': 'taxon'}, 'not a list'),
        ({'label': 'S', 'heading': 'S'}, 'no id'),
    ])
    def test_an_incomplete_or_colliding_kind_is_warned_about_and_ignored(
            self, tmp_path, monkeypatch, capsys, kind, reason):
        _config_site(tmp_path, monkeypatch, [kind])

        assert site_kinds() == ()
        out = capsys.readouterr().out
        assert '[WARN]' in out and reason in out
        if 'id' in kind:
            assert f"'{kind['id']}'" in out

    def test_two_site_kinds_claiming_one_value_keep_the_first(
            self, tmp_path, monkeypatch, capsys):
        _config_site(tmp_path, monkeypatch, [
            SPECIES, {'id': 'plant', 'label': 'Plant', 'heading': 'Plants',
                      'values': ['Taxon']}])

        assert [k['id'] for k in site_kinds()] == ['species']
        out = capsys.readouterr().out
        assert "'plant'" in out and "'species'" in out
        assert resolve_kind('taxon') == 'species'

    def test_a_repeated_id_is_ignored(self, tmp_path, monkeypatch, capsys):
        _config_site(tmp_path, monkeypatch, [SPECIES, dict(SPECIES, label='Other')])

        assert [k['label'] for k in site_kinds()] == ['Species']
        assert '[WARN]' in capsys.readouterr().out

    def test_its_label_and_heading_are_as_written(self, tmp_path, monkeypatch):
        _config_site(tmp_path, monkeypatch, [dict(SPECIES, label='Especie',
                                                  heading='Especies')])

        assert kind_text('species', 'label') == 'Especie'
        assert kind_text('species', 'heading') == 'Especies'

    def test_a_core_kinds_label_and_heading_come_from_the_catalogue(self):
        assert kind_text('entity', 'label') == 'Person or entity'
        assert kind_text('place', 'heading') == 'Places'
        assert kind_text('nothing', 'label') is None

    def test_the_build_writes_the_accepted_kinds_for_the_layouts(
            self, tmp_path, monkeypatch):
        out = _config_site(tmp_path, monkeypatch,
                           [SPECIES, {'id': 'bad', 'label': 'Bad'}],
                           'quercus,Quercus,An oak.,taxon\nloom,Loom,A frame.,\n')

        generate_glossary()

        written = json.loads((tmp_path / '_data' / 'glossary_site_kinds.json')
                             .read_text(encoding='utf-8'))
        assert written == [{'id': 'species', 'label': 'Species', 'heading': 'Species'}]
        assert _front_matter(out / 'quercus.md')['glossary_kind'] == 'species'
        assert _front_matter(out / 'loom.md')['glossary_kind'] == 'term'

    def test_a_site_with_no_kinds_writes_an_empty_list(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\nloom,Loom,A frame.\n')

        generate_glossary()

        assert json.loads((tmp_path / '_data' / 'glossary_site_kinds.json')
                          .read_text(encoding='utf-8')) == []

    def test_a_markdown_entry_takes_a_site_kind(self, tmp_path, monkeypatch):
        out = _config_site(tmp_path, monkeypatch, [SPECIES])
        texts = tmp_path / 'telar-content' / 'texts' / 'glossary'
        texts.mkdir(parents=True)
        (texts / 'quercus.md').write_text(
            '---\nterm_id: quercus\ntitle: Quercus\ntipo: especie\n---\n\nAn oak.\n',
            encoding='utf-8')

        generate_glossary()

        assert _front_matter(out / 'quercus.md')['glossary_kind'] == 'species'
