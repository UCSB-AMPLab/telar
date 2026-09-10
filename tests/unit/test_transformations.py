"""Tests for the tree-conditioned transformations.

The property these exist to hold is idempotence. A transformation that
decides from the tree rather than from a version number can run against any
site, including one it has already run against — which is what lets a
half-finished upgrade be repaired by running it again rather than leaving
the site stranded.

Every test here runs its transformation twice.

Version: v1.7.0
"""

import os
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import transformations as t
from migrations.base import BaseMigration, ChangeStatus


class _Site(BaseMigration):
    """A migration standing in for whatever chain calls these."""

    from_version, to_version = '0.2.0-beta', '1.7.0'
    description = 'test double'

    def __init__(self, repo_root, originals=None):
        super().__init__(repo_root)
        self.originals = originals or {}
        self.fetched = []

    def check_applicable(self):
        return True

    def apply(self):
        return []

    def _fetch_from_github(self, path, branch=None, timeout=10):
        self.fetched.append((path, branch))
        return self.originals.get(path)


# The README the framework shipped in components/, by content.
_SHIPPED_README = subprocess.run(
    ['git', 'show', 'v0.8.1-beta:components/README.md'],
    capture_output=True, text=True,
    cwd=os.path.join(os.path.dirname(__file__), '..', '..')).stdout


def _run_twice(transformation, site):
    """Run it, run it again, and return both sets of records."""
    return transformation(site), transformation(site)


class TestGitignorePathRewrite:

    def test_it_points_at_the_relocated_directories(self, tmp_path):
        (tmp_path / '.gitignore').write_text(
            'components/images/thumbs/\ncomponents/texts/glossary/_demo_*\n')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.rewrite_gitignore_paths, site)

        assert (tmp_path / '.gitignore').read_text() == (
            'telar-content/objects/thumbs/\n'
            'telar-content/texts/glossary/_demo_*\n')
        assert len(first) == 1
        assert second == [], 'a second run had nothing left to rewrite'

    def test_a_site_with_no_gitignore_is_left_alone(self, tmp_path):
        site = _Site(str(tmp_path))
        assert _run_twice(t.rewrite_gitignore_paths, site) == ([], [])
        assert not (tmp_path / '.gitignore').exists()

    def test_an_already_relocated_gitignore_is_untouched(self, tmp_path):
        before = 'telar-content/objects/\n_data/*.json\n'
        (tmp_path / '.gitignore').write_text(before)
        site = _Site(str(tmp_path))

        assert _run_twice(t.rewrite_gitignore_paths, site) == ([], [])
        assert (tmp_path / '.gitignore').read_text() == before


class TestGitignoreEntries:

    def test_missing_entries_are_added_once(self, tmp_path):
        (tmp_path / '.gitignore').write_text('_site/\n')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.ensure_gitignore_entries, site)

        content = (tmp_path / '.gitignore').read_text()
        for _, entries in t.GITIGNORE_SECTIONS:
            for entry in entries:
                assert content.count(entry) >= 1
        assert first, 'nothing was added on the first run'
        assert second == [], 'a second run added entries again'

    def test_what_the_owner_added_survives(self, tmp_path):
        (tmp_path / '.gitignore').write_text('# mine\nmy-drafts/\n*.bak\n')
        site = _Site(str(tmp_path))

        t.ensure_gitignore_entries(site)

        content = (tmp_path / '.gitignore').read_text()
        assert 'my-drafts/' in content and '*.bak' in content


class TestDeadPaths:

    def test_a_dead_file_is_removed(self, tmp_path):
        dead = tmp_path / 'assets/js/story.js'
        dead.parent.mkdir(parents=True)
        dead.write_text('// superseded')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.remove_dead_paths, site)

        assert not dead.exists()
        assert len(first) == 1
        assert second == [], 'a second run found nothing to remove'

    def test_a_dead_directory_is_removed_whole(self, tmp_path):
        directory = tmp_path / 'assets/images/openseadragon'
        directory.mkdir(parents=True)
        (directory / 'sprite.png').write_bytes(b'\x89PNG')
        site = _Site(str(tmp_path))

        t.remove_dead_paths(site)

        assert not directory.exists()

    def test_a_site_that_never_had_them_is_untouched(self, tmp_path):
        (tmp_path / 'index.md').write_text('mine')
        site = _Site(str(tmp_path))

        assert _run_twice(t.remove_dead_paths, site) == ([], [])
        assert (tmp_path / 'index.md').read_text() == 'mine'


class TestWithdrawnGlossaryTerms:

    def _term(self, tmp_path, directory, name, text):
        path = tmp_path / directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    # The term is compared against where it lived in the release that
    # withdrew it, not where the relocation has since put it.
    WITHDRAWN_FROM = 'components/texts/glossary'

    def test_an_untouched_term_is_removed(self, tmp_path):
        rel = 'telar-content/texts/glossary/reduccion.md'
        self._term(tmp_path, 'telar-content/texts/glossary', 'reduccion.md',
                   'shipped text\n')
        site = _Site(str(tmp_path), originals={
            f'{self.WITHDRAWN_FROM}/reduccion.md': 'shipped text\n'})

        first, second = _run_twice(t.remove_withdrawn_glossary_terms, site)

        assert not (tmp_path / rel).exists()
        assert 'Removed' in first[0].description
        assert second == []

    def test_an_edited_term_is_kept(self, tmp_path):
        rel = 'telar-content/texts/glossary/reduccion.md'
        self._term(tmp_path, 'telar-content/texts/glossary', 'reduccion.md',
                   'my own definition\n')
        site = _Site(str(tmp_path), originals={
            f'{self.WITHDRAWN_FROM}/reduccion.md': 'shipped text\n'})

        records = t.remove_withdrawn_glossary_terms(site)

        assert (tmp_path / rel).exists()
        assert 'edited on this site' in records[0].description

    def test_a_term_that_cannot_be_checked_is_kept(self, tmp_path):
        # Not knowing whether someone wrote it is a reason to leave it.
        rel = 'telar-content/texts/glossary/reduccion.md'
        self._term(tmp_path, 'telar-content/texts/glossary', 'reduccion.md',
                   'shipped text\n')
        site = _Site(str(tmp_path), originals={})

        records = t.remove_withdrawn_glossary_terms(site)

        assert (tmp_path / rel).exists()
        assert 'could not check' in records[0].description

    def test_an_empty_original_is_content_not_a_failed_fetch(self, tmp_path):
        # The distinction that stranded 65 of 71 entry points: an empty file
        # read as a failure. An empty shipped term matching an empty site
        # copy is an untouched term.
        rel = 'telar-content/texts/glossary/markdown.md'
        self._term(tmp_path, 'telar-content/texts/glossary', 'markdown.md', '')
        site = _Site(str(tmp_path), originals={
            f'{self.WITHDRAWN_FROM}/markdown.md': ''})

        records = t.remove_withdrawn_glossary_terms(site)

        assert not (tmp_path / rel).exists()
        assert 'Removed' in records[0].description

    def test_it_finds_terms_before_the_relocation_too(self, tmp_path):
        # A site entering from 0.6.x still has components/.
        rel = 'components/texts/glossary/viceroyalty.md'
        self._term(tmp_path, 'components/texts/glossary', 'viceroyalty.md',
                   'shipped\n')
        site = _Site(str(tmp_path), originals={rel: 'shipped\n'})

        t.remove_withdrawn_glossary_terms(site)

        assert not (tmp_path / rel).exists()

    def test_the_comparison_is_pinned_to_the_release_that_withdrew_them(
            self, tmp_path):
        rel = 'telar-content/texts/glossary/markdown.md'
        self._term(tmp_path, 'telar-content/texts/glossary', 'markdown.md', 'x')
        site = _Site(str(tmp_path), originals={
            f'{self.WITHDRAWN_FROM}/markdown.md': 'x'})

        t.remove_withdrawn_glossary_terms(site)

        # The historical path, not the relocated one. Asking v0.6.1-beta
        # for telar-content/ finds nothing, which reads as "cannot check"
        # and keeps every withdrawn term on every site, for ever.
        assert site.fetched == [
            (f'{self.WITHDRAWN_FROM}/markdown.md', t.WITHDRAWN_AT)]

    def test_a_relocated_term_is_still_checked(self, tmp_path):
        # The order the catalogue runs in puts the relocation first, so
        # this is the shape every pre-0.9.0 site arrives in.
        self._term(tmp_path, 'telar-content/texts/glossary', 'resguardo.md',
                   'shipped\n')
        site = _Site(str(tmp_path), originals={
            f'{self.WITHDRAWN_FROM}/resguardo.md': 'shipped\n'})

        records = t.remove_withdrawn_glossary_terms(site)

        assert not (tmp_path / 'telar-content/texts/glossary/resguardo.md').exists()
        assert 'Removed' in records[0].description


class TestTheCatalogue:

    def test_every_transformation_runs_against_an_empty_site(self, tmp_path):
        # The whole point: any of these can run against any site.
        site = _Site(str(tmp_path))
        for transformation in t.TRANSFORMATIONS:
            transformation(site)

    def test_no_transformation_reports_a_hard_failure_on_an_empty_site(
            self, tmp_path):
        site = _Site(str(tmp_path))
        for transformation in t.TRANSFORMATIONS:
            for record in transformation(site):
                assert not (record.status == ChangeStatus.FAILED
                            and record.severity == 'hard'), transformation.__name__


class TestContentRelocation:

    def _write(self, root, rel, text='content\n'):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_the_three_directories_move(self, tmp_path):
        self._write(tmp_path, 'components/images/photo.jpg')
        self._write(tmp_path, 'components/structures/objects.csv')
        self._write(tmp_path, 'components/texts/stories/mine/step.md')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.relocate_content, site)

        assert (tmp_path / 'telar-content/objects/photo.jpg').exists()
        assert (tmp_path / 'telar-content/spreadsheets/objects.csv').exists()
        assert (tmp_path / 'telar-content/texts/stories/mine/step.md').exists()
        assert not (tmp_path / 'components').exists()
        assert second == [], 'a second run had nothing left to move'

    def test_a_site_already_relocated_is_untouched(self, tmp_path):
        self._write(tmp_path, 'telar-content/objects/photo.jpg')
        site = _Site(str(tmp_path))

        assert _run_twice(t.relocate_content, site) == ([], [])
        assert (tmp_path / 'telar-content/objects/photo.jpg').exists()

    def test_both_present_refuses_rather_than_choosing(self, tmp_path):
        # Two directories of someone's work cannot be merged by guesswork.
        self._write(tmp_path, 'components/images/old.jpg', 'old\n')
        self._write(tmp_path, 'telar-content/objects/new.jpg', 'new\n')
        site = _Site(str(tmp_path))

        records = t.relocate_content(site)

        assert (tmp_path / 'components/images/old.jpg').read_text() == 'old\n'
        assert (tmp_path / 'telar-content/objects/new.jpg').read_text() == 'new\n'
        assert any('merge them by hand' in r.description for r in records)

    def test_components_is_kept_when_it_holds_the_owners_work(self, tmp_path):
        self._write(tmp_path, 'components/images/photo.jpg')
        self._write(tmp_path, 'components/my-notes/draft.md')
        site = _Site(str(tmp_path))

        records = t.relocate_content(site)

        assert (tmp_path / 'components/my-notes/draft.md').exists()
        assert any('still holds my-notes' in r.description for r in records)

    def test_placeholder_directories_do_not_stop_the_removal(self, tmp_path):
        self._write(tmp_path, 'components/images/photo.jpg')
        (tmp_path / 'components/audio').mkdir(parents=True)
        (tmp_path / 'components/pdfs').mkdir(parents=True)
        self._write(tmp_path, 'components/README.md')
        (tmp_path / 'components/README.md').write_text(
            _SHIPPED_README, encoding='utf-8')
        site = _Site(str(tmp_path))

        t.relocate_content(site)

        assert not (tmp_path / 'components').exists()

    def test_a_readme_the_owner_rewrote_stops_the_removal(self, tmp_path):
        self._write(tmp_path, 'components/images/photo.jpg')
        (tmp_path / 'components/README.md').write_text('Notes on our images\n')
        site = _Site(str(tmp_path))

        records = t.relocate_content(site)

        assert (tmp_path / 'components/README.md').read_text() == \
            'Notes on our images\n'
        assert any('still holds README.md' in r.description for r in records)


class TestAboutPage:

    def test_it_moves_and_keeps_what_the_owner_wrote(self, tmp_path):
        page = tmp_path / 'pages/about.md'
        page.parent.mkdir(parents=True)
        page.write_text('# About my project\n')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.relocate_about_page, site)

        moved = tmp_path / 'telar-content/texts/pages/about.md'
        assert moved.read_text() == '# About my project\n'
        assert not (tmp_path / 'pages').exists()
        assert second == []

    def test_a_site_without_one_is_left_alone(self, tmp_path):
        site = _Site(str(tmp_path))
        assert _run_twice(t.relocate_about_page, site) == ([], [])

    def test_both_present_refuses_rather_than_choosing(self, tmp_path):
        old = tmp_path / 'pages/about.md'
        old.parent.mkdir(parents=True)
        old.write_text('old\n')
        new = tmp_path / 'telar-content/texts/pages/about.md'
        new.parent.mkdir(parents=True)
        new.write_text('new\n')
        site = _Site(str(tmp_path))

        records = t.relocate_about_page(site)

        assert old.read_text() == 'old\n' and new.read_text() == 'new\n'
        assert any('merge them by hand' in r.description for r in records)

    def test_a_non_empty_pages_directory_survives(self, tmp_path):
        (tmp_path / 'pages').mkdir()
        (tmp_path / 'pages/about.md').write_text('about\n')
        (tmp_path / 'pages/contact.md').write_text('mine\n')
        site = _Site(str(tmp_path))

        t.relocate_about_page(site)

        assert (tmp_path / 'pages/contact.md').read_text() == 'mine\n'


class TestRelocationRunsFirst:

    def test_relocation_precedes_everything_that_speaks_in_new_paths(self):
        # The gitignore rewrite and the glossary removal both name
        # telar-content paths. Running either before the move would find
        # nothing and silently do nothing.
        order = [f.__name__ for f in t.TRANSFORMATIONS]
        assert order.index('relocate_content') < order.index('rewrite_gitignore_paths')
        assert order.index('relocate_content') < order.index('remove_withdrawn_glossary_terms')


class TestImageFlattening:

    def _site_with(self, tmp_path, base, objects=(), additional=()):
        for subdirectory, names in (('objects', objects),
                                    ('additional', additional)):
            directory = tmp_path / base / subdirectory
            directory.mkdir(parents=True, exist_ok=True)
            for name in names:
                (directory / name).write_text(f'{subdirectory}/{name}')
        return _Site(str(tmp_path))

    def test_it_brings_images_up_a_level(self, tmp_path):
        site = self._site_with(tmp_path, 'components/images',
                               objects=['a.jpg'], additional=['b.png'])

        first, second = _run_twice(t.flatten_image_directories, site)

        images = tmp_path / 'components/images'
        assert (images / 'a.jpg').read_text() == 'objects/a.jpg'
        assert (images / 'b.png').read_text() == 'additional/b.png'
        assert not (images / 'objects').exists()
        assert not (images / 'additional').exists()
        assert first and second == []

    def test_it_works_after_the_relocation_too(self, tmp_path):
        site = self._site_with(tmp_path, 'telar-content/objects',
                               objects=['a.jpg'])

        t.flatten_image_directories(site)

        assert (tmp_path / 'telar-content/objects/a.jpg').exists()
        assert not (tmp_path / 'telar-content/objects/objects').exists()

    def test_the_csv_referenced_name_wins_a_conflict(self, tmp_path):
        site = self._site_with(tmp_path, 'components/images',
                               objects=['map.jpg'], additional=['map.jpg'])

        t.flatten_image_directories(site)

        images = tmp_path / 'components/images'
        assert (images / 'map.jpg').read_text() == 'objects/map.jpg'
        assert (images / 'map-2.jpg').read_text() == 'additional/map.jpg'

    def test_it_keeps_a_file_rather_than_overwrite_the_suffixed_name(self, tmp_path):
        site = self._site_with(tmp_path, 'components/images',
                               objects=['map.jpg'], additional=['map.jpg'])
        (tmp_path / 'components/images/map-2.jpg').write_text('already here')

        records = t.flatten_image_directories(site)

        assert (tmp_path / 'components/images/map-2.jpg').read_text() == 'already here'
        assert (tmp_path / 'components/images/additional/map.jpg').exists()
        assert any('are taken' in record.description for record in records)

    def test_it_rewrites_the_paths_a_story_names(self, tmp_path):
        site = self._site_with(tmp_path, 'components/images',
                               objects=['a.jpg'], additional=['b.png'])
        (tmp_path / '_stories').mkdir()
        story = tmp_path / '_stories' / 'one.md'
        story.write_text(
            '![a](components/images/objects/a.jpg)\n'
            '<img src="/components/images/additional/b.png">\n'
            'url(../components/images/objects/a.jpg)\n')

        _run_twice(t.flatten_image_directories, site)

        assert story.read_text() == (
            '![a](components/images/a.jpg)\n'
            '<img src="/components/images/b.png">\n'
            'url(../components/images/a.jpg)\n')

    def test_a_rewritten_path_follows_the_rename(self, tmp_path):
        site = self._site_with(tmp_path, 'components/images',
                               objects=['map.jpg'], additional=['map.jpg'])
        (tmp_path / '_stories').mkdir()
        story = tmp_path / '_stories' / 'one.md'
        story.write_text('![m](components/images/additional/map.jpg)\n'
                         '![m](components/images/objects/map.jpg)\n')

        t.flatten_image_directories(site)

        assert story.read_text() == ('![m](components/images/map-2.jpg)\n'
                                     '![m](components/images/map.jpg)\n')

    def test_it_keeps_the_host_on_an_absolute_reference(self, tmp_path):
        site = self._site_with(tmp_path, 'components/images', objects=['a.jpg'])
        page = tmp_path / 'index.md'
        page.write_text('![a](https://example.org/site/components/images/objects/a.jpg)\n')

        t.flatten_image_directories(site)

        assert page.read_text() == (
            '![a](https://example.org/site/components/images/a.jpg)\n')

    def test_it_leaves_a_site_that_has_already_flattened_alone(self, tmp_path):
        (tmp_path / 'components/images').mkdir(parents=True)
        (tmp_path / 'components/images/a.jpg').write_text('flat')
        (tmp_path / '_stories').mkdir()
        story = tmp_path / '_stories' / 'one.md'
        story.write_text('![a](components/images/a.jpg)\n')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.flatten_image_directories, site)

        assert first == [] and second == []
        assert story.read_text() == '![a](components/images/a.jpg)\n'

    def test_it_does_not_touch_a_subdirectory_of_another_name(self, tmp_path):
        thumbs = tmp_path / 'components/images/thumbs'
        thumbs.mkdir(parents=True)
        (thumbs / 'a.jpg').write_text('thumb')
        site = _Site(str(tmp_path))

        assert t.flatten_image_directories(site) == []
        assert (thumbs / 'a.jpg').exists()


class TestSpreadsheetColumns:

    OBJECTS = ('object_id,title,source_url\n'
               'id_objeto,titulo,url_fuente\n'
               '# an object id,# a title,# where it came from\n'
               'map-1,A map,https://example.org/manifest\n')

    def _write(self, tmp_path, name, content,
               directory='telar-content/spreadsheets'):
        full = tmp_path / directory
        full.mkdir(parents=True, exist_ok=True)
        (full / name).write_text(content, encoding='utf-8')
        return full / name

    def test_each_header_row_gets_the_column_in_its_own_language(self, tmp_path):
        sheet = self._write(tmp_path, 'objects.csv', self.OBJECTS)
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.ensure_spreadsheet_columns, site)

        rows = sheet.read_text(encoding='utf-8').split('\n')
        assert rows[0] == ('object_id,title,source_url,year,object_type,'
                           'subjects,featured')
        assert rows[1] == ('id_objeto,titulo,url_fuente,año,tipo_objeto,'
                           'temas,destacado')
        assert rows[2].endswith(',,,,')
        assert rows[3] == 'map-1,A map,https://example.org/manifest,,,,'
        assert first and second == []

    def test_a_spanish_only_story_sheet_gets_the_spanish_name(self, tmp_path):
        sheet = self._write(tmp_path, 'mi-historia.csv',
                            'paso,objeto\n1,mapa\n')
        site = _Site(str(tmp_path))

        t.ensure_spreadsheet_columns(site)

        assert sheet.read_text(encoding='utf-8').split('\n')[0] == \
            'paso,objeto,página'

    def test_an_older_spelling_counts_as_present(self, tmp_path):
        sheet = self._write(
            tmp_path, 'project.csv',
            'order,story_id,title,protected\n'
            'orden,id_historia,titulo,protegido\n'
            '1,one,One,no\n')
        site = _Site(str(tmp_path))

        t.ensure_spreadsheet_columns(site)

        # private is present under its v0.8.1 spelling, so nothing is
        # added. show_sections is v1.2.0 work and not this hop's.
        assert sheet.read_text(encoding='utf-8') == (
            'order,story_id,title,protected\n'
            'orden,id_historia,titulo,protegido\n'
            '1,one,One,no\n')

    def test_it_leaves_the_templates_alone(self, tmp_path):
        blank = self._write(tmp_path, 'blank_template.csv', 'step,object\n')
        spanish = self._write(tmp_path, 'plantilla_en_blanco.csv', 'paso,objeto\n')
        site = _Site(str(tmp_path))

        assert t.ensure_spreadsheet_columns(site) == []
        assert blank.read_text() == 'step,object\n'
        assert spanish.read_text() == 'paso,objeto\n'

    def test_it_finds_spreadsheets_before_the_relocation(self, tmp_path):
        sheet = self._write(tmp_path, 'objects.csv',
                            'object_id,title\nmap-1,A map\n',
                            directory='components/structures')
        site = _Site(str(tmp_path))

        t.ensure_spreadsheet_columns(site)

        assert sheet.read_text(encoding='utf-8').split('\n')[0] == \
            'object_id,title,year,object_type,subjects,featured'

    def test_it_ignores_a_file_with_no_header_row(self, tmp_path):
        sheet = self._write(tmp_path, 'objects.csv', 'nonsense,rows\n1,2\n')
        site = _Site(str(tmp_path))

        assert t.ensure_spreadsheet_columns(site) == []
        assert sheet.read_text() == 'nonsense,rows\n1,2\n'


class TestSpreadsheetRename:

    def test_it_renames_the_manifest_column(self, tmp_path):
        directory = tmp_path / 'components/structures'
        directory.mkdir(parents=True)
        sheet = directory / 'objects.csv'
        sheet.write_text('object_id,title,iiif_manifest\n'
                         'map-1,A map,manifest.json\n', encoding='utf-8')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.rename_spreadsheet_columns, site)

        assert sheet.read_text(encoding='utf-8').split('\n')[0] == \
            'object_id,title,source_url'
        assert len(first) == 1 and second == []

    def test_it_leaves_a_data_cell_of_the_same_name_alone(self, tmp_path):
        directory = tmp_path / 'telar-content/spreadsheets'
        directory.mkdir(parents=True)
        sheet = directory / 'objects.csv'
        sheet.write_text('object_id,title,source_url\n'
                         'iiif_manifest,A map,x\n', encoding='utf-8')
        site = _Site(str(tmp_path))

        assert t.rename_spreadsheet_columns(site) == []
        assert 'iiif_manifest,A map,x' in sheet.read_text(encoding='utf-8')


class TestLegacyProjectSpreadsheet:

    LEGACY = ('key,value\n'
              'project_title,My project\n'
              'tagline,A tagline\n'
              'STORIES,\n'
              '1,First story\n'
              '2,Second story\n')

    def test_it_keeps_only_the_stories(self, tmp_path):
        directory = tmp_path / 'components/structures'
        directory.mkdir(parents=True)
        sheet = directory / 'project.csv'
        sheet.write_text(self.LEGACY, encoding='utf-8')
        site = _Site(str(tmp_path))

        first, second = _run_twice(t.restructure_project_spreadsheet, site)

        assert sheet.read_text(encoding='utf-8') == (
            'order,title,subtitle\n1,First story,\n2,Second story,\n')
        assert len(first) == 1 and second == []

    def test_it_leaves_a_current_spreadsheet_alone(self, tmp_path):
        directory = tmp_path / 'telar-content/spreadsheets'
        directory.mkdir(parents=True)
        sheet = directory / 'project.csv'
        current = 'order,story_id,title\n1,one,One\n'
        sheet.write_text(current, encoding='utf-8')
        site = _Site(str(tmp_path))

        assert t.restructure_project_spreadsheet(site) == []
        assert sheet.read_text(encoding='utf-8') == current


TEMPLATE_CONFIG = '''# Telar
title: "Telar"
description: "The demo site"
url: "https://demo.example.org"
baseurl: "/telar"
telar_theme: "trama" # Options: trama, paisajes
telar_language: "en" # Options: "en", "es"
collection_mode: false # Collection-first homepage

# Story Interface Settings
story_interface:
  show_story_steps: true # Set to false to hide the overlay
  include_demo_content: true # Fetch demo stories

story_key: "test"

google_sheets:
  enabled: true
  published_url: "https://docs.google.com/demo/pubhtml"

collection_interface:
  show_sample_on_homepage: true # The demo opts in

telar:
  version: "1.7.0"
  release_date: "2026-08-28"

development-features:
  skip_stories: false
  skip_collections: false
'''


class TestConfiguration:

    def _site(self, tmp_path, config):
        (tmp_path / '_config.yml').write_text(config, encoding='utf-8')
        return _Site(str(tmp_path), originals={'_config.yml': TEMPLATE_CONFIG})

    def test_it_keeps_the_sites_own_settings(self, tmp_path):
        site = self._site(tmp_path,
                          'title: "My site"\n'
                          'url: "https://mine.example.org"\n'
                          'baseurl: ""\n'
                          'telar_theme: "neogranadina"\n')

        first, second = _run_twice(t.reinstate_configuration, site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert 'title: "My site"' in merged
        assert 'url: "https://mine.example.org"' in merged
        assert 'baseurl: ""' in merged
        assert 'telar_theme: "neogranadina" # Options: trama, paisajes' in merged
        assert first and second == []

    def test_it_never_hands_a_site_the_demo_settings(self, tmp_path):
        site = self._site(tmp_path, 'title: "My site"\nurl: "https://mine.org"\n')

        t.reinstate_configuration(site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert 'story_key: ""' in merged
        assert 'enabled: false' in merged
        assert 'published_url: ""' in merged
        assert 'demo/pubhtml' not in merged

    def test_a_site_that_never_had_demo_content_does_not_get_it(self, tmp_path):
        site = self._site(tmp_path, 'title: "My site"\n')

        t.reinstate_configuration(site)

        assert 'include_demo_content: false' in \
            (tmp_path / '_config.yml').read_text(encoding='utf-8')

    def test_a_site_that_asked_for_demo_content_keeps_it(self, tmp_path):
        site = self._site(tmp_path,
                          'title: "My site"\n'
                          'story_interface:\n'
                          '  include_demo_content: true\n')

        t.reinstate_configuration(site)

        assert 'include_demo_content: true' in \
            (tmp_path / '_config.yml').read_text(encoding='utf-8')

    def test_it_follows_a_key_that_changed_name(self, tmp_path):
        site = self._site(tmp_path,
                          'title: "My site"\n'
                          'show_story_steps: false\n'
                          'testing-features:\n'
                          '  hide_stories: true\n')

        t.reinstate_configuration(site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert 'show_story_steps: false' in merged
        assert 'skip_stories: true' in merged
        assert 'testing-features' not in merged
        assert 'hide_stories' not in merged.replace(
            '# (Backward compatible: hide_stories also supported)', '')

    def test_it_drops_a_key_the_framework_retired(self, tmp_path):
        site = self._site(tmp_path,
                          'title: "My site"\n'
                          'openseadragon:\n'
                          '  prefixUrl: "/assets/images/openseadragon/"\n'
                          'telar:\n'
                          '  version: "0.2.0-beta"\n'
                          '  tagline: "old"\n')

        t.reinstate_configuration(site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert 'openseadragon' not in merged
        assert 'tagline' not in merged

    def test_the_merge_does_not_stamp_the_version(self, tmp_path):
        # The stamp is the migration's to write, once, at the end. Taking
        # the release's version here would mark the site as upgraded
        # before the framework had been installed.
        site = self._site(tmp_path,
                          'title: "My site"\ntelar:\n  version: "0.6.2-beta"\n')

        t.reinstate_configuration(site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert 'version: "0.6.2-beta"' in merged
        assert '1.7.0' not in merged

    def test_it_carries_a_key_the_site_added(self, tmp_path):
        site = self._site(tmp_path,
                          'title: "My site"\n'
                          '# our own switch\n'
                          'my_setting: true\n')

        t.reinstate_configuration(site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert t.config_merge.CARRIED_HEADING in merged
        assert yaml.safe_load(merged)['my_setting'] is True

    def test_a_failed_fetch_is_a_hard_failure(self, tmp_path):
        (tmp_path / '_config.yml').write_text('title: "My site"\n')
        site = _Site(str(tmp_path))

        records = t.reinstate_configuration(site)

        assert len(records) == 1
        assert records[0].severity == 'hard'
        assert 'Could not fetch' in records[0].description
        assert (tmp_path / '_config.yml').read_text() == 'title: "My site"\n'


class TestRoundNineteenFixes:
    """The defects an outside review found in the catalogue.

    Each of these had a passing test that did not detect it, so each one
    is pinned here by the failure it would cause on a real site.
    """

    # --- components/ removal

    def test_a_placeholder_holding_the_sites_media_stops_the_removal(self, tmp_path):
        (tmp_path / 'components/images').mkdir(parents=True)
        (tmp_path / 'components/images/a.jpg').write_text('x')
        (tmp_path / 'components/audio').mkdir(parents=True)
        (tmp_path / 'components/audio/interview.mp3').write_text('recording')
        site = _Site(str(tmp_path))

        records = t.relocate_content(site)

        assert (tmp_path / 'components/audio/interview.mp3').read_text() == 'recording'
        assert any('still holds audio' in r.description for r in records)

    def test_an_empty_placeholder_does_not_stop_it(self, tmp_path):
        (tmp_path / 'components/images').mkdir(parents=True)
        (tmp_path / 'components/images/a.jpg').write_text('x')
        (tmp_path / 'components/audio').mkdir(parents=True)
        (tmp_path / 'components/README.md').write_text(
            _SHIPPED_README, encoding='utf-8')
        site = _Site(str(tmp_path))

        t.relocate_content(site)

        assert not (tmp_path / 'components').exists()

    # --- flattening

    def test_a_different_file_of_the_same_name_is_not_assumed_moved(self, tmp_path):
        images = tmp_path / 'components/images'
        (images / 'objects').mkdir(parents=True)
        (images / 'map.jpg').write_text('the flat one')
        (images / 'objects/map.jpg').write_text('a different image')
        (tmp_path / '_stories').mkdir()
        story = tmp_path / '_stories/one.md'
        story.write_text('![m](components/images/objects/map.jpg)\n')
        site = _Site(str(tmp_path))

        records = t.flatten_image_directories(site)

        # objects.csv names this image by filename, so it cannot be
        # renamed here, and neither file is lost.
        assert (images / 'map.jpg').read_text() == 'the flat one'
        assert (images / 'objects/map.jpg').read_text() == 'a different image'
        assert story.read_text() == '![m](components/images/objects/map.jpg)\n'
        assert any('is a different image' in r.description for r in records)

    def test_the_same_file_already_moved_is_cleared_away(self, tmp_path):
        images = tmp_path / 'components/images'
        (images / 'objects').mkdir(parents=True)
        (images / 'map.jpg').write_text('same bytes')
        (images / 'objects/map.jpg').write_text('same bytes')
        site = _Site(str(tmp_path))

        t.flatten_image_directories(site)

        assert (images / 'map.jpg').read_text() == 'same bytes'
        assert not (images / 'objects').exists()

    # --- spreadsheets

    def test_a_cell_holding_a_newline_survives(self, tmp_path):
        directory = tmp_path / 'telar-content/spreadsheets'
        directory.mkdir(parents=True)
        sheet = directory / 'mi-historia.csv'
        sheet.write_text('step,answer\n1,"first line\nsecond line"\n',
                         encoding='utf-8', newline='')
        site = _Site(str(tmp_path))

        t.ensure_spreadsheet_columns(site)

        import csv
        with open(sheet, newline='', encoding='utf-8') as handle:
            rows = list(csv.reader(handle))
        assert rows[0] == ['step', 'answer', 'page']
        assert rows[1] == ['1', 'first line\nsecond line', '']

    def test_a_data_row_is_not_a_header_because_of_its_first_cell(self, tmp_path):
        directory = tmp_path / 'telar-content/spreadsheets'
        directory.mkdir(parents=True)
        sheet = directory / 'objects.csv'
        sheet.write_text('object_id,title,iiif_manifest\n'
                         'id_objeto,titulo,manifiesto\n'
                         'object_id,An object,iiif_manifest\n',
                         encoding='utf-8', newline='')
        site = _Site(str(tmp_path))

        t.rename_spreadsheet_columns(site)
        t.ensure_spreadsheet_columns(site)

        import csv
        with open(sheet, newline='', encoding='utf-8') as handle:
            rows = list(csv.reader(handle))
        # The third row is the site's data, whatever its first cell says.
        assert rows[2][0] == 'object_id'
        assert rows[2][2] == 'iiif_manifest'
        assert rows[2][3:] == ['', '', '', '']
        assert rows[0][2] == 'source_url'

    # --- configuration

    def _config_site(self, tmp_path, config):
        (tmp_path / '_config.yml').write_text(config, encoding='utf-8')
        return _Site(str(tmp_path), originals={'_config.yml': TEMPLATE_CONFIG})

    def test_an_escaped_quote_does_not_break_the_file(self, tmp_path):
        site = self._config_site(tmp_path, 'title: "He said \\" #tag"\n')

        t.reinstate_configuration(site)

        merged = yaml.safe_load(
            (tmp_path / '_config.yml').read_text(encoding='utf-8'))
        assert merged['title'] == 'He said " #tag'

    def test_a_block_scalar_keeps_its_body(self, tmp_path):
        site = self._config_site(
            tmp_path, 'description: |\n  My project\n  Its history\n')

        t.reinstate_configuration(site)

        merged = yaml.safe_load(
            (tmp_path / '_config.yml').read_text(encoding='utf-8'))
        assert merged['description'] == 'My project\nIts history\n'

    def test_a_flow_mapping_keeps_its_settings(self, tmp_path):
        site = self._config_site(
            tmp_path,
            'title: "M"\n'
            'google_sheets: {enabled: true, published_url: "mine"}\n')

        t.reinstate_configuration(site)

        merged = yaml.safe_load(
            (tmp_path / '_config.yml').read_text(encoding='utf-8'))
        assert merged['google_sheets'] == {'enabled': True,
                                           'published_url': 'mine'}

    def test_a_byte_order_mark_does_not_lose_the_settings(self, tmp_path):
        site = self._config_site(tmp_path,
                                 '﻿title: "My site"\nurl: "https://mine.org"\n')

        t.reinstate_configuration(site)

        merged = yaml.safe_load(
            (tmp_path / '_config.yml').read_text(encoding='utf-8'))
        assert merged['title'] == 'My site'
        assert merged['url'] == 'https://mine.org'

    def test_a_config_that_does_not_parse_is_left_alone(self, tmp_path):
        broken = 'title: "unclosed\n  - nonsense: [\n'
        site = self._config_site(tmp_path, broken)

        records = t.reinstate_configuration(site)

        assert (tmp_path / '_config.yml').read_text(encoding='utf-8') == broken
        assert any('could not be read as YAML' in r.description
                   for r in records)

    def test_the_demo_opt_in_is_not_handed_to_a_site(self, tmp_path):
        site = self._config_site(tmp_path, 'title: "My site"\n')

        t.reinstate_configuration(site)

        merged = yaml.safe_load(
            (tmp_path / '_config.yml').read_text(encoding='utf-8'))
        assert merged['collection_interface']['show_sample_on_homepage'] is False

    def test_a_key_the_release_dropped_is_not_put_back(self, tmp_path):
        site = self._config_site(
            tmp_path,
            'title: "M"\ngoogle_sheets:\n  enabled: true\n'
            '  shared_url: "https://docs.google.com/mine/edit"\n'
            '  published_url: "https://docs.google.com/mine/pubhtml"\n')

        t.reinstate_configuration(site)

        merged = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        assert 'shared_url' not in merged
        assert 'https://docs.google.com/mine/pubhtml' in merged

    def test_carrying_a_key_across_stays_stable(self, tmp_path):
        site = self._config_site(tmp_path,
                                 'title: "M"\n# our own switch\nmy_setting: true\n')

        t.reinstate_configuration(site)
        once = (tmp_path / '_config.yml').read_text(encoding='utf-8')
        t.reinstate_configuration(site)
        twice = (tmp_path / '_config.yml').read_text(encoding='utf-8')

        assert twice == once
        assert once.count(t.config_merge.CARRIED_HEADING) == 1


class TestRoundTwentyOneFixes:

    def test_a_carried_key_lands_inside_its_section(self, tmp_path):
        (tmp_path / '_config.yml').write_text(
            'title: "M"\ngoogle_sheets:\n  private_feed: secret\n',
            encoding='utf-8')
        site = _Site(str(tmp_path), originals={'_config.yml': TEMPLATE_CONFIG})

        t.reinstate_configuration(site)

        merged = yaml.safe_load(
            (tmp_path / '_config.yml').read_text(encoding='utf-8'))
        assert merged['google_sheets']['private_feed'] == 'secret'

    def test_a_reference_below_the_subdirectory_is_left_alone(self, tmp_path):
        nested = tmp_path / 'components/images/objects/sub'
        nested.mkdir(parents=True)
        (nested / 'map.jpg').write_text('x')
        (tmp_path / '_stories').mkdir()
        story = tmp_path / '_stories/a.md'
        story.write_text('![m](components/images/objects/sub/map.jpg)\n')
        site = _Site(str(tmp_path))

        t.flatten_image_directories(site)

        # The file is not moved, so pointing its reference one level up
        # would name a path that does not exist.
        assert story.read_text() == \
            '![m](components/images/objects/sub/map.jpg)\n'

    def test_a_query_string_is_not_part_of_the_filename(self, tmp_path):
        images = tmp_path / 'components/images'
        (images / 'objects').mkdir(parents=True)
        (images / 'map.jpg').write_text('the flat one')
        (images / 'objects/map.jpg').write_text('a different image')
        (tmp_path / '_stories').mkdir()
        story = tmp_path / '_stories/a.md'
        story.write_text('![m](components/images/objects/map.jpg?v=1)\n')
        site = _Site(str(tmp_path))

        t.flatten_image_directories(site)

        assert story.read_text() == \
            '![m](components/images/objects/map.jpg?v=1)\n'

    def test_a_spanish_only_sheet_has_no_second_header(self, tmp_path):
        directory = tmp_path / 'telar-content/spreadsheets'
        directory.mkdir(parents=True)
        sheet = directory / 'objetos.csv'
        # The second row is an object whose id is legitimately object_id.
        sheet.write_text('id_objeto\nobject_id\n', encoding='utf-8', newline='')
        site = _Site(str(tmp_path))

        t.ensure_spreadsheet_columns(site)

        assert sheet.read_text(encoding='utf-8') == (
            'id_objeto,año,tipo_objeto,temas,destacado\nobject_id,,,,\n')


class TestComponentsPlaceholders:
    """The shape the harness found on 21 of 71 real upgrade fixtures."""

    def _shipped(self, relative):
        return subprocess.run(
            ['git', 'show', f'v0.8.1-beta:components/{relative}'],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..', '..')).stdout

    def test_the_placeholders_the_framework_filled_do_not_stop_it(self, tmp_path):
        (tmp_path / 'components/images').mkdir(parents=True)
        (tmp_path / 'components/images/a.jpg').write_text('x')
        for relative in ('README.md', 'audio/README.md', 'pdfs/README.md',
                         '3d-models/README.md'):
            path = tmp_path / 'components' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._shipped(relative), encoding='utf-8')
        site = _Site(str(tmp_path))

        t.relocate_content(site)

        # Every one of these is the framework's own, so none of it is the
        # owner's work and the directory goes.
        assert not (tmp_path / 'components').exists()

    def test_a_file_of_the_owners_in_a_placeholder_stops_it(self, tmp_path):
        (tmp_path / 'components/images').mkdir(parents=True)
        (tmp_path / 'components/images/a.jpg').write_text('x')
        (tmp_path / 'components/audio').mkdir(parents=True)
        (tmp_path / 'components/audio/README.md').write_text(
            self._shipped('audio/README.md'), encoding='utf-8')
        (tmp_path / 'components/audio/interview.mp3').write_text('recording')
        site = _Site(str(tmp_path))

        records = t.relocate_content(site)

        assert (tmp_path / 'components/audio/interview.mp3').exists()
        assert any('audio/interview.mp3' in r.description for r in records)
