"""
Unit Tests for the v1.8.0 Migration's Edit to the `exclude:` List

`v180_sources.add_exclude_entries` adds the development files a site must
not publish to `_config.yml`'s `exclude:` list, as a text edit. These tests
hold the bytes around the edit, check the parsed result, find the key where
Jekyll's own YAML reader finds it, and read the rewritten file with Jekyll's
reader itself.

Every fixture runs against a temporary site directory.

Version: v1.8.0
"""

import os
import random
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v180_sources
from migrations.base import ChangeStatus


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _write(root, rel_path, text):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))
    return path


def _read(root, rel_path):
    return (root / rel_path).read_bytes().decode('utf-8')


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


# ---------- The top-level key where Jekyll's reader finds it ----------

BOM = '\ufeff'


def _first(text):
    """The first document of *text*, the one Jekyll reads."""
    return next(iter(yaml.safe_load_all(text)))


def _indented(block, by='  '):
    return ''.join(by + line for line in block.splitlines(keepends=True))


# Input, and the bytes the upgrade writes. A BOM, a `---` line and an
# indented top-level mapping are all read by Jekyll as the same keys, so
# `exclude:` is found after the first two and at the mapping's own
# indentation, and the BOM, line endings and every other line stay.
READER_CASES = [
    ('bom-scalar', BOM + 'exclude: vendor\n', BOM + 'exclude:\n  - vendor\n' + ALL_FOUR),
    ('bom-null', BOM + 'exclude: null\n', BOM + 'exclude:\n' + ALL_FOUR),
    ('bom-crlf', BOM + 'exclude: vendor\r\ntitle: x\r\n',
     BOM + 'exclude:\r\n  - vendor\r\n' + ALL_FOUR.replace('\n', '\r\n') + 'title: x\r\n'),
    ('bom-comment-first', BOM + '# My site\nexclude: vendor\n',
     BOM + '# My site\nexclude:\n  - vendor\n' + ALL_FOUR),
    ('bom-block', BOM + 'exclude:\n  - vendor\n', BOM + 'exclude:\n  - vendor\n' + ALL_FOUR),
    ('bom-flow', BOM + 'exclude: [vendor]\n', BOM + f'exclude: [vendor, {FLOW}]\n'),
    ('indented-scalar', '  exclude: vendor\n',
     '  exclude:\n    - vendor\n' + _indented(ALL_FOUR)),
    ('indented-scalar-comment', '  title: x\n  exclude: vendor # gems\n  other: 1\n',
     '  title: x\n  exclude: # gems\n    - vendor\n' + _indented(ALL_FOUR) + '  other: 1\n'),
    ('indented-null', '  exclude: ~\n  other: 1\n',
     '  exclude:\n' + _indented(ALL_FOUR) + '  other: 1\n'),
    ('indented-bare', '  exclude:\n  other: 1\n',
     '  exclude:\n' + _indented(ALL_FOUR) + '  other: 1\n'),
    ('indented-block', '  title: x\n  exclude:\n    - vendor\n  other: 1\n',
     '  title: x\n  exclude:\n    - vendor\n' + _indented(ALL_FOUR) + '  other: 1\n'),
    ('indented-block-at-key', '  exclude:\n  - vendor\n  other: 1\n',
     '  exclude:\n  - vendor\n' + ALL_FOUR + '  other: 1\n'),
    ('indented-flow', '  exclude: [vendor] # built\n  other: 1\n',
     f'  exclude: [vendor, {FLOW}] # built\n  other: 1\n'),
    ('indented-continued', '  exclude: two\n    lines\n  other: 1\n',
     '  exclude:\n    - "two lines"\n' + _indented(ALL_FOUR) + '  other: 1\n'),
    ('indented-bom-crlf', BOM + '  exclude: vendor\r\n  other: 1\r\n',
     BOM + '  exclude:\r\n    - vendor\r\n' + _indented(ALL_FOUR).replace('\n', '\r\n')
     + '  other: 1\r\n'),
    ('nested-only', 'sass:\n  exclude: vendor\ntitle: x\n',
     'sass:\n  exclude: vendor\ntitle: x\n\nexclude:\n' + ALL_FOUR),
    ('nested-after', 'exclude: vendor\nsass:\n  exclude: x\n',
     'exclude:\n  - vendor\n' + ALL_FOUR + 'sass:\n  exclude: x\n'),
    ('indented-nested-before', '  sass:\n    exclude: x\n  exclude: vendor\n',
     '  sass:\n    exclude: x\n  exclude:\n    - vendor\n' + _indented(ALL_FOUR)),
    ('indented-nested-after', '  exclude: [a]\n  sass:\n    exclude: x\n',
     f'  exclude: [a, {FLOW}]\n  sass:\n    exclude: x\n'),
    ('document-start', '---\nexclude: vendor\n', '---\nexclude:\n  - vendor\n' + ALL_FOUR),
    ('document-start-indented', '---\n  exclude: vendor\n',
     '---\n  exclude:\n    - vendor\n' + _indented(ALL_FOUR)),
    ('bom-document-start', BOM + '--- # site\nexclude: vendor\n',
     BOM + '--- # site\nexclude:\n  - vendor\n' + ALL_FOUR),
    ('indented-absent', '  title: x\n', '  title: x\n\n  exclude:\n' + _indented(ALL_FOUR)),
    ('indented-absent-no-final-newline', '  title: x',
     '  title: x\n\n  exclude:\n' + _indented(ALL_FOUR)),
    ('indented-absent-bom', BOM + '  title: x\n',
     BOM + '  title: x\n\n  exclude:\n' + _indented(ALL_FOUR)),
    ('indented-absent-document-start', '---\n    title: x\n',
     '---\n    title: x\n\n    exclude:\n' + _indented(ALL_FOUR, '    ')),
    ('indented-absent-crlf', '  title: x\r\n  other: 1\r\n',
     '  title: x\r\n  other: 1\r\n\r\n  exclude:\r\n'
     + _indented(ALL_FOUR).replace('\n', '\r\n')),
    ('indented-absent-nested', '  sass:\n    exclude: vendor\n  title: x\n',
     '  sass:\n    exclude: vendor\n  title: x\n\n  exclude:\n' + _indented(ALL_FOUR)),
    ('double-quoted-key-flow', '"exclude": [vendor]\n', f'"exclude": [vendor, {FLOW}]\n'),
    ('single-quoted-key-spaced', "'exclude' : vendor\n",
     "'exclude' :\n  - vendor\n" + ALL_FOUR),
    ('spaced-key-block', 'exclude  :\n  - a\ntitle: x\n',
     'exclude  :\n  - a\n' + ALL_FOUR + 'title: x\n'),
    ('double-quoted-key-null', '"exclude": ~ # none\n', '"exclude": # none\n' + ALL_FOUR),
    ('indented-quoted-key-continued', BOM + '  title: x\n  "exclude" : two\n    lines\n',
     BOM + '  title: x\n  "exclude" :\n    - "two lines"\n' + _indented(ALL_FOUR)),
    ('quoted-key-comment', "'exclude' : vendor # gems\n",
     "'exclude' : # gems\n  - vendor\n" + ALL_FOUR),
    ('escaped-key-block', '"exclu\\x64e":\n  - vendor\n',
     '"exclu\\x64e":\n  - vendor\n' + ALL_FOUR),
    ('escaped-key-scalar', '"\\x65xclude" : vendor # gems\n',
     '"\\x65xclude" : # gems\n  - vendor\n' + ALL_FOUR),
    ('escaped-key-flow', '  "excl\\u0075de": [vendor]\n', f'  "excl\\u0075de": [vendor, {FLOW}]\n'),
    ('escaped-key-null', '"exclud\\x65": null\ntitle: x\n',
     '"exclud\\x65":\n' + ALL_FOUR + 'title: x\n'),
    # A quoted key that does not read as `exclude` after the one that does:
    # `''` in single quotes is one quote, and a colon inside quotes is text.
    ('single-quoted-key-doubled-quote', "exclude: vendor\n'exclude''': [a]\n",
     "exclude:\n  - vendor\n" + ALL_FOUR + "'exclude''': [a]\n"),
    ('quoted-other-key-with-colon', 'exclude: [a]\n"exclude: no": [b]\n',
     f'exclude: [a, {FLOW}]\n"exclude: no": [b]\n'),
    ('escaped-other-key', 'exclude: [a]\n"exclude\\x21": [b]\n',
     f'exclude: [a, {FLOW}]\n"exclude\\x21": [b]\n'),
    ('document-end', 'title: x\n...\n', 'title: x\n\nexclude:\n' + ALL_FOUR + '...\n'),
    ('document-end-comment-after', 'title: x\n... # end\n# after\n',
     'title: x\n\nexclude:\n' + ALL_FOUR + '... # end\n# after\n'),
    ('document-end-indented-crlf', '  title: x\r\n...\r\n',
     '  title: x\r\n\r\n  exclude:\r\n' + _indented(ALL_FOUR).replace('\n', '\r\n')
     + '...\r\n'),
    ('document-end-list', 'exclude: [a]\n...\n', f'exclude: [a, {FLOW}]\n...\n'),
    ('multi-document-flow', '---\nexclude: [vendor]\n---\ntitle: x\n',
     f'---\nexclude: [vendor, {FLOW}]\n---\ntitle: x\n'),
    ('multi-document-scalar', '---\nexclude: vendor\n---\nexclude: other\n',
     '---\nexclude:\n  - vendor\n' + ALL_FOUR + '---\nexclude: other\n'),
    ('multi-document-absent', 'title: x\n...\n---\nexclude: y\n',
     'title: x\n\nexclude:\n' + ALL_FOUR + '...\n---\nexclude: y\n'),
    ('multi-document-absent-no-end', BOM + 'title: x\n--- # two\nexclude: y\n',
     BOM + 'title: x\n\nexclude:\n' + ALL_FOUR + '--- # two\nexclude: y\n'),
]

# Inputs that fail as they do without a BOM or indentation: the file stays
# as it is and the texts entry's failure is hard.
READER_FAILURES = [
    ('bom-tagged-null', BOM + 'exclude: !!null\n'),
    ('bom-map', BOM + 'exclude:\n  vendor: true\n'),
    ('indented-tagged-null', '  exclude: !!null\n  other: 1\n'),
    ('indented-map', '  exclude:\n    vendor: true\n  other: 1\n'),
    ('indented-flow-map', '  exclude: {vendor: true}\n'),
    # A top-level flow mapping has no line a key can be added on.
    ('flow-mapping-absent', '{title: x}\n'),
    # PyYAML refuses a tab after the colon, which Jekyll's reader allows.
    ('tab-after-colon', 'exclude:\tvendor\n'),
]


class TestExcludeWhereJekyllReadsIt:

    @pytest.mark.parametrize('text, written', [case[1:] for case in READER_CASES],
                             ids=[case[0] for case in READER_CASES])
    def test_the_key_is_found_and_only_it_changes(self, tmp_path, text, written):
        before = _first(text)

        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == written
        after = _first(written)
        assert after['exclude'] == v180_sources._as_list(
            before.get('exclude')) + list(v180_sources.EXCLUDE_ENTRIES)
        assert v180_sources._without_exclude(after) == v180_sources._without_exclude(before)
        assert [r.status for r in records] == [ChangeStatus.APPLIED]
        again = v180_sources.add_exclude_entries(str(tmp_path), 'en')
        assert _read(tmp_path, '_config.yml') == written
        assert 'already excludes' in again[0].description

    @pytest.mark.parametrize('text', [case[1] for case in READER_FAILURES],
                             ids=[case[0] for case in READER_FAILURES])
    def test_the_other_shapes_still_fail(self, tmp_path, text):
        records = _config(tmp_path, text)

        assert _read(tmp_path, '_config.yml') == text
        assert [(r.status, r.severity) for r in records] == [
            (ChangeStatus.FAILED, 'hard'), (ChangeStatus.FAILED, 'soft')]


# ---------- Jekyll reads the rewritten file ----------

# Jekyll's own reader, one JSON path per line in, one result per line out:
# the mapping as `read_config_file` loads it (SafeYAML, BOM-aware), and the
# error `Jekyll.configuration` raises when it refuses the file, or null.
JEKYLL_READ = '''
require "jekyll"
require "json"
Jekyll.logger.log_level = :error
STDIN.each_line do |line|
  path = JSON.parse(line)
  begin
    raw = Jekyll::Configuration.new.read_config_file(path)
  rescue StandardError => e
    puts JSON.generate({"config" => nil, "error" => "#{e.class}: #{e.message}"})
    next
  end
  begin
    Jekyll.configuration("source" => File.dirname(path), "config" => path, "quiet" => true)
    error = nil
  rescue StandardError => e
    error = "#{e.class}: #{e.message}"
  end
  puts JSON.generate({"config" => raw, "error" => error})
end
'''


def _bundle_env():
    env = dict(os.environ, BUNDLE_GEMFILE=os.path.join(REPO_ROOT, 'Gemfile'))
    env.pop('BUNDLE_PATH', None)
    return env


def jekyll_read(paths):
    """What Jekyll reads from each file in *paths*, as `{'config', 'error'}`;
    skips the calling test when `bundle exec` cannot run Jekyll."""
    import json
    import shutil
    import subprocess
    if shutil.which('bundle') is None:
        pytest.skip('bundle is not on PATH')
    result = subprocess.run(
        ['bundle', 'exec', 'ruby', '-e', JEKYLL_READ],
        input=''.join(json.dumps(str(path)) + '\n' for path in paths),
        capture_output=True, text=True, cwd=REPO_ROOT, env=_bundle_env(), timeout=300)
    if result.returncode != 0 and 'cannot load such file' in result.stderr:
        pytest.skip('bundle exec cannot load Jekyll with this Ruby')
    assert result.returncode == 0, result.stderr[-2000:]
    read = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(read) == len(paths)
    return read


def _written_sites(tmp_path, texts):
    """Each text as a site's `_config.yml`, the upgrade's step run on it:
    (input path, output path, records) per text."""
    sites = []
    for index, text in enumerate(texts):
        site = tmp_path / f'site{index}'
        original = _write(site, 'original.yml', text)
        _write(site, '_config.yml', text)
        records = v180_sources.add_exclude_entries(str(site), 'en')
        sites.append((original, site / '_config.yml', records))
    return sites


class TestJekyllReadsTheRewrite:

    def test_each_rewrite_is_an_array_jekyll_accepts(self, tmp_path):
        sites = _written_sites(tmp_path, [case[1] for case in READER_CASES])

        read = jekyll_read([path for site in sites for path in site[:2]])

        for (name, text, _), before, after in zip(READER_CASES, read[0::2], read[1::2]):
            assert after['error'] is None, (name, after)
            exclude = after['config']['exclude']
            assert isinstance(exclude, list), name
            assert exclude == v180_sources._as_list(
                before['config'].get('exclude')) + list(v180_sources.EXCLUDE_ENTRIES), name
            assert v180_sources._without_exclude(after['config']) == \
                v180_sources._without_exclude(before['config']), name

    def test_jekyll_refused_the_scalars_and_nulls_before(self, tmp_path):
        """The inputs are the ones the issue is about: Jekyll reads the same
        top-level key and refuses what it holds."""
        refused = [case for case in READER_CASES
                   if not isinstance(_first(case[1]).get('exclude', []), list)]
        sites = _written_sites(tmp_path, [case[1] for case in refused])

        read = jekyll_read([site[0] for site in sites])

        assert len(refused) >= 8
        for (name, _, _), before in zip(refused, read):
            assert "'exclude' should be set as an array" in (before['error'] or ''), name

    def test_random_configs(self, tmp_path):
        """Each seeded config is either rewritten to a list Jekyll accepts,
        holding what it held and the four entries with every other key as it
        was, or left byte for byte and failed, and only for a shape that
        fails however it is written."""
        configs = random_configs(400)
        sites = _written_sites(tmp_path, [text for _, _, text, _ in configs])

        read = jekyll_read([path for site in sites for path in site[:2]])

        wrong = []
        for (form, k, text, tail), site, before, after in zip(configs, sites, read[0::2],
                                                              read[1::2]):
            outcome = random_config_outcome(form, k, text, tail, site, before, after)
            if outcome not in ('rewritten', 'present', 'failed'):
                wrong.append((form, text, outcome))
        assert wrong == []


# The value `exclude:` holds in a seeded config: a name, and its lines at
# key indentation *k*, the first of them following `exclude:`.
EXCLUDE_FORMS = {
    'absent': None,
    'bare': lambda k: [''],
    'null': lambda k: [' ~'],
    'null-word': lambda k: [' null # none yet'],
    'NULL': lambda k: [' NULL'],
    'tagged-null': lambda k: [' !!null'],
    'plain': lambda k: [' vendor'],
    'plain-comment': lambda k: [' vendor  # gems'],
    'single-quoted': lambda k: [" 'vendor'"],
    'double-quoted-hash': lambda k: [' "a #b" # note'],
    'entry': lambda k: [' telar-content/texts'],
    'number': lambda k: [' 3'],
    'continued': lambda k: [' two', k + '  lines'],
    'folded': lambda k: [' >', k + '  vendor'],
    'block': lambda k: ['', k + '  - Gemfile', k + '  # vendored', k + '  - "vendor"'],
    'block-at-key': lambda k: ['', k + '- Gemfile', k + '- vendor'],
    'block-all': lambda k: ['', k + '  - tests/', k + '  - pytest.ini',
                            k + '  - vitest.config.js', k + '  - telar-content/texts/'],
    'flow': lambda k: [' [Gemfile, "vendor"]'],
    'flow-comment': lambda k: [' [Gemfile] # built'],
    'flow-empty': lambda k: [' []'],
    'flow-lines': lambda k: [' [', k + '  Gemfile,', k + '  vendor  # last', k + ']'],
    'map': lambda k: ['', k + '  vendor: true'],
    'flow-map': lambda k: [' {vendor: true}'],
}

# The shapes that fail wherever the key is: a tagged null and a mapping are
# not rewritten.
FAILING_FORMS = ('tagged-null', 'map', 'flow-map')


def random_configs(count, seed=603):
    """(exclude form, indentation, text, what follows the first document)
    mixing a BOM, CRLF, a `---` line, a leading comment, the mapping's
    indentation, the key's spelling, a nested `exclude:`, other keys, a
    missing final newline, and a document end or second document after
    each form."""
    rng = random.Random(seed)
    forms = sorted(EXCLUDE_FORMS)
    configs = []
    for _ in range(count):
        form = rng.choice(forms)
        k = rng.choice(['', '', '  ', '    '])
        lines = []
        if rng.random() < 0.3:
            lines.append(rng.choice(['---', '--- # site', '---  ']))
        if rng.random() < 0.3:
            lines.append(rng.choice(['# My site', '  # indented comment']))
        if rng.random() < 0.5:
            lines.append(k + 'title: "x: y" # a title')
        if rng.random() < 0.4:
            lines += [k + 'sass:', k + '  exclude: nested']
        if EXCLUDE_FORMS[form] is not None:
            value = EXCLUDE_FORMS[form](k)
            spelling = rng.choice(['exclude', 'exclude', '"exclude"', "'exclude'",
                                   'exclude ', "'exclude'  ", '"exclu\\x64e"'])
            lines += [k + spelling + ':' + value[0]] + value[1:]
        if rng.random() < 0.5:
            lines += ['', k + 'other: 1']
        if rng.random() < 0.3:
            lines.append(k + '# the end')
        newline = '\r\n' if rng.random() < 0.3 else '\n'
        text = newline.join(lines)
        tail = ''
        # A `---` after nothing but comments starts the first document rather
        # than a second one.
        content = any(line.strip() and not line.strip().startswith(('#', '---'))
                      for line in lines)
        if content and rng.random() < 0.3:
            tail = newline.join(rng.choice([['...'], ['... # end', '# after'],
                                            ['---', 'exclude: other'],
                                            ['--- # two', 'title: y']])) + newline
        if tail or rng.random() < 0.8:
            text += newline
        if rng.random() < 0.3:
            text = BOM + text
        configs.append((form, k, text + tail, tail))
    return configs


def random_config_outcome(form, k, text, tail, site, before, after):
    """'rewritten', 'present' or 'failed' when *site* is right for *form*;
    otherwise a description of what is wrong."""
    original, path, records = site
    written = path.read_bytes().decode('utf-8')
    if 'already excludes' in records[0].description:
        if written != text or after['error'] is not None:
            return f'present, but written or refused: {after}'
        return 'present'
    if [r.status for r in records] == [ChangeStatus.APPLIED]:
        if after['error'] is not None or not isinstance(after['config'].get('exclude'), list):
            return f'Jekyll refuses the rewrite: {after}'
        wanted = v180_sources._as_list(before['config'].get('exclude'))
        present = {v180_sources._normalise_entry(e) for e in wanted if isinstance(e, str)}
        wanted = wanted + [e for e in v180_sources.EXCLUDE_ENTRIES
                           if v180_sources._normalise_entry(e) not in present]
        if after['config']['exclude'] != wanted:
            return f"exclude reads {after['config']['exclude']!r}"
        if v180_sources._without_exclude(after['config']) != \
                v180_sources._without_exclude(before['config']):
            return 'another key changed'
        if written.startswith(BOM) != text.startswith(BOM):
            return 'the BOM changed'
        bare = written.replace('\r\n', '') if '\r\n' in text else written
        if '\r' in bare or ('\r\n' in text and '\n' in bare):
            return 'the line endings changed'
        if not written.endswith(tail):
            return 'what follows the first document changed'
        return 'applied without a change' if written == text else 'rewritten'
    if written != text:
        return 'failed but wrote the file'
    if form in FAILING_FORMS:
        return 'failed'
    return f'failed: {[r.description for r in records]}'
