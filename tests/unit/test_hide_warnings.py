"""
Unit Tests for `development-features.hide_warnings`

A site can keep build warnings off its published pages. Two parts of that
live in Python and are tested here: reading the switch from `_config.yml`,
and the marker the glossary pass writes for an entry the glossary lacks,
which becomes the text as written while the warning is still reported. The
layouts' guards are checked by building a site with the switch on and off.

Version: v1.8.1
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.config import warnings_hidden
from telar.glossary import process_glossary_links


def _site(tmp_path, monkeypatch, config):
    if config is not None:
        (tmp_path / '_config.yml').write_text(config, encoding='utf-8')
    monkeypatch.chdir(tmp_path)


ON = 'development-features:\n  hide_warnings: true\n'
OFF = 'development-features:\n  hide_warnings: false\n'


class TestTheSwitch:

    def test_on(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, ON)
        assert warnings_hidden() is True

    @pytest.mark.parametrize('config', [
        OFF,
        'development-features:\n  christmas_tree_mode: false\n',
        'development-features:\n',
        'title: Site\n',
        'development-features:\n  hide_warnings: "yes"\n',
        ': not yaml [\n',
        None,
    ])
    def test_off_unless_set_to_true(self, tmp_path, monkeypatch, config):
        _site(tmp_path, monkeypatch, config)
        assert warnings_hidden() is False


class TestAMissingGlossaryEntry:

    def test_shows_the_marker_by_default(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, OFF)
        warnings = []

        out = process_glossary_links('<p>See [[absent]].</p>', {'telar': 'Telar'}, warnings, 1, 'layer1')

        assert 'glossary-link-error' in out
        assert len(warnings) == 1

    def test_is_the_text_as_written_when_hidden(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, ON)
        warnings = []

        out = process_glossary_links('<p>See [[absent]].</p>', {'telar': 'Telar'}, warnings, 1, 'layer1')

        assert out == '<p>See absent.</p>'
        assert [w['term_id'] for w in warnings] == ['absent']

    def test_keeps_its_display_text_when_hidden(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, ON)

        out = process_glossary_links('<p>[[the map|absent]]</p>', {'telar': 'Telar'})

        assert out == '<p>the map</p>'

    def test_a_present_entry_is_still_linked_when_hidden(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, ON)

        out = process_glossary_links('<p>[[telar]]</p>', {'telar': 'Telar'})

        assert 'glossary-inline' in out or 'data-term-id="telar"' in out
        assert 'glossary-link-error' not in out
