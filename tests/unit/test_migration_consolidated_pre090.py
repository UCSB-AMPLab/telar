"""Unit tests for the consolidated pre-v0.9.0 migration.

Eighteen migration modules were collapsed into one that can be entered from
any of the versions they covered. These tests cover what that collapse
changes: multi-entry dispatch, entry pinning, which steps run for a given
entry, and that a step failing part-way still stops the upgrade where it
stood.

Version: v1.7.0
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations import v020_to_v090
from migrations.base import BaseMigration, ChangeRecord, ChangeStatus
from migrations.v020_to_v090 import (
    ENTRY_VERSIONS, FRAMEWORK_FILES_090, MANUAL_STEPS_EN,
    MANUAL_STEPS_ES, Migration020to090,
)


def _fake_migration(frm, to, changes=None, raises=None):
    class _Step(BaseMigration):
        from_version = frm
        to_version = to
        description = f"fake {frm}"

        def check_applicable(self):
            return True

        def apply(self):
            _Step.ran = True
            if raises:
                raise raises
            return list(changes or [])

    _Step.ran = False
    return _Step


def _fake_transformation(name, changes=None, raises=None):
    """A transformation that records that it ran and returns what it is told."""
    def transformation(migration):
        transformation.ran = True
        if raises:
            raise raises
        return list(changes or [])

    transformation.__name__ = name
    transformation.ran = False
    return transformation


@pytest.fixture
def fake_chain(monkeypatch):
    """Replace the eighteen real steps with cheap ones, and stub the install.

    Without the stub these tests fetch 110 files from GitHub and write them
    into whatever path they were handed — which they did, into /tmp, at
    eleven seconds a test. A unit test that reaches the network is not a
    unit test, and one that installs a framework into a directory it does
    not own is a hazard.

    Both halves are replaced on setup, not only on request. The install
    stub alone left the real TRANSFORMATIONS in place, so any test that
    took the fixture without calling `catalogue()` still ran
    `reinstate_configuration`, which fetches. It failed silently rather
    than loudly, because the migration treats a failed fetch as a soft
    warning: the test passed, over the network, on whatever GitHub
    happened to be serving.
    """
    installed = []

    def _fake_install(self, file_map, tag=None):
        installed.append((file_map, tag))
        return []

    monkeypatch.setattr(Migration020to090, '_apply_framework_files',
                        _fake_install)

    def _catalogue(*transformations):
        monkeypatch.setattr(v020_to_v090, 'TRANSFORMATIONS',
                            list(transformations))
        return transformations

    _catalogue(_fake_transformation('stubbed_by_default'))

    def _install(*versions):
        monkeypatch.setattr(v020_to_v090, 'ENTRY_VERSIONS', tuple(versions))
        return versions

    _install.installed = installed
    _install.catalogue = _catalogue
    return _install


class TestTheFixtureLeavesNothingReal:

    def test_taking_the_fixture_replaces_the_catalogue(self, fake_chain):
        """Without this, a test that takes the fixture and does not call
        `catalogue()` runs the real transformations, one of which fetches
        from GitHub. A failed fetch is a soft warning, so the test passes
        either way and the network use is invisible."""
        assert v020_to_v090.TRANSFORMATIONS == [] or all(
            t.__module__ == __name__ for t in v020_to_v090.TRANSFORMATIONS)


class TestEntryVersions:

    def test_covers_every_legacy_release(self):
        assert Migration020to090.entry_version_list() == list(ENTRY_VERSIONS)
        assert len(ENTRY_VERSIONS) == 18

    def test_lands_on_the_first_tagged_release(self):
        assert Migration020to090.to_version == '0.9.0-beta'
        assert Migration020to090.to_version not in ENTRY_VERSIONS

    def test_the_run_is_a_set_with_the_ends_it_claims(self):
        assert len(set(ENTRY_VERSIONS)) == len(ENTRY_VERSIONS)
        assert ENTRY_VERSIONS[0] == '0.2.0-beta'
        assert ENTRY_VERSIONS[-1] == '0.8.1-beta'

    def test_every_last_writer_names_a_position_in_the_run(self):
        """FRAMEWORK_FILES_090's indices are positions in ENTRY_VERSIONS.

        An index past the end would withhold a file from every entry; a
        negative one would install it for all of them.
        """
        for path, (_, last_writer) in FRAMEWORK_FILES_090.items():
            assert 0 <= last_writer < len(ENTRY_VERSIONS), path

    def test_every_entry_version_is_applicable(self, tmp_path):
        for entry in ENTRY_VERSIONS:
            migration = Migration020to090(str(tmp_path))
            migration.from_version = entry
            assert migration.check_applicable(), entry

    def test_a_version_below_the_range_is_rejected(self, tmp_path):
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.1.1-beta'
        assert not migration.check_applicable()
        with pytest.raises(ValueError, match='0.1.1-beta'):
            migration._entry_index()


class TestDispatch:

    @pytest.mark.parametrize('entry', Migration020to090.entry_version_list())
    def test_every_legacy_version_reaches_the_latest_release(self, entry, monkeypatch):
        monkeypatch.setattr(Migration020to090, 'check_applicable', lambda self: True)
        # Later migrations decide applicability from the tree; the question
        # here is only which links the dispatcher chains together.
        for MigrationClass in upgrade.MIGRATIONS:
            if MigrationClass is not Migration020to090:
                monkeypatch.setattr(MigrationClass, 'check_applicable', lambda self: True)

        path = upgrade.get_migration_path(entry, '/tmp')

        assert isinstance(path[0], Migration020to090)
        assert path[-1].to_version == upgrade.LATEST_VERSION

    def test_dispatch_pins_the_version_the_site_is_on(self, monkeypatch):
        monkeypatch.setattr(Migration020to090, 'check_applicable', lambda self: True)
        for MigrationClass in upgrade.MIGRATIONS:
            if MigrationClass is not Migration020to090:
                monkeypatch.setattr(MigrationClass, 'check_applicable', lambda self: False)

        path = upgrade.get_migration_path('0.6.2-beta', '/tmp')

        # Not the class default of 0.2.0-beta: the summary has to name the
        # version the user actually started from.
        assert path[0].from_version == '0.6.2-beta'

    def test_a_version_outside_the_run_is_rejected(self, tmp_path):
        """An out-of-range version is not applicable, and has no position.

        `get_migration_path` guards on `entry_versions` before it pins
        anything, so False is what the dispatcher asks for; the position
        lookup is the one that has no answer to give.
        """
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.9.9-beta'
        assert not migration.check_applicable()
        with pytest.raises(ValueError, match='not one of the versions'):
            migration._entry_index()


class TestTheCatalogueRuns:
    """Every transformation runs, whatever version the site entered at.

    That is the whole point of deciding from the tree: there is no run of
    steps to join part-way through, so nothing has to work out which of
    them this site has already had.
    """

    def test_every_transformation_runs_whatever_the_entry_version(
            self, fake_chain, tmp_path):
        first, second, third = fake_chain.catalogue(
            _fake_transformation('first'), _fake_transformation('second'),
            _fake_transformation('third'))

        for entry in ('0.2.0-beta', '0.6.2-beta', '0.8.1-beta'):
            first.ran = second.ran = third.ran = False
            migration = Migration020to090(str(tmp_path))
            migration.from_version = entry
            migration.apply()

            assert first.ran and second.ran and third.ran, entry

    def test_one_with_nothing_to_do_does_not_stop_the_others(
            self, fake_chain, tmp_path):
        quiet, later = fake_chain.catalogue(
            _fake_transformation('quiet'), _fake_transformation('later'))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        records = migration.apply()

        assert quiet.ran and later.ran
        assert all(r.status == ChangeStatus.APPLIED for r in records)


class TestFailureStopsTheRun:

    def test_a_failed_fetch_stops_before_the_next_transformation(
            self, fake_chain, tmp_path):
        failing, later = fake_chain.catalogue(
            _fake_transformation('failing', changes=[
                'Warning: Could not fetch _config.yml from GitHub']),
            _fake_transformation('later'))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        records = migration.apply()

        assert not later.ran
        assert records[-1].status == ChangeStatus.FAILED
        assert records[-1].severity == 'hard'

    def test_a_migration_raising_is_recorded_rather_than_crashing(self, tmp_path):
        """run_migrations catches an unexpected exception and records a hard
        failure, so the chain fails closed. The handler asked a name that was
        never in scope, so it raised NameError out of the runner instead --
        on the one path whose whole job is to stop cleanly. Nothing exercised
        it, which is why it survived."""
        Raiser = _fake_migration('1.0', '2.0', raises=RuntimeError('boom'))

        records = upgrade.run_migrations([Raiser(str(tmp_path))])

        assert records[-1].status == ChangeStatus.FAILED
        assert records[-1].severity == 'hard'
        assert 'boom' in records[-1].description

    def test_a_dry_run_names_each_migration_without_applying_it(self, tmp_path):
        """The dry-run branch reads the site's language the same way, so it
        carried the same undefined name."""
        Step = _fake_migration('1.0', '2.0')

        records = upgrade.run_migrations([Step(str(tmp_path))], dry_run=True)

        assert records == []
        assert not Step.ran

    def test_a_raising_transformation_is_named(self, fake_chain, tmp_path):
        fake_chain.catalogue(
            _fake_transformation('relocate_content',
                                 raises=RuntimeError('disk full')),
            _fake_transformation('later'))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        records = migration.apply()

        # Named, not merely reported: the owner needs to know which part
        # of the upgrade gave out, not only that it did.
        assert records[-1].description.startswith(
            'relocate_content aborted: disk full')
        assert records[-1].severity == 'hard'

    def test_a_soft_change_does_not_stop_the_run(self, fake_chain, tmp_path):
        _, later = fake_chain.catalogue(
            _fake_transformation('soft', changes=['Could not move old_file.md']),
            _fake_transformation('later'))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        records = migration.apply()

        assert later.ran
        assert all(r.status == ChangeStatus.APPLIED for r in records)

    def test_every_record_of_the_failing_step_is_reported(self, fake_chain, tmp_path):
        # A legacy step keeps working after a failed fetch and reports what it
        # did. The chain runner coerces that whole list before it stops, so
        # anything the consolidated migration drops is work performed and not
        # accounted for.
        fake_chain.catalogue(_fake_transformation('noisy', changes=[
            'Updated _config.yml',
            'Warning: Could not fetch assets/js/story.js from GitHub',
            'Updated _data/navigation.yml',
            'Warning: Could not fetch _includes/viewer.html from GitHub',
        ]))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        records = migration.apply()

        assert [r.description for r in records] == [
            'Updated _config.yml',
            'Warning: Could not fetch assets/js/story.js from GitHub',
            'Updated _data/navigation.yml',
            'Warning: Could not fetch _includes/viewer.html from GitHub',
        ]

    def test_the_consolidated_run_matches_the_chain_runner(self, fake_chain, tmp_path):
        # The two must agree exactly: one of them stopping earlier than the
        # other is a difference in what the user is told went wrong.
        import telar_upgrade as upgrade

        changes = ['before', 'Warning: Could not fetch x from GitHub', 'after']
        fake_chain('1.0', '2.0')
        step = _fake_migration('1.0', '2.0', changes=changes)
        fake_chain.catalogue(_fake_transformation('whole', changes=changes))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        consolidated = [r.description for r in migration.apply()]

        through_runner = [r.description for r in upgrade.run_migrations([step('/tmp')])]

        assert consolidated == through_runner


class TestManualSteps:
    """Forty-three instructions became four, plus the demo-content notice.

    The chain handed out one set per release, so a site entering at
    0.2.0-beta was told three separate times to replace build.yml, walked
    through feature tours for releases it had never run, and read six
    variations of "nothing to do". None of the four that remain is
    conditional: the hop lands every entry version on the same tree, so it
    leaves them all the same work.
    """

    def _steps(self, tmp_path, entry='0.2.0-beta'):
        migration = Migration020to090(str(tmp_path))
        migration.from_version = entry
        return migration.get_manual_steps()

    def test_every_entry_version_is_left_the_same_work(self, tmp_path):
        for entry in ENTRY_VERSIONS:
            assert self._steps(tmp_path, entry) == self._steps(tmp_path), entry

    def test_the_four_and_the_notice(self, tmp_path):
        assert len(self._steps(tmp_path)) == 5
        assert len(MANUAL_STEPS_EN) == len(MANUAL_STEPS_ES) == 4

    def test_the_workflow_files_are_the_one_critical_step(self, tmp_path):
        first = self._steps(tmp_path)[0]

        assert first['critical'] is True
        for workflow in ('build.yml', 'upgrade.yml', 'telar-tests.yml'):
            assert f'.github/workflows/{workflow}' in first['description']

    def test_the_workflows_come_from_the_tag_this_hop_lands_on(self):
        """A site that has just reached 0.9.0 cannot run main's workflow.

        Every pre-0.9.0 build.yml reads `components/`; the one at
        v0.9.0-beta reads `telar-content/`, which is where this hop puts
        the content. A later one expects a tree the site does not have.
        """
        for steps in (MANUAL_STEPS_EN, MANUAL_STEPS_ES):
            assert Migration020to090._TARGET_TAG in steps[0]['description']
            assert '/tree/main/' not in steps[0]['description']
            assert '/blob/main/' not in steps[0]['description']

    def test_a_spanish_site_is_told_in_spanish(self, tmp_path):
        (tmp_path / '_config.yml').write_text('telar_language: "es"\n',
                                              encoding='utf-8')

        assert self._steps(tmp_path)[0]['description'].startswith(
            '**Actualiza los flujos de trabajo')

    def test_the_two_languages_carry_the_same_fields(self):
        for english, spanish in zip(MANUAL_STEPS_EN, MANUAL_STEPS_ES):
            assert set(english) == set(spanish)

    def test_the_paths_it_names_are_the_ones_the_hop_moved_content_to(self,
                                                                     tmp_path):
        relocation = self._steps(tmp_path)[1]['description']

        assert 'components/images/' in relocation
        assert 'telar-content/objects/' in relocation

    def test_manual_steps_survive_a_failed_run(self, fake_chain, tmp_path):
        fake_chain('1.0')
        fake_chain.catalogue(_fake_transformation(
            'stops', changes=['Warning: Could not fetch x from GitHub']))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '1.0'
        migration.apply()

        # The chain runner builds the summary from the migrations in the
        # path, not from the ones that finished, so a stopped run still
        # lists what the user has to do by hand.
        assert len(migration.get_manual_steps()) == 5


class TestOneStampPerHop:
    """One hop writes one stamp, at the end, so a chain that gives out
    part-way leaves no stamp for a version whose files were never
    installed."""

    def test_the_hop_stamps_its_own_target_once(self, fake_chain, tmp_path):
        config = tmp_path / '_config.yml'
        config.write_text('telar:\n  version: "0.2.0-beta"\n'
                          '  release_date: "2000-01-01"\n')
        fake_chain('1.0', '2.0')

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '1.0'
        records = migration.apply()

        stamps = [r for r in records if 'version 0.9.0-beta' in r.description]
        assert len(stamps) == 1
        assert '0.9.0-beta' in config.read_text()

    def test_a_failed_hop_leaves_the_entry_version_in_place(self, fake_chain,
                                                             tmp_path):
        # The site must stay at a version it really is, so a re-run enters
        # this migration again rather than resuming inside a half-applied
        # hop. The failing transformation writes to _config.yml first, the
        # way the real configuration one does: without that this passes
        # whether or not the stamp is held back, because nothing ever
        # tried to write.
        config = tmp_path / '_config.yml'
        config.write_text('telar:\n  version: "0.2.0-beta"\n'
                          '  release_date: "2000-01-01"\n')

        def writes_then_fails(migration):
            migration._write_file('_config.yml',
                                  'telar:\n  version: "0.2.0-beta"\n'
                                  '  release_date: "2000-01-01"\n'
                                  'title: ""\n')
            return ['Warning: Could not fetch x from GitHub']

        writes_then_fails.__name__ = 'writes_then_fails'
        fake_chain.catalogue(writes_then_fails,
                             _fake_transformation('never_reached'))

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        records = migration.apply()

        assert not any('version 0.9.0-beta' in r.description for r in records)
        assert '0.2.0-beta' in config.read_text()


class TestTheSingleInstall:
    """Eighteen steps fetched 311 file entries covering 187 paths, each
    overwriting the last. One install of 110 replaces them."""

    def test_it_installs_the_framework_set_pinned_to_the_target_tag(
            self, fake_chain, tmp_path):
        fake_chain('1.0')

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '1.0'
        migration.apply()

        assert len(fake_chain.installed) == 1
        file_map, tag = fake_chain.installed[0]
        assert set(file_map) <= set(FRAMEWORK_FILES_090)
        assert all(isinstance(v, str) for v in file_map.values())
        # tag=None means _target_ref(), which resolves to _TARGET_TAG.
        assert tag is None
        assert Migration020to090._TARGET_TAG == 'v0.9.0-beta'

    def test_a_failed_install_stops_before_the_stamp(self, fake_chain, tmp_path,
                                                     monkeypatch):
        config = tmp_path / '_config.yml'
        config.write_text('telar:\n  version: "0.2.0-beta"\n'
                          '  release_date: "2000-01-01"\n')
        fake_chain('1.0')

        monkeypatch.setattr(
            Migration020to090, '_apply_framework_files',
            lambda self, file_map, tag=None: [ChangeRecord(
                description='Warning: Could not fetch README.md from GitHub',
                status=ChangeStatus.FAILED, severity='hard')])

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '1.0'
        records = migration.apply()

        assert not any('version 0.9.0-beta' in r.description for r in records)
        assert '0.2.0-beta' in config.read_text()


class TestTheInstallSetIsSafe:
    """Structural, not behavioural: these hold whatever the list is edited
    to say, because the cost of getting them wrong is a user's own files."""

    def test_it_installs_no_user_content(self):
        # telar-content/ holds the site's own writing. The templates among
        # those files are replaced only by _update_template_content(), which
        # first checks the user has not edited them; installing them here
        # would walk past that check and overwrite a site's objects.csv.
        assert [p for p in FRAMEWORK_FILES_090
                if p.startswith('telar-content/')] == []

    def test_it_installs_no_workflow_files(self):
        # GITHUB_TOKEN cannot write these, so an upgrade running in Actions
        # would fail on them. They are manual instructions instead.
        assert [p for p in FRAMEWORK_FILES_090
                if p.startswith('.github/workflows/')] == []

    def test_every_path_exists_at_the_tag_it_is_fetched_from(self):
        # A path absent at v0.9.0-beta is a fetch that must fail, and a
        # failed framework fetch stops the whole upgrade.
        import subprocess
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        listing = subprocess.run(
            ['git', '-C', str(repo_root),
             'ls-tree', '-r', '--name-only', 'v0.9.0-beta'],
            capture_output=True, text=True)
        if listing.returncode != 0:
            pytest.skip('the framework repository is not available here')
        at_tag = set(listing.stdout.split())
        assert sorted(set(FRAMEWORK_FILES_090) - at_tag) == []

    def test_every_path_has_a_description(self):
        # The description is what the user reads in the upgrade summary.
        assert [p for p, (d, _) in FRAMEWORK_FILES_090.items()
                if not d.strip()] == []


class TestTheInstallIsEntryAware:
    """A path whose last writer sits before the entry version is one the
    replaced chain never touched from here. Installing it anyway overwrites
    whatever the site's owner has there."""

    def test_a_late_entry_does_not_touch_the_customisable_themes(self, tmp_path):
        # v081_to_v090 is all a 0.8.1 site runs, and it never writes these
        # four. A site whose owner customised paisajes.yml keeps it. The
        # protection is about files the site HAS: a theme it lacks is
        # installed regardless.
        themes = tmp_path / '_data/themes'
        themes.mkdir(parents=True)
        for theme in ('austin', 'neogranadina', 'paisajes', 'santa-barbara'):
            (themes / f'{theme}.yml').write_text('# the owner\'s\n')

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.8.1-beta'
        selected = migration._files_for_entry()

        for theme in ('austin', 'neogranadina', 'paisajes', 'santa-barbara'):
            assert f'_data/themes/{theme}.yml' not in selected

    def test_a_late_entry_still_gets_the_theme_that_is_new(self):
        # trama.yml arrives with v0.9.0-beta, so every entry needs it.
        migration = Migration020to090('/tmp')
        migration.from_version = '0.8.1-beta'
        assert '_data/themes/trama.yml' in migration._files_for_entry()

    def test_an_early_entry_does_get_the_themes(self, tmp_path):
        # v034_to_v040 overwrites them unconditionally, so withholding them
        # here would be its own regression.
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        selected = migration._files_for_entry()

        for theme in ('austin', 'neogranadina', 'paisajes', 'santa-barbara'):
            assert f'_data/themes/{theme}.yml' in selected

    def test_the_selection_shrinks_as_the_entry_rises(self, tmp_path):
        # Against a site that already holds every framework file, so the
        # absent-file clause does not mask the entry rule.
        for path in FRAMEWORK_FILES_090:
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text('present\n')

        sizes = []
        for version in Migration020to090.entry_version_list():
            migration = Migration020to090(str(tmp_path))
            migration.from_version = version
            sizes.append(len(migration._files_for_entry()))

        assert sizes == sorted(sizes, reverse=True)
        assert sizes[0] > sizes[-1]

    def test_no_selection_is_empty(self):
        # An entry that installed nothing would leave a site on 0.9.0-beta
        # with none of its files.
        for version in Migration020to090.entry_version_list():
            migration = Migration020to090('/tmp')
            migration.from_version = version
            assert migration._files_for_entry(), version

    def test_the_updater_is_never_installed_into_a_site(self):
        # The tool that upgrades a site is downloaded as a verified release
        # asset and run from a temp dir; a copy written into the site is
        # stale weight that imports migration modules the site lacks.
        assert 'scripts/upgrade.py' not in FRAMEWORK_FILES_090
        assert [p for p in FRAMEWORK_FILES_090
                if p.startswith('scripts/migrations/')] == []

    def test_paths_the_repository_never_held_are_not_in_the_map(self):
        # The map is derived from what the framework repository has actually
        # shipped, not from what a string looks like — NOTICE and LICENSE
        # carry neither a slash nor a dot.
        assert 'NOTICE' in FRAMEWORK_FILES_090
        assert 'LICENSE' in FRAMEWORK_FILES_090


class TestAbsentFilesAreStillInstalled:
    """Absent is a different question from customised. Withholding a file the
    site does not have leaves it missing something the framework needs."""

    def test_a_missing_early_file_is_installed_at_a_late_entry(self, tmp_path):
        # scripts/telar/config.py is written by an early step and imported by
        # csv_to_json.py, whose failure is a hard failure.
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.8.1-beta'

        assert 'scripts/telar/config.py' in migration._files_for_entry()

    def test_a_present_early_file_is_still_withheld_at_a_late_entry(self, tmp_path):
        theme = tmp_path / '_data/themes/paisajes.yml'
        theme.parent.mkdir(parents=True)
        theme.write_text('# customised by the owner\n')

        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.8.1-beta'

        assert '_data/themes/paisajes.yml' not in migration._files_for_entry()

    def test_a_missing_theme_is_installed_even_at_a_late_entry(self, tmp_path):
        # Nothing to overwrite, and a site without its themes is broken.
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.8.1-beta'

        assert '_data/themes/paisajes.yml' in migration._files_for_entry()


class TestTheDemoContentNotice:
    """The hop keeps demo content, so it must say so."""

    def _notice(self, tmp_path, language):
        (tmp_path / '_config.yml').write_text(
            f'telar_language: "{language}"\n', encoding='utf-8')
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.2.0-beta'
        return migration._demo_content_step()['description']

    def test_it_tells_an_english_site_where_the_files_are(self, tmp_path):
        notice = self._notice(tmp_path, 'en')

        assert 'telar-content/objects/' in notice
        assert 'telar-content/texts/stories/' in notice
        assert 'telar-content/spreadsheets/' in notice
        assert 'objects.csv' in notice

    def test_a_spanish_site_is_told_in_spanish(self, tmp_path):
        notice = self._notice(tmp_path, 'es')

        assert notice.startswith('**Revisa los archivos de demostración')
        assert 'bórralos' in notice

    def test_the_notice_is_always_offered(self, tmp_path):
        (tmp_path / '_config.yml').write_text('telar_language: "en"\n')
        migration = Migration020to090(str(tmp_path))
        migration.from_version = '0.8.1-beta'

        assert any('demo files' in step['description'].lower()
                   for step in migration.get_manual_steps())
