"""Unit Tests for Telling a Transient Fetch Failure from a Structural One

The chain stops on a HARD failure so a migration cannot report a missing
file as done. That is right for a failure a re-run clears. It is a trap for
one that does not: the next attempt hits the identical step at the identical
pinned tag and stops in the identical place, so the site converges on
nothing. One unreadable JPEG left 65 of 71 entry points permanently stuck.

`_fetch_from_github` could not tell the two apart — a 404 and a timeout were
both `None` — which is the root rather than the symptom. `_fetch_result`
now carries the outcome, and the chain acts on it: a transient failure still
stops and writes nothing, a structural one is flagged and the chain goes on
to the latest release.

The trade is deliberate and is the thing to keep an eye on. Writing the
files that did arrive is a partial install, which is what the staged-atomic
design exists to prevent, and it is accepted only for the failure a re-run
cannot clear.

Version: v1.8.0
"""

import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import (
    STRUCTURAL_HTTP_CODES,
    BaseMigration,
    ChangeRecord,
    ChangeStatus,
    FetchOutcome,
    FetchResult,
    is_hard_failure,
)


def _site(tmp_path, lang='en'):
    (tmp_path / '_config.yml').write_text(
        'telar_language: "%s"\n' % lang, encoding='utf-8')
    return str(tmp_path)


class _Migration(BaseMigration):
    from_version = '1.0.0'
    to_version = '1.1.0'
    description = 'test'
    _TARGET_TAG = 'v1.1.0'

    def check_applicable(self):
        return True

    def apply(self):
        return []


def _migration(tmp_path, lang='en'):
    return _Migration(_site(tmp_path, lang))


def _http_error(code):
    return urllib.error.HTTPError(
        'https://example.invalid/x', code, 'reason', {}, None)


class TestWhyAFetchFailed:
    """The classification, read off the response rather than guessed."""

    def _fetch_raising(self, tmp_path, error, monkeypatch):
        migration = _migration(tmp_path)

        def _boom(*args, **kwargs):
            raise error

        monkeypatch.setattr('urllib.request.urlopen', _boom)
        return migration._fetch_result('README.md')

    def test_the_structural_codes_are_pinned(self):
        """Spelled out here rather than read from the module.

        Parametrising the cases below over the constant itself would make
        emptying it pass: zero codes, zero cases, green suite. Pinning the
        set means widening or narrowing it is a visible change in the commit
        that makes it.
        """
        assert set(STRUCTURAL_HTTP_CODES) == {404, 410}

    @pytest.mark.parametrize('code', [404, 410])
    def test_a_missing_path_is_structural(self, tmp_path, monkeypatch, code):
        result = self._fetch_raising(tmp_path, _http_error(code), monkeypatch)

        assert result.outcome is FetchOutcome.STRUCTURAL
        assert result.content is None

    @pytest.mark.parametrize('code', [403, 429, 500, 502, 503])
    def test_everything_else_with_a_code_is_transient(self, tmp_path,
                                                      monkeypatch, code):
        """The asymmetry is the safe one.

        403 is what a rate limit looks like and 5xx is the server having a
        bad minute; both clear. Reading either as structural would write a
        partial install the site never needed.
        """
        result = self._fetch_raising(tmp_path, _http_error(code), monkeypatch)

        assert result.outcome is FetchOutcome.TRANSIENT

    def test_a_network_failure_is_transient(self, tmp_path, monkeypatch):
        result = self._fetch_raising(
            tmp_path, urllib.error.URLError('connection refused'), monkeypatch)

        assert result.outcome is FetchOutcome.TRANSIENT

    def test_an_unexpected_error_is_transient(self, tmp_path, monkeypatch):
        """An error nobody anticipated is not evidence the file is absent."""
        result = self._fetch_raising(tmp_path, RuntimeError('?'), monkeypatch)

        assert result.outcome is FetchOutcome.TRANSIENT

    def test_the_thin_wrapper_still_answers_with_content_or_none(
            self, tmp_path, monkeypatch):
        """Most of the chain only needs the content, and still gets it."""
        migration = _migration(tmp_path)
        monkeypatch.setattr(
            migration, '_fetch_result',
            lambda *a, **k: FetchResult(None, FetchOutcome.STRUCTURAL))

        assert migration._fetch_from_github('README.md') is None


class TestAStructuralFailureIsNotRetried:
    """The tag does not change between the two requests.

    A retry asks the identical question of the identical ref and waits out
    the backoff for the answer it already has — per path, on a file map that
    may have several wrong ones.
    """

    def _counting_migration(self, tmp_path, outcome):
        migration = _migration(tmp_path)
        calls = []

        def _result(path, branch=None, timeout=10):
            calls.append(path)
            return FetchResult(None, outcome, 'stub')

        migration._fetch_result = _result
        return migration, calls

    def test_a_structural_failure_is_asked_once(self, tmp_path):
        migration, calls = self._counting_migration(
            tmp_path, FetchOutcome.STRUCTURAL)

        migration._fetch_with_retry('README.md', 'v1.1.0')

        assert len(calls) == 1

    def test_a_transient_failure_is_retried(self, tmp_path, monkeypatch):
        monkeypatch.setattr('time.sleep', lambda _: None)
        migration, calls = self._counting_migration(
            tmp_path, FetchOutcome.TRANSIENT)

        migration._fetch_with_retry('README.md', 'v1.1.0')

        assert len(calls) == 1 + migration._FETCH_RETRIES


class TestTheStagedFetchSortsTheTwo:

    def _migration_missing(self, tmp_path, absent, lang='en'):
        """A migration whose fetch 404s exactly the paths in *absent*."""
        migration = _migration(tmp_path, lang)

        def _with_retry(path, branch):
            if path in absent:
                return FetchResult(None, FetchOutcome.STRUCTURAL, '404')
            return FetchResult('content of %s' % path, FetchOutcome.OK)

        migration._fetch_with_retry = _with_retry
        return migration

    FILE_MAP = {
        '_layouts/story.html': 'Story layout',
        'assets/js/telar.js': 'Bundle',
        'README.md': 'Readme',
    }

    def test_a_missing_path_is_flagged_not_blocking(self, tmp_path):
        migration = self._migration_missing(tmp_path, {'README.md'})

        content_map, blocking, flagged = migration._fetch_all_staged(
            self.FILE_MAP, tag='v1.1.0')

        assert blocking == []
        assert len(flagged) == 1
        assert not is_hard_failure(flagged[0])
        assert flagged[0].status == ChangeStatus.FAILED
        assert 'README.md' in flagged[0].description
        assert sorted(content_map) == ['_layouts/story.html', 'assets/js/telar.js']

    def test_the_flag_names_the_version_and_not_the_ref(self, tmp_path):
        migration = self._migration_missing(tmp_path, {'README.md'})

        _, _, flagged = migration._fetch_all_staged(self.FILE_MAP)

        assert migration.to_version in flagged[0].description
        assert 'main' not in flagged[0].description

    def test_the_flag_does_not_carry_the_hard_failure_phrase(self, tmp_path):
        """`coerce_change` classifies a bare string by that phrase.

        A soft record worded like the hard one would be read as hard the
        moment anything round-tripped it through text.
        """
        migration = self._migration_missing(tmp_path, {'README.md'})

        _, _, flagged = migration._fetch_all_staged(self.FILE_MAP)

        assert 'Could not fetch' not in flagged[0].description

    def test_a_spanish_site_is_flagged_in_spanish(self, tmp_path):
        migration = self._migration_missing(tmp_path, {'README.md'}, lang='es')

        _, _, flagged = migration._fetch_all_staged(self.FILE_MAP)

        assert 'no existe' in flagged[0].description


class TestWhatReachesTheDisk:
    """The trade, stated as behaviour rather than as intent."""

    FILE_MAP = {
        '_layouts/story.html': 'Story layout',
        'README.md': 'Readme',
    }

    def _migration(self, tmp_path, outcomes):
        """*outcomes* maps a path to the FetchOutcome its fetch returns."""
        migration = _migration(tmp_path)

        def _with_retry(path, branch):
            outcome = outcomes.get(path, FetchOutcome.OK)
            if outcome is FetchOutcome.OK:
                return FetchResult('content of %s' % path, FetchOutcome.OK)
            return FetchResult(None, outcome, 'stub')

        migration._fetch_with_retry = _with_retry
        return migration

    def test_everything_arrives_when_every_fetch_succeeds(self, tmp_path):
        migration = self._migration(tmp_path, {})

        records = migration._apply_framework_files(self.FILE_MAP)

        assert [r for r in records if r.status == ChangeStatus.FAILED] == []
        assert (tmp_path / 'README.md').exists()
        assert (tmp_path / '_layouts' / 'story.html').exists()

    def test_a_structural_failure_writes_the_rest(self, tmp_path):
        """The partial install the atomic design exists to prevent.

        Accepted here because the alternative is a site that stops on this
        step on every upgrade it ever runs.
        """
        migration = self._migration(
            tmp_path, {'README.md': FetchOutcome.STRUCTURAL})

        records = migration._apply_framework_files(self.FILE_MAP)

        assert (tmp_path / '_layouts' / 'story.html').exists()
        assert not (tmp_path / 'README.md').exists()
        assert [r for r in records if is_hard_failure(r)] == []
        assert len([r for r in records if r.status == ChangeStatus.FAILED]) == 1

    def test_a_transient_failure_still_writes_nothing(self, tmp_path):
        migration = self._migration(
            tmp_path, {'README.md': FetchOutcome.TRANSIENT})

        records = migration._apply_framework_files(self.FILE_MAP)

        assert not (tmp_path / '_layouts' / 'story.html').exists()
        assert not (tmp_path / 'README.md').exists()
        assert [r for r in records if is_hard_failure(r)] != []

    THREE_FILE_MAP = dict(FILE_MAP, **{'assets/js/telar.js': 'Bundle'})

    def test_a_transient_failure_beside_a_structural_one_blocks(self, tmp_path):
        """A re-run can still complete the set, so the atomic guarantee holds.

        The structural record rides along, so the summary names everything
        that did not arrive rather than only what stopped the chain.
        """
        migration = self._migration(tmp_path, {
            'README.md': FetchOutcome.STRUCTURAL,
            '_layouts/story.html': FetchOutcome.TRANSIENT,
        })

        records = migration._apply_framework_files(self.THREE_FILE_MAP)

        assert list(tmp_path.glob('_layouts/*')) == []
        assert len([r for r in records if is_hard_failure(r)]) == 1
        assert len([r for r in records
                    if r.status == ChangeStatus.FAILED
                    and not is_hard_failure(r)]) == 1


class TestNothingArrivingIsAWrongRefNotAWrongPath:
    """The hole the flag-and-continue rule opens if left unguarded.

    One wrong path in a file map is a wrong file map. Every path wrong at
    once is a wrong ref — and flagging past that would stamp the site with a
    version whose files it never received, while reporting a completed
    upgrade. Nothing arriving is the test that tells the two apart.
    """

    FILE_MAP = {
        '_layouts/story.html': 'Story layout',
        'assets/js/telar.js': 'Bundle',
        'README.md': 'Readme',
    }

    def _migration(self, tmp_path, present):
        migration = _migration(tmp_path)

        def _with_retry(path, branch):
            if path in present:
                return FetchResult('content of %s' % path, FetchOutcome.OK)
            return FetchResult(None, FetchOutcome.STRUCTURAL, '404')

        migration._fetch_with_retry = _with_retry
        return migration

    def test_a_whole_map_of_404s_stops_the_chain(self, tmp_path):
        migration = self._migration(tmp_path, present=set())

        records = migration._apply_framework_files(self.FILE_MAP)

        assert len([r for r in records if is_hard_failure(r)]) == 3
        assert list(tmp_path.glob('_layouts/*')) == []

    def test_one_survivor_is_enough_to_call_it_a_wrong_map(self, tmp_path):
        """The ref resolved, so the paths that 404 are the file map's fault."""
        migration = self._migration(tmp_path, present={'README.md'})

        records = migration._apply_framework_files(self.FILE_MAP)

        assert [r for r in records if is_hard_failure(r)] == []
        assert (tmp_path / 'README.md').exists()

    def test_the_escalated_records_keep_their_wording(self, tmp_path):
        """The file is still absent; only what the chain does about it changed."""
        migration = self._migration(tmp_path, present=set())

        records = migration._apply_framework_files(self.FILE_MAP)

        assert all('is not part of Telar' in r.description for r in records)

    def test_no_state_marker_is_left_behind(self, tmp_path):
        """A leftover in_progress marker reads as a crash mid-write."""
        migration = self._migration(
            tmp_path, {'README.md': FetchOutcome.STRUCTURAL})

        migration._apply_framework_files(self.FILE_MAP)

        assert not (tmp_path / 'UPGRADE_STATE.json').exists()


class TestTheMigrationsThatWriteOneFileAtATime:
    """The pre-consolidation shape, which does not stage anything.

    Nine migrations fetch and write each file as it arrives. They were the
    other half of the stall: a 404 in any of their maps reached
    `coerce_change` as the phrase that classifies a bare string as hard, so
    the chain stopped there on every run.
    """

    FILE_MAP = {
        '_layouts/story.html': 'Story layout',
        'assets/js/telar.js': 'Bundle',
        'README.md': 'Readme',
    }

    def _migration(self, tmp_path, present):
        migration = _migration(tmp_path)

        def _result(path, branch=None, timeout=10):
            if path in present:
                return FetchResult('content of %s' % path, FetchOutcome.OK)
            return FetchResult(None, FetchOutcome.STRUCTURAL, '404')

        migration._fetch_result = _result
        return migration

    def test_the_files_that_arrive_are_written(self, tmp_path):
        migration = self._migration(tmp_path, present={'README.md'})

        records = migration._install_files_one_by_one(
            self.FILE_MAP, 'Updated {path} - {description}')

        assert (tmp_path / 'README.md').read_text() == 'content of README.md'
        assert 'Updated README.md - Readme' in [r.description for r in records]

    def test_a_missing_path_does_not_stop_the_chain(self, tmp_path):
        migration = self._migration(tmp_path, present={'README.md'})

        records = migration._install_files_one_by_one(
            self.FILE_MAP, 'Updated {path} - {description}')

        assert [r for r in records if is_hard_failure(r)] == []
        assert len([r for r in records if r.status == ChangeStatus.FAILED]) == 2

    def test_a_whole_map_of_404s_still_stops_it(self, tmp_path):
        """Same rule as the staged path: nothing arriving is a wrong ref."""
        migration = self._migration(tmp_path, present=set())

        records = migration._install_files_one_by_one(
            self.FILE_MAP, 'Updated {path} - {description}')

        assert len([r for r in records if is_hard_failure(r)]) == 3

    def test_a_transient_failure_is_still_hard(self, tmp_path):
        migration = _migration(tmp_path)
        migration._fetch_result = lambda path, branch=None, timeout=10: (
            FetchResult('x', FetchOutcome.OK) if path == 'README.md'
            else FetchResult(None, FetchOutcome.TRANSIENT, 'timed out'))

        records = migration._install_files_one_by_one(
            self.FILE_MAP, 'Updated {path} - {description}')

        assert len([r for r in records if is_hard_failure(r)]) == 2

    def test_no_migration_still_reports_a_fetch_failure_as_a_bare_string(self):
        """`coerce_change`'s phrase was the classification for all nine.

        A string is all that helper has to go on, so it cannot carry an
        outcome — which is why the phrase had to stop being how a fetch
        failure in these migrations gets classified.
        """
        import pathlib
        directory = pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'migrations'
        offenders = [path.name for path in sorted(directory.glob('v*.py'))
                     if 'Could not fetch' in path.read_text(encoding='utf-8')]

        assert offenders == []


class _Recorder(BaseMigration):
    """A migration that records that it ran and returns what it was given."""

    description = 'test'
    _TARGET_TAG = None

    def __init__(self, root, ran, name, records):
        super().__init__(root)
        self.from_version = name
        self.to_version = name
        self._ran = ran
        self._name = name
        self._records = records

    def check_applicable(self):
        return True

    def apply(self):
        self._ran.append(self._name)
        return list(self._records)


class TestTheChainReachesTheEnd:
    """The property the whole issue is about: repeated runs make progress.

    A chain that stops on a failure no re-run can clear stops there every
    time, which is convergence on nothing.
    """

    def _chain(self, tmp_path, middle_records):
        root = _site(tmp_path)
        ran = []
        return ran, [
            _Recorder(root, ran, 'first', []),
            _Recorder(root, ran, 'middle', middle_records),
            _Recorder(root, ran, 'last', []),
        ]

    def test_a_soft_failure_does_not_stop_it(self, tmp_path):
        flagged = ChangeRecord(description='x is not part of Telar 1.1.0',
                               status=ChangeStatus.FAILED, severity='soft')
        ran, chain = self._chain(tmp_path, [flagged])

        changes = upgrade.run_migrations(chain)

        assert ran == ['first', 'middle', 'last']
        assert [r for r in changes if is_hard_failure(r)] == []

    def test_a_hard_failure_still_stops_it(self, tmp_path):
        blocking = ChangeRecord(description='Could not fetch x',
                                status=ChangeStatus.FAILED, severity='hard')
        ran, chain = self._chain(tmp_path, [blocking])

        upgrade.run_migrations(chain)

        assert ran == ['first', 'middle']


class TestTheSummaryShowsTheFlag:

    def _summary(self, records):
        return upgrade.generate_checklist(
            migrations=[], all_changes=records,
            from_version='1.0.0', to_version='1.1.0', lang='en')

    FLAGGED = ChangeRecord(description='README.md is not part of Telar 1.1.0',
                           status=ChangeStatus.FAILED, severity='soft')
    BLOCKING = ChangeRecord(description='Could not fetch _layouts/story.html',
                            status=ChangeStatus.FAILED, severity='hard')

    def test_a_flagged_file_is_listed_unticked(self):
        summary = self._summary([self.FLAGGED])

        assert '- [ ] README.md is not part of Telar 1.1.0' in summary
        assert '- [x] README.md is not part of Telar 1.1.0' not in summary

    def test_it_is_not_counted_as_an_automated_change(self):
        """A flagged file reported as completed work is the original defect."""
        applied = ChangeRecord(description='Updated _layouts/story.html',
                               status=ChangeStatus.APPLIED)

        summary = self._summary([applied, self.FLAGGED])

        assert '**Automated changes:** 1' in summary
        assert '**Files not installed:** 1' in summary

    def test_it_is_not_told_the_site_was_not_upgraded(self):
        """The blocking section's body is false of a flagged file.

        It says the site was not upgraded and that resolving the problem and
        re-running is the fix. Under a flagged failure the site was upgraded
        and a re-run changes nothing, so the two cannot share a heading.
        """
        summary = self._summary([self.FLAGGED])

        assert 'was **not** upgraded' not in summary
        assert 'running it again will not change this' in summary

    def test_a_blocking_failure_keeps_its_own_section(self):
        summary = self._summary([self.BLOCKING])

        assert 'was **not** upgraded' in summary
        assert 'Files Not Installed' not in summary

    def test_the_two_are_separated_when_both_are_present(self):
        summary = self._summary([self.BLOCKING, self.FLAGGED])

        assert '**Failed / needs attention:** 1' in summary
        assert '**Files not installed:** 1' in summary
        blocking_at = summary.index('Could not fetch _layouts/story.html')
        flagged_at = summary.index('README.md is not part of Telar 1.1.0')
        assert summary.index('Files Not Installed') > blocking_at
        assert flagged_at > summary.index('Files Not Installed')

    def test_a_spanish_summary_separates_them_too(self):
        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[self.BLOCKING, self.FLAGGED],
            from_version='1.0.0', to_version='1.1.0', lang='es')

        assert 'Archivos que no se instalaron' in summary
        assert 'volver a ejecutarla no cambia nada' in summary

    @pytest.mark.parametrize('lang,marker', [('en', '**did** complete'),
                                             ('es', '**s\u00ed** termin\u00f3')])
    def test_the_completed_half_is_emphasised_in_both_languages(self, lang, marker):
        """The sibling section leans on `**not** upgraded` to be read at a glance.

        Without the matching emphasis here the only typographic signal
        separating the two sits in one of them, and the reader this section
        exists for is the one about to re-run an upgrade that cannot help.
        """
        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[self.FLAGGED],
            from_version='1.0.0', to_version='1.1.0', lang=lang)

        assert marker in summary


class TestAStepForTheOwnerIsAManualStep:
    """A failure the site's owner resolves is not a fault in the release.

    The flagged section tells the reader to report a fault in Telar, and the
    Actions issue copies only the manual steps, so a step for the owner filed
    as a flag sends them to report a bug and never reaches the issue.
    """

    STEP = ChangeRecord(description='Delete the column `object_type` in the sheet itself.',
                        status=ChangeStatus.FAILED, severity='author')
    FLAGGED = TestTheSummaryShowsTheFlag.FLAGGED

    def _summary(self, records, lang='en'):
        return upgrade.generate_checklist(
            migrations=[], all_changes=records,
            from_version='1.0.0', to_version='1.1.0', lang=lang)

    def test_it_is_numbered_among_the_manual_steps(self):
        summary = self._summary([self.STEP])

        steps = summary[summary.index('## Manual Steps Required'):]
        assert '1. Delete the column `object_type` in the sheet itself.' in steps
        assert '- **Manual steps:** 1' in summary

    def test_it_is_not_a_flag(self):
        summary = self._summary([self.STEP])

        assert 'Files Not Installed' not in summary
        assert 'Files not installed' not in summary

    def test_a_real_flag_is_still_a_flag(self):
        summary = self._summary([self.STEP, self.FLAGGED])

        flags = summary[summary.index('## Files Not Installed'):summary.index('## Manual Steps')]
        assert 'README.md is not part of Telar 1.1.0' in flags
        assert 'object_type' not in flags
        assert '- **Files not installed:** 1' in summary

    def test_a_spanish_summary_numbers_it_too(self):
        summary = self._summary([self.STEP], lang='es')

        assert '1. Delete the column `object_type` in the sheet itself.' in summary
        assert 'Archivos que no se instalaron' not in summary

    def test_it_is_neither_applied_nor_hard(self):
        assert not upgrade.is_hard_failure(self.STEP)
        assert not upgrade.is_flagged(self.STEP)
        assert upgrade.is_flagged(self.FLAGGED)


class TestOneDefinitionOfTheStopRule:
    """Two severities are now load-bearing, so the predicate cannot be copied.

    An inline `severity == "hard"` that drifts from `is_hard_failure` would
    decide differently in one of the three places the chain asks.
    """

    def test_nothing_tests_the_severity_by_hand(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2] / 'scripts'
        offenders = []
        for path in sorted(root.rglob('*.py')):
            for number, line in enumerate(
                    path.read_text(encoding='utf-8').split('\n'), start=1):
                if 'severity == "hard"' in line and 'def is_hard_failure' not in line:
                    offenders.append('%s:%d' % (path.name, number))

        assert offenders == ['%s:%d' % _is_hard_failure_line()]


def _is_hard_failure_line():
    """The file and line inside `is_hard_failure` itself, the one definition.

    Taken from the function, not assumed: it is imported through
    `migrations.base` and defined wherever that module gets it from.
    """
    import inspect
    import pathlib
    from migrations import base
    source, start = inspect.getsourcelines(base.is_hard_failure)
    name = pathlib.Path(inspect.getsourcefile(base.is_hard_failure)).name
    for offset, line in enumerate(source):
        if 'severity == "hard"' in line:
            return name, start + offset
    raise AssertionError('is_hard_failure no longer tests severity')
