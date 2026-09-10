#!/usr/bin/env python3
"""Read the migration chain off this package, and refuse an ambiguous one.

The chain is read off the modules in this package, so registration cannot
drift from the files: there is no hand-kept import block, list or version
constant that a shipped migration can fail to appear in. Several places that
must agree is a defect waiting for the next release; one place that is
derived cannot disagree with itself.

A module in this package is a migration when its name is `v<x>_to_v<y>` and
it defines exactly one `BaseMigration` subclass. The chain's order, its head
and its terminus are then read off `from_version` and `to_version`.

Anything that is not a single unbroken run raises. That is deliberate: a
chain with two heads, a duplicate entry point or an unreachable migration is
a wiring mistake, and the cost of guessing at one is a site upgraded to the
wrong version while being told it succeeded. Failing at import puts the
mistake in front of whoever made it.

Version: v1.7.0
"""

import importlib
import inspect
import pkgutil
import re
from typing import List, Type

from .base import BaseMigration

# `v020_to_v090`, `v161_to_v162`. Deliberately not a version grammar: the
# filename only has to identify a migration module, and the versions that
# matter are the ones the class declares.
MODULE_NAME = re.compile(r'^v\d+_to_v\d+$')


class MigrationChainError(Exception):
    """The modules in this package do not form one unbroken chain."""


def migration_modules(package=None) -> List[str]:
    """The names of the migration modules in this package, alphabetically."""
    if package is None:
        package = importlib.import_module(__package__)
    return sorted(name for _, name, _ in pkgutil.iter_modules(package.__path__)
                  if MODULE_NAME.match(name))


def migration_in(module) -> Type[BaseMigration]:
    """The one migration class a module defines.

    Classes imported into the module are not its own — `BaseMigration`
    itself is imported by every one of them.
    """
    found = [obj for _, obj in inspect.getmembers(module, inspect.isclass)
             if issubclass(obj, BaseMigration)
             and obj is not BaseMigration
             and obj.__module__ == module.__name__]

    if len(found) != 1:
        names = ', '.join(sorted(cls.__name__ for cls in found)) or 'none'
        raise MigrationChainError(
            f"{module.__name__} defines {len(found)} migrations ({names}); "
            f"a migration module defines exactly one")
    return found[0]


def order_chain(classes) -> List[Type[BaseMigration]]:
    """Put the classes in chain order, from the entry no other one reaches."""
    by_entry = {}
    for cls in classes:
        clash = by_entry.get(cls.from_version)
        if clash is not None:
            raise MigrationChainError(
                f"{clash.__name__} and {cls.__name__} both start at "
                f"{cls.from_version}; the dispatcher would run whichever "
                f"came first and skip the other")
        by_entry[cls.from_version] = cls

    reached = {cls.to_version for cls in classes}
    heads = [cls for cls in classes if cls.from_version not in reached]
    if len(heads) != 1:
        named = ', '.join(sorted(f'{c.__name__} ({c.from_version})'
                                 for c in heads)) or 'none'
        raise MigrationChainError(
            f"the chain needs exactly one starting point, found "
            f"{len(heads)}: {named}")

    ordered, seen, cursor = [], set(), heads[0]
    while cursor is not None:
        if cursor.__name__ in seen:
            raise MigrationChainError(
                f"the chain returns to {cursor.__name__}")
        seen.add(cursor.__name__)
        ordered.append(cursor)
        cursor = by_entry.get(cursor.to_version)

    if len(ordered) != len(classes):
        stranded = sorted(cls.__name__ for cls in classes
                          if cls.__name__ not in seen)
        raise MigrationChainError(
            f"no path from {heads[0].from_version} reaches "
            f"{', '.join(stranded)}")
    return ordered


def discover_migrations(package=None) -> List[Type[BaseMigration]]:
    """Every migration in this package, in the order the chain runs them."""
    if package is None:
        package = importlib.import_module(__package__)

    classes = []
    for name in migration_modules(package):
        module = importlib.import_module(f'{package.__name__}.{name}')
        classes.append(migration_in(module))

    if not classes:
        raise MigrationChainError(
            f"no migration modules found in {package.__name__}")
    return order_chain(classes)
