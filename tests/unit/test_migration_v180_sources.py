"""
Unit Tests for the v1.8.0 Migration's Edits to Site-Owned Text Files

`v180_sources` edits four kinds of file a site owns: one line in each
built-in page, the `exclude:` list in `_config.yml`, the front matter of
the page sources, and a scalar `related_terms` in glossary markdown. The
`exclude:` edit is tested in test_migration_v180_exclude.py. Each
edit is a text edit, so these tests hold the bytes around it as well as the
edit: comments, key order, quoting, line endings, and a second run that
finds nothing to do. Where YAML is involved they check the parsed result
too, since a text edit that reads differently is the failure being guarded.

Every fixture runs against a temporary site directory.

Version: v1.8.0
"""

import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v180_sources
from migrations.base import ChangeStatus
from migrations.messages import get_message


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _write(root, rel_path, text):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))
    return path


def _read(root, rel_path):
    return (root / rel_path).read_bytes().decode('utf-8')


# ---------- Built-in pages ----------

INDEX_V170 = ('---\nlayout: index\ntitle_key: navigation.home\n---\n\n'
              '{{ lang.index_page.welcome | markdownify }}\n')
GLOSSARY_V170 = ('---\nlayout: glossary-index\npermalink: /glossary/\n---\n\n'
                 '{{ lang.pages.glossary_intro }}\n')


class TestBuiltInPages:

    def test_the_lines_are_the_ones_the_templates_carry(self):
        """Against git, not the working tree: the old line at the v1.7.0
        tag, the new one in this repository's own pages."""
        import subprocess
        for rel_path, old, new in v180_sources.SITE_PAGE_LINES:
            at_tag = subprocess.run(['git', '-C', REPO_ROOT, 'show', f'v1.7.0:{rel_path}'],
                                    capture_output=True, text=True, check=True).stdout
            current = open(os.path.join(REPO_ROOT, rel_path), encoding='utf-8').read()
            assert old in at_tag.splitlines()
            assert new in current.splitlines()

    def test_the_template_lines_are_replaced(self, tmp_path):
        _write(tmp_path, 'index.md', INDEX_V170)
        _write(tmp_path, 'pages/glossary.md', GLOSSARY_V170)

        records = v180_sources.update_site_pages(str(tmp_path), 'en')

        assert _read(tmp_path, 'index.md') == INDEX_V170.replace(
            '{{ lang.index_page.welcome | markdownify }}',
            '{{ lang.index_page.welcome | default: site.data.languages.en.index_page.welcome'
            ' | markdownify }}')
        assert _read(tmp_path, 'pages/glossary.md').endswith(
            '{% include glossary-intro.html lang=lang %}\n')
        assert [r.status for r in records] == [ChangeStatus.APPLIED] * 2
        assert all('Updated' in r.description for r in records)

    def test_a_line_the_owner_changed_is_theirs(self, tmp_path):
        own = INDEX_V170.replace('{{ lang.index_page.welcome | markdownify }}',
                                 'Welcome to my collection.')
        indented = GLOSSARY_V170.replace('{{ lang', '  {{ lang')
        _write(tmp_path, 'index.md', own)
        _write(tmp_path, 'pages/glossary.md', indented)

        records = v180_sources.update_site_pages(str(tmp_path), 'en')

        assert _read(tmp_path, 'index.md') == own
        assert _read(tmp_path, 'pages/glossary.md') == indented
        assert all('its own text' in r.description for r in records)

    def test_crlf_is_kept(self, tmp_path):
        _write(tmp_path, 'index.md', INDEX_V170.replace('\n', '\r\n'))

        v180_sources.update_site_pages(str(tmp_path), 'en')

        text = _read(tmp_path, 'index.md')
        assert text.endswith('| markdownify }}\r\n')
        assert '\n' not in text.replace('\r\n', '')

    def test_a_second_run_changes_nothing(self, tmp_path):
        _write(tmp_path, 'index.md', INDEX_V170)
        _write(tmp_path, 'pages/glossary.md', GLOSSARY_V170)
        v180_sources.update_site_pages(str(tmp_path), 'en')
        first = (_read(tmp_path, 'index.md'), _read(tmp_path, 'pages/glossary.md'))

        records = v180_sources.update_site_pages(str(tmp_path), 'en')

        assert (_read(tmp_path, 'index.md'), _read(tmp_path, 'pages/glossary.md')) == first
        assert all('already has' in r.description for r in records)

    def test_an_absent_page_is_recorded(self, tmp_path):
        records = v180_sources.update_site_pages(str(tmp_path), 'en')

        assert [r.status for r in records] == [ChangeStatus.APPLIED] * 2
        assert all('nothing to update' in r.description for r in records)


# ---------- Page sources ----------

PAGE = '''---
title: About
layout: page
permalink: /about/
title_key: navigation.about # the menu label
---

# About this site
'''


def _page(tmp_path, name, text):
    return _write(tmp_path, f'telar-content/texts/pages/{name}', text)


def _strip(tmp_path):
    return v180_sources.strip_page_sources(str(tmp_path), 'en')


class TestPageSources:

    def test_the_pre_090_pair_goes(self, tmp_path):
        _page(tmp_path, 'about.md', PAGE)

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == (
            '---\ntitle: About\ntitle_key: navigation.about # the menu label\n---\n\n'
            '# About this site\n')
        assert [r.status for r in records] == [ChangeStatus.APPLIED]
        assert '`layout`, `permalink`' in records[0].description

    @pytest.mark.parametrize('value', ['/about', '"/about/"', 'user-page'])
    def test_the_other_redundant_spellings(self, tmp_path, value):
        key = 'layout' if value == 'user-page' else 'permalink'
        _page(tmp_path, 'about.md', f'---\ntitle: About\n{key}: {value}\n---\nBody\n')

        _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == (
            '---\ntitle: About\n---\nBody\n')

    def test_a_custom_layout_is_kept_and_reported(self, tmp_path):
        text = '---\ntitle: About\nlayout: wide\n---\nBody\n'
        _page(tmp_path, 'about.md', text)

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == text
        assert [r.description for r in records] == [
            get_message('en', 'v180_page_key_kept', 'telar-content/texts/pages/about.md',
                        'layout', 'wide', '/about/')]

    def test_a_dropped_key_takes_its_continuation_lines(self, tmp_path):
        _page(tmp_path, 'about.md', '---\ntitle: About\nlayout:\n  page\nnav: 2\n---\nBody\n')

        _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == (
            '---\ntitle: About\nnav: 2\n---\nBody\n')

    @pytest.mark.parametrize('comment', [
        '  # Translator note: keep title in Spanish',
        '    # indented further',
        ' #',
    ])
    def test_a_comment_under_a_removed_key_survives_byte_for_byte(self, tmp_path, comment):
        _page(tmp_path, 'about.md',
              f'---\ntitle: Acerca\nlayout: page\n{comment}\nlanguage: es\n---\nBody\n')

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == (
            f'---\ntitle: Acerca\n{comment}\nlanguage: es\n---\nBody\n')
        assert records[0].status == ChangeStatus.APPLIED

    def test_a_comment_between_continuation_lines_survives(self, tmp_path):
        _page(tmp_path, 'about.md',
              '---\ntitle: About\nlayout:\n  # why\n  page\nnav: 2\n---\nBody\n')

        _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == (
            '---\ntitle: About\n  # why\nnav: 2\n---\nBody\n')

    def test_a_localized_sister_keeps_its_routing_keys_byte_for_byte(self, tmp_path):
        text = ('---\nlocalized_for: about.md\nlanguage: es\ntitle: "Acerca"\n'
                'layout: page\npermalink: /acerca/\n---\nCuerpo\n')
        _page(tmp_path, 'acerca.md', text)

        _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/acerca.md') == (
            '---\nlocalized_for: about.md\nlanguage: es\ntitle: "Acerca"\n---\nCuerpo\n')

    def test_a_custom_permalink_is_kept_and_reported_with_the_real_address(self, tmp_path):
        text = '---\ntitle: About\npermalink: /who-we-are/\n---\nBody\n'
        _page(tmp_path, 'about.md', text)

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == text
        assert [r.description for r in records] == [
            get_message('en', 'v180_page_key_kept', 'telar-content/texts/pages/about.md',
                        'permalink', '/who-we-are/', '/about/')]

    def test_a_list_valued_permalink_is_kept(self, tmp_path):
        text = '---\ntitle: About\npermalink:\n  - /about/\n  - /a/\n---\nBody\n'
        _page(tmp_path, 'about.md', text)

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == text
        assert len(records) == 1 and '`permalink:' in records[0].description

    def test_a_page_without_front_matter_is_left_alone(self, tmp_path):
        _page(tmp_path, 'notes.md', '# Notes\n')

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/notes.md') == '# Notes\n'
        assert records[0].description == get_message('en', 'v180_pages_clean')

    def test_crlf(self, tmp_path):
        _page(tmp_path, 'about.md', PAGE.replace('\n', '\r\n'))

        _strip(tmp_path)

        text = _read(tmp_path, 'telar-content/texts/pages/about.md')
        assert 'layout' not in text and 'permalink' not in text
        assert '\n' not in text.replace('\r\n', '')

    def test_a_second_run_changes_nothing(self, tmp_path):
        _page(tmp_path, 'about.md', PAGE)
        _strip(tmp_path)
        first = _read(tmp_path, 'telar-content/texts/pages/about.md')

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == first
        assert records[0].description == get_message('en', 'v180_pages_clean')

    def test_a_strip_that_would_change_another_key_is_refused(self, tmp_path, monkeypatch):
        """The parse before and after is the guard, not the line walker: a
        walker that took a neighbouring key with it must write nothing."""
        _page(tmp_path, 'about.md', PAGE)
        walker = v180_sources._without_keys
        monkeypatch.setattr(v180_sources, '_without_keys',
                            lambda lines, keys: walker(lines, tuple(keys) + ('title',)))

        records = _strip(tmp_path)

        assert _read(tmp_path, 'telar-content/texts/pages/about.md') == PAGE
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'soft')]


# ---------- Glossary related_terms ----------

def _term(tmp_path, value, extra=''):
    text = f'---\nterm_id: cord\ntitle: Cord\nrelated_terms: {value}\n{extra}---\n\nA cord.\n'
    _write(tmp_path, 'telar-content/texts/glossary/cord.md', text)
    return text


def _terms(tmp_path):
    records = v180_sources.list_related_terms(str(tmp_path), 'en')
    text = _read(tmp_path, 'telar-content/texts/glossary/cord.md')
    front = yaml.safe_load(text.split('---')[1])
    return records, text, front


class TestRelatedTerms:

    def test_the_comma_list(self, tmp_path):
        _term(tmp_path, 'primary-cord, subsidiary-cord')

        records, text, front = _terms(tmp_path)

        assert 'related_terms: ["primary-cord", "subsidiary-cord"]\n' in text
        assert front == {'term_id': 'cord', 'title': 'Cord',
                         'related_terms': ['primary-cord', 'subsidiary-cord']}
        assert records[0].status == ChangeStatus.APPLIED

    @pytest.mark.parametrize('value, expected', [
        ('primary-cord', ['primary-cord']),
        ('primary-cord | subsidiary-cord', ['primary-cord', 'subsidiary-cord']),
        ('"primary-cord, subsidiary-cord"', ['primary-cord', 'subsidiary-cord']),
        ('primary-cord,, subsidiary-cord,', ['primary-cord', 'subsidiary-cord']),
    ])
    def test_the_other_shapes(self, tmp_path, value, expected):
        _term(tmp_path, value)

        _records, _text, front = _terms(tmp_path)

        assert front['related_terms'] == expected

    @pytest.mark.parametrize('value', ['', '[]', '["a"]'])
    def test_empty_or_already_a_list_is_left_alone(self, tmp_path, value):
        text = _term(tmp_path, value)

        records, after, _front = _terms(tmp_path)

        assert after == text
        assert records[0].description == get_message('en', 'v180_glossary_clean')

    @pytest.mark.parametrize('value, extra', [
        ('|\n  a, b', ''),
        ('>\n  a, b', ''),
        ('&terms a, b', ''),
        ('!!str a, b', ''),
        ('a,\n  b', ''),
        ('a, b', 'related_terms: c, d\n'),
        ('a, b # the neighbours', ''),
    ], ids=['literal', 'folded', 'anchor', 'tag', 'continuation', 'duplicate', 'comment'])
    def test_refused_and_reported(self, tmp_path, value, extra):
        text = _term(tmp_path, value, extra)

        records = v180_sources.list_related_terms(str(tmp_path), 'en')

        assert _read(tmp_path, 'telar-content/texts/glossary/cord.md') == text
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'soft')]

    def test_a_key_written_twice_has_no_line_to_rewrite(self):
        lines = ['related_terms: a, b\n', 'title: T\n', 'related_terms: c\n']

        assert v180_sources._related_terms_line(lines) is None
        assert v180_sources._related_terms_line(lines[:2]) == 0

    def test_crlf(self, tmp_path):
        text = '---\r\nterm_id: cord\r\nrelated_terms: a, b\r\n---\r\nA cord.\r\n'
        _write(tmp_path, 'telar-content/texts/glossary/cord.md', text)

        v180_sources.list_related_terms(str(tmp_path), 'en')

        assert _read(tmp_path, 'telar-content/texts/glossary/cord.md') == text.replace(
            'related_terms: a, b', 'related_terms: ["a", "b"]')

    def test_a_second_run_changes_nothing(self, tmp_path):
        _term(tmp_path, 'primary-cord, subsidiary-cord')
        _terms(tmp_path)
        first = _read(tmp_path, 'telar-content/texts/glossary/cord.md')

        records, text, _front = _terms(tmp_path)

        assert text == first
        assert records[0].description == get_message('en', 'v180_glossary_clean')

    def test_the_glossary_generator_reads_the_rewritten_value_as_a_list(self, tmp_path):
        from telar.frontmatter import FRONTMATTER_PATTERN
        _term(tmp_path, 'primary-cord, subsidiary-cord')
        _terms(tmp_path)

        match = FRONTMATTER_PATTERN.match(_read(tmp_path, 'telar-content/texts/glossary/cord.md'))

        assert yaml.safe_load(match.group(1))['related_terms'] == [
            'primary-cord', 'subsidiary-cord']
