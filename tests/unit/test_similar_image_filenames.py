"""Unit tests for the near-miss filenames an unmatched object is shown.

When an object has no manifest and no image named for it, the build names the
files that nearly match, so the author can see which one they meant. Those
names come out sorted: the directory's own order is the filesystem's, and the
same site would otherwise list its candidates one way on the author's machine
and another on the build.

Version: v1.8.0
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors.objects.local import _find_similar_image_filenames


def test_the_candidates_come_out_sorted_by_name(tmp_path):
    # Created in reverse name order, so a listing in creation order is not
    # already sorted.
    for name in ('a-photo.webp', 'aphoto.png', 'a_photo.jpg', 'A Photo.tif'):
        (tmp_path / name).write_bytes(b'')
    found = _find_similar_image_filenames('a-photos', tmp_path)
    assert found == sorted(found)
    assert set(found) == {'a-photo.webp', 'aphoto.png', 'a_photo.jpg', 'A Photo.tif'}


def test_the_exact_stem_and_other_files_are_not_candidates(tmp_path):
    for name in ('a-photo.jpg', 'a-photo-notes.md', 'unrelated.jpg'):
        (tmp_path / name).write_bytes(b'')
    assert _find_similar_image_filenames('a-photo', tmp_path) == []
