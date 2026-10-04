"""
Unit Tests for the demo glossary meeting the site's own glossary

The demo bundle's glossary is written into the same collection as the
site's terms, and several of its ids carry no `demo-` prefix (`viewer`,
`story`, `IIIF`). Jekyll publishes a glossary document at
`/glossary/<slug>/`, where the slug is the file name lower-cased with
every run of punctuation made a hyphen, so a demo term whose slug matches
a site term's would publish at the site term's address. The site's term
has to be the one published there.

Version: v1.8.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.glossary_pages import generate_glossary


DEMO_VIEWER = {'term_id': 'viewer', 'title': 'Viewer',
               'content': '<p>DEMO DEFINITION</p>'}
DEMO_PANEL = {'term_id': 'panel', 'title': 'Panel',
              'content': '<p>Demo panel.</p>'}
DEMO_IIIF = {'term_id': 'IIIF', 'title': 'IIIF',
             'content': '<p>Demo IIIF.</p>'}


def _site(tmp_path, monkeypatch, rows, demo_terms):
    monkeypatch.chdir(tmp_path)
    sheets = tmp_path / 'telar-content' / 'spreadsheets'
    sheets.mkdir(parents=True)
    (sheets / 'glossary.csv').write_text(
        'term_id,title,definition\n' + rows, encoding='utf-8')
    data = tmp_path / '_data'
    data.mkdir()
    (data / 'demo-glossary.json').write_text(
        json.dumps(demo_terms), encoding='utf-8')
    return tmp_path / '_jekyll-files' / '_glossary'


def _pages(glossary_dir):
    return {p.name: p.read_text(encoding='utf-8')
            for p in glossary_dir.glob('*.md')}


class TestTheSiteTermWinsOverTheDemoTerm:

    def test_a_demo_term_with_the_site_terms_id_does_not_replace_it(
            self, tmp_path, monkeypatch):
        glossary_dir = _site(
            tmp_path, monkeypatch,
            'viewer,User Viewer Term,USER-AUTHORED DEFINITION\n',
            [DEMO_VIEWER, DEMO_PANEL])

        generate_glossary()

        page = (glossary_dir / 'viewer.md').read_text(encoding='utf-8')
        assert 'USER-AUTHORED DEFINITION' in page
        assert 'DEMO DEFINITION' not in page
        assert 'demo: true' not in page

    def test_the_demo_terms_that_do_not_collide_are_still_published(
            self, tmp_path, monkeypatch):
        glossary_dir = _site(
            tmp_path, monkeypatch,
            'viewer,User Viewer Term,USER-AUTHORED DEFINITION\n',
            [DEMO_VIEWER, DEMO_PANEL])

        generate_glossary()

        assert 'Demo panel.' in (glossary_dir / 'panel.md').read_text(
            encoding='utf-8')

    def test_the_skipped_demo_term_is_named_in_the_build_output(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch,
              'viewer,User Viewer Term,USER-AUTHORED DEFINITION\n',
              [DEMO_VIEWER, DEMO_PANEL])

        generate_glossary()

        out = capsys.readouterr().out
        skipped = [line for line in out.splitlines() if 'skipped' in line]
        assert len(skipped) == 1
        assert "'viewer'" in skipped[0]
        assert '[DEMO]' not in ''.join(
            line for line in out.splitlines() if 'viewer.md' in line)

    @pytest.mark.parametrize('site_id, demo_term', [
        ('Viewer', DEMO_VIEWER),
        ('iiif', DEMO_IIIF),
        ('Viewer!', DEMO_VIEWER),
    ])
    def test_ids_that_publish_at_the_same_address_collide(
            self, tmp_path, monkeypatch, site_id, demo_term):
        """Jekyll lower-cases the slug and hyphenates punctuation.

        `Viewer.md` and `viewer.md` are two files on a case-sensitive
        disk and one on a case-insensitive one, and either way Jekyll
        renders both at `/glossary/viewer/`, where only one can be served.
        """
        glossary_dir = _site(
            tmp_path, monkeypatch,
            f'{site_id},Site Title,SITE DEFINITION\n', [demo_term])

        generate_glossary()

        pages = _pages(glossary_dir)
        assert len(pages) == 1
        (content,) = pages.values()
        assert 'SITE DEFINITION' in content
        assert 'demo: true' not in content

    def test_without_a_site_glossary_every_demo_term_is_published(
            self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        data = tmp_path / '_data'
        data.mkdir()
        (data / 'demo-glossary.json').write_text(
            json.dumps([DEMO_VIEWER, DEMO_PANEL, DEMO_IIIF]),
            encoding='utf-8')

        generate_glossary()

        pages = _pages(tmp_path / '_jekyll-files' / '_glossary')
        assert sorted(pages) == ['IIIF.md', 'panel.md', 'viewer.md']

    def test_a_legacy_markdown_site_term_also_wins(
            self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        texts = tmp_path / 'telar-content' / 'texts' / 'glossary'
        texts.mkdir(parents=True)
        (texts / 'viewer.md').write_text(
            '---\nterm_id: viewer\ntitle: "User Viewer"\n---\n\n'
            'USER-AUTHORED DEFINITION\n', encoding='utf-8')
        data = tmp_path / '_data'
        data.mkdir()
        (data / 'demo-glossary.json').write_text(
            json.dumps([DEMO_VIEWER]), encoding='utf-8')

        generate_glossary()

        page = (tmp_path / '_jekyll-files' / '_glossary'
                / 'viewer.md').read_text(encoding='utf-8')
        assert 'USER-AUTHORED DEFINITION' in page
        assert 'DEMO DEFINITION' not in page
