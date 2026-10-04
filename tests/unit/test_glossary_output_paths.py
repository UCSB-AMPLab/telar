"""
Glossary Pages That Jekyll Writes to One File

Two glossary pages collide when Jekyll writes them to one output file, not
only when their permalinks are the same string: a placeholder permalink is
resolved as Jekyll resolves it for a document in the glossary collection,
`/shared/` and `/shared/index.html` are one file, and a case-insensitive
disk holds `/Case/` and `/case/` as one folder. The build writes each page
to `_glossary/<term_id>.md`, so ids whose file names casefold alike also
share a file. Of pages sharing either, the first is kept, the other is
reported, and the link map, the generator and the demo placement all read
that one decision. Expected addresses and output files were checked against Jekyll 4.4.1.

Version: v1.8.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.demo import _demo_link_terms
from telar.glossary import (glossary_output_file, load_glossary_terms,
                            markdown_glossary_address, process_glossary_links)
from telar.glossary_pages import generate_glossary
from telar.jekyll_urls import glossary_index_addresses
from telar.widgets import reset_base_url_cache

SPREADSHEETS = 'telar-content/spreadsheets'
LEGACY = 'telar-content/texts/glossary'
OUT = '_jekyll-files/_glossary'


@pytest.fixture(autouse=True)
def _fresh_base_url():
    reset_base_url_cache()
    yield
    reset_base_url_cache()


def _site(tmp_path, monkeypatch, csv=None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('baseurl: ""\n', encoding='utf-8')
    if csv is not None:
        (tmp_path / SPREADSHEETS).mkdir(parents=True)
        (tmp_path / SPREADSHEETS / 'glossary.csv').write_text(csv, encoding='utf-8')


def _legacy(tmp_path, name, front_matter):
    folder = tmp_path / LEGACY
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f'---\n{front_matter}\n---\n\nBody.\n', encoding='utf-8')


def _demo(tmp_path, *terms):
    (tmp_path / '_data').mkdir()
    (tmp_path / '_data/demo-glossary.json').write_text(json.dumps(
        [{'term_id': i, 'title': t, 'content': t} for i, t in terms]), encoding='utf-8')


def _link(term_id, terms):
    return process_glossary_links(f'See [[{term_id}]].', terms, [], base_url='')


def _written(tmp_path):
    return sorted(p.name for p in (tmp_path / OUT).glob('*.md'))


def _page(tmp_path, term_id):
    return (tmp_path / OUT / f'{term_id}.md').read_text(encoding='utf-8')


class TestAPlaceholderPermalinkIsResolved:
    @pytest.mark.parametrize('term_id,front_matter,address', [
        ('old', 'permalink: /custom/:name/', '/custom/old/'),
        ('Path.Term', 'permalink: /p:path/', '/p/Path.Term/'),
        ('Dots...', 'permalink: /d/:path/', '/d/Dots/'),
        ('Ti', 'permalink: /:collection/:title/:slug:output_ext', '/glossary/Ti/ti.html'),
        ('Sl', 'slug: My Slug!\npermalink: /:title/:slug/', '/My-Slug!/my-slug/'),
        ('Straße', 'permalink: /s/:name/:title/', '/s/stra%C3%9Fe/Stra%C3%9Fe/'),
        ('Ca', 'categories: Foo Bar foo\n'
               'permalink: /:categories/:slugified_categories/:name_/',
         '/foo/bar/foo/bar/ca_/'),
        ('Cb', 'categories: [Ünï Cödé, x y]\n'
               'permalink: /:categories/:slugified_categories/',
         '/%C3%BCn%C3%AF%20c%C3%B6d%C3%A9/x%20y/%C3%BCn%C3%AF-c%C3%B6d%C3%A9/x-y/'),
        ('A%2FB', 'permalink: /:path/', '/A%252FB/'),
        ('A#B', 'permalink: /:path/', '/A%23B/'),
        ('A#B#C', 'permalink: /:path/', '/A%23B%23C/'),
        ('A B', 'permalink: /:path/', '/A%20B/'),
        ('A%B', 'permalink: /:path/:title/', '/A%25B/A-B/'),
        ('Ka', 'category: North\npermalink: /:categories/:slug/', '/north/ka/'),
        ('Kb', 'categories: [South]\ncategory: North\npermalink: /:categories/',
         '/south/north/'),
        ('Kc', 'categories: [true, 7]\npermalink: /:categories/', '/true/7/'),
        ('Kd', 'categories: [1.5, 2026-01-02, ~, x, X]\n'
               'permalink: /:categories/:slugified_categories/',
         '/1.5/2026-01-02/x/1-5/2026-01-02/x/'),
        ('Ke', 'category: [P, Q]\ncategories: q\npermalink: /:categories/', '/q/p/'),
        ('Kg', 'category: false\ncategories: [z]\npermalink: /:categories/', '/z/'),
        ('2026-01-02-Foo', 'permalink: /:title/:slug/:name/', '/Foo/foo/2026-01-02-foo/'),
        ('2026-1-2-Bar.', 'permalink: /:title/:slug/', '/Bar/bar/'),
        ('A.B.', 'permalink: /:title/', '/A.B/'),
        ('Sf', 'slug: false\npermalink: /:slug/', '/sf/'),
        ('Kh', 'category: "a:b"\npermalink: /c/:categories/', '/c/a:b/'),
        ('Ki', 'category: "mailto:x y"\npermalink: /c/:categories/', '/c/mailto:x%20y/'),
        ('Kj', 'category: "a:b#c"\npermalink: /c/:categories/', '/c/a:b%23c/'),
    ])

    def test_as_jekyll_resolves_it(self, term_id, front_matter, address):
        assert markdown_glossary_address(front_matter, term_id) == (address, [])

    @pytest.mark.parametrize('category', ['http:', '1a:b', ':x', 'é:b'])
    def test_a_value_jekyll_cannot_build_is_reported(self, category):
        # Addressable refuses each of these, and Jekyll's build stops.
        front_matter = f'category: "{category}"\npermalink: /c/:categories/'
        assert markdown_glossary_address(front_matter, 't') == (
            '/c/:categories/', [':categories'])

    def test_the_link_goes_to_the_resolved_address(self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: old\ntitle: Old\npermalink: /custom/:name/')

        terms = generate_glossary()

        assert 'data-term-url="/custom/old/"' in _link('old', terms)
        assert 'data-term-url="/custom/old/"' in _link('old', load_glossary_terms())
        assert 'permalink: /custom/:name/' in _page(tmp_path, 'old')
        assert '⚠️' not in capsys.readouterr().out

    def test_one_it_cannot_resolve_is_reported_and_linked_as_written(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: old\ntitle: Old\npermalink: /x/:year/:foo/')

        terms = generate_glossary()

        assert 'data-term-url="/x/:year/:foo/"' in _link('old', terms)
        assert ("  ⚠️ Glossary entry 'old' (a.md): its permalink uses :year and :foo, "
                "which the build cannot work out, so links to it may not reach its "
                "page. Write the permalink without :year and :foo.") in capsys.readouterr().out

    def test_the_per_story_link_map_does_not_repeat_that_report(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: old\ntitle: Old\npermalink: /x/:year/')
        load_glossary_terms()
        assert capsys.readouterr().out == ''


class TestPagesWrittenToOneOutputFile:
    @pytest.mark.parametrize('first,second,shown', [
        ('/custom/:name/', '/custom/old/', '/custom/old/'),
        ('/custom/other/', '/custom/:name/', '/custom/other/'),
        ('/shared/', '/shared/index.html', '/shared/'),
        ('/shared/index.html', '/shared/', '/shared/index.html'),
        ('/Case/', '/case/', '/Case/'),
        ('/foo', '/foo.html', '/foo'),
    ])
    def test_the_first_is_kept_and_the_other_reported(
            self, tmp_path, monkeypatch, capsys, first, second, shown):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', f'term_id: old\ntitle: First\npermalink: {first}')
        _legacy(tmp_path, 'b.md', f'term_id: other\ntitle: Second\npermalink: {second}')

        terms = generate_glossary()

        assert _written(tmp_path) == ['old.md']
        assert list(terms) == ['old']
        assert 'glossary-link-error' in _link('other', terms)
        assert capsys.readouterr().out.count(
            f"  ⚠️ Glossary entries 'old' and 'other' would both be published at "
            f"{shown}. 'old' keeps that address; 'other' is not published and "
            f"cannot be linked.") == 1
        assert list(load_glossary_terms()) == ['old']

    def test_the_output_file_is_named_as_jekyll_writes_it(self):
        assert glossary_output_file('/shared/') == 'shared/index.html'
        assert glossary_output_file('/shared/index.html') == 'shared/index.html'
        assert glossary_output_file('/foo') == 'foo.html'
        assert glossary_output_file('/Case/') == glossary_output_file('/case/')

    def test_pages_at_different_addresses_are_both_kept(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: one\ntitle: One\npermalink: /a/')
        _legacy(tmp_path, 'b.md', 'term_id: two\ntitle: Two\npermalink: /b/')

        terms = generate_glossary()

        assert _written(tmp_path) == ['one.md', 'two.md']
        assert 'data-term-url="/a/"' in _link('one', terms)
        assert 'data-term-url="/b/"' in _link('two', terms)
        assert '⚠️' not in capsys.readouterr().out


class TestPagesWrittenToOneGlossaryFile:
    def test_legacy_ids_differing_in_case_keep_the_first(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: Viewer\ntitle: First\npermalink: /a/')
        _legacy(tmp_path, 'b.md', 'term_id: viewer\ntitle: Second\npermalink: /b/')

        terms = generate_glossary()

        assert _written(tmp_path) == ['Viewer.md']
        assert 'permalink: /a/' in _page(tmp_path, 'Viewer')
        assert list(terms) == ['Viewer']
        assert 'data-term-url="/a/"' in _link('viewer', terms)
        assert ("  ⚠️ Glossary entries 'Viewer' and 'viewer' would both be "
                "written to the same file, _glossary/Viewer.md. 'Viewer' keeps "
                "that file; 'viewer' is not published and cannot be linked."
                ) in capsys.readouterr().out

    def test_csv_ids_that_casefold_alike_keep_the_first(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch,
              'term_id,title,definition\nStraße,Street,one\nStrasse,Second,two\n')

        terms = generate_glossary()

        assert _written(tmp_path) == ['Straße.md']
        assert 'Street' in _page(tmp_path, 'Straße')
        assert list(terms) == ['Straße']
        assert list(load_glossary_terms()) == ['Straße']
        # Their slugs are glossary/straße/ and glossary/strasse/, one folder
        # on such a disk, so the output file is the one reported.
        assert ("  ⚠️ Glossary entries 'Straße' and 'Strasse' would both be "
                "published at /glossary/straße/. 'Straße' keeps that address; "
                "'Strasse' is not published and cannot be linked."
                ) in capsys.readouterr().out


class TestADemoIdLinksToThePageTheFileHolds:
    def test_the_file_and_the_link_name_the_same_site_term(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: Straße\ntitle: Street\npermalink: /one/')
        _legacy(tmp_path, 'b.md', 'term_id: Strasse\ntitle: Second\npermalink: /two/')
        _demo(tmp_path, ('STRASSE', 'Demo'))

        generate_glossary()

        assert _written(tmp_path) == ['Straße.md']
        page = _page(tmp_path, 'Straße')
        assert 'permalink: /one/' in page and 'Street' in page
        out = capsys.readouterr().out
        assert ("Glossary entries 'Straße' and 'Strasse' would both be written "
                "to the same file, _glossary/Straße.md.") in out
        assert ("Demo glossary term 'STRASSE' skipped: the site's glossary term "
                "'Straße' is written to the same file, _glossary/Straße.md, "
                "which is kept.") in out

        terms = _demo_link_terms({'glossary': {'STRASSE': {'term': 'Demo'}}})
        link = _link('STRASSE', terms)
        assert 'data-term-url="/one/"' in link
        assert '>Street<' in link


class TestJekyllsEscapingAndPathRules:
    def test_an_escaped_placeholder_and_a_literal_percent_do_not_collide(
            self, tmp_path, monkeypatch, capsys):
        # Jekyll writes /A%252FB/ to A%2FB/index.html and the literal
        # /A%2FB/ to A/B/index.html.
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: A%2FB\ntitle: First\npermalink: /:path/')
        _legacy(tmp_path, 'b.md', 'term_id: other\ntitle: Second\npermalink: /A%2FB/')

        terms = generate_glossary()

        assert _written(tmp_path) == ['A%2FB.md', 'other.md']
        assert 'data-term-url="/A%252FB/"' in _link('A%2FB', terms)
        assert 'data-term-url="/A%2FB/"' in _link('other', terms)
        assert '⚠️' not in capsys.readouterr().out

    def test_a_hash_in_an_id_is_not_a_fragment(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: A#B\ntitle: First\npermalink: /:path/')
        assert 'data-term-url="/A%23B/"' in _link('A#B', load_glossary_terms())

    def test_an_escaped_dot_dot_resolves_in_the_output_file(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: one\ntitle: First\npermalink: /x/%2E%2E/y/')
        _legacy(tmp_path, 'b.md', 'term_id: two\ntitle: Second\npermalink: /y/')

        terms = generate_glossary()

        assert glossary_output_file('/x/%2E%2E/y/') == 'y/index.html'
        assert list(terms) == ['one']
        assert ("Glossary entries 'one' and 'two' would both be published at "
                "/x/%2E%2E/y/.") in capsys.readouterr().out

    def test_a_dot_dot_in_a_sole_permalink_is_linked_where_jekyll_publishes_it(
            self, tmp_path, monkeypatch):
        # Jekyll's sanitize_url reads `..` as `/`: /x/../y/ is /x/y/.
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: one\ntitle: One\npermalink: /x/../y/')
        assert 'data-term-url="/x/y/"' in _link('one', load_glossary_terms())


class TestTheGlossaryPagesOwnAddress:
    WARNING = ("  ⚠️ Glossary entry '{}' would be published at /glossary/, the "
               "glossary page's own address. '{}' is not published and cannot "
               "be linked.")

    def test_an_id_with_an_empty_slug_is_not_published(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\n!!!,Bangs,x\nok,Fine,y\n')
        self._glossary_page(tmp_path, 'layout: glossary-index\npermalink: /glossary/')

        terms = generate_glossary()

        assert _written(tmp_path) == ['ok.md']
        assert list(terms) == ['ok']
        assert self.WARNING.format('!!!', '!!!') in capsys.readouterr().out

    def test_a_permalink_at_the_glossary_page_is_not_published(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        self._glossary_page(tmp_path, 'layout: glossary-index\npermalink: /glossary/')
        _legacy(tmp_path, 'a.md', 'term_id: top\ntitle: Top\npermalink: /glossary/index.html')
        terms = generate_glossary()
        assert _written(tmp_path) == []
        assert 'top' not in terms and 'data-term-url' not in _link('top', terms)
        assert self.WARNING.format('top', 'top') in capsys.readouterr().out

    def test_a_demo_id_with_an_empty_slug_is_skipped_and_not_linked(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        self._glossary_page(tmp_path, 'layout: glossary-index\npermalink: /glossary/')
        _demo(tmp_path, ('???', 'Demo'))

        generate_glossary()

        assert _written(tmp_path) == []
        assert ("  ⚠️ Demo glossary term '???' skipped: it would be published at "
                "/glossary/, the glossary page's own address.") in capsys.readouterr().out
        terms = _demo_link_terms({'glossary': {'???': {'term': 'Demo'}}})
        assert '???' not in terms and 'data-term-url' not in _link('???', terms)

    def _glossary_page(self, tmp_path, front_matter, name='pages/glossary.md'):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(f'---\n{front_matter}\n---\n\nx\n', encoding='utf-8')

    def test_the_glossary_pages_own_permalink_is_claimed(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\n!!!,Bangs,x\n')
        self._glossary_page(tmp_path, 'layout: glossary-index\npermalink: /terms/')

        terms = generate_glossary()

        # The glossary page is at /terms/, so /glossary/ is free and the
        # empty-slug row is published there.
        assert _written(tmp_path) == ['!!!.md']
        assert 'data-term-url="/glossary/"' in _link('!!!', terms)
        assert '⚠️ Glossary entry' not in capsys.readouterr().out

    def test_an_entry_at_the_glossary_pages_permalink_is_named_there(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        self._glossary_page(tmp_path, 'layout: glossary-index\npermalink: /terms/')
        _legacy(tmp_path, 'a.md', 'term_id: top\ntitle: Top\npermalink: /terms/index.html')
        _demo(tmp_path, ('???', 'Demo'))

        generate_glossary()

        out = capsys.readouterr().out
        assert _written(tmp_path) == ['???.md']
        assert self.WARNING.format('top', 'top').replace(
            '/glossary/,', '/terms/,') in out

    def test_a_glossary_page_found_by_its_layout_without_a_permalink(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        (tmp_path / '_config.yml').write_text('baseurl: ""\npermalink: pretty\n',
                                              encoding='utf-8')
        self._glossary_page(tmp_path, 'layout: glossary-index', name='pages/glosario.md')
        _legacy(tmp_path, 'a.md', 'term_id: top\ntitle: Top\npermalink: /pages/glosario/')
        generate_glossary()
        assert ("Glossary entry 'top' would be published at /pages/glosario/, "
                "the glossary page's own address.") in capsys.readouterr().out


class TestIdsOneDiskNameHolds:
    """`é` written as one character and as `e` and a combining accent are
    one file and one folder on APFS, which ignores normalization."""

    COMPOSED, DECOMPOSED = 'caf\u00e9', 'cafe\u0301'

    def test_csv_rows_keep_the_first(self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\n'
              f'{self.COMPOSED},First,one\n{self.DECOMPOSED},Second,two\n')

        terms = generate_glossary()

        assert len(_written(tmp_path)) == 1
        assert 'First' in _page(tmp_path, self.COMPOSED)
        assert list(terms) == [self.COMPOSED]
        assert (f"Glossary entries '{self.COMPOSED}' and '{self.DECOMPOSED}' would "
                f"both be published at") in capsys.readouterr().out

    def test_legacy_files_keep_the_first(self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', f'term_id: {self.DECOMPOSED}\ntitle: First\npermalink: /a/')
        _legacy(tmp_path, 'b.md', f'term_id: {self.COMPOSED}\ntitle: Second\npermalink: /b/')

        terms = generate_glossary()

        assert len(_written(tmp_path)) == 1
        assert 'First' in _page(tmp_path, self.DECOMPOSED)
        assert list(terms) == [self.DECOMPOSED]
        assert (f"Glossary entries '{self.DECOMPOSED}' and '{self.COMPOSED}' would "
                f"both be written to the same file") in capsys.readouterr().out

    def test_the_output_file_ignores_normalization(self):
        assert (glossary_output_file(f'/{self.COMPOSED}/')
                == glossary_output_file(f'/{self.DECOMPOSED}/'))


class TestEveryGlossaryPageIsClaimed:
    def _page(self, tmp_path, name, front_matter):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(f'---\n{front_matter}\n---\n\nx\n', encoding='utf-8')

    def test_without_a_glossary_page_nothing_is_claimed(self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\n!!!,Bangs,x\n')
        terms = generate_glossary()
        assert _written(tmp_path) == ['!!!.md']
        assert 'data-term-url="/glossary/"' in _link('!!!', terms)
        assert '⚠️' not in capsys.readouterr().out

    def test_each_glossary_page_is_named_in_its_own_warning(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        (tmp_path / '_config.yml').write_text('baseurl: ""\npermalink: pretty\n',
                                              encoding='utf-8')
        self._page(tmp_path, 'pages/glossary.md', 'layout: glossary-index\npermalink: /glossary/')
        self._page(tmp_path, 'pages/glosario.md', 'layout: glossary-index\npermalink: /glosario/')
        self._page(tmp_path, 'pages/es/glosario.md', 'layout: glossary-index')
        self._page(tmp_path, 'pages/es/lex.md',
                   'layout: glossary-index\npermalink: /lex/:basename/')
        _legacy(tmp_path, 'a.md', 'term_id: a\ntitle: A\npermalink: /glossary/')
        _legacy(tmp_path, 'b.md', 'term_id: b\ntitle: B\npermalink: /glosario/')
        _legacy(tmp_path, 'c.md', 'term_id: c\ntitle: C\npermalink: /pages/es/glosario/')
        _legacy(tmp_path, 'd.md', 'term_id: d\ntitle: D\npermalink: /lex/lex/')
        _legacy(tmp_path, 'e.md', 'term_id: e\ntitle: E\npermalink: /lex/:basename/')

        terms = generate_glossary()

        out = capsys.readouterr().out
        assert list(terms) == ['e']
        for term_id, address in (('a', '/glossary/'), ('b', '/glosario/'),
                                 ('c', '/pages/es/glosario/'), ('d', '/lex/lex/')):
            assert (f"Glossary entry '{term_id}' would be published at {address}, "
                    f"the glossary page's own address.") in out

    def test_only_the_root_and_pages_are_read_as_jekyll_reads_them(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        (tmp_path / '_config.yml').write_text('baseurl: ""\nexclude:\n  - pages/old/\n',
                                              encoding='utf-8')
        self._page(tmp_path, 'pages/old/g.md', 'layout: glossary-index\npermalink: /a/')
        self._page(tmp_path, 'pages/_drafts/g.md', 'layout: glossary-index\npermalink: /b/')
        self._page(tmp_path, 'pages/.hidden/g.md', 'layout: glossary-index\npermalink: /c/')
        self._page(tmp_path, 'pages/g.md',
                   'layout: glossary-index\npublished: false\npermalink: /d/')
        self._page(tmp_path, 'pages/es/terms.markdown', 'layout: glossary-index\npermalink: /e/')
        self._page(tmp_path, 'terms.html', 'layout: glossary-index\npermalink: /f/')
        self._page(tmp_path, 'stuff/g.md', 'layout: glossary-index\npermalink: /g/')
        self._page(tmp_path, 'pages/g.txt', 'layout: glossary-index\npermalink: /h/')
        assert sorted(glossary_index_addresses()) == ['/e/', '/f/']
