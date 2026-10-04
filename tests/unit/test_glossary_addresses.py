"""
A Glossary Link Goes to the Address Its Page Is Published At

A legacy glossary file with a `permalink` of its own is published there,
not at `/glossary/<slug>/`, and two term ids that make one slug claim one
address. The link map and the pages the generator writes agree on both: a
link uses the page's own address, and of ids sharing an address the first
(sheet order, or file-name order for markdown) is published and linkable
while the later ones are neither, with one warning naming both.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.demo import _demo_link_terms
from telar.glossary import load_glossary_terms, process_glossary_links
from telar.glossary_pages import generate_glossary
from telar.widgets import reset_base_url_cache

SPREADSHEETS = 'telar-content/spreadsheets'
LEGACY = 'telar-content/texts/glossary'


@pytest.fixture(autouse=True)
def _fresh_base_url():
    reset_base_url_cache()
    yield
    reset_base_url_cache()


def _site(tmp_path, monkeypatch, csv=None, baseurl=''):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text(f'baseurl: "{baseurl}"\n', encoding='utf-8')
    if csv is not None:
        (tmp_path / SPREADSHEETS).mkdir(parents=True)
        (tmp_path / SPREADSHEETS / 'glossary.csv').write_text(csv, encoding='utf-8')


def _legacy(tmp_path, name, front_matter):
    folder = tmp_path / LEGACY
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f'---\n{front_matter}\n---\n\nBody.\n', encoding='utf-8')


def _link(term_id, terms, base_url=''):
    return process_glossary_links(f'See [[{term_id}]].', terms, [], base_url=base_url)


def _written(tmp_path):
    return sorted(p.name for p in (tmp_path / '_jekyll-files/_glossary').glob('*.md'))


class TestALegacyPermalinkIsTheLinkAddress:
    def test_the_link_goes_to_the_permalink(self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')

        terms = generate_glossary()

        assert 'data-term-url="/other/"' in _link('old', terms)
        page = (tmp_path / '_jekyll-files/_glossary/old.md').read_text(encoding='utf-8')
        assert 'permalink: /other/' in page

    def test_the_link_map_read_per_story_agrees(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')
        assert 'data-term-url="/other/"' in _link('old', load_glossary_terms())

    def test_the_baseurl_is_put_in_front_of_the_permalink(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, baseurl='/site')
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')
        html = _link('old', load_glossary_terms(), base_url='/site')
        assert 'data-term-url="/site/other/"' in html

    @pytest.mark.parametrize('written', ['other/', '/other/', '//other/', '"/other/"'])
    def test_a_permalink_without_the_leading_slash_is_read_as_jekyll_does(
            self, tmp_path, monkeypatch, written):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', f'term_id: old\ntitle: Old\npermalink: {written}')
        assert 'data-term-url="/other/"' in _link('old', load_glossary_terms())

    def test_a_file_without_a_permalink_is_linked_at_its_slug(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'plain.md', 'term_id: Plain_Term\ntitle: Plain')
        assert 'data-term-url="/glossary/plain-term/"' in _link('Plain_Term', load_glossary_terms())

    def test_a_callout_uses_the_permalink_too(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')
        terms = load_glossary_terms()
        assert terms.addresses == {'old': '/other/'}

    def test_two_files_at_one_permalink_keep_the_first_by_file_name(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'b.md', 'term_id: b\ntitle: B\npermalink: /same/')
        _legacy(tmp_path, 'a.md', 'term_id: a\ntitle: A\npermalink: /same/')

        terms = generate_glossary()

        assert list(terms) == ['a']
        assert _written(tmp_path) == ['a.md']
        assert "'a' and 'b' would both be published at /same/" in capsys.readouterr().out


class TestIdsThatShareASlug:
    CSV = 'term_id,title,definition\na b,First,one\na-b,Second,two\n'

    def test_the_first_row_keeps_the_address_and_the_link_map_agrees(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, self.CSV)

        terms = generate_glossary()

        assert _written(tmp_path) == ['a b.md']
        assert list(terms) == ['a b']
        assert 'data-term-id="a b"' in _link('a b', terms)
        assert 'glossary-link-error' in _link('a-b', terms)

    def test_the_build_reports_it_once_with_both_ids_and_the_address(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, self.CSV)
        load_glossary_terms()
        generate_glossary()
        out = capsys.readouterr().out
        assert out.count("Glossary entries 'a b' and 'a-b' would both be published at "
                         "/glossary/a-b/. 'a b' keeps that address; 'a-b' is not "
                         "published and cannot be linked.") == 1

    def test_the_per_story_link_map_is_silent_and_agrees(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, self.CSV)
        terms = load_glossary_terms()
        assert list(terms) == ['a b']
        assert capsys.readouterr().out == ''

    @pytest.mark.parametrize('rows,kept', [
        ('Viewer,First,one\nviewer,Second,two\n', 'Viewer.md'),
        ('viewer,First,one\nViewer,Second,two\n', 'viewer.md'),
    ])
    def test_ids_differing_in_case_collide(self, tmp_path, monkeypatch, rows, kept):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\n' + rows)
        terms = generate_glossary()
        assert _written(tmp_path) == [kept]
        assert len(terms) == 1

    def test_markdown_files_keep_the_first_by_file_name(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'z.md', 'term_id: a-b\ntitle: Second')
        _legacy(tmp_path, 'y.md', 'term_id: a_b\ntitle: First')

        terms = generate_glossary()

        assert list(terms) == ['a_b']
        assert _written(tmp_path) == ['a_b.md']
        assert "'a_b' and 'a-b'" in capsys.readouterr().out

    def test_a_permalinked_page_does_not_take_a_slug_address(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: a_b\ntitle: First\npermalink: /elsewhere/')
        _legacy(tmp_path, 'b.md', 'term_id: a-b\ntitle: Second')
        terms = generate_glossary()
        assert list(terms) == ['a_b', 'a-b']


class TestTheDemoPathFollowsTheSameRule:
    def _bundle(self, *ids):
        return {'glossary': {i: {'term': i.upper()} for i in ids}}

    def test_a_legacy_permalink_is_the_address_of_the_site_term(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')
        terms = _demo_link_terms(self._bundle('demo-x'))
        assert 'data-term-url="/other/"' in _link('old', terms)
        assert 'data-term-url="/glossary/demo-x/"' in _link('demo-x', terms)

    def test_a_demo_id_at_a_permalinked_site_term_slug_stays_its_own(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')
        terms = _demo_link_terms(self._bundle('old'))
        # The site's page is at /other/, so nothing of the demo's is at
        # /glossary/old/ to displace: the id names the site's page.
        assert 'data-term-url="/other/"' in _link('old', terms)

    def test_demo_ids_sharing_a_slug_link_to_the_first(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        terms = _demo_link_terms(self._bundle('demo-a b', 'demo-a-b'))
        assert list(terms) == ['demo-a b', 'demo-a-b']
        assert terms['demo-a-b'] == terms['demo-a b']
        assert 'data-term-url="/glossary/demo-a-b/"' in _link('demo-a-b', terms)

    def test_a_site_term_at_a_demo_terms_slug_replaces_it(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\nViewer,Site viewer,x\n')
        terms = _demo_link_terms(self._bundle('viewer'))
        assert terms['viewer'] == 'Site viewer'

    def test_the_generator_skips_a_demo_term_at_a_site_permalink(
            self, tmp_path, monkeypatch):
        import json
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'old.md', 'term_id: old\ntitle: Old\npermalink: /glossary/viewer/')
        (tmp_path / '_data').mkdir()
        (tmp_path / '_data/demo-glossary.json').write_text(json.dumps(
            [{'term_id': 'viewer', 'title': 'V', 'content': 'x'}]), encoding='utf-8')
        generate_glossary()
        assert _written(tmp_path) == ['old.md']


class TestADemoTermDoesNotReplaceASitePageFile:
    """A demo term is written to `_glossary/<term_id>.md`, so a site page in
    that file is replaced even when the site page is published elsewhere
    by its own permalink. The file name is compared as a case-insensitive
    disk holds it."""

    def _demo(self, tmp_path, term_id):
        import json
        (tmp_path / '_data').mkdir()
        (tmp_path / '_data/demo-glossary.json').write_text(json.dumps(
            [{'term_id': term_id, 'title': 'Demo', 'content': 'demo text'}]),
            encoding='utf-8')

    @pytest.mark.parametrize('site_id,demo_id', [('old', 'old'), ('Old', 'old')])
    def test_the_site_page_is_kept_and_linked(
            self, tmp_path, monkeypatch, capsys, site_id, demo_id):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, f'{site_id}.md',
                f'term_id: {site_id}\ntitle: Old\npermalink: /other/')
        self._demo(tmp_path, demo_id)

        terms = generate_glossary()

        assert _written(tmp_path) == [f'{site_id}.md']
        page = (tmp_path / f'_jekyll-files/_glossary/{site_id}.md').read_text(encoding='utf-8')
        assert 'permalink: /other/' in page
        assert 'demo text' not in page
        assert 'data-term-url="/other/"' in _link(site_id, terms)
        assert (f"Demo glossary term '{demo_id}' skipped: the site's glossary "
                f"term '{site_id}' is written to the same file, "
                f"_glossary/{site_id}.md, which is kept.") in capsys.readouterr().out

    def test_a_name_the_disk_folds_to_a_site_file_is_skipped_and_linked_there(
            self, tmp_path, monkeypatch, capsys):
        # A case-insensitive disk (APFS here) holds Straße.md and Strasse.md
        # as one file, and glossary/straße/ and glossary/strasse/ as one
        # folder, so the output file is taken first.
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'Straße.md', 'term_id: Straße\ntitle: Street')
        self._demo(tmp_path, 'Strasse')

        generate_glossary()

        assert _written(tmp_path) == ['Straße.md']
        assert ("Demo glossary term 'Strasse' skipped: another glossary term is "
                "published at /glossary/straße/, which is kept."
                ) in capsys.readouterr().out
        terms = _demo_link_terms({'glossary': {'Strasse': {'term': 'Demo'}}})
        assert terms['Strasse'] == 'Street'

    def test_of_two_demo_terms_in_one_file_the_first_is_kept_and_named(
            self, tmp_path, monkeypatch, capsys):
        import json
        _site(tmp_path, monkeypatch)
        (tmp_path / '_data').mkdir()
        (tmp_path / '_data/demo-glossary.json').write_text(json.dumps(
            [{'term_id': 'Straße', 'title': 'Street', 'content': 'a'},
             {'term_id': 'Strasse', 'title': 'Other', 'content': 'b'}]),
            encoding='utf-8')

        generate_glossary()

        assert _written(tmp_path) == ['Straße.md']
        assert ("Demo glossary term 'Strasse' skipped: another glossary term is "
                "published at /glossary/straße/, which is kept."
                ) in capsys.readouterr().out
        terms = _demo_link_terms({'glossary': {'Straße': {'term': 'Street'},
                                               'Strasse': {'term': 'Other'}}})
        assert terms['Strasse'] == 'Street'
        assert terms.addresses['Strasse'] == terms.addresses.get(
            'Straße', '/glossary/straße/')

    def test_a_demo_story_links_the_demo_id_to_the_site_page(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'Old.md', 'term_id: Old\ntitle: Old\npermalink: /other/')
        terms = _demo_link_terms({'glossary': {'old': {'term': 'Demo'}}})
        # [[old]] is looked up case-insensitively and the site's key is
        # entered last, so the link names the site's page.
        assert 'data-term-url="/other/"' in _link('old', terms)


def _published(tmp_path):
    """{address: (term_id, title)} of the pages the generator wrote, each at
    the address Jekyll publishes it at."""
    import yaml
    from telar.glossary import glossary_term_address, markdown_glossary_permalink
    pages = {}
    for path in (tmp_path / '_jekyll-files/_glossary').glob('*.md'):
        front_matter = path.read_text(encoding='utf-8').split('---\n')[1]
        fields = yaml.safe_load(front_matter)
        term_id = str(fields['term_id'])
        address = glossary_term_address(term_id, markdown_glossary_permalink(front_matter))
        pages[address] = (term_id, str(fields.get('title') or term_id))
    return pages


# (site legacy files as (file name, front matter), site CSV, demo ids)
_SITES = {
    'legacy Straße': ([('Straße.md', 'term_id: Straße\ntitle: Street')], None),
    'legacy X at /glossary/straße/': (
        [('x.md', 'term_id: X\ntitle: Site X\npermalink: /glossary/straße/')], None),
    'legacy a_b at /elsewhere/': (
        [('a.md', 'term_id: a_b\ntitle: Site AB\npermalink: /elsewhere/')], None),
    'legacy old at /other/': (
        [('old.md', 'term_id: old\ntitle: Old\npermalink: /other/')], None),
    'legacy Old at /other/': (
        [('Old.md', 'term_id: Old\ntitle: Old\npermalink: /other/')], None),
    'legacy old at /glossary/viewer/': (
        [('old.md', 'term_id: old\ntitle: Old\npermalink: /glossary/viewer/')], None),
    'csv Viewer': ([], 'term_id,title,definition\nViewer,Site viewer,x\n'),
    'csv a b, a-b': ([], 'term_id,title,definition\na b,First,one\na-b,Second,two\n'),
    'csv Straße': ([], 'term_id,title,definition\nStraße,Street,x\n'),
    'none': ([], None),
}

_DEMOS = [
    ('Strasse',), ('Straße', 'Strasse'), ('Strasse', 'Straße'),
    ('a_b', 'a-b'), ('a-b', 'a_b'), ('demo-x',), ('old',), ('Old', 'old'),
    ('demo-a b', 'demo-a-b'), ('viewer',), ('viewer', 'Viewer'),
    ('a_b',), ('strasse', 'Strasse', 'Straße'),
]


class TestTheLinkMapNamesOnlyPagesTheGeneratorWrote:
    """For every site and every ordering of demo ids, each demo id the link
    map resolves goes to a page the generator wrote, at the address that
    page is published at, and shows that page's title; a demo id whose own
    page was written is linked to it; any other demo id is not linked."""

    @pytest.mark.parametrize('site', sorted(_SITES))
    @pytest.mark.parametrize('demo_ids', _DEMOS, ids='/'.join)
    def test_every_link_is_to_a_written_page(self, tmp_path, monkeypatch, site, demo_ids):
        import html
        import json
        import re
        legacy, csv = _SITES[site]
        _site(tmp_path, monkeypatch, csv)
        for name, front_matter in legacy:
            _legacy(tmp_path, name, front_matter)
        (tmp_path / '_data').mkdir()
        (tmp_path / '_data/demo-glossary.json').write_text(json.dumps(
            [{'term_id': i, 'title': f'Demo {i}', 'content': i} for i in demo_ids]),
            encoding='utf-8')

        generate_glossary()
        published = _published(tmp_path)
        terms = _demo_link_terms({'glossary': {i: {'term': f'Demo {i}'} for i in demo_ids}})

        own = {term_id: address for address, (term_id, _title) in published.items()}
        for demo_id in demo_ids:
            link = _link(demo_id, terms)
            url = re.search(r'data-term-url="([^"]*)"', link)
            if url is None:
                assert 'glossary-link-error' in link
                assert demo_id not in own, (demo_id, published)
                continue
            address = html.unescape(url.group(1))
            assert address in published, (demo_id, address, published)
            assert f'>{html.escape(published[address][1])}<' in link, (demo_id, link, published)
            if demo_id in own:
                assert address == own[demo_id], (demo_id, address, published)


class TestASkippedDemoTermLeavesItsAddressAndFileFree:
    """Only a page that is written holds its address and its file, so a demo
    term skipped for one of them does not keep a later demo term out."""

    def _run(self, tmp_path, demo_ids):
        import json
        (tmp_path / '_data').mkdir()
        (tmp_path / '_data/demo-glossary.json').write_text(json.dumps(
            [{'term_id': i, 'title': f'Demo {i}', 'content': i} for i in demo_ids]),
            encoding='utf-8')
        generate_glossary()
        return _demo_link_terms({'glossary': {i: {'term': f'Demo {i}'} for i in demo_ids}})

    def test_a_term_skipped_for_its_file_leaves_its_address(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'a.md', 'term_id: a_b\ntitle: Site AB\npermalink: /elsewhere/')
        terms = self._run(tmp_path, ['a_b', 'a-b'])
        assert _written(tmp_path) == ['a-b.md', 'a_b.md']
        assert 'data-term-url="/elsewhere/"' in _link('a_b', terms)
        assert 'data-term-url="/glossary/a-b/"' in _link('a-b', terms)

    def test_ids_sharing_a_file_share_an_output_folder_too(self, tmp_path, monkeypatch):
        # Ids that casefold alike make slugs that casefold alike, so a demo
        # term skipped for its address cannot leave a file another demo id
        # could take: glossary/strasse/ is the folder glossary/straße/ is.
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'x.md', 'term_id: X\ntitle: Site X\npermalink: /glossary/straße/')
        terms = self._run(tmp_path, ['Straße', 'Strasse'])
        assert _written(tmp_path) == ['X.md']
        assert 'data-term-url="/glossary/straße/"' in _link('Straße', terms)
        assert 'data-term-url="/glossary/straße/"' in _link('Strasse', terms)
        assert '>Site X<' in _link('Strasse', terms)

    def test_a_term_skipped_for_a_site_file_links_at_the_site_pages_slug(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy(tmp_path, 'Straße.md', 'term_id: Straße\ntitle: Street')
        terms = self._run(tmp_path, ['Strasse'])
        assert _written(tmp_path) == ['Straße.md']
        assert 'data-term-url="/glossary/straße/"' in _link('Strasse', terms)
