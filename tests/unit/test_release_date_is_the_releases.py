"""Unit Tests for `telar.release_date` Meaning One Thing

A site's `_config.yml` carries `telar.release_date` beside `telar.version`,
and the two upgrade routes filled it from different sources. The engine
stamped the day the upgrade ran; the Compositor stamps the day the release
was published. So two sites on the same framework version disagreed, and
the key answered neither question reliably.

Settled with the Compositor: the key means **the release's date**, and the
framework moves. It is the value their route has always written, it is the
one the key's name claims, and reading it from the release rather than the
clock makes an upgrade reproducible — the same site upgraded twice now
produces the same file.

Each migration therefore declares the date of the release it installs,
beside the version it installs, taken from that release's git tag. A
separate table would be a second place to keep the same fact.

Version: v1.8.0
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.discovery import discover_migrations

MIGRATIONS = discover_migrations()
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


@pytest.mark.parametrize('migration', MIGRATIONS,
                         ids=lambda m: m.__name__)
class TestEveryMigrationKnowsItsReleaseDate:

    def test_it_declares_one(self, migration):
        assert getattr(migration, 'release_date', None), migration.__name__

    def test_it_is_a_date_rather_than_a_sentence(self, migration):
        assert DATE.match(migration.release_date), migration.release_date


class TestTheDatesAgreeWithTheChain:

    def test_they_run_forward(self):
        """A chain whose dates go backwards means one was mistyped.

        The only check available offline: the tags they came from are in
        release order, so the dates must be too.
        """
        dates = [m.release_date for m in MIGRATIONS]

        assert dates == sorted(dates), dates

    def test_no_two_releases_share_a_date(self):
        """Not a rule of the world, but true of every release so far.

        Two migrations with one date is what a copy-paste looks like, and
        the assertion is cheap while it holds.
        """
        dates = [m.release_date for m in MIGRATIONS]

        assert len(set(dates)) == len(dates)

    def test_the_engine_takes_the_last_one(self):
        assert upgrade.LATEST_RELEASE_DATE == MIGRATIONS[-1].release_date
        assert upgrade.LATEST_VERSION == MIGRATIONS[-1].to_version


class TestTheStampDoesNotComeFromTheClock:

    def test_it_is_the_release_date_when_there_is_one(self, capsys):
        assert upgrade._stamp_date('en') == upgrade.LATEST_RELEASE_DATE
        assert capsys.readouterr().out == ''

    def test_an_untagged_release_falls_back_and_says_so(self, monkeypatch, capsys):
        """The only case that may use the clock, and it is announced.

        A release under development has no date, because its date is not a
        fact until it is tagged. Stamping today silently is the behaviour
        this change removes, so the fallback is loud.
        """
        monkeypatch.setattr(upgrade, 'LATEST_RELEASE_DATE', None)

        stamped = upgrade._stamp_date('en')

        assert DATE.match(stamped)
        assert upgrade.LATEST_VERSION in capsys.readouterr().out

    def test_no_migration_reads_the_clock_any_more(self):
        """Read off the source: a stamp only runs on a site at that version.

        A migration still calling date.today() would be stamping the day
        the upgrade ran, and nothing here builds a site old enough to make
        it happen.
        """
        directory = os.path.join(os.path.dirname(__file__), '..', '..',
                                 'scripts', 'migrations')
        offenders = []
        for name in sorted(os.listdir(directory)):
            if not name.startswith('v') or not name.endswith('.py'):
                continue
            text = open(os.path.join(directory, name), encoding='utf-8').read()
            if 'date.today' in text or 'datetime.now' in text:
                offenders.append(name)

        assert offenders == []


class TestTheDatesThatAreStillNow:
    """Not everything about an upgrade is about the release.

    The summary's own date and the state file's timestamp record when this
    run happened, and both should keep moving.
    """

    def test_the_clock_is_still_available(self):
        assert DATE.match(upgrade._get_date())
