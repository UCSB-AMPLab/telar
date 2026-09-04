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

Version: v1.7.0
"""

import ast
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import telar_upgrade as upgrade

# What data regeneration runs, and the package they pull in behind them.
REGENERATION_ENTRY_POINTS = ('csv_to_json.py', 'generate_collections.py')


def _top_level_names():
    """The names that resolve locally with scripts/ on sys.path.

    Not the package's own submodule names: `scripts/telar/markdown.py` is
    `telar.markdown`, and a bare `import markdown` in that package reaches
    the third-party library. Treating the submodule as local hides the
    dependency — which it did, in the first draft of this test.
    """
    return ({path.stem for path in SCRIPTS.glob('*.py')}
            | {entry.name for entry in SCRIPTS.iterdir() if entry.is_dir()})


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
                target |= {alias.name.split('.')[0] for alias in sub.names}
            elif isinstance(sub, ast.ImportFrom) and sub.level == 0 and sub.module:
                target.add(sub.module.split('.')[0])

    return unconditional, guarded


def _third_party(names):
    local = _top_level_names()
    return {name for name in names
            if name not in sys.stdlib_module_names and name not in local}


def _regeneration_files():
    return ([SCRIPTS / name for name in REGENERATION_ENTRY_POINTS]
            + sorted((SCRIPTS / 'telar').glob('*.py')))


def _required_and_optional():
    required, optional = set(), set()
    for path in _regeneration_files():
        unconditional, guarded = _imports_at_module_level(path)
        required |= unconditional
        optional |= guarded
    return _third_party(required), _third_party(optional)


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
        assert len(files) > len(REGENERATION_ENTRY_POINTS)

    def test_the_package_submodules_are_not_taken_for_local_names(self):
        assert (SCRIPTS / 'telar' / 'markdown.py').is_file()
        assert 'markdown' not in _top_level_names()
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

    def test_a_relative_import_is_not_a_third_party_name(self, tmp_path):
        module = tmp_path / 'sample.py'
        module.write_text('from . import sibling\nfrom .other import thing\n')

        unconditional, guarded = _imports_at_module_level(module)

        assert unconditional == set()
        assert guarded == set()
