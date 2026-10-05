"""Unit tests for the name `generate_iiif` reports for an object's image.

On a case-insensitive filesystem a lookup for `calib.png` succeeds when the
file is `calib.PNG`. The file found must be reported under the name the
directory holds it by, which is what the Linux build reports, and a name that
exists exactly is never exchanged for another.

Version: v1.8.0
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from generate_iiif import find_image_for_object, _as_named_on_disk


def test_an_uppercase_extension_is_reported_as_it_is_on_disk(tmp_path):
    (tmp_path / 'calib.PNG').write_bytes(b'')
    assert find_image_for_object('calib', tmp_path).name == 'calib.PNG'


def test_a_name_that_exists_exactly_is_kept(tmp_path):
    (tmp_path / 'calib.png').write_bytes(b'')
    assert _as_named_on_disk(tmp_path / 'calib.png').name == 'calib.png'


def test_a_case_insensitive_match_is_renamed_to_the_file_it_found(tmp_path):
    """The macOS case, on any platform: the probed name is not in the listing."""
    (tmp_path / 'calib.PNG').write_bytes(b'')
    assert _as_named_on_disk(tmp_path / 'calib.png').name == 'calib.PNG'


def test_two_names_differing_only_in_case_are_not_guessed_between(tmp_path):
    """Only possible on a case-sensitive filesystem; the probed name is kept."""
    (tmp_path / 'calib.PnG').write_bytes(b'')
    (tmp_path / 'calib.pNg').write_bytes(b'')
    if len(list(tmp_path.iterdir())) < 2:
        return  # a case-insensitive filesystem holds only one of them
    assert _as_named_on_disk(tmp_path / 'calib.png').name == 'calib.png'
