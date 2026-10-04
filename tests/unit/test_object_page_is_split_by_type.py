"""
Every media type the build can produce has a full set of parts, and no more.

The object page used to be one layout that branched on the media type in nine
places and one bundle carrying all three viewers, so an audio page downloaded
the IIIF viewer to leave it unused. It is now one layout that chooses, per
type: an author-tools include, a script bundle, and the entry module that
bundle is built from.

That makes adding a type a matter of adding parts, and this is what fails when
a set is incomplete. The three failure modes are each their own assertion,
because "Audio has no tools include" and "Audio's bundle is never built" are
different mistakes with the same symptom — an object page that renders with
nothing on it.

The set of types is read out of `detect_media_type` rather than written here.
A fourth type added to that function fails this file until its parts exist,
which is the point: the function is the build's own answer to what a type is.

Version: v1.8.0
"""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / '_layouts' / 'object.html'
MEDIA_TYPE = ROOT / 'scripts' / 'telar' / 'media_type.py'


def media_types():
    """The strings `detect_media_type` can return, from its syntax tree.

    Read rather than listed: a grep for quoted words in that file also finds
    the extension lists and the docstring's examples.
    """
    tree = ast.parse(MEDIA_TYPE.read_text(encoding='utf-8'))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == 'detect_media_type')
    found = {node.value.value for node in ast.walk(function)
             if isinstance(node, ast.Return)
             and isinstance(node.value, ast.Constant)
             and isinstance(node.value.value, str)}
    assert found, 'detect_media_type returns no string literals; the scan is broken'
    return sorted(found)


TYPES = media_types()


def test_the_scan_found_the_types_the_build_actually_uses():
    """The list this file is built on, pinned so a broken scan is not silence."""
    assert TYPES == ['Audio', 'Image', 'Video']


@pytest.mark.parametrize('media_type', TYPES)
def test_the_type_has_an_author_tools_include(media_type):
    include = ROOT / '_includes' / 'objects' / 'tools' / f'{media_type.lower()}.html'
    assert include.is_file(), f'{media_type} has no tools include at {include}'


@pytest.mark.parametrize('media_type', TYPES)
def test_the_layout_reaches_for_that_include(media_type):
    layout = LAYOUT.read_text(encoding='utf-8')
    arm = (f"{{% when '{media_type}' %}}"
           f"{{% include objects/tools/{media_type.lower()}.html %}}")
    assert arm in layout, f'the tools case has no arm for {media_type}'


@pytest.mark.parametrize('media_type', TYPES)
def test_the_type_has_its_own_bundle_and_the_layout_loads_it(media_type):
    """One bundle per type is the whole point: a shared one is dead weight."""
    bundle = f'assets/js/object-{media_type.lower()}.js'
    assert (ROOT / bundle).is_file(), f'{bundle} has not been built'

    layout = LAYOUT.read_text(encoding='utf-8')
    arm = f"{{% when '{media_type}' %}}<script src=\"{{{{ '/{bundle}'"
    assert arm in layout, f'the script case has no arm loading {bundle}'


@pytest.mark.parametrize('media_type', TYPES)
def test_the_bundle_is_built_from_an_entry_that_exists(media_type):
    """A bundle nothing rebuilds silently keeps last release's behaviour."""
    entry = f'assets/js/object-page/{media_type.lower()}-entry.js'
    assert (ROOT / entry).is_file(), f'{entry} is missing'

    scripts = json.loads((ROOT / 'package.json').read_text())['scripts']
    task = f'build:js:object-{media_type.lower()}'
    assert task in scripts, f'package.json has no {task}'
    assert entry in scripts[task]
    assert f'assets/js/object-{media_type.lower()}.js' in scripts[task]
    assert task in scripts['build:js'], f'{task} is not in the build:js chain'


def test_no_bundle_carries_a_viewer_its_pages_never_open():
    """The saving, asserted rather than assumed.

    An audio page must not be shipped the IIIF viewer, and an image page must
    not be shipped WaveSurfer. Read on the built bundles, because the import
    graph is what decides this and only esbuild has resolved it.
    """
    image = (ROOT / 'assets' / 'js' / 'object-image.js').read_text(encoding='utf-8')
    audio = (ROOT / 'assets' / 'js' / 'object-audio.js').read_text(encoding='utf-8')
    video = (ROOT / 'assets' / 'js' / 'object-video.js').read_text(encoding='utf-8')

    assert 'telarLoadWaveSurfer' not in image, 'the image bundle carries the audio player'
    assert 'IiifViewer' not in audio, 'the audio bundle carries the IIIF viewer'
    assert 'IiifViewer' not in video, 'the video bundle carries the IIIF viewer'
    assert 'telarLoadWaveSurfer' not in video, 'the video bundle carries the audio player'


def test_the_superseded_single_bundle_is_gone():
    """object-page.js was every type at once; leaving it would ship both."""
    assert not (ROOT / 'assets' / 'js' / 'object-page.js').exists()
    assert not (ROOT / 'assets' / 'js' / 'object-page' / 'main.js').exists()
    layout = LAYOUT.read_text(encoding='utf-8')
    assert 'object-page.js' not in layout
