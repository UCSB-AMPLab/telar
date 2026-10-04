"""Unit tests pinning _REGENERATION_IMPORTS to the real import graph.

`upgrade.py` refuses to upgrade a site whose data regeneration would fail
for want of a package, and it decides that by probing a hand-written list.
A list that drifts under-declared is the dangerous direction: the upgrade
proceeds, then csv_to_json.py dies on an ImportError the probe said would
not happen.

The derivation lives here rather than in `upgrade.py` on purpose. Parsing
the import graph at upgrade time would put an AST walk of the site's own
scripts on the path of every run, to answer a question that only changes
when someone edits an import. A literal that a test pins is cheaper at
runtime and louder at edit time.

**The derivation used to be a second hand-kept list.** It globbed
`scripts/telar/*.py` — one directory, one level — which is an enumeration
of the graph rather than the graph. It missed the whole
`telar/processors/` subpackage, eight files that `telar/__init__.py`
imports on the first `import telar.anything`, and it included
`build_conflicts.py`, which data regeneration never loads. Neither error
showed, because the names in those files happened to be names the list
already had. A test that pins a list against an enumeration pins it
against the same mistake.

It now follows the imports from the two entry points, and counts the
`__init__.py` of every package it passes through, because that is what
Python runs.

**Where the derivation stops.** A local module imported inside a `try`
still contributes its own unconditional imports as required. Nothing in
this graph does that, and resolving it properly means modelling which
failures the guard was written for — so the boundary is stated rather
than guessed at.

Version: v1.8.0
"""

import ast
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import telar_upgrade as upgrade

# What data regeneration runs. Everything else is reached from here.
REGENERATION_ENTRY_POINTS = ('csv_to_json.py', 'generate_collections.py')


def _module_files(name):
    """The files under scripts/ that Python runs to satisfy `import name`.

    Empty when the name is not local, which is how a third-party name is
    told from a first-party one: `scripts/telar/markdown.py` is
    `telar.markdown`, and a bare `import markdown` in that package reaches
    the third-party library. Treating the submodule as local hides the
    dependency — which it did, in the first draft of this test.

    Every package on the way counts. `import telar.processors.objects`
    runs `telar/__init__.py` and `telar/processors/__init__.py` first, and
    the first of those is where this package wires its subpackages
    together.
    """
    files, parts = [], name.split('.')
    for depth in range(1, len(parts) + 1):
        base = SCRIPTS.joinpath(*parts[:depth])
        if (base / '__init__.py').is_file():
            files.append(base / '__init__.py')
        elif base.with_suffix('.py').is_file():
            files.append(base.with_suffix('.py'))
        else:
            return []
    return files


def _absolute_name(path, level, module):
    """What `from ..x import y` means, written from where it was written."""
    package = path.relative_to(SCRIPTS).with_suffix('').parts[:-1]
    base = package[:len(package) - (level - 1)] if level > 1 else package
    return '.'.join(base + ((module,) if module else ()))


def _imports_at_module_level(path):
    """(unconditional, guarded) top-level import names in one file.

    Only `tree.body` counts as eager. An import inside a function runs when
    that function is called, and one inside a try or an if is by
    construction allowed to fail.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'))
    unconditional, guarded = set(), set()

    for node in tree.body:
        target, nodes = unconditional, [node]
        if isinstance(node, (ast.Try, ast.If)):
            target, nodes = guarded, list(ast.walk(node))
        for sub in nodes:
            if isinstance(sub, ast.Import):
                target |= {alias.name for alias in sub.names}
            elif isinstance(sub, ast.ImportFrom):
                if sub.level == 0 and sub.module:
                    target.add(sub.module)
                    # `from telar import x` may import the module
                    # `telar.x` rather than a name inside `telar`, and
                    # resolving only `telar` walks the package's
                    # __init__ and stops -- so a helper reached that way,
                    # and whatever it imports, was never read.
                    target |= {'%s.%s' % (sub.module, alias.name)
                               for alias in sub.names}
                elif sub.level:
                    target.add(_absolute_name(path, sub.level, sub.module))

    return unconditional, guarded


def _walk_regeneration_graph():
    """(required, optional, files) — third-party names and what was read.

    Third-party is what does not resolve to a file under scripts/, minus
    the standard library. Local names are followed instead of recorded.
    """
    required, optional, seen = set(), set(), set()
    queue = [SCRIPTS / name for name in REGENERATION_ENTRY_POINTS]

    while queue:
        path = queue.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)

        unconditional, guarded = _imports_at_module_level(path)
        for names, bucket in ((unconditional, required), (guarded, optional)):
            for name in names:
                local = _module_files(name)
                if local:
                    queue.extend(local)
                    continue
                top = name.split('.')[0]
                # A candidate that does not resolve is only third-party if
                # its package does not either. `from telar import x` offers
                # `telar.x` whether x is a module or a function, and the
                # function spelling must not be reported as a missing
                # dependency called `telar`.
                if _module_files(top) or top in sys.stdlib_module_names:
                    continue
                bucket.add(top)

    return required, optional, seen


def _required_and_optional():
    required, optional, _ = _walk_regeneration_graph()
    return required, optional


def _regeneration_files():
    return sorted(_walk_regeneration_graph()[2])


class TestTheProbeListMatchesTheGraph:

    def test_it_names_exactly_what_regeneration_imports_eagerly(self):
        required, _ = _required_and_optional()

        assert set(upgrade._REGENERATION_IMPORTS) == required, (
            "scripts/upgrade.py:_REGENERATION_IMPORTS has drifted from the "
            "imports data regeneration actually makes. Missing from the list: "
            f"{sorted(required - set(upgrade._REGENERATION_IMPORTS))}; listed "
            "but not imported eagerly: "
            f"{sorted(set(upgrade._REGENERATION_IMPORTS) - required)}")

    def test_an_optional_dependency_is_not_required(self):
        """pillow_heif and fitz are imported inside functions, not up front.

        Requiring them would make a site that never touches HEIC or PDF
        install them to upgrade.
        """
        _, optional = _required_and_optional()

        assert not optional & set(upgrade._REGENERATION_IMPORTS)

    def test_every_name_is_importable_as_written(self):
        """PIL, not Pillow — the list is import names, not distributions."""
        import importlib.util

        for name in upgrade._REGENERATION_IMPORTS:
            assert importlib.util.find_spec(name) is not None, name


class TestTheDerivationItself:
    """A derivation that silently finds nothing would pass the test above."""

    def test_it_reads_the_files_it_claims_to(self):
        files = _regeneration_files()

        assert all(path.is_file() for path in files)
        assert len(files) > 20

    def test_it_reaches_the_subpackage_a_directory_glob_missed(self):
        """The gap that made this derivation worth rewriting.

        `telar/__init__.py` imports `telar.processors.objects`, so those
        files run on the first `import telar.anything`. A glob of
        `telar/*.py` never saw them.
        """
        reached = {path.relative_to(SCRIPTS).as_posix()
                   for path in _regeneration_files()}

        assert 'telar/processors/objects/local.py' in reached
        assert 'telar/processors/stories.py' in reached
        assert 'telar/__init__.py' in reached

    def test_it_does_not_read_what_regeneration_never_loads(self):
        """The other direction: an over-broad set can only over-declare.

        `build_conflicts.py` sits in the same directory and is imported by
        the conflict checker, not by anything regeneration runs.
        """
        reached = {path.relative_to(SCRIPTS).as_posix()
                   for path in _regeneration_files()}

        assert 'telar/build_conflicts.py' not in reached

    def test_the_package_submodules_are_not_taken_for_local_names(self):
        assert (SCRIPTS / 'telar' / 'markdown.py').is_file()
        assert _module_files('markdown') == []
        assert _module_files('telar.markdown') != []
        assert 'markdown' in set(upgrade._REGENERATION_IMPORTS)

    def test_a_function_level_import_is_not_eager(self, tmp_path):
        module = tmp_path / 'sample.py'
        module.write_text('import os\n\n\ndef f():\n    import lazypkg\n')

        unconditional, guarded = _imports_at_module_level(module)

        assert unconditional == {'os'}
        assert 'lazypkg' not in unconditional | guarded

    def test_a_guarded_import_is_optional_not_required(self, tmp_path):
        module = tmp_path / 'sample.py'
        module.write_text('try:\n    import optpkg\nexcept ImportError:\n'
                          '    optpkg = None\n')

        unconditional, guarded = _imports_at_module_level(module)

        assert unconditional == set()
        assert guarded == {'optpkg'}

    def test_a_name_imported_from_a_package_is_tried_as_a_module(self):
        """`from telar import glossary` and `from telar import X` are the
        same syntax, and only one of them is a module. Both candidates are
        offered; the one that is not a file resolves to nothing."""
        module = SCRIPTS / 'sample_from_package.py'
        module.write_text('from telar import glossary, NOT_A_MODULE\n',
                          encoding='utf-8')
        try:
            unconditional, _ = _imports_at_module_level(module)
        finally:
            module.unlink()

        assert 'telar.glossary' in unconditional
        assert _module_files('telar.glossary') != []
        assert _module_files('telar.NOT_A_MODULE') == []

    def test_a_relative_import_resolves_to_its_package(self):
        """Nothing in this graph writes one, so it is checked on a file
        that does: a relative import read as a bare name would be
        classified third-party and demand a package nobody ships."""
        path = SCRIPTS / 'migrations' / 'discovery.py'

        assert _absolute_name(path, 1, 'base') == 'migrations.base'
        assert _absolute_name(path, 1, None) == 'migrations'
        assert _module_files('migrations.base') != []
