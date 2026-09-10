"""Unit tests for migration discovery.

Registration was three hand-synced places, and v1.6.0 shipped with them out
of sync: every upgrade stopped at 1.5.4 and reported success. Discovery
replaces them with one derivation, so these tests are mostly about what it
refuses — a chain with two heads, a duplicate entry point, a stranded
migration — because a wrong chain that runs is exactly the failure being
designed out.

Version: v1.7.0
"""

import os
import sys
import textwrap
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import BaseMigration
from migrations.discovery import (
    MigrationChainError, discover_migrations, migration_in,
    migration_modules, order_chain,
)


def _migration(name, frm, to, module='fake.module'):
    return type(name, (BaseMigration,), {
        '__module__': module,
        'from_version': frm,
        'to_version': to,
        'description': f'{frm} to {to}',
    })


def _module(name, *classes):
    module = types.ModuleType(name)
    for cls in classes:
        setattr(module, cls.__name__, cls)
    # Every migration module imports this; none of them defines it.
    module.BaseMigration = BaseMigration
    return module


class TestTheRealChain:

    def test_it_finds_the_chain_upgrade_runs(self):
        assert discover_migrations() == upgrade.MIGRATIONS

    def test_it_starts_at_the_consolidated_hop_and_ends_at_the_latest(self):
        chain = discover_migrations()

        assert chain[0].from_version == '0.2.0-beta'
        assert chain[-1].to_version == upgrade.LATEST_VERSION

    def test_the_latest_version_is_derived_and_not_declared(self):
        """LATEST_VERSION is derived from the chain, not written down."""
        source = open(upgrade.__file__, encoding='utf-8').read()

        assert 'LATEST_VERSION = MIGRATIONS[-1].to_version' in source

    def test_no_module_is_silently_skipped(self):
        assert len(migration_modules()) == len(discover_migrations())

    def test_the_helpers_are_not_mistaken_for_migrations(self):
        names = migration_modules()

        for helper in ('base', 'messages', 'transformations', 'config_merge',
                       'discovery'):
            assert helper not in names

    def test_the_run_is_unbroken(self):
        chain = discover_migrations()

        for earlier, later in zip(chain, chain[1:]):
            assert earlier.to_version == later.from_version


class TestWhatAModuleMustDefine:

    def test_one_migration_is_the_one_it_returns(self):
        only = _migration('Only', '1.0', '2.0', module='m')

        assert migration_in(_module('m', only)) is only

    def test_two_migrations_in_one_module_is_refused(self):
        first = _migration('First', '1.0', '2.0', module='m')
        second = _migration('Second', '2.0', '3.0', module='m')

        with pytest.raises(MigrationChainError, match='defines 2 migrations'):
            migration_in(_module('m', first, second))

    def test_a_module_with_none_is_refused(self):
        with pytest.raises(MigrationChainError, match='defines 0 migrations'):
            migration_in(_module('m'))

    def test_an_imported_migration_is_not_the_modules_own(self):
        """A migration imported from elsewhere keeps its own __module__."""
        elsewhere = _migration('Elsewhere', '1.0', '2.0', module='other')

        with pytest.raises(MigrationChainError, match='defines 0 migrations'):
            migration_in(_module('m', elsewhere))


class TestWhatAChainMustBe:

    def test_it_orders_from_the_entry_nothing_reaches(self):
        middle = _migration('Middle', '2.0', '3.0')
        head = _migration('Head', '1.0', '2.0')
        tail = _migration('Tail', '3.0', '4.0')

        assert order_chain([middle, tail, head]) == [head, middle, tail]

    def test_two_starting_points_are_refused(self):
        one = _migration('One', '1.0', '2.0')
        other = _migration('Other', '5.0', '6.0')

        with pytest.raises(MigrationChainError, match='exactly one starting'):
            order_chain([one, other])

    def test_a_duplicate_entry_point_is_refused(self):
        """The dispatcher matches from_version and takes the first hit.

        Two migrations claiming one entry means one of them never runs, and
        which one is decided by discovery order rather than by anybody.
        """
        first = _migration('First', '1.0', '2.0')
        second = _migration('Second', '1.0', '9.0')

        with pytest.raises(MigrationChainError, match='both start at 1.0'):
            order_chain([first, second])

    def test_a_migration_the_head_cannot_reach_is_refused(self):
        """Two of these reach each other, so neither looks like a head."""
        head = _migration('Head', '1.0', '2.0')
        there = _migration('There', '3.0', '4.0')
        back = _migration('Back', '4.0', '3.0')

        with pytest.raises(MigrationChainError, match='Back, There'):
            order_chain([head, there, back])

    def test_an_empty_package_is_refused(self):
        empty = types.ModuleType('empty')
        empty.__path__ = []

        with pytest.raises(MigrationChainError, match='no migration modules'):
            discover_migrations(empty)


class TestANewMigrationNeedsNoWiring:
    """The v1.6.0 failure: a migration that shipped without its registration.

    Adding a module to the package is now the whole of adding a migration.
    """

    def _package(self, tmp_path, name, *pairs):
        root = tmp_path / name
        root.mkdir()
        (root / '__init__.py').write_text('')
        for frm, to in pairs:
            module_name = f"v{frm.replace('.', '')}_to_v{to.replace('.', '')}"
            (root / f'{module_name}.py').write_text(textwrap.dedent(f'''
                from migrations.base import BaseMigration

                class Migration{frm.replace('.', '')}to{to.replace('.', '')}(BaseMigration):
                    from_version = "{frm}"
                    to_version = "{to}"
                    description = "fake"
            '''))
        sys.path.insert(0, str(tmp_path))
        try:
            import importlib
            return importlib.import_module(name)
        finally:
            sys.path.remove(str(tmp_path))

    def test_the_chain_grows_with_the_directory(self, tmp_path):
        package = self._package(tmp_path, 'growing_chain',
                                ('1.0.0', '1.1.0'), ('1.1.0', '1.2.0'))
        chain = discover_migrations(package)

        assert [m.from_version for m in chain] == ['1.0.0', '1.1.0']
        assert chain[-1].to_version == '1.2.0'

    def test_a_gap_in_the_directory_is_refused_not_shortened(self, tmp_path):
        """v1.6.0 shortened the chain and called it a success."""
        package = self._package(tmp_path, 'gapped_chain',
                                ('1.0.0', '1.1.0'), ('1.2.0', '1.3.0'))

        with pytest.raises(MigrationChainError):
            discover_migrations(package)
