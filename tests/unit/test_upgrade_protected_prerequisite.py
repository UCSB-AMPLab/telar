"""Unit Tests for an Upgrade That Finishes Despite an Unencryptable Story

A site below v0.9.0 whose owner edited their spreadsheets keeps the
template's demo stories, and the v0.8.1 template ships one of them marked
protected. At the end of the upgrade `csv_to_json.py` refuses, because the
site's `build.yml` predates the post-build encrypt step, and the upgrade
treated that refusal as a hard failure: a working site was left at its old
version, and the only way forward was a hand edit of a workflow file the
tool is not permitted to write.

Two facts decide that this is the wrong outcome rather than a strict one.
The check runs *after* every JSON file is written, so the regeneration it
appears to fail has already succeeded. And the build workflow runs
`csv_to_json.py` too, so the same refusal stops publication whether or not
the upgrade completes. Aborting prevents nothing and costs the upgrade.

So the refusal keeps its own exit code, the upgrade completes, and the
workflow edit is carried into the summary as a flagged item — the section
whose body says the site was upgraded and a re-run changes nothing, which
is exactly true here.

Version: v1.8.0
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import ChangeRecord, ChangeStatus
from telar.core import PROTECTED_PREREQUISITE_EXIT as ENGINE_EXIT


class TestTheTwoCopiesOfTheExitCode:
    """`telar_upgrade` cannot import the engine's copy.

    `scripts/telar` eagerly imports pandas and PIL, and the upgrade script
    runs before it has had the chance to install them — that is what
    `_ensure_regeneration_dependencies` exists for. So the value is
    written twice, and this is what stops the two drifting.
    """

    def test_the_upgrade_and_the_engine_agree(self):
        assert upgrade.PROTECTED_PREREQUISITE_EXIT == ENGINE_EXIT

    def test_it_is_not_the_ordinary_failure_code(self):
        """The whole point is telling this apart from a failed conversion."""
        assert ENGINE_EXIT not in (0, 1)


class TestRegenerationTellsTheTwoApart:
    """Driven through real subprocesses, because the distinction is a
    process exit code and a mock of it would assert the mapping twice."""

    def _repo(self, tmp_path, exit_code, write_marker=True):
        scripts = tmp_path / 'scripts'
        scripts.mkdir()
        body = 'import sys\n'
        if write_marker:
            body += "open('ran', 'w').write('yes')\n"
        body += 'sys.exit(%d)\n' % exit_code
        (scripts / 'csv_to_json.py').write_text(body, encoding='utf-8')
        (tmp_path / '_config.yml').write_text('telar_language: "en"\n',
                                              encoding='utf-8')
        return str(tmp_path)

    def test_a_protected_refusal_leaves_the_upgrade_able_to_continue(self, tmp_path):
        csv_ok, _, blocked = upgrade._regenerate_data_files(
            self._repo(tmp_path, ENGINE_EXIT))

        assert csv_ok is True
        assert blocked is True

    def test_an_ordinary_failure_still_stops_the_upgrade(self, tmp_path):
        csv_ok, _, blocked = upgrade._regenerate_data_files(
            self._repo(tmp_path, 1))

        assert csv_ok is False
        assert blocked is False

    def test_success_is_neither(self, tmp_path):
        csv_ok, _, blocked = upgrade._regenerate_data_files(
            self._repo(tmp_path, 0))

        assert csv_ok is True
        assert blocked is False

    def test_a_missing_script_is_a_hard_failure_not_a_flag(self, tmp_path):
        (tmp_path / 'scripts').mkdir()

        csv_ok, _, blocked = upgrade._regenerate_data_files(str(tmp_path))

        assert csv_ok is False
        assert blocked is False


class TestTheSummarySaysWhichKindItIs:

    def _record(self):
        return ChangeRecord(
            description=upgrade.get_message(
                'en', 'record_protected_unencryptable'),
            status=ChangeStatus.FAILED,
            severity="soft",
        )

    def test_it_lands_in_the_flagged_section(self):
        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[self._record()],
            from_version='0.8.1-beta', to_version='0.9.0')

        flagged = summary.index(upgrade.get_message(
            'en', 'flagged_needs_attention'))
        assert 'encrypt_protected_stories.py' in summary[flagged:]

    def test_it_is_not_counted_as_a_blocking_failure(self):
        """The two sections' bodies contradict each other, so a record in
        the wrong one tells the reader the opposite of the truth."""
        assert not upgrade.is_hard_failure(self._record())

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_the_message_exists_in_both_languages(self, lang):
        text = upgrade.get_message(lang, 'record_protected_unencryptable')

        assert 'build.yml' in text
        assert 'encrypt_protected_stories.py' in text
