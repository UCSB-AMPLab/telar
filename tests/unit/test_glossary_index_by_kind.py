"""
Unit Tests for the Glossary Page Grouped by Kind

The grouping and the intro are Liquid, so these tests build a small Jekyll
site from the real glossary layouts, includes, kinds list, language
catalogues and glossary page, with a stand-in for the outer layout, and read
the HTML. The entries are what the build writes: a page per entry with its
`glossary_kind`.

Jekyll needs the Ruby the Gemfile asks for. Where `bundle exec jekyll` cannot
run against it, the tests are skipped and say so; run them with that Ruby on
PATH, e.g.

    PATH="$HOME/.rubies/ruby-3.2.11/bin:$PATH" GEM_HOME="$HOME/.gem/ruby/3.2.11" \\
        .venv/bin/python3 -m pytest tests/unit/test_glossary_index_by_kind.py

Version: v1.8.0
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]


def _jekyll_env():
    env = dict(os.environ, BUNDLE_GEMFILE=str(REPO / 'Gemfile'))
    env.pop('BUNDLE_PATH', None)
    return env


def _jekyll_runs():
    if shutil.which('bundle') is None:
        return False
    try:
        result = subprocess.run(['bundle', 'exec', 'jekyll', '--version'],
                                capture_output=True, text=True, cwd=REPO,
                                env=_jekyll_env(), timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _jekyll_runs(),
    reason='bundle exec jekyll does not run against the Gemfile with this Ruby')


def _entry(term_id, title, kind):
    lines = ['---', f'term_id: {term_id}', f'title: {title}']
    if kind is not None:
        lines.append(f'glossary_kind: {kind}')
    lines += ['layout: glossary', '---', '', f'<p>{title}.</p>', '']
    return '\n'.join(lines)


def _build(tmp_path, entries, language='en', site_kinds=None):
    """Build the glossary page for these entries; return its HTML.

    `site_kinds` is the `glossary: kinds:` list of the site's config, written
    both into `_config.yml` and, as the build writes it, into
    `_data/glossary_site_kinds.json`.
    """
    site = tmp_path / 'site'
    for folder in ('_layouts', '_includes', '_data', 'pages',
                   '_jekyll-files/_glossary'):
        (site / folder).mkdir(parents=True, exist_ok=True)
    for name in ('glossary-index.html', 'glossary.html'):
        shutil.copy(REPO / '_layouts' / name, site / '_layouts' / name)
    for path in (REPO / '_includes').glob('glossary-*.html'):
        shutil.copy(path, site / '_includes' / path.name)
    (site / '_layouts' / 'default.html').write_text('{{ content }}\n', encoding='utf-8')
    shutil.copy(REPO / '_data' / 'glossary_kinds.yml', site / '_data' / 'glossary_kinds.yml')
    shutil.copytree(REPO / '_data' / 'languages', site / '_data' / 'languages')
    shutil.copy(REPO / 'pages' / 'glossary.md', site / 'pages' / 'glossary.md')
    config = (f'telar_language: {language}\n'
              'collections_dir: _jekyll-files\n'
              'collections:\n'
              '  glossary:\n'
              '    output: true\n'
              '    permalink: /glossary/:name/\n')
    if site_kinds is not None:
        config += yaml.safe_dump({'glossary': {'kinds': site_kinds}}, allow_unicode=True)
        written = [{'id': k['id'], 'label': k['label'], 'heading': k['heading']}
                   for k in site_kinds]
        (site / '_data' / 'glossary_site_kinds.json').write_text(
            json.dumps(written), encoding='utf-8')
    (site / '_config.yml').write_text(config, encoding='utf-8')
    for term_id, title, kind in entries:
        (site / '_jekyll-files' / '_glossary' / f'{term_id}.md').write_text(
            _entry(term_id, title, kind), encoding='utf-8')

    result = subprocess.run(
        ['bundle', 'exec', 'jekyll', 'build', '--source', str(site),
         '--destination', str(site / '_site'), '--quiet'],
        capture_output=True, text=True, cwd=REPO, env=_jekyll_env(), timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return (site / '_site' / 'glossary' / 'index.html').read_text(encoding='utf-8')


def _headings(html):
    """The page's kind and letter headings, in order, as (tag, text)."""
    return re.findall(
        r'<(h[23]) class="glossary-(?:section-heading|letter)">([^<]*)</h[23]>', html)


def _entries(html):
    return re.findall(r'class="glossary-term-link" data-term-id="([^"]+)"', html)


TERMS_ONLY = [('telar', 'Telar', 'term'), ('loom', 'Loom', 'term'),
              ('atlas', 'Atlas', 'term')]
MIXED = TERMS_ONLY + [('letter', 'Letter of 1810', 'source'),
                      ('census', 'Census', 'source')]


class TestAGlossaryOfTermsAlone:

    def test_has_no_kind_headings_and_its_letters_stay_second_level(self, tmp_path):
        html = _build(tmp_path, TERMS_ONLY)

        assert 'glossary-section' not in html
        assert _headings(html) == [('h2', 'A'), ('h2', 'L'), ('h2', 'T')]
        assert _entries(html) == ['atlas', 'loom', 'telar']

    def test_keeps_its_intro(self, tmp_path):
        html = _build(tmp_path, TERMS_ONLY)

        assert '<p>Key terms and concepts used in these stories.</p>' in html
        assert '<p>Key terms and primary sources' not in html


ALL_KINDS = TERMS_ONLY + [
    ('letter', 'Letter of 1810', 'source'),
    ('bolivar', 'Simón Bolívar', 'entity'),
    ('cabildo', 'Cabildo', 'entity'),
    ('bogota', 'Santafé', 'place'),
    ('quercus', 'Quercus', 'species'),
]
SPECIES = [{'id': 'species', 'label': 'Species', 'heading': 'Species found',
            'values': ['taxon']}]


class TestEveryKind:

    def test_the_core_kinds_then_the_sites_in_order(self, tmp_path):
        html = _build(tmp_path, ALL_KINDS, site_kinds=SPECIES)

        assert [text for tag, text in _headings(html) if tag == 'h2'] == [
            'Key terms', 'Primary sources', 'People and entities', 'Places',
            'Species found']
        assert _entries(html) == ['atlas', 'loom', 'telar', 'letter',
                                  'cabildo', 'bolivar', 'bogota', 'quercus']

    def test_a_kind_without_entries_shows_nothing(self, tmp_path):
        html = _build(tmp_path, TERMS_ONLY + [('bogota', 'Santafé', 'place')],
                      site_kinds=SPECIES)

        assert [text for tag, text in _headings(html) if tag == 'h2'] == [
            'Key terms', 'Places']
        assert 'data-glossary-kind="species"' not in html

    def test_in_spanish_the_core_headings_translate_and_the_sites_are_as_written(
            self, tmp_path):
        html = _build(tmp_path, ALL_KINDS, language='es',
                      site_kinds=[dict(SPECIES[0], heading='Especies')])

        assert [text for tag, text in _headings(html) if tag == 'h2'] == [
            'Palabras clave', 'Fuentes primarias', 'Personas y entidades',
            'Lugares', 'Especies']

    def test_entities_and_places_without_sources_keep_the_plain_intro(self, tmp_path):
        html = _build(tmp_path, TERMS_ONLY + [('bolivar', 'Simón Bolívar', 'entity'),
                                              ('bogota', 'Santafé', 'place')])

        assert '<p>Key terms and concepts used in these stories.</p>' in html
        assert 'People and entities' in html

    def test_any_source_gives_the_intro_with_sources(self, tmp_path):
        html = _build(tmp_path, [('bogota', 'Santafé', 'place'),
                                 ('letter', 'Letter', 'source')])

        assert '<p>Key terms and primary sources used in these stories.</p>' in html


class TestAGlossaryWithSources:

    def test_groups_each_kind_under_its_heading_in_the_registry_order(self, tmp_path):
        html = _build(tmp_path, MIXED)

        assert _headings(html) == [
            ('h2', 'Key terms'), ('h3', 'A'), ('h3', 'L'), ('h3', 'T'),
            ('h2', 'Primary sources'), ('h3', 'C'), ('h3', 'L'),
        ]
        assert _entries(html) == ['atlas', 'loom', 'telar', 'census', 'letter']

    def test_says_it_has_sources_in_its_intro(self, tmp_path):
        html = _build(tmp_path, MIXED)

        assert 'Key terms and primary sources used in these stories.' in html

    def test_a_glossary_of_sources_alone_is_headed_as_sources(self, tmp_path):
        html = _build(tmp_path, [('letter', 'Letter', 'source')])

        assert _headings(html) == [('h2', 'Primary sources'), ('h3', 'L')]
        assert 'Key terms and primary sources used in these stories.' in html

    def test_in_spanish(self, tmp_path):
        html = _build(tmp_path, MIXED, language='es')

        headings = [text for _tag, text in _headings(html)]
        assert headings[0] == 'Palabras clave'
        assert 'Fuentes primarias' in headings
        assert ('Palabras clave y fuentes primarias que aparecen en estas '
                'historias.') in html


class TestAnEmptyGlossary:

    @pytest.mark.parametrize('language, text', [
        ('en', 'There are no glossary entries yet.'),
        ('es', 'Aún no hay entradas en el glosario.'),
    ])
    def test_says_how_to_add_entries(self, tmp_path, language, text):
        html = _build(tmp_path, [], language=language)

        assert text in html
        assert 'glossary-section' not in html


class TestTheEntryPage:

    @pytest.mark.parametrize('language, kind, label', [
        ('en', 'term', 'Key term'), ('en', 'source', 'Primary source'),
        ('es', 'term', 'Palabra clave'), ('es', 'source', 'Fuente primaria'),
        ('en', 'entity', 'Person or entity'), ('es', 'entity', 'Persona o entidad'),
        ('en', 'place', 'Place'), ('es', 'place', 'Lugar'),
        ('en', 'species', 'Species'), ('es', 'species', 'Species'),
    ])
    def test_carries_the_label_of_its_kind_for_the_panel(self, tmp_path, language, kind, label):
        _build(tmp_path, [('carta', 'Carta', kind)], language=language, site_kinds=SPECIES)
        page = (tmp_path / 'site' / '_site' / 'glossary' / 'carta' / 'index.html').read_text(
            encoding='utf-8')

        assert f'data-glossary-kind-label="{label}"' in page
