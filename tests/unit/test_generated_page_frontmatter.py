"""Unit Tests for the Front Matter a Generated Page Carries

A page's URL comes from the `pages` collection permalink and its layout from
the collection default. A source file that declares either takes a decision
that belongs to the build. The pre-0.9.0 page format declares both, so any
site old enough to carry it arrives with the decision already taken.

The permalink is the one that breaks a site: the source renders at the
address it claims and the page generated from it renders there too, which
Jekyll reports as a destination conflict and the build gate fails on. The
layout is quieter and still wrong — `layout: page` resolves, so the page
renders through a different template from every other page on the site
rather than failing visibly.

Generation is authoritative for both (Juan, 2026-09-13). The migration also
removes the keys from the source file, but a site whose pages have been
through a round trip that preserves unrecognised front matter can have them
back, so this path holds whether or not the strip ever ran.

Version: v1.8.0
"""

import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from generate_collections import (
    GENERATED_PAGE_IGNORED_KEYS,
    _strip_generated_page_keys,
)


class TestTheSourceDoesNotDecideTheUrlOrTheLayout:

    def test_a_pre_090_page_keeps_only_its_title(self):
        frontmatter = 'title: About\nlayout: page\npermalink: /about/'

        assert _strip_generated_page_keys(frontmatter) == 'title: About'

    def test_a_source_of_nothing_else_yields_empty_front_matter(self):
        assert _strip_generated_page_keys('layout: page\npermalink: /about/') == ''

    @pytest.mark.parametrize('key', GENERATED_PAGE_IGNORED_KEYS)
    def test_each_ignored_key_goes(self, key):
        assert _strip_generated_page_keys('title: A\n%s: x' % key) == 'title: A'


class TestEverythingElseSurvivesUntouched:
    """The page format is the author's, not ours.

    Re-serialising the parsed dict would have been shorter and would have
    rewritten every other key's spelling, quoting and order, and dropped the
    author's comments. The filter works on the text for that reason.
    """

    def test_a_current_page_is_unchanged(self):
        assert _strip_generated_page_keys('title: About') == 'title: About'

    def test_the_sister_file_keys_survive(self):
        """`localized_for` and `language` are how a Spanish site routes.

        They are exactly the keys the Compositor was found to be stripping
        on publish, so the framework must not strip them either.
        """
        frontmatter = ('title: Acerca de Telar\n'
                       'localized_for: about.md\n'
                       'language: es')

        assert _strip_generated_page_keys(frontmatter) == frontmatter

    def test_title_key_survives(self):
        """Page front matter the framework reads at _layouts/default.html."""
        frontmatter = 'title: Objects\ntitle_key: navigation.objects\nlayout: page'

        assert (_strip_generated_page_keys(frontmatter)
                == 'title: Objects\ntitle_key: navigation.objects')

    def test_a_comment_survives(self):
        frontmatter = '# the page shown in the nav\ntitle: About\nlayout: page'

        assert (_strip_generated_page_keys(frontmatter)
                == '# the page shown in the nav\ntitle: About')


class TestOnlyTopLevelKeysAreDropped:
    """A nested `layout:` belongs to whatever key contains it."""

    def test_a_nested_layout_is_not_a_page_layout(self):
        frontmatter = 'title: A\nnav:\n  layout: wide\n  permalink: /x/'

        assert _strip_generated_page_keys(frontmatter) == frontmatter

    def test_a_dropped_key_takes_its_continuation_lines(self):
        """A list value would otherwise be left behind as orphan YAML.

        `permalink:` followed by two indented list items, with the key gone
        and the items kept, is a parse error in the generated file — which
        would turn a quiet wrong layout into a broken build.
        """
        frontmatter = ('title: A\n'
                       'permalink:\n'
                       '  - /about/\n'
                       '  - /acerca/\n'
                       'language: es')

        assert _strip_generated_page_keys(frontmatter) == 'title: A\nlanguage: es'

class TestJekyllDoesNotRenderTheSourcesItself:
    """Stripping the generated page is only half of making generation decide.

    The source file is markdown with front matter sitting in the site tree,
    so Jekyll renders it too unless told not to. That put a raw, unprocessed
    copy of every page, glossary entry and story panel at a second URL — and
    a source declaring its own permalink landed on top of the page generated
    from it, which is the collision the build gate fails on.

    It also gave a sister file a URL. `acerca.md` is `localized_for:
    about.md` and is deliberately denied one, so an English site was serving
    the Spanish page at /telar-content/texts/pages/acerca/.
    """

    def _exclude(self):
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '_config.yml')
        with open(config_path, encoding='utf-8') as handle:
            return yaml.safe_load(handle).get('exclude', [])

    def test_the_text_sources_are_excluded(self):
        assert 'telar-content/texts/' in self._exclude()

    def test_the_test_suite_is_not_published(self):
        """A fixture is content written to be wrong in a particular way.

        Published beside the site's own, it is indistinguishable from it —
        and nothing on a site links to any of it, so the whole tree was
        served to no one.
        """
        excluded = self._exclude()

        for path in ('tests/', 'pytest.ini', 'vitest.config.js'):
            assert path in excluded, path

    def test_the_spreadsheets_passthrough_is_left_alone(self):
        """The encryptor's sentinel sweep skips _site/telar-content/ by design.

        Narrowing the exclusion to the text sources keeps that argument
        intact: the spreadsheets and object files it refers to are still
        served, so the skip still has something to skip and the reasoning in
        `encrypt_protected_stories` does not silently become stale.
        """
        excluded = self._exclude()
        assert 'telar-content/' not in excluded
        assert 'telar-content/spreadsheets/' not in excluded
