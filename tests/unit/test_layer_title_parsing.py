"""Unit Tests for Reading a Layer's Title Out of Its Front Matter

`_split_frontmatter` used `TITLE_PATTERN`, a regex, both to find the
`title:` key and to read its value — stripping one leading and one
trailing quote character and returning whatever sits between them. That
is not a YAML parse: an escape inside a quoted title (`\\"`, `\\n`, `\\N`)
is YAML's to interpret, and the regex only trims quote characters, so a
title written `"A \\"quoted\\" title"` came back with its backslashes
still in it.

The fix keeps the regex as the gate — does this block carry a title: key
at all — and reads the value by parsing the block as YAML once the gate
passes. A block that does not parse as YAML, or parses to something other
than a mapping with a title, falls back to the regex reading it always
had, with a warning naming the source.

Version: v1.8.0
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.markdown import _split_frontmatter


def _title(frontmatter, source='a-layer.md'):
    content = f'---\n{frontmatter}\n---\nbody\n'
    return _split_frontmatter(content, source=source)


class TestATitleIsReadAsYamlNotUnquotedByRegex:

    def test_a_quoted_title_keeps_its_escaped_quotes_unescaped(self):
        title, body = _title(r'title: "A \"quoted\" title"')

        assert title == 'A "quoted" title'
        assert body == 'body'

    def test_a_backslash_survives_as_one_character(self):
        title, _ = _title(r'title: "A backslash \\ in the middle"')

        assert title == 'A backslash \\ in the middle'

    def test_an_escaped_newline_becomes_a_real_line_break(self):
        title, _ = _title(r'title: "Line one\nLine two"')

        assert title == 'Line one\nLine two'

    def test_a_nel_escape_becomes_the_nel_character(self):
        """`\\N` is YAML's escape for NEL (U+0085), not two characters."""
        title, _ = _title(r'title: "a\Nb"')

        assert title == 'a\x85b'

    def test_a_single_quoted_doubled_apostrophe_becomes_one(self):
        title, _ = _title("title: 'it''s'")

        assert title == "it's"

    def test_a_bare_numeric_title_stays_text(self):
        """A title is text: YAML would otherwise hand back an int."""
        title, _ = _title('title: 2024')

        assert title == '2024'
        assert isinstance(title, str)

    def test_an_unquoted_title_is_unchanged(self):
        title, _ = _title('title: Panel Title Without Quotes')

        assert title == 'Panel Title Without Quotes'

    def test_an_unparseable_block_falls_back_to_the_regex_reading(self, capsys):
        """`[oops` is not valid YAML — the block still carries `title:`.

        The gate (`TITLE_PATTERN`) still matches, so the function does not
        treat the block as titleless; it reads the value with the regex
        and says why.
        """
        title, body = _title('title: [oops', source='broken-layer.md')

        assert title == '[oops'
        assert body == 'body'

        warning = capsys.readouterr().out
        assert 'broken-layer.md' in warning
        assert 'could not be parsed as YAML' in warning


class TestATitleIsTextEvenWhenYamlReadsItAsSomethingElse:
    """A panel title is whatever the author typed on the `title:` line.

    YAML types the value: `yes` is a boolean, `~` and `null` are null,
    `[a]` a list, `{a: 1}` a mapping. Handing those to `str()` put a Python
    literal on the page — `True`, `None`, `['a']` — which is neither the
    author's text nor anything they could search for. The regex gate has
    already matched the line, so its reading is the text as typed, and that
    is what a title is.
    """

    def test_a_yes_title_is_the_word_yes(self):
        title, body = _title('title: yes')

        assert title == 'yes'
        assert body == 'body'

    def test_a_no_title_is_the_word_no(self):
        title, _ = _title('title: no')

        assert title == 'no'

    def test_a_tilde_title_is_a_tilde(self):
        title, _ = _title('title: ~')

        assert title == '~'

    def test_a_null_title_is_the_word_null(self):
        title, _ = _title('title: null')

        assert title == 'null'

    def test_a_bracketed_title_is_the_text_between_the_brackets(self):
        title, _ = _title('title: [a]')

        assert title == '[a]'

    def test_a_braced_title_is_the_text_as_typed(self):
        title, _ = _title('title: {a: 1}')

        assert title == '{a: 1}'

    def test_a_numeric_title_is_still_its_digits(self):
        title, _ = _title('title: 2024')

        assert title == '2024'
        assert isinstance(title, str)

    def test_an_empty_title_is_empty_not_none(self):
        title, _ = _title('title:')

        assert title == ''

    def test_a_quoted_title_is_still_parsed_as_yaml(self):
        """The YAML reading is only bypassed when it hands back a non-string."""
        title, _ = _title(r'title: "A \"quoted\" title"')

        assert title == 'A "quoted" title'

    def test_a_quoted_yes_is_still_the_word_yes(self):
        title, _ = _title("title: 'yes'")

        assert title == 'yes'

    def test_every_one_of_these_comes_back_a_string(self):
        for written in ['yes', 'no', 'on', 'off', 'true', 'false', '~',
                        'null', '[a]', '{a: 1}', '2024', '3.14', '.inf']:
            title, _ = _title(f'title: {written}')

            assert isinstance(title, str), written
            assert title == written


class TestOnlyAKeyOfItsOwnCountsAsTheTitle:
    """`subtitle:` ends in `title:`, and the gate was unanchored.

    `re.search(r'title:…')` matches at the fourth character of
    `subtitle: x`, so a block whose only key was a subtitle read as
    titled and the subtitle's text was handed back as the title. It went
    unnoticed while the YAML parse won every string case; the fallback to
    the matched line reaches it, because that is the line it falls back to.

    Anchoring the gate to the start of a line is also what makes the gate
    and the parse agree on the same key. A top-level YAML key sits at
    column 0 -- an indented `title:` belongs to the mapping above it, and
    `parsed['title']` would not find it either -- so no allowance is made
    for leading whitespace. Nothing in the content tree or in these tests
    writes an indented `title:`.
    """

    def test_a_block_with_only_a_subtitle_has_no_title(self, capsys):
        title, body = _title('subtitle: x')

        assert title == ''
        assert 'subtitle: x' in body

        warning = capsys.readouterr().out
        assert 'has no title: key' in warning

    def test_a_subtitle_above_a_title_does_not_stand_in_for_it(self):
        title, _ = _title('subtitle: x\ntitle: ~')

        assert title == '~'

    def test_a_subtitle_above_a_string_title_is_still_ignored(self):
        title, _ = _title('subtitle: x\ntitle: The Real Title')

        assert title == 'The Real Title'

    def test_a_title_inside_a_nested_mapping_is_not_the_blocks_title(self,
                                                                    capsys):
        """It is not a top-level key, so it is nobody's title."""
        title, body = _title('meta:\n  title: yes')

        assert title == ''
        assert 'title: yes' in body

        warning = capsys.readouterr().out
        assert 'has no title: key' in warning

    def test_a_title_below_a_nested_mapping_is_still_found(self):
        title, _ = _title('meta:\n  subtitle: x\ntitle: yes')

        assert title == 'yes'

    def test_any_key_ending_in_title_is_ignored(self):
        for key in ['subtitle', 'sub_title', 'alt-title']:
            title, _ = _title(f'{key}: x')

            assert title == '', key
