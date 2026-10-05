"""Unit Tests for How an Audio Object's File Size Is Written

The size is written into the object page as text, so it is formatted at
build time in the site's language: `5.4 MB` in English, `5,4 MB` in Spanish,
which writes a decimal with a comma. Sizes under a megabyte are whole
kilobytes and carry no decimal mark at all.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import generate_collections as gc


@pytest.fixture
def objects(tmp_path, monkeypatch):
    (tmp_path / 'telar-content' / 'objects').mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    def _write(name, size):
        (tmp_path / 'telar-content' / 'objects' / name).write_bytes(b'\0' * size)
    return _write


@pytest.mark.parametrize('language, expected', [('en', '5.4 MB'), ('es', '5,4 MB')])
def test_megabytes_use_the_language_s_decimal_mark(objects, language, expected):
    objects('song.mp3', int(5.4 * 1024 * 1024))
    mark = gc.DECIMAL_MARK.get(language, '.')
    assert gc._audio_file_details('song', mark) == {
        'audio_filesize': expected, 'audio_format': 'MP3'}


def test_kilobytes_have_no_decimal_to_mark(objects):
    objects('clip.ogg', 4 * 1024)
    assert gc._audio_file_details('clip', ',')['audio_filesize'] == '4 KB'


def test_the_default_is_a_point(objects):
    objects('song.mp3', int(5.4 * 1024 * 1024))
    assert gc._audio_file_details('song')['audio_filesize'] == '5.4 MB'
