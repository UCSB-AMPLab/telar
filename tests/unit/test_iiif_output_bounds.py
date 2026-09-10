"""
Unit Tests for the IIIF output-path boundary guard

_process_object() refuses to rmtree or mkdir anywhere but under the run's
output directory, whatever the object_id resolved to. The guard sits behind
load_objects_needing_tiles()'s _SAFE_OBJECT_ID allowlist, so no id that
reaches it through the normal path can escape and the characterisation
corpus cannot distinguish the guard from its absence. These tests call the
function directly with the id class the guard exists for.

Version: v1.7.0
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from generate_iiif import _process_object


def write_source_image(path):
    """Write a small RGB PNG for the guard to be handed.

    The guard runs before any pixel work, and the in-bounds case only needs
    an image the tile backend can read, so the content is irrelevant.
    """
    Image.new('RGB', (64, 40), (120, 90, 60)).save(path)


@pytest.fixture
def escaping_site(tmp_path):
    """A site whose source directory holds an image one level above itself.

    The escaping object_id is '../escape', so find_image_for_object() looks
    for 'objects/../escape.png' and finds the file beside the source
    directory, which puts a real image in front of the guard.
    """
    source_dir = tmp_path / 'objects'
    source_dir.mkdir()
    output_path = tmp_path / 'iiif'
    output_path.mkdir()
    write_source_image(tmp_path / 'escape.png')
    return source_dir, output_path


def test_out_of_bounds_object_is_rejected(escaping_site, capsys):
    """An id resolving outside the output directory is neither processed nor skipped."""
    source_dir, output_path = escaping_site

    outcome = _process_object('../escape', str(source_dir), output_path,
                              'https://example.test', 'iiif')

    assert outcome == 'rejected'
    assert 'out-of-bounds output path' in capsys.readouterr().out


def test_out_of_bounds_object_writes_nothing(escaping_site):
    """The guard runs before the rmtree and the mkdir, so nothing moves on disk."""
    source_dir, output_path = escaping_site
    tmp_path = output_path.parent
    before = sorted(p.name for p in tmp_path.iterdir())

    _process_object('../escape', str(source_dir), output_path,
                    'https://example.test', 'iiif')

    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert (tmp_path / 'escape.png').is_file()
    assert list(output_path.iterdir()) == []


def test_in_bounds_object_is_not_rejected(escaping_site):
    """A plain id under the output directory passes the guard."""
    source_dir, output_path = escaping_site
    write_source_image(source_dir / 'calib-landscape.png')

    outcome = _process_object('calib-landscape', str(source_dir), output_path,
                              'https://example.test', 'iiif')

    assert outcome != 'rejected'
    assert (output_path / 'calib-landscape').is_dir()
