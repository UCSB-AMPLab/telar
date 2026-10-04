"""
Unit Tests for the v1.8.0 Migration's Edits to Site-Owned Text Files

`v180_sources` edits four kinds of file a site owns: one line in each
built-in page, the `exclude:` list in `_config.yml`, the front matter of
the page sources, and a scalar `related_terms` in glossary markdown. Each
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


# ---------- _config.yml exclude entries ----------

CONFIG_BLOCK = '''title: My site
# Build Settings
exclude:
  - Gemfile
  # The vendored gems.
  - vendor
  - scripts/

# Defaults
defaults: []
'''

TESTS_GROUP = (
    "  # Telar's own test suite and the configuration that runs it. Nothing on a\n"
    "  # site links to any of it, and a fixture is content written to be wrong in\n"
    "  # a particular way — published, it is indistinguishable from the site's own.\n"
    '  - tests/\n'
    '  - pytest.ini\n'
    '  - vitest.config.js\n'
)
TEXTS_GROUP = (
    '  # Page, story and glossary sources. The build reads them and generates the\n'
    '  # published pages from them; Jekyll rendering them as well puts a raw,\n'
    '  # unprocessed copy of every one at a second URL, and a source that declares\n'
    '  # its own permalink lands on top of the page generated from it.\n'
    '  - telar-content/texts/\n'
)
ALL_FOUR = TESTS_GROUP + TEXTS_GROUP
FLOW = 'tests/, pytest.ini, vitest.config.js, telar-content/texts/'


def _config(tmp_path, text):
    _write(tmp_path, '_config.yml', text)
    return v180_sources.add_exclude_entries(str(tmp_path), 'en')


def _excluded(tmp_path):
    return yaml.safe_load(_read(tmp_path, '_config.yml'))['exclude']


class TestExcludeEntries:

    def test_the_entries_are_the_templates(self):
        assert v180_sources.EXCLUDE_ENTRIES == (
            'tests/', 'pytest.ini', 'vitest.config.js', 'telar-content/texts/')
        template = yaml.safe_load(open(os.path.join(REPO_ROOT, '_config.yml'), encoding='utf-8'))
        assert set(v180_sources.EXCLUDE_ENTRIES) <= set(template['exclude'])

    def test_the_comments_are_the_templates(self):
        template = open(os.path.join(REPO_ROOT, '_config.yml'), encoding='utf-8').read()
        for group in v180_sources.EXCLUDE_GROUPS:
            assert '\n'.join('  ' + line for line in group['comment']) in template

    def test_a_block_list_gains_all_four_once(self, tmp_path):
        records = _config(tmp_path, CONFIG_BLOCK)

        assert _excluded(tmp_path) == ['Gemfile', 'vendor', 'scripts/', 'tests/', 'pytest.ini',
                                       'vitest.config.js', 'telar-content/texts/']
        text = _read(tmp_path, '_config.yml')
        assert text.startswith(CONFIG_BLOCK.split('\n\n# Defaults')[0])
        assert text.endswith('\n\n# Defaults\ndefaults: []\n')
        assert "  # Telar's own test suite" in text
        assert '  # Page, story and glossary sources.' in text
        assert [r.status for r in records] == [ChangeStatus.APPLIED]

    def test_applied_twice_inserts_once(self, tmp_path):
        _config(tmp_path, CONFIG_BLOCK)
        first = _read(tmp_path, '_config.yml')

        records = v180_sources.add_exclude_entries(str(tmp_path), 'en')

        assert _read(tmp_path, '_config.yml') == first
        assert 'already excludes' in records[0].description

    def test_the_template_itself_needs_nothing(self, tmp_path):
        template = open(os.path.join(REPO_ROOT, '_config.yml'), encoding='utf-8').read()

        _config(tmp_path, template)

        assert _read(tmp_path, '_config.yml') == template

    def test_an_unindented_list(self, tmp_path):
        _config(tmp_path, 'exclude:\n- Gemfile\n- vendor\ntitle: x\n')

        assert _excluded(tmp_path)[-1] == 'telar-content/texts/'
        assert '\n- telar-content/texts/\ntitle: x\n' in _read(tmp_path, '_config.yml')

    @pytest.mark.parametrize('present', ['tests', 'tests/', '"tests/"', "'tests'"])
    def test_an_entry_already_present_is_not_added_again(self, tmp_path, present):
        _config(tmp_path, f'exclude:\n  - {present}\n')

        text = _read(tmp_path, '_config.yml')
        assert _excluded(tmp_path)[0].rstrip('/') == 'tests'
        assert _excluded(tmp_path)[1:] == ['pytest.ini', 'vitest.config.js',
                                           'telar-content/texts/']
        assert "Telar's own test suite" not in text

    @pytest.mark.parametrize('present', [
        '"telar-content/texts/ "', '" telar-content/texts/"', '"telar-content/texts//"',
        'Telar-content/texts/',
    ], ids=['trailing-space', 'leading-space', 'double-slash', 'case'])
    def test_presence_is_the_parsed_string_exactly(self, tmp_path, present):
        """Only quotes (by parsing) and one trailing slash are forgiven."""
        _config(tmp_path, f'exclude:\n  - {present}\n  - tests/\n  - pytest.ini\n'
                          '  - vitest.config.js\n')

        assert _excluded(tmp_path)[-1] == 'telar-content/texts/'

    @pytest.mark.parametrize('present', ['telar-content/texts', "'telar-content/texts/'"])
    def test_one_trailing_slash_and_quotes_are_the_same_entry(self, tmp_path, present):
        text = (f'exclude:\n  - {present}\n  - tests/\n  - pytest.ini\n'
                '  - vitest.config.js\n')

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == text
        assert 'already excludes' in records[0].description

    @pytest.mark.parametrize('item, parsed', [
        ('{path: vendor}', {'path': 'vendor'}),
        ('[tests/, x]', ['tests/', 'x']),
        ('3', 3),
    ], ids=['dict', 'list', 'number'])
    def test_an_item_that_is_not_a_string_is_skipped_not_fatal(self, tmp_path, item, parsed):
        """It cannot be a path, so it is never present, and the entries go
        in after it."""
        records = _config(tmp_path, f'exclude:\n  - {item}\n')

        assert _excluded(tmp_path) == [parsed] + list(v180_sources.EXCLUDE_ENTRIES)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]

    def test_a_matching_line_outside_exclude_does_not_count(self, tmp_path):
        _config(tmp_path, 'include:\n  - tests/\nexclude:\n  - vendor\n')

        assert _excluded(tmp_path) == ['vendor', 'tests/', 'pytest.ini', 'vitest.config.js',
                                       'telar-content/texts/']

    def test_an_empty_exclude_key(self, tmp_path):
        _config(tmp_path, 'exclude:\ntitle: x\n')

        assert _excluded(tmp_path) == list(v180_sources.EXCLUDE_ENTRIES)

    def test_crlf_and_no_final_newline(self, tmp_path):
        _config(tmp_path, 'exclude:\r\n  - vendor')

        text = _read(tmp_path, '_config.yml')
        assert '\n' not in text.replace('\r\n', '')
        assert _excluded(tmp_path)[-1] == 'telar-content/texts/'

    @pytest.mark.parametrize('text, expected', [
        ('title: x\nexclude:\n  - vendor\n', ['vendor']),
        ('title: x\nexclude: [Gemfile, vendor]\n', ['Gemfile', 'vendor']),
        ('title: x\nexclude: [\n  Gemfile,\n  vendor,\n]\nnext: 1\n', ['Gemfile', 'vendor']),
        ('title: x\nexclude: []\n', []),
        ('title: x\n', []),
        ('title: x', []),
    ], ids=['block', 'flow', 'flow-multiline', 'flow-empty', 'missing', 'missing-no-newline'])
    def test_each_shape_twice(self, tmp_path, text, expected):
        """The shapes the Compositor's `yaml_list_add` takes: appended to a
        block list, inserted inside a flow list, added as a block key."""
        first = _config(tmp_path, text)
        once = _read(tmp_path, '_config.yml')
        second = v180_sources.add_exclude_entries(str(tmp_path), 'en')

        config = yaml.safe_load(once)
        assert config['exclude'] == expected + list(v180_sources.EXCLUDE_ENTRIES)
        assert config['title'] == 'x'
        assert _read(tmp_path, '_config.yml') == once
        assert [r.status for r in first + second] == [ChangeStatus.APPLIED] * 2
        assert 'already excludes' in second[0].description

    def test_a_flow_list_keeps_its_line(self, tmp_path):
        _config(tmp_path, 'exclude: [Gemfile, vendor] # built files\ntitle: x\n')

        assert _read(tmp_path, '_config.yml') == (
            'exclude: [Gemfile, vendor, tests/, pytest.ini, vitest.config.js, '
            'telar-content/texts/] # built files\ntitle: x\n')

    def test_a_missing_key_is_added_as_a_block_with_the_comments(self, tmp_path):
        _config(tmp_path, 'title: x\n')

        text = _read(tmp_path, '_config.yml')
        assert text.startswith('title: x\n\nexclude:\n  # Telar')
        assert text.endswith('  - telar-content/texts/\n')

    @pytest.mark.parametrize('text, written, expected', [
        ('exclude: vendor\ntitle: x\n',
         'exclude:\n  - vendor\n' + ALL_FOUR + 'title: x\n', ['vendor']),
        ("exclude: 'vendor'\ntitle: x\n",
         "exclude:\n  - 'vendor'\n" + ALL_FOUR + 'title: x\n', ['vendor']),
        ('exclude: "vendor"\ntitle: x\n',
         'exclude:\n  - "vendor"\n' + ALL_FOUR + 'title: x\n', ['vendor']),
        ('exclude: vendor  # built gems\ntitle: x\n',
         'exclude: # built gems\n  - vendor\n' + ALL_FOUR + 'title: x\n', ['vendor']),
        ('exclude: "a #b" # note\n',
         'exclude: # note\n  - "a #b"\n' + ALL_FOUR, ['a #b']),
        ('exclude: 3\n', 'exclude:\n  - 3\n' + ALL_FOUR, [3]),
        ('title: x\r\nexclude: vendor\r\n',
         'title: x\r\nexclude:\r\n  - vendor\r\n' + ALL_FOUR.replace('\n', '\r\n'),
         ['vendor']),
        ('exclude: >\n  vendor\ntitle: x\n',
         'exclude:\n  - "vendor\\n"\n' + ALL_FOUR + 'title: x\n', ['vendor\n']),
        ('exclude: two\n  lines # c\ntitle: x\n',
         'exclude:\n  - "two lines"\n' + ALL_FOUR + 'title: x\n', ['two lines']),
    ], ids=['plain', 'single-quoted', 'double-quoted', 'comment', 'hash-in-quotes',
            'number', 'crlf', 'folded', 'continued'])
    def test_a_scalar_becomes_a_block_list_with_it_first(self, tmp_path, text, written,
                                                          expected):
        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == written
        assert _excluded(tmp_path) == expected + list(v180_sources.EXCLUDE_ENTRIES)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]
        again = v180_sources.add_exclude_entries(str(tmp_path), 'en')
        assert _read(tmp_path, '_config.yml') == written
        assert 'already excludes' in again[0].description

    @pytest.mark.parametrize('text, written', [
        ('exclude: telar-content/texts\n',
         'exclude:\n  - telar-content/texts\n' + TESTS_GROUP),
        ("exclude: 'tests/'\n",
         "exclude:\n  - 'tests/'\n  - pytest.ini\n  - vitest.config.js\n" + TEXTS_GROUP),
    ], ids=['texts', 'tests'])
    def test_a_scalar_that_is_an_entry_counts_as_present(self, tmp_path, text, written):
        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == written
        config = yaml.safe_load(written)['exclude']
        assert config[0] == yaml.safe_load(text)['exclude']
        assert sorted(entry.rstrip('/') for entry in config) == sorted(
            entry.rstrip('/') for entry in v180_sources.EXCLUDE_ENTRIES)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]
        added = [entry for entry in v180_sources.EXCLUDE_ENTRIES
                 if entry.rstrip('/') != config[0].rstrip('/')]
        assert records[0].description.startswith(f"Added {', '.join(added)} to")

    @pytest.mark.parametrize('token', ['~', 'null', 'Null', 'NULL'])
    @pytest.mark.parametrize('comment', ['', ' # ours'], ids=['bare', 'comment'])
    def test_a_written_null_is_filled_like_a_bare_key(self, tmp_path, token, comment):
        """Jekyll refuses an `exclude` that is not a list, so the token goes
        and the entries go under the key, which keeps its comment."""
        records = _config(tmp_path, f'exclude: {token}{comment}\ntitle: x\n')

        assert _read(tmp_path, '_config.yml') == (
            f'exclude:{comment}\n' + ALL_FOUR + 'title: x\n')
        assert _excluded(tmp_path) == list(v180_sources.EXCLUDE_ENTRIES)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]

    def test_a_tagged_null_is_refused(self, tmp_path):
        text = 'exclude: !!null\ntitle: x\n'

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == text
        assert [(r.status, r.severity) for r in records] == [
            (ChangeStatus.FAILED, 'hard'), (ChangeStatus.FAILED, 'soft')]

    def test_a_scalar_that_is_every_entry_is_still_rewritten(self, tmp_path, monkeypatch):
        """No single value can be all four entries, so the phase is narrowed
        to one; Jekyll refuses the scalar whatever it holds."""
        monkeypatch.setattr(v180_sources, 'EXCLUDE_GROUPS', (
            {'comment': ('# unused',), 'entries': ('tests/',), 'hard': False},))
        monkeypatch.setattr(v180_sources, 'EXCLUDE_ENTRIES', ('tests/',))

        records = _config(tmp_path, 'exclude: tests # ours\nother: 1\n')

        assert _read(tmp_path, '_config.yml') == 'exclude: # ours\n  - tests\nother: 1\n'
        assert _excluded(tmp_path) == ['tests']
        assert [r.status for r in records] == [ChangeStatus.APPLIED]
        again = v180_sources.add_exclude_entries(str(tmp_path), 'en')
        assert _read(tmp_path, '_config.yml') == 'exclude: # ours\n  - tests\nother: 1\n'
        assert 'already excludes' in again[0].description

    def test_a_comment_under_a_continued_scalar_stays(self, tmp_path):
        text = 'exclude: vendor\n  gems\n  # the gems we vendor\nother: 1\n'

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == (
            'exclude:\n  - "vendor gems"\n' + ALL_FOUR + '  # the gems we vendor\nother: 1\n')
        assert _excluded(tmp_path) == ['vendor gems'] + list(v180_sources.EXCLUDE_ENTRIES)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]

    @pytest.mark.parametrize('text, written', [
        ('exclude: [\n  a,\n  b  # the last one\n]\nother: 1\n',
         f'exclude: [\n  a,\n  b,  # the last one\n  {FLOW}\n]\nother: 1\n'),
        ('exclude: [\r\n  a,  # first\r\n]\r\n',
         f'exclude: [\r\n  a,  # first\r\n  {FLOW}\r\n]\r\n'),
        ('exclude: [\n  a,\n  # more to come\n]\n',
         f'exclude: [\n  a,\n  # more to come\n  {FLOW}\n]\n'),
        ('exclude: [ # none yet\n]\n', f'exclude: [ # none yet\n  {FLOW}\n]\n'),
        ("exclude: [a, # don't ] stop\n  b]\n", f"exclude: [a, # don't ] stop\n  b, {FLOW}]\n"),
    ], ids=['last-item-comment', 'crlf', 'comment-line', 'empty-with-comment',
            'comment-with-quote-and-bracket'])
    def test_a_flow_list_ending_in_a_comment(self, tmp_path, text, written):
        """The entries go on a line of their own before a `]` on its own
        line, never into the comment."""
        before = yaml.safe_load(text)['exclude']

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == written
        assert _excluded(tmp_path) == before + list(v180_sources.EXCLUDE_ENTRIES)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]

    def test_a_scalar_on_further_lines_that_is_not_a_string_fails(self, tmp_path):
        """Only a string can be written again double-quoted."""
        text = 'a: &n 3\nexclude: *n\n'

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == text
        assert [(r.status, r.severity) for r in records] == [
            (ChangeStatus.FAILED, 'hard'), (ChangeStatus.FAILED, 'soft')]

    def test_a_rewrite_that_loses_the_scalar_is_refused(self, tmp_path, monkeypatch):
        """The parse afterwards has to find the scalar first and the
        entries after it, not only the entries."""
        monkeypatch.setattr(v180_sources, '_from_scalar',
                            lambda text, start, value, missing: 'exclude:\n' + ALL_FOUR)
        text = 'exclude: vendor\n'

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == text
        assert records[0].severity == 'hard'

    @pytest.mark.parametrize('text', [
        'exclude:\n  vendor: true\n',
        'exclude: {vendor: true}\n',
    ], ids=['map', 'flow-map'])
    def test_a_map_is_left_alone_and_fails(self, tmp_path, text):
        """Hard for the texts entry only; twice, with the same answer."""
        for _ in range(2):
            records = _config(tmp_path, text)

            assert _read(tmp_path, '_config.yml') == text
            assert [(r.status, r.severity) for r in records] == [
                (ChangeStatus.FAILED, 'hard'), (ChangeStatus.FAILED, 'soft')]
            assert 'telar-content/texts/' in records[0].description
            assert 'tests/, pytest.ini, vitest.config.js' in records[1].description

    def test_a_scalar_is_soft_when_only_the_tests_entries_are_wanted(self, tmp_path):
        """The texts entry already present in a list cannot coexist with a
        scalar, so this is the flow list holding it and a quoted bracket
        the scanner must not stop at."""
        _config(tmp_path, 'exclude: ["a]b", telar-content/texts]\n')

        assert yaml.safe_load(_read(tmp_path, '_config.yml'))['exclude'] == [
            'a]b', 'telar-content/texts', 'tests/', 'pytest.ini', 'vitest.config.js']

    def test_the_later_of_two_keys_is_the_one_edited(self, tmp_path):
        """YAML keeps the last of two `exclude` keys, so that is the list
        that has to gain the entries."""
        _config(tmp_path, 'exclude:\n  - vendor\nexclude: [Gemfile]\n')

        assert _excluded(tmp_path) == ['Gemfile'] + list(v180_sources.EXCLUDE_ENTRIES)

    def test_an_insertion_that_would_read_differently_is_refused(self, tmp_path, monkeypatch):
        """The parse before and after is the guard: lines that would add
        something besides the four entries are not written."""
        lines = v180_sources._exclude_lines
        monkeypatch.setattr(v180_sources, '_exclude_lines',
                            lambda missing, indent, nl: lines(missing, indent, nl)
                            + [f'{indent}- extra{nl}'])

        records = _config(tmp_path, CONFIG_BLOCK)

        assert _read(tmp_path, '_config.yml') == CONFIG_BLOCK
        assert records[0].severity == 'hard'

    def test_a_config_that_does_not_parse_is_left_alone(self, tmp_path):
        text = 'exclude:\n  - vendor\n: : :\n'
        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == text
        assert records[0].severity == 'hard'


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
