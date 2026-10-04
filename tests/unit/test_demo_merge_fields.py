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
        assert 'alt_text' not in demo and demo['media_type'] == 'Image'

    def test_a_step_gains_no_empty_field(self, site):
        merge_demo_content(_bundle())

        step = _read(site, 'demo-story.json')[0]
        for key in ('alt_text', 'page', 'clip_start', 'clip_end', 'loop'):
            assert key not in step, key
        assert step['answer'] == '<p>Plain answer.</p>'

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
        assert rows[1]['answer'] == '<p>Area \\(x^2\\).</p>'

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
        assert answer == '<p>' + ' '.join(['word'] * 190) + '…</p>'

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


class TestAgreementWithTheSite:

    def test_an_objects_media_type_is_the_one_its_page_shows(self, site):
        """objects.json and the object page classify from the source URL
        alone; a bundle's own media_type is not a third reading."""
        from generate_collections import _object_page

        objects = {
            'film': {'title': 'A film', 'media_type': 'Video',
                     'source_url': 'https://x.test/film.mp4'},
            'clip': {'title': 'A clip', 'media_type': 'Image',
                     'source_url': 'https://www.youtube.com/watch?v=abc'},
        }
        merge_demo_content(_bundle(objects=objects))

        for obj in _read(site, 'objects.json'):
            page = _object_page(obj)
            assert f"media_type: {obj['media_type']}\n" in page, obj['object_id']
        by_id = {o['object_id']: o['media_type'] for o in _read(site, 'objects.json')}
        assert by_id == {'film': 'Image', 'clip': 'Video'}

    def test_an_answer_links_a_term_the_site_glossary_holds(self, site):
        sheets = site.parent / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title,definition\nsite-term,A site term,Defined.\n',
            encoding='utf-8')
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q',
             'answer': 'See [[site-term]] and [[demo-term]].'},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        answer = _read(site, 'demo-story.json')[0]['answer']
        assert 'data-term-id="site-term"' in answer
        assert 'data-term-id="demo-term"' in answer
        assert 'glossary-link-error' not in answer

    def test_the_sites_title_wins_over_a_demo_term_of_the_same_id(self, site):
        sheets = site.parent / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title,definition\ndemo-term,Site title,Defined.\n',
            encoding='utf-8')
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': 'See [[demo-term]].'},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        answer = _read(site, 'demo-story.json')[0]['answer']
        assert '>Site title</a>' in answer
        assert '>A term</a>' not in answer


class TestASiteTermAtTheSameAddress:

    def _site_glossary(self, site, rows):
        sheets = site.parent / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title,definition\n' + rows, encoding='utf-8')

    @pytest.mark.parametrize('demo_id, site_id', [
        ('Viewer', 'viewer'),
        ('my term', 'my-term'),
    ])
    def test_the_site_term_wins_where_the_ids_differ_but_the_address_is_shared(
            self, site, demo_id, site_id):
        from telar.story_pages import jekyll_slug
        assert jekyll_slug(demo_id) == jekyll_slug(site_id)
        self._site_glossary(site, f'{site_id},Site title,Defined.\n')
        glossary = {demo_id: {'term': 'Demo title', 'content': 'A definition.'}}
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q',
             'answer': f'See [[{demo_id}]].'},
        ]}}

        merge_demo_content(_bundle(glossary=glossary, stories=stories))

        answer = _read(site, 'demo-story.json')[0]['answer']
        assert '>Site title</a>' in answer
        assert 'Demo title' not in answer

    def test_a_site_term_the_generator_does_not_publish_does_not_win(self, site, tmp_path):
        """A glossary.csv without a `definition` column publishes no site
        page, so the demo term keeps the address and the link names it."""
        sheets = site.parent / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title\ndemo-term,Site title\n', encoding='utf-8')
        glossary = {'Demo Term': {'term': 'Demo title', 'content': 'A definition.'}}
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q',
             'answer': 'See [[Demo Term]].'},
        ]}}

        merge_demo_content(_bundle(glossary=glossary, stories=stories))
        generate_glossary()

        pages = sorted(p.name for p in (tmp_path / '_jekyll-files' / '_glossary').glob('*.md'))
        assert pages == ['Demo Term.md']
        answer = _read(site, 'demo-story.json')[0]['answer']
        assert '>Demo title</a>' in answer
        assert 'Site title' not in answer

    def test_a_site_term_with_no_page_is_not_linked_from_a_demo_answer(self, site):
        """No `definition` column: no site page, so there is nothing at
        /glossary/site-term/ for a demo answer to link."""
        sheets = site.parent / 'telar-content' / 'spreadsheets'
        sheets.mkdir(parents=True)
        (sheets / 'glossary.csv').write_text(
            'term_id,title\nsite-term,Site title\n', encoding='utf-8')
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': 'See [[site-term]].'},
        ]}}

        merge_demo_content(_bundle(stories=stories))

        answer = _read(site, 'demo-story.json')[0]['answer']
        assert 'glossary-inline-link' not in answer
        assert 'glossary-link-error' in answer

    @pytest.mark.parametrize('front_matter, shown', [
        ('term_id: viewer\n', 'viewer'),
        ('term_id: viewer\ntitle: Site viewer\n', 'Site viewer'),
        ('term_id: viewer\ntitle: "Site viewer" # a note\n', 'Site viewer'),
        ('term_id: viewer\nsubtitle: Other text\n', 'viewer'),
        ('term_id: viewer\nsubtitle: Other text\ntitle: Site viewer\n', 'Site viewer'),
        ('term_id: viewer\ntitle: [Site, viewer]\n', 'Siteviewer'),
        ('term_id: viewer\ntitle: .inf\n', 'Infinity'),
        ('term_id: viewer\ntitle: 2024-01-02T10:30:00Z\n', '2024-01-02 10:30:00 UTC'),
        ('term_id: viewer\ntitle: 2024-01-02T10:30:00+00:00\n', '2024-01-02 10:30:00 +0000'),
        ('term_id: viewer\ntitle: 2024-01-02T10:30:00+02:00\n', '2024-01-02 10:30:00 +0200'),
    ])
    def test_a_legacy_markdown_page_names_the_link_as_the_page_does(
            self, site, tmp_path, front_matter, shown):
        glossary_dir = site.parent / 'telar-content' / 'texts' / 'glossary'
        glossary_dir.mkdir(parents=True)
        (glossary_dir / 'viewer.md').write_text(
            f'---\n{front_matter}---\n\nThe site viewer.\n', encoding='utf-8')
        glossary = {'viewer': {'term': 'Demo title', 'content': 'A definition.'}}
        stories = {'demo-story': {'steps': [
            {'step': 1, 'object': 'map', 'question': 'Q', 'answer': 'See [[viewer]].'},
        ]}}

        merge_demo_content(_bundle(glossary=glossary, stories=stories))
        generate_glossary()

        pages = sorted(p.name for p in (tmp_path / '_jekyll-files' / '_glossary').glob('*.md'))
        assert pages == ['viewer.md']
        answer = _read(site, 'demo-story.json')[0]['answer']
        assert f'>{shown}</a>' in answer
        assert 'Demo title' not in answer
