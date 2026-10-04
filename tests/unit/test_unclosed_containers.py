"""
Unit Tests for Unclosed markdown="1" Containers

An author's text is never dropped. A panel that opens block containers
with markdown="1" and does not close them renders exactly as the Markdown
library renders the same text with the missing closing tags appended, and
the build prints one warning naming the unclosed tags. Text that already
closes its containers is not changed.

Version: v1.8.0
"""

import os
import random
import sys

import markdown
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.markdown import process_inline_content

EXTENSIONS = ['extra', 'nl2br']


def library(text):
    return markdown.markdown(text, extensions=EXTENSIONS)


def content(text):
    return process_inline_content(text)['content']


# (input, closing tags appended by hand, innermost first)
UNCLOSED = {
    'issue case': ('<div markdown="1">\nA\n\n<div markdown="1">\nB',
                   '</div></div>'),
    'one level': ('<div markdown="1">\nA', '</div>'),
    'three levels same name': (
        '<div markdown="1">\nA\n\n<div markdown="1">\nB\n\n<div markdown="1">\nC',
        '</div></div></div>'),
    'differently named': (
        '<div markdown="1">\nA\n\n<section markdown="1">\nB', '</section></div>'),
    'named, then same name again': (
        '<div markdown="1">\nA\n\n<section markdown="1">\nB\n\n'
        '<div markdown="1">\nC', '</div></section></div>'),
    'closed inner, unclosed outer': (
        '<div markdown="1">\nA\n\n<div markdown="1">\nB\n</div>\n\nC', '</div>'),
    'fenced code after the opening': (
        '<div markdown="1">\nA\n\n```\n<div markdown="1">\n```\n\nB', '</div>'),
    'span-level container': ('<p markdown="1">hi *x*', '</p>'),
}


@pytest.mark.parametrize('name', sorted(UNCLOSED))
def test_unclosed_renders_as_library_renders_closed_form(name, capsys):
    text, closers = UNCLOSED[name]
    assert content(text) == library(text + '\n' + closers)


def test_issue_case_keeps_every_word():
    html = content('<div markdown="1">\nA\n\n<div markdown="1">\nB')
    assert '<p>A</p>' in html and '<p>B</p>' in html


def test_warning_names_unclosed_tags_once(capsys):
    content('<div markdown="1">\nA\n\n<section markdown="1">\nB\n\n'
            '<div markdown="1">\nC')
    warnings = [l for l in capsys.readouterr().out.splitlines() if 'Warning' in l]
    assert len(warnings) == 1
    assert '<div>, <section>, <div>' in warnings[0]
    assert '</div></section></div>' in warnings[0]


def test_no_warning_when_closed(capsys):
    content('<div markdown="1">\nA\n\n<div markdown="1">\nB\n</div>\n</div>')
    assert capsys.readouterr().out == ''


def test_container_inside_fenced_code_is_text_and_not_closed(capsys):
    text = '```\n<div markdown="1">\nx\n```'
    assert content(text) == library(text)
    assert capsys.readouterr().out == ''


def test_container_in_code_span_is_not_closed(capsys):
    text = 'use `<div markdown="1">` here'
    assert content(text) == library(text)
    assert capsys.readouterr().out == ''


def test_span_level_markdown_attribute_is_not_a_container(capsys):
    text = 'a <span markdown="1">b</span> c\n\nand <span markdown="1">d'
    assert content(text) == library(text)
    assert capsys.readouterr().out == ''


def test_latex_holds_a_tag_out_of_the_block_pass(capsys):
    text = '$$<div markdown="1">$$'
    assert '$$&lt;div markdown="1"&gt;$$' in content(text)
    assert capsys.readouterr().out == ''


PIECES = [
    'plain words', '**bold** and *it*', '# Heading', '- item\n- item two',
    '> quote', '```\n<div markdown="1">\ncode\n```', '`<div markdown="1">`',
    '<span markdown="1">s</span>', '[l](http://x.org)', 'a\nb',
    '<div markdown="1">\ninner\n</div>', '<section>\nraw\n</section>',
    '<div markdown="1">\nx\n\n<section markdown="1">\ny\n</section>\n</div>',
    '<p markdown="1">p *s*</p>', '<details markdown="1">\nd\n</details>',
]


def test_closed_inputs_are_unchanged(capsys):
    rng = random.Random(623)
    for _ in range(400):
        text = '\n\n'.join(rng.choice(PIECES) for _ in range(rng.randint(1, 5)))
        assert content(text) == library(text), text
    assert capsys.readouterr().out == ''
