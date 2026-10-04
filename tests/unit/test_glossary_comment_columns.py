"""
Every glossary reader reads glossary.csv the same way: instruction columns
and a bilingual second header row are ignored by all of them.

A column whose header starts with `#` is the author's note. `csv_to_json`,
which reads glossary.csv as a story sheet, drops such columns before it
checks for two columns claiming one name; both glossary readers have to do
the same, or `#note` beside `#Note` stops the build in one reader while the
others, and the upgrade's column check, pass the same file.

Version: v1.8.0
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.glossary import load_glossary_terms
from telar.glossary_pages import _generate_glossary_from_csv


SHEET = ('term_id,title,definition,#note,#Note\n'
         'encomienda,Encomienda,A grant of labour from a community,,\n')


def _write(tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text(SHEET, encoding='utf-8')
    return path


def _site_sheet(tmp_path, text):
    folder = tmp_path / 'telar-content' / 'spreadsheets'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'glossary.csv').write_text(text, encoding='utf-8')


class TestCommentColumnsAreIgnored:
    def test_the_story_conversion_accepts_the_sheet(self, tmp_path):
        assert csv_to_json(str(_write(tmp_path)), str(tmp_path / 'out.json')) is True

    def test_the_link_map_reads_the_term(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _site_sheet(tmp_path, SHEET)
        assert 'encomienda' in load_glossary_terms()

    def test_the_page_generator_writes_the_term(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / 'pages'
        out.mkdir()
        _generate_glossary_from_csv(_write(tmp_path), out, {})
        assert (out / 'encomienda.md').exists()


class TestTheSecondHeaderRowIsNotATerm:
    """A bilingual glossary.csv carries its Spanish header as the first row;
    the link map skips it as the page generator does."""

    SHEET = ('term_id,title,definition\n'
             'id_término,titulo,definición\n'
             'encomienda,Encomienda,A grant of labour from a community\n')

    def test_the_link_map_holds_only_the_terms(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _site_sheet(tmp_path, self.SHEET)
        assert load_glossary_terms() == {'encomienda': 'Encomienda'}

    def test_the_page_generator_agrees(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = tmp_path / 'glossary.csv'
        path.write_text(self.SHEET, encoding='utf-8')
        out = tmp_path / 'pages'
        out.mkdir()
        _generate_glossary_from_csv(path, out, {})
        assert sorted(p.name for p in out.iterdir()) == ['encomienda.md']
