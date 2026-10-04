"""
Unit Tests for the Glossary Callout Widget

`:::glossary` links a glossary entry as a box: the kind's icon, the kind's
label and the entry's title. The widget step reads `entry:` and `align:` and
leaves a slot; the glossary pass, which every widget path runs afterwards,
resolves the entry as it resolves `[[entry]]` and draws the box, or reports
and marks an entry the glossary lacks exactly as it does for `[[entry]]`.

Version: v1.8.0
"""

import os
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar.config
from telar.glossary import (GlossaryTerms, load_glossary_from_csv,
                            process_glossary_links, strip_glossary_links)
from telar.latex import convert_markdown
from telar.widgets import parse_glossary_widget, process_widgets

REPO = Path(__file__).resolve().parents[2]

ICON_PATHS = {
    'document': 'M6.5 2.75h7.25l4 4V21.25H6.5z',
    'bookmark': 'M6.75 3.25h10.5v17.5L12 16.75l-5.25 4z',
    'person': 'M4.75 20.5c.6-3.9 3.6-6 7.25-6s6.65 2.1 7.25 6',
    'pin': 'M12 21.25s-6.25-6-6.25-11a6.25 6.25 0 0 1 12.5 0c0 5-6.25 11-6.25 11z',
    'alert': 'M12 7.5v5.5',
}


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site in its own directory, in a language chosen per test."""
    monkeypatch.chdir(tmp_path)
    shutil.copytree(REPO / '_includes' / 'widgets', tmp_path / '_includes' / 'widgets')
    shutil.copytree(REPO / '_data' / 'languages', tmp_path / '_data' / 'languages')
    monkeypatch.setattr(telar.config, '_lang_data', None)

    def configure(language='en', kinds=None):
        config = {'telar_language': language, 'baseurl': '/telar'}
        if kinds is not None:
            config['glossary'] = {'kinds': kinds}
        (tmp_path / '_config.yml').write_text(yaml.safe_dump(config), encoding='utf-8')
        telar.config._lang_data = None
        from telar.widgets import reset_base_url_cache
        reset_base_url_cache()
        return tmp_path

    configure()
    return configure


def _glossary(entries):
    terms = GlossaryTerms()
    for term_id, title, kind in entries:
        terms[term_id] = title
        if kind:
            terms.kinds[term_id] = kind
    return terms


GLOSSARY = _glossary([('carta', 'Carta de 1810', 'source'),
                      ('telar', 'Telar', None),
                      ('bolivar', 'Simón Bolívar', 'entity'),
                      ('bogota', 'Santafé', 'place')])


def _render(block, glossary=GLOSSARY, warnings=None):
    """A panel's markdown through the widget, markdown and glossary passes."""
    warnings = [] if warnings is None else warnings
    text = process_widgets(f'Before.\n\n{block}\n\nAfter.', 'test', warnings)
    text = convert_markdown(text, extensions=['extra', 'nl2br', 'sane_lists'])
    return process_glossary_links(text, glossary, warnings)


def _callout(html):
    found = re.findall(r'<a [^>]*class="glossary-inline-link glossary-callout[^"]*".*?</a>',
                       html, re.S)
    assert len(found) == 1, html
    return found[0]


class TestTheBlock:

    @pytest.mark.parametrize('line, align', [
        ('', 'right'), ('align: right', 'right'), ('align: left', 'left'),
        ('align: derecha', 'right'), ('align: izquierda', 'left'),
        ('align: Izquierda', 'left'), ('align: LEFT', 'left'),
    ])
    def test_align_is_right_unless_it_says_left(self, line, align):
        warnings = []
        slot = parse_glossary_widget(f'entry: carta\n{line}', 'test', warnings)

        assert f'data-align="{align}"' in slot
        assert warnings == []

    @pytest.mark.parametrize('value', ['center', 'centro', 'top', 'izq'])
    def test_any_other_align_warns_and_is_right(self, value):
        warnings = []
        slot = parse_glossary_widget(f'entry: carta\nalign: {value}', 'test', warnings)

        assert 'data-align="right"' in slot
        assert len(warnings) == 1
        assert warnings[0]['widget_type'] == 'glossary'
        assert f"'{value}'" in warnings[0]['message']

    def test_the_slot_is_a_block_of_its_own(self):
        slot = parse_glossary_widget('entry: carta', 'test', [])

        assert slot.startswith('\n\n<div class="glossary-callout-slot"')
        assert slot.endswith('></div>\n\n')


class TestTheCallout:

    def test_it_links_the_entry_as_an_inline_link_does(self, site):
        box = _callout(_render(':::glossary\nentry: carta\n:::'))

        assert 'class="glossary-inline-link glossary-callout glossary-callout--right"' in box
        assert 'data-term-id="carta"' in box
        assert 'data-term-url="/telar/glossary/carta/"' in box
        assert box.startswith('<a href="#"')

    def test_left_is_the_mirror(self, site):
        box = _callout(_render(':::glossary\nentry: carta\nalign: izquierda\n:::'))

        assert 'glossary-callout--left' in box

    def test_the_entry_is_matched_without_case_as_a_link_is(self, site):
        box = _callout(_render(':::glossary\nentry: CARTA\n:::'))

        assert 'data-term-id="carta"' in box

    @pytest.mark.parametrize('language, kind_id, entry, label', [
        ('en', 'source', 'carta', 'Primary source'),
        ('es', 'source', 'carta', 'Fuente primaria'),
        ('en', 'term', 'telar', 'Key term'),
        ('es', 'term', 'telar', 'Palabra clave'),
        ('en', 'entity', 'bolivar', 'Person or entity'),
        ('es', 'place', 'bogota', 'Lugar'),
    ])
    def test_it_shows_the_kinds_label_in_the_site_language(
            self, site, language, kind_id, entry, label):
        site(language)
        box = _callout(_render(f':::glossary\nentry: {entry}\n:::'))

        assert f'<span class="glossary-callout-kind">{label}</span>' in box
        assert f'data-glossary-kind="{kind_id}"' in box
        # The panel label's colon is the panel's, not the callout's.
        assert f'{label}:' not in box

    @pytest.mark.parametrize('entry, icon', [
        ('carta', 'document'), ('telar', 'bookmark'),
        ('bolivar', 'person'), ('bogota', 'pin'),
    ])
    def test_each_core_kind_has_its_icon(self, site, entry, icon):
        box = _callout(_render(f':::glossary\nentry: {entry}\n:::'))

        icon_svg = re.search(r'<svg class="glossary-callout-icon".*?</svg>', box).group(0)
        assert ICON_PATHS[icon] in icon_svg
        for other, path in ICON_PATHS.items():
            if other != icon:
                assert path not in icon_svg

    def test_a_site_kind_gets_the_exclamation_mark(self, site):
        site(kinds=[{'id': 'species', 'label': 'Species', 'heading': 'Species',
                     'icon': 'document'}])
        box = _callout(_render(':::glossary\nentry: quercus\n:::',
                               _glossary([('quercus', 'Quercus', 'species')])))

        icon_svg = re.search(r'<svg class="glossary-callout-icon".*?</svg>', box).group(0)
        assert ICON_PATHS['alert'] in icon_svg
        # A site cannot give its kind an icon of its own.
        assert ICON_PATHS['document'] not in icon_svg
        assert '<span class="glossary-callout-kind">Species</span>' in box

    def test_the_title_is_decoded_once_and_escaped(self, site):
        box = _callout(_render(':::glossary\nentry: amp\n:::',
                               _glossary([('amp', 'Tom &amp; Jerry <b>', 'term')])))

        assert '<span class="glossary-callout-title">Tom &amp; Jerry &lt;b&gt;</span>' in box

    def test_its_accessible_name_is_its_visible_text(self, site):
        """No aria-label: the kind label and the title are the name, and the
        icons are hidden from it."""
        box = _callout(_render(':::glossary\nentry: carta\n:::'))

        assert 'aria-label' not in box
        assert box.count('aria-hidden="true"') == 2
        text = re.sub(r'\s+', ' ', re.sub(r'<svg.*?</svg>|<[^>]+>', ' ', box, flags=re.S)).strip()
        assert text == 'Primary source Carta de 1810'

    def test_it_reaches_the_page_as_one_line(self, site):
        html = _render(':::glossary\nentry: carta\n:::')

        assert '\n' not in _callout(html)

    def test_a_demo_entry_is_marked_as_a_link_to_one_is(self, site):
        box = _callout(_render(':::glossary\nentry: demo-iiif\n:::',
                               _glossary([('demo-iiif', 'IIIF', None)])))

        assert 'data-demo="true"' in box


class TestAnEntryTheGlossaryLacks:

    def test_an_unknown_entry_is_reported_and_marked_as_a_link_is(self, site):
        callout_warnings, link_warnings = [], []
        callout = _render(':::glossary\nentry: nowhere\n:::', warnings=callout_warnings)
        link = process_glossary_links('<p>[[nowhere]]</p>', GLOSSARY, link_warnings)

        marker = '<span class="glossary-link-error" data-term-id="nowhere">⚠️ [[nowhere]]</span>'
        assert marker in callout and marker in link
        assert callout_warnings == link_warnings
        assert 'glossary-callout' not in callout

    def test_a_missing_entry_is_reported_as_an_empty_one(self, site):
        warnings = []
        html = _render(':::glossary\nalign: left\n:::', warnings=warnings)

        assert '<span class="glossary-link-error" data-term-id="">' in html
        assert len(warnings) == 1 and warnings[0]['type'] == 'glossary'
        assert warnings[0]['term_id'] == ''

    def test_a_site_without_a_glossary_marks_it_too(self, site):
        warnings = []
        html = _render(':::glossary\nentry: carta\n:::', glossary={}, warnings=warnings)

        assert 'glossary-callout-slot' not in html
        assert 'glossary-link-error' in html
        assert len(warnings) == 1


class TestWhereItWorks:

    def test_a_protected_story_keeps_the_title(self, site):
        html = _render(':::glossary\nentry: carta\n:::')

        stripped = strip_glossary_links(html)
        assert 'glossary-callout' not in stripped
        assert 'Carta de 1810' in stripped

    def test_a_glossary_definition(self, site, tmp_path):
        from telar.glossary_pages import generate_glossary
        sheets = tmp_path / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title,definition,kind\n'
            'carta,Carta,A letter.,source\n'
            'telar,Telar,"Woven.\n\n:::glossary\nentry: carta\n:::\n\nMore.",\n',
            encoding='utf-8')

        generate_glossary()

        page = (tmp_path / '_jekyll-files' / '_glossary' / 'telar.md').read_text(encoding='utf-8')
        box = _callout(page)
        assert 'data-term-id="carta"' in box
        assert 'Primary source' in box

    def test_a_user_page(self, site, tmp_path):
        from telar.pages import generate_pages
        sheets = tmp_path / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title,definition,kind\nbogota,Santafé,A city.,place\n',
            encoding='utf-8')
        pages = tmp_path / 'telar-content' / 'texts' / 'pages'
        pages.mkdir(parents=True)
        (pages / 'about.md').write_text(
            '---\ntitle: About\n---\n\nText.\n\n:::glossary\nentry: bogota\nalign: left\n:::\n\nMore.\n',
            encoding='utf-8')

        generate_pages()

        page = next((tmp_path / '_jekyll-files' / '_pages').glob('about.md')).read_text(
            encoding='utf-8')
        box = _callout(page)
        assert 'glossary-callout--left' in box and 'Place' in box

    def test_the_loaders_keep_each_entrys_kind(self, site, tmp_path):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text('term_id,title,kind\ncarta,Carta,fuente\ntelar,Telar,\n',
                            encoding='utf-8')

        terms = load_glossary_from_csv(csv_path)

        assert terms.kinds == {'carta': 'source', 'telar': 'term'}


class TestAStepsAnswer:

    @pytest.mark.xfail(strict=True, reason=(
        'No answer rule removes a widget block: :::glossary, like :::carousel, '
        'stays in the answer as literal text. Reported for a ruling; a new rule '
        'is part of the contract the Compositor mirrors.'))
    def test_the_answer_rules_remove_it(self):
        from telar.processors.stories import _reduce_answer_to_prose
        answer = 'Before.\n\n:::glossary\nentry: carta\n:::\n\nAfter.'

        prose, _kinds = _reduce_answer_to_prose(answer)

        assert ':::glossary' not in prose
