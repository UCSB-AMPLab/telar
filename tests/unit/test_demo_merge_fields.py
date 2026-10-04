"""
Unit Tests for the Fields a Demo Bundle Carries into a Site

A demo bundle shows what the framework does, so its merge carries the fields
a site's own content carries: an object's alt text, media type and medium
(the gallery's Medium/Genre facet reads `medium`, where bundles may say
`object_type`); a step's page, clip, loop and alt text; the `has_latex` row
that loads KaTeX; the passes a site's own answers take; and a glossary
entry's related terms, which the entry's page lists.

A field the bundle does not hold is not written, because the step template
emits an attribute for any value, and to Liquid an empty string is one.

Version: v1.8.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.demo import merge_demo_content
from telar.glossary_pages import generate_glossary


def _bundle(**overrides):
    bundle = {
        '_meta': {'telar_version': '1.8.0', 'language': 'en'},
        'project': [{'order': 1, 'story_id': 'demo-story', 'title': 'A demo'}],
        'objects': {
            'map': {'title': 'A map', 'object_type': 'Map', 'source_url': 'https://x.test/m.json'},
        },
        'stories': {
            'demo-story': {'steps': [
                {'step': 1, 'object': 'map', 'x': 0.5, 'y': 0.5, 'zoom': 1,
                 'question': 'Q', 'answer': 'Plain answer.'},
            ]},
        },
        'glossary': {'demo-term': {'term': 'A term', 'content': 'A definition.'}},
    }
    bundle.update(overrides)
    return bundle


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / '_data'
    data.mkdir()
    (data / 'project.json').write_text(json.dumps([]), encoding='utf-8')
    (data / 'objects.json').write_text(json.dumps([]), encoding='utf-8')
    return data


def _read(site, name):
    return json.loads((site / name).read_text(encoding='utf-8'))


class TestAReleasedBundle:

    def test_an_object_gains_its_medium_from_object_type(self, site):
        merge_demo_content(_bundle())

        demo = _read(site, 'objects.json')[0]
        assert demo['medium'] == 'Map'
        assert demo['object_type'] == 'Map'
        assert 'alt_text' not in demo and 'media_type' not in demo

    def test_a_step_gains_no_empty_field(self, site):
        merge_demo_content(_bundle())

        step = _read(site, 'demo-story.json')[0]
        for key in ('alt_text', 'page', 'clip_start', 'clip_end', 'loop', 'answer_kramdown'):
            assert key not in step, key
        assert step['answer'] == 'Plain answer.'

    def test_a_story_without_maths_has_no_metadata_row(self, site):
        merge_demo_content(_bundle())

        assert not any(step.get('_metadata') for step in _read(site, 'demo-story.json'))


class TestABundleWithTheNewerFields:

    def test_object_fields_are_carried(self, site):
        objects = {'clip': {'title': 'A clip', 'medium': 'Film', 'object_type': 'Video',
                            'alt_text': 'A clip of a loom', 'media_type': 'Video',
                            'source_url': 'https://youtu.be/x'}}

        merge_demo_content(_bundle(objects=objects))

        demo = _read(site, 'objects.json')[0]
        assert (demo['medium'], demo['alt_text'], demo['media_type']) == \
            ('Film', 'A clip of a loom', 'Video')

    def test_step_fields_are_carried_as_text(self, site):
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': 'A.', 'page': 3,
             'clip_start': '0:05', 'clip_end': '0:20', 'loop': 'yes', 'alt_text': 'Page three'},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        step = _read(site, 'demo-story.json')[0]
        assert [step[k] for k in ('page', 'clip_start', 'clip_end', 'loop', 'alt_text')] == \
            ['3', '0:05', '0:20', 'yes', 'Page three']

    def test_maths_in_an_answer_loads_katex_and_reaches_it_as_written(self, site):
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': 'Area \\(x^2\\).'},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        rows = _read(site, 'demo-story.json')
        assert rows[0] == {'_metadata': True, 'has_latex': True}
        assert rows[1]['answer'] == 'Area \\(x^2\\).'
        assert rows[1]['answer_kramdown'] == 'Area $$x^2$$.'

    def test_a_glossary_link_in_an_answer_is_resolved(self, site):
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': 'See [[demo-term]].'},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        answer = _read(site, 'demo-story.json')[0]['answer']
        assert 'class="glossary-inline-link" data-term-id="demo-term"' in answer
        assert '>A term</a>' in answer

    def test_an_over_long_answer_is_cut(self, site):
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': ' '.join(['word'] * 400)},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        answer = _read(site, 'demo-story.json')[0]['answer']
        assert answer.endswith('…')
        assert len(answer.split()) < 400

    @pytest.mark.parametrize('related', [['demo-other', 'demo-third'], 'demo-other|demo-third'],
                             ids=['list', 'pipe-separated'])
    def test_related_terms_reach_the_glossary_page_as_a_list(self, site, tmp_path, related):
        glossary = {'demo-term': {'term': 'A term', 'content': 'A definition.',
                                  'related_terms': related}}

        merge_demo_content(_bundle(glossary=glossary))
        generate_glossary()

        entry = _read(site, 'demo-glossary.json')[0]
        assert entry['related_terms'] == ['demo-other', 'demo-third']
        page = (tmp_path / '_jekyll-files' / '_glossary' / 'demo-term.md').read_text(encoding='utf-8')
        assert 'related_terms:\n- demo-other\n- demo-third\n' in page


class TestTheGalleryFacet:

    def test_a_demo_object_is_counted_under_its_medium(self, site):
        from telar.search import build_facets

        merge_demo_content(_bundle())

        assert build_facets(_read(site, 'objects.json'))['medium'] == {'Map': 1}
