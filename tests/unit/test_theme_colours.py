"""
Unit Tests for Derived Theme On-Colours

The derivation replaces a theme's hand-picked text colour only when that
colour would be illegible on the background it sits on. These tests pin the
WCAG arithmetic, the candidate order, what the five shipped themes come out
as, the line an author gets whenever their own colour is overruled, and the
two things the module refuses to do: invent a colour for a value it cannot
read, and write anything for a site with no themes.

The expected on-colours below were computed from the WCAG 2.1 formula against
the checked-in theme files; each carries its contrast ratio in a comment.

Version: v1.8.0
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.theme_colours import (
    CONTRAST_FLOOR,
    DERIVED_BACKGROUNDS,
    DERIVED_TEXT_GROUNDS,
    MANIFEST_SCHEMA,
    LIGHT_COLOUR_LUMINANCE,
    build_manifest,
    contrast_ratio,
    light_colours,
    derive_theme,
    generate,
    relative_luminance,
    manifest_path,
    manifest_warnings,
    parse_hex,
    read_manifest,
    relative_luminance,
    write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_THEMES_DIR = REPO_ROOT / '_data' / 'themes'
SASS_DIR = REPO_ROOT / '_sass'
JS_DIR = REPO_ROOT / 'assets' / 'js'


class TestHexParsing:
    """What counts as a colour this module may compute with."""

    @pytest.mark.parametrize("value,expected", [
        ("#FFFFFF", (255, 255, 255)),
        ("#000000", (0, 0, 0)),
        ("#00b35c", (0, 179, 92)),
        ("#00B35C", (0, 179, 92)),
        ("#fff", (255, 255, 255)),
        ("#F00", (255, 0, 0)),
        ("  #333333  ", (51, 51, 51)),
    ])
    def test_reads_three_and_six_digit_hex(self, value, expected):
        assert parse_hex(value) == expected

    @pytest.mark.parametrize("value", [
        "rebeccapurple",
        "rgb(0, 179, 92)",
        "hsl(150, 100%, 35%)",
        "#gggggg",
        "#12345",
        "#1234567",
        "333333",
        "",
        None,
        0x333333,
    ])
    def test_refuses_anything_else(self, value):
        assert parse_hex(value) is None


class TestWcagArithmetic:
    """The luminance and contrast formulas, against published references."""

    @pytest.mark.parametrize("colour,expected", [
        ("#000000", 0.0),
        ("#FFFFFF", 1.0),
        # The sRGB coefficients themselves, one channel at a time.
        ("#FF0000", 0.2126),
        ("#00FF00", 0.7152),
        ("#0000FF", 0.0722),
    ])
    def test_relative_luminance(self, colour, expected):
        assert relative_luminance(colour) == pytest.approx(expected, abs=1e-6)

    def test_black_on_white_is_twenty_one_to_one(self):
        assert contrast_ratio('#000000', '#FFFFFF') == pytest.approx(21.0)

    def test_a_colour_against_itself_is_one_to_one(self):
        assert contrast_ratio('#883C36', '#883C36') == pytest.approx(1.0)

    def test_order_does_not_matter(self):
        assert contrast_ratio('#333333', '#C6D0F8') == pytest.approx(
            contrast_ratio('#C6D0F8', '#333333')
        )

    @pytest.mark.parametrize("foreground,background,expected", [
        # The smallest grey that clears AA on white, and its mirror on black.
        ("#767676", "#FFFFFF", 4.54),
        ("#949494", "#000000", 6.92),
        ("#0000FF", "#FFFFFF", 8.59),
        ("#FF0000", "#FFFFFF", 4.00),
    ])
    def test_mid_tone_reference_pairs(self, foreground, background, expected):
        assert contrast_ratio(foreground, background) == pytest.approx(
            expected, abs=0.005
        )

    def test_unreadable_colour_raises_rather_than_guessing(self):
        with pytest.raises(ValueError):
            relative_luminance('rebeccapurple')


# Every shipped theme's derived on-colour, with the contrast ratio it reaches,
# computed from the WCAG 2.1 formula against _data/themes/*.yml. Two pairs sit
# below the floor and are replaced: neogranadina's layer-1 white on #00b35c at
# 2.76:1, and santa-barbara's button white on the #FEBC11 gold at 1.69:1. Each
# replacement costs the author a warning line, so this table and REPLACED_PAIRS
# below are what pins how many lines a build may print.
SHIPPED_ON_COLOURS = {
    'austin': {
        'heading': '#FFFFFF',         # on #BF5700, 4.59:1, the theme's light text
        'button': '#FFFFFF',          # on #BF5700, 4.59:1, theme's own
        'panel_layer1': '#333F48',    # on #9CADB7, 4.66:1, theme's own
        'panel_layer2': '#FFFFFF',    # on #577565, 5.08:1, theme's own
        'panel_glossary': '#333F48',  # on #D6D2C4, 7.13:1, theme's own
    },
    'neogranadina': {
        'heading': '#FFFFFF',         # on #000000, 21.00:1, the theme's light text
        'button': '#FFFFFF',          # on #2A2F36, 13.48:1, theme's own
        'panel_layer1': '#000000',    # on #00b35c, 7.60:1, REPLACES #FFFFFF at 2.76:1
        'panel_layer2': '#FFFFFF',    # on #b31235, 6.87:1, theme's own
        'panel_glossary': '#2A2F36',  # on #F5F7FA, 12.56:1, theme's own
    },
    'paisajes': {
        'heading': '#FFFFFF',         # on #2c3e50, 10.98:1, the theme's light text
        'button': '#FFFFFF',          # on #2c3e50, 10.98:1, theme's own
        'panel_layer1': '#2c3e50',    # on #A8C5D4, 6.07:1, theme's own
        'panel_layer2': '#FFFFFF',    # on #3d2645, 13.45:1, theme's own
        'panel_glossary': '#333333',  # on #F5EDE1, 10.88:1, theme's own
    },
    'santa-barbara': {
        'heading': '#FFFFFF',         # on #003660, 12.38:1, the theme's light text
        'button': '#003660',          # on #FEBC11, 7.32:1, REPLACES #FFFFFF at 1.69:1
        'panel_layer1': '#FFFFFF',    # on #047C91, 4.89:1, theme's own
        'panel_layer2': '#FFFFFF',    # on #003660, 12.38:1, theme's own
        'panel_glossary': '#333333',  # on #F1EEEA, 10.92:1, theme's own
    },
    'trama': {
        'heading': '#FFFFFF',         # on #333333, 12.63:1, the theme's light text
        'button': '#FFFFFF',          # on #883C36, 7.65:1, theme's own
        'panel_layer1': '#333333',    # on #C6D0F8, 8.29:1, theme's own
        'panel_layer2': '#FFFFFF',    # on #883C36, 7.65:1, theme's own
        'panel_glossary': '#333333',  # on #FFF6EF, 11.84:1, theme's own
    },
}

# The pairs the derivation replaces, as (theme, background key).
REPLACED_PAIRS = {
    ('neogranadina', 'panel_layer1'),
    ('santa-barbara', 'button'),
}


def _shipped_colours(theme):
    """The `colors` block of a checked-in theme file."""
    document = yaml.safe_load(
        (SHIPPED_THEMES_DIR / f'{theme}.yml').read_text(encoding='utf-8')
    )
    return document['colors']


def _ground(colours, key):
    """The colour an on-colour sits on, from whichever block names it."""
    if key in DERIVED_TEXT_GROUNDS:
        return colours['text'][key]
    return colours['background'][key]


class TestShippedThemes:
    """What the five themes in the repo come out as."""

    def test_every_theme_file_is_covered(self):
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        assert set(manifest['themes']) == set(SHIPPED_ON_COLOURS)
        assert manifest['schema'] == MANIFEST_SCHEMA

    @pytest.mark.parametrize("theme", sorted(SHIPPED_ON_COLOURS))
    def test_on_colours(self, theme):
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        assert manifest['themes'][theme]['on'] == SHIPPED_ON_COLOURS[theme]

    @pytest.mark.parametrize("theme", sorted(SHIPPED_ON_COLOURS))
    def test_every_derived_colour_clears_the_floor(self, theme):
        colours = _shipped_colours(theme)
        for key, colour in SHIPPED_ON_COLOURS[theme].items():
            ground = _ground(colours, key)
            ratio = contrast_ratio(colour, ground)
            assert ratio >= CONTRAST_FLOOR, (
                f'{theme} {key}: {colour} on {ground} is {ratio:.2f}:1'
            )

    @pytest.mark.parametrize("theme", sorted(SHIPPED_ON_COLOURS))
    def test_only_the_measured_pairs_are_replaced(self, theme):
        text = _shipped_colours(theme)['text']
        for key in DERIVED_BACKGROUNDS:
            colour = SHIPPED_ON_COLOURS[theme][key]
            replaced = colour != text[key]
            assert replaced == ((theme, key) in REPLACED_PAIRS), (
                f'{theme} {key}: derived {colour}, theme wrote {text[key]}'
            )

    @pytest.mark.parametrize("theme", sorted(SHIPPED_ON_COLOURS))
    def test_no_text_ground_replaces_anything(self, theme):
        """A ground with no explicit on-colour has nothing to overrule.

        The four backgrounds can cost an author a warning line; these cannot,
        whatever the derivation picks, because the author never wrote a
        colour to sit on them.
        """
        for key in DERIVED_TEXT_GROUNDS:
            assert not any(t == theme and k == key for t, k in REPLACED_PAIRS)

    def test_the_shipped_themes_warn_once_per_replaced_pair(self):
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        warnings = manifest_warnings(manifest)
        assert len(warnings) == len(REPLACED_PAIRS)
        for theme, key in sorted(REPLACED_PAIRS):
            assert any(
                f'"{theme}"' in w and f'colors.text.{key}' in w for w in warnings
            ), f'no line for {theme} {key} in {warnings}'

    def test_a_theme_whose_choices_all_pass_says_nothing(self):
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        for theme in sorted(SHIPPED_ON_COLOURS):
            replaced = any(t == theme for t, _ in REPLACED_PAIRS)
            if not replaced:
                assert manifest['themes'][theme]['warnings'] == []


def _theme(text, background, fill=True):
    """A `colors` block.

    A background the caller does not name is filled in with black or white,
    whichever the theme's own text colour for it passes against, so a test
    about one background is not also a test about the three it did not set:
    the filled ones warn about nothing and replace nothing. Pass fill=False
    to leave them out.
    """
    grounds = dict(background)
    if fill:
        for key in DERIVED_BACKGROUNDS:
            explicit = text.get(key)
            inert = '#FFFFFF'
            if parse_hex(explicit) is not None:
                inert = (
                    '#000000'
                    if contrast_ratio(explicit, '#000000') >= CONTRAST_FLOOR
                    else '#FFFFFF'
                )
            grounds.setdefault(key, inert)
    return {'text': dict(text), 'background': grounds}


class TestCandidateOrder:
    """Which colour wins, and why."""

    def test_a_passing_explicit_choice_is_kept_byte_for_byte(self):
        # Lower case hex, kept as the author wrote it rather than normalised.
        on, warnings = derive_theme('t', _theme(
            {'heading': '#000000', 'button': '#FFFFFF', 'panel_layer1': '#2c3e50'},
            {'panel_layer1': '#A8C5D4'},
        ))
        assert on['panel_layer1'] == '#2c3e50'
        assert warnings == []

    def test_a_failing_explicit_choice_gives_way_to_the_theme_fallbacks(self):
        # White on this green is 2.76:1; the theme's own black heading is 7.60:1.
        on, _ = derive_theme('t', _theme(
            {'heading': '#000000', 'button': '#FFFFFF', 'panel_layer1': '#FFFFFF'},
            {'panel_layer1': '#00b35c'},
        ))
        assert on['panel_layer1'] == '#000000'

    def test_the_higher_contrast_of_heading_and_button_text_wins(self):
        # Gold ground: the navy heading is 7.32:1, the white button text 1.69:1.
        on, _ = derive_theme('t', _theme(
            {'heading': '#003660', 'button': '#FFFFFF', 'button_unused': '#000000'},
            {'button': '#FEBC11'},
        ))
        assert on['button'] == '#003660'

    def test_a_dark_ground_takes_the_light_text_the_theme_named(self):
        # Both theme candidates pass; the lighter one has the higher ratio.
        on, _ = derive_theme('t', _theme(
            {'heading': '#555555', 'button': '#FFFFFF'},
            {'panel_layer2': '#1A1A1A'},
        ))
        assert on['panel_layer2'] == '#FFFFFF'

    def test_black_or_white_when_neither_theme_colour_passes(self):
        # Heading and button text are both mid-greys that fail on this ground.
        on, _ = derive_theme('t', _theme(
            {'heading': '#888888', 'button': '#999999'},
            {'panel_layer1': '#7A7A7A'},
        ))
        assert on['panel_layer1'] == '#000000'

    def test_a_theme_with_no_fallback_colours_still_derives(self):
        on, warnings = derive_theme('t', _theme(
            {}, {'panel_layer2': '#000000'},
        ))
        assert on['panel_layer2'] == '#FFFFFF'
        # A colour the theme never named is not a value to complain about.
        assert warnings == []


class TestTextGrounds:
    """The heading colour, which the stylesheet also paints behind text."""

    def test_the_heading_ground_takes_the_theme_light_text(self):
        # White on this navy is 12.38:1; the heading against itself is 1:1.
        on, warnings = derive_theme('t', _theme(
            {'heading': '#003660', 'button': '#FFFFFF'}, {},
        ))
        assert on['heading'] == '#FFFFFF'
        assert warnings == []

    def test_the_ground_is_never_chosen_to_sit_on_itself(self):
        # The theme names no other candidate, so the fallback pair offers only
        # the heading, at 1:1 on itself, and the floor sends it to black.
        on, _ = derive_theme('t', _theme({'heading': '#EEEEEE'}, {}))
        assert on['heading'] == '#000000'

    def test_a_theme_that_names_no_heading_gets_no_entry(self):
        # Nothing named wrong, so nothing to say; the stylesheet's own
        # fallback carries the four rules.
        on, warnings = derive_theme('t', _theme({'button': '#FFFFFF'}, {}))
        assert 'heading' not in on
        assert warnings == []

    def test_an_unreadable_heading_is_reported_once_and_not_derived_for(self):
        on, warnings = derive_theme('t', _theme(
            {'heading': 'rebeccapurple', 'button': '#FFFFFF'}, {},
        ))
        assert 'heading' not in on
        assert len([w for w in warnings if 'rebeccapurple' in w]) == 1

    def test_no_shipped_theme_changes_how_the_four_rules_render(self):
        """Every shipped heading takes the white those rules hard-coded.

        The point of the change is the theme that would not — a mid-tone
        heading now gets a legible colour instead of silence — so a shipped
        theme moving off white is a visible restyle and has to be noticed.
        """
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        for theme in sorted(SHIPPED_ON_COLOURS):
            assert manifest['themes'][theme]['on']['heading'] == '#FFFFFF'


class TestWhichWayTheGroundRuns:
    """`light`, which the object page's author panels read.

    The panels sit on the button background, and their wells and close icon
    differ on a dark ground from a light one. That used to be a second
    luminance test in the browser, against the background, with its own
    threshold — two contrast decisions on one background, free to disagree.
    It is now a reading of the colour the derivation already chose.
    """

    def test_a_light_colour_was_chosen_because_the_ground_is_dark(self):
        assert light_colours({'button': '#FFFFFF'}) == {'button': True}
        assert light_colours({'button': '#003660'}) == {'button': False}

    def test_the_flag_agrees_with_the_colour_for_every_shipped_theme(self):
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        for theme in sorted(SHIPPED_ON_COLOURS):
            entry = manifest['themes'][theme]
            for key, colour in entry['on'].items():
                assert entry['light'][key] == (
                    relative_luminance(colour) > LIGHT_COLOUR_LUMINANCE
                ), f'{theme} {key}: {colour}'

    def test_every_derived_ground_is_flagged(self):
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        for theme in sorted(SHIPPED_ON_COLOURS):
            entry = manifest['themes'][theme]
            assert set(entry['light']) == set(entry['on'])

    def test_the_panels_keep_the_ground_the_browser_used_to_measure(self):
        """The four dark button grounds and the one light one, as before.

        The old browser-side test read --color-button-bg and compared its
        luminance to the same constant. Every shipped theme has to land the
        same side of it, or this change restyled a panel while claiming to
        remove a duplicate decision.
        """
        manifest = build_manifest(SHIPPED_THEMES_DIR)
        light_ground = {
            theme for theme in sorted(SHIPPED_ON_COLOURS)
            if not manifest['themes'][theme]['light']['button']
        }
        assert light_ground == {'santa-barbara'}


class TestUnreadableValues:
    """Values the module leaves alone rather than replacing."""

    def test_a_named_background_colour_is_not_derived_for(self):
        on, warnings = derive_theme('t', _theme(
            {'heading': '#000000', 'button': '#FFFFFF', 'panel_layer1': '#FFFFFF'},
            {'panel_layer1': 'rebeccapurple'},
        ))
        assert 'panel_layer1' not in on
        assert any('rebeccapurple' in w for w in warnings)

    def test_a_missing_background_is_not_derived_for(self):
        on, warnings = derive_theme('t', _theme(
            {'heading': '#000000', 'button': '#FFFFFF'},
            {'panel_layer1': '#C6D0F8'}, fill=False,
        ))
        # The heading is derived for too — it is a ground the theme names,
        # and the backgrounds it left out have nothing to do with it.
        assert set(on) == {'panel_layer1', 'heading'}
        assert len(warnings) == len(DERIVED_BACKGROUNDS) - 1
        assert all('colors.background.' in w for w in warnings)

    def test_an_unreadable_candidate_is_reported_once_not_once_per_background(self):
        on, warnings = derive_theme('t', _theme(
            {'heading': 'rgb(0, 0, 0)', 'button': '#FFFFFF'},
            {key: '#000000' for key in DERIVED_BACKGROUNDS},
        ))
        assert len(on) == len(DERIVED_BACKGROUNDS)
        assert len([w for w in warnings if 'rgb(0, 0, 0)' in w]) == 1

    def test_the_warning_names_the_value(self):
        _, warnings = derive_theme('mytheme', _theme(
            {'heading': '#000000', 'button': '#FFFFFF'},
            {'button': 'goldenrod', 'panel_layer1': '#C6D0F8',
             'panel_layer2': '#883C36', 'panel_glossary': '#FFF6EF'},
        ))
        assert any('mytheme' in w and 'goldenrod' in w for w in warnings)


class TestReplacementWarning:
    """The line a theme author gets when their own colour is overruled.

    The floor decides: an explicit colour below it is replaced, and every
    replacement is reported. Black or white always reaches the floor — they
    meet at 4.58:1 at worst — so the derivation always has something to
    choose, and there is no "nothing passed" case to report.
    """

    def test_black_or_white_always_reaches_the_floor(self):
        worst = min(
            max(contrast_ratio('#FFFFFF', f'#{v:02x}{v:02x}{v:02x}'),
                contrast_ratio('#000000', f'#{v:02x}{v:02x}{v:02x}'))
            for v in range(256)
        )
        assert worst > CONTRAST_FLOOR

    def test_the_line_names_the_theme_key_author_value_and_choice(self):
        on, warnings = derive_theme('mytheme', _theme(
            {'heading': '#000000', 'button': '#FFFFFF', 'panel_layer1': '#FFFFFF'},
            {'panel_layer1': '#00b35c'},
        ))
        assert len(warnings) == 1
        warning = warnings[0]
        assert 'mytheme' in warning
        assert 'colors.text.panel_layer1' in warning
        # The author's value with its ratio, and the chosen one with its own.
        assert '#FFFFFF' in warning and '2.76:1' in warning
        assert '#00b35c' in warning
        assert '#000000' in warning and '7.60:1' in warning
        assert on['panel_layer1'] == '#000000'

    def test_the_line_says_what_to_change(self):
        _, warnings = derive_theme('mytheme', _theme(
            {'heading': '#003660', 'button': '#FFFFFF'},
            {'button': '#FEBC11'},
        ))
        assert 'colors.background.button' in warnings[0]

    def test_a_passing_choice_says_nothing(self):
        _, warnings = derive_theme('mytheme', _theme(
            {'heading': '#333333', 'button': '#FFFFFF',
             'panel_layer1': '#333333', 'panel_layer2': '#FFFFFF',
             'panel_glossary': '#333333'},
            {'button': '#883C36', 'panel_layer1': '#C6D0F8',
             'panel_layer2': '#883C36', 'panel_glossary': '#FFF6EF'},
        ))
        assert warnings == []

    def test_one_line_per_replaced_pair(self):
        _, warnings = derive_theme('mytheme', _theme(
            {'heading': '#000000', 'button': '#FFFFFF',
             'panel_layer1': '#FFFFFF', 'panel_layer2': '#FFFFFF'},
            {'panel_layer1': '#00b35c', 'panel_layer2': '#00b35c'},
        ))
        assert len(warnings) == 2
        assert all('colors.text.panel_layer' in w for w in warnings)

    def test_a_choice_the_theme_never_made_is_not_a_replacement(self):
        # No colors.text.panel_layer2: the derivation fills one in, but the
        # author chose nothing for it to overrule.
        _, warnings = derive_theme('mytheme', _theme(
            {'heading': '#000000', 'button': '#FFFFFF'},
            {'panel_layer2': '#00b35c'},
        ))
        assert warnings == []

    def test_an_unreadable_choice_is_reported_as_unreadable_not_replaced(self):
        _, warnings = derive_theme('mytheme', _theme(
            {'heading': '#000000', 'button': '#FFFFFF',
             'panel_layer1': 'rebeccapurple'},
            {'panel_layer1': '#00b35c'},
        ))
        assert len(warnings) == 1
        assert 'rebeccapurple' in warnings[0]
        assert 'contrast ratio' not in warnings[0]


class TestOutput:
    """What lands in _data/telar-build/, and when nothing does."""

    def _themes(self, tmp_path, files):
        themes_dir = tmp_path / 'themes'
        themes_dir.mkdir()
        for name, document in files.items():
            (themes_dir / f'{name}.yml').write_text(
                yaml.safe_dump(document), encoding='utf-8'
            )
        return themes_dir

    def test_written_json_round_trips(self, tmp_path):
        self._themes(tmp_path, {'one': {'colors': _theme(
            {'heading': '#000000', 'button': '#FFFFFF'},
            {'button': '#883C36'},
        )}})
        path = generate(tmp_path, announce=lambda _: None)
        assert path == manifest_path(tmp_path)
        assert read_manifest(tmp_path)['themes']['one']['on']['button'] == '#FFFFFF'

    def test_the_file_is_byte_stable_across_runs(self, tmp_path):
        self._themes(tmp_path, {
            'zebra': {'colors': _theme(
                {'heading': '#003660', 'button': '#FFFFFF'},
                {'button': '#FEBC11', 'panel_layer1': '#047C91'},
            )},
            'alpha': {'colors': _theme(
                {'heading': '#333333', 'button': '#FFFFFF'},
                {'button': '#883C36', 'panel_layer2': '#883C36'},
            )},
        })
        generate(tmp_path, announce=lambda _: None)
        first = manifest_path(tmp_path).read_bytes()
        generate(tmp_path, announce=lambda _: None)
        assert manifest_path(tmp_path).read_bytes() == first

    def test_nothing_is_written_without_a_themes_directory(self, tmp_path):
        assert generate(tmp_path, announce=lambda _: None) is None
        assert not manifest_path(tmp_path).exists()
        assert read_manifest(tmp_path) is None

    def test_an_empty_themes_directory_writes_an_empty_set(self, tmp_path):
        self._themes(tmp_path, {})
        generate(tmp_path, announce=lambda _: None)
        assert read_manifest(tmp_path) == {'schema': MANIFEST_SCHEMA, 'themes': {}}

    def test_themes_are_keyed_by_file_stem(self, tmp_path):
        self._themes(tmp_path, {'santa-barbara': {'colors': _theme(
            {'heading': '#003660', 'button': '#FFFFFF'},
            {'button': '#FEBC11'},
        )}})
        manifest = build_manifest(tmp_path / 'themes')
        assert list(manifest['themes']) == ['santa-barbara']

    def test_warnings_reach_stdout_and_the_json_alike(self, tmp_path):
        self._themes(tmp_path, {'one': {'colors': _theme(
            {'heading': '#000000', 'button': '#FFFFFF'},
            {'button': 'goldenrod', 'panel_layer1': '#C6D0F8',
             'panel_layer2': '#883C36', 'panel_glossary': '#FFF6EF'},
        )}})
        printed = []
        generate(tmp_path, announce=printed.append)
        assert printed == read_manifest(tmp_path)['themes']['one']['warnings']
        assert printed

    def test_a_json_file_is_valid_json_with_a_trailing_newline(self, tmp_path):
        self._themes(tmp_path, {'one': {'colors': _theme(
            {'heading': '#000000', 'button': '#FFFFFF'},
            {'button': '#883C36'},
        )}})
        generate(tmp_path, announce=lambda _: None)
        raw = manifest_path(tmp_path).read_text(encoding='utf-8')
        assert raw.endswith('\n')
        assert json.loads(raw)['schema'] == MANIFEST_SCHEMA


class TestTheHiddenTramaDefaults:
    """The literal after the last `default:` in every emitted property.

    `telar.scss` resolves a theme in three steps: the site's own, then
    `site.data.themes['trama']`, then `site.data.defaults.themes.trama`. The
    third names a file no repo ships, so it has never fired; what actually
    carries a site whose theme resolves to nothing is the literal at the end
    of each property's `default:` chain. Those literals are Trama, written
    out by hand, and nothing has been comparing them to Trama.

    A value that drifts here is invisible: the site still builds, still
    renders, and renders a colour no theme file names.
    """

    PROPERTY = re.compile(r'(--[a-z0-9-]+):\s*\{\{(.+?)\}\};')
    LITERAL = re.compile(r'default:\s*"([^"]*)"')
    THEME_KEY = re.compile(r'theme\.([a-z_0-9.]+)')
    ON_KEY = re.compile(r'\bon\.([a-z_0-9]+)')

    @staticmethod
    def _dig(document, path):
        for part in path.split('.'):
            document = (document or {}).get(part)
        return document

    def _rows(self):
        """Each emitted property, with the literal it falls back to."""
        source = (REPO_ROOT / 'assets' / 'css' / 'telar.scss').read_text(
            encoding='utf-8'
        )
        trama = yaml.safe_load(
            (SHIPPED_THEMES_DIR / 'trama.yml').read_text(encoding='utf-8')
        )
        derived = build_manifest(SHIPPED_THEMES_DIR)['themes']['trama']['on']

        for prop, expression in self.PROPERTY.findall(source):
            literals = self.LITERAL.findall(expression)
            if not literals:
                continue
            theme_keys = self.THEME_KEY.findall(expression)
            on_keys = self.ON_KEY.findall(expression)
            if theme_keys:
                wanted = self._dig(trama, theme_keys[-1])
                source_name = 'trama.' + theme_keys[-1]
            elif on_keys:
                wanted = derived.get(on_keys[-1])
                source_name = 'the colour derived for ' + on_keys[-1]
            else:
                wanted, source_name = None, None
            yield prop, literals[-1], wanted, source_name

    def test_every_fallback_is_the_value_trama_names(self):
        adrift = [
            f'{prop}: falls back to {literal!r}, but {source_name} is {wanted!r}'
            for prop, literal, wanted, source_name in self._rows()
            if wanted is not None and str(wanted).strip() != literal.strip()
        ]
        assert adrift == [], '\n'.join(adrift)

    def test_every_fallback_has_something_to_compare_against(self):
        """A property whose chain names no theme key is one this cannot check."""
        unanchored = [
            prop for prop, _, wanted, _ in self._rows() if wanted is None
        ]
        assert unanchored == [], (
            'these fall back to a literal with no theme value behind it, so '
            f'nothing can tell whether it is right: {unanchored}'
        )

    def test_the_defaults_file_the_stylesheet_reaches_for_does_not_exist(self):
        """Pinned as the fact it is, not as behaviour worth keeping.

        If someone adds `_data/defaults/themes.yml`, this fails and the third
        guard starts firing — which may be what they intended, and should be
        a deliberate change rather than a discovery.
        """
        source = (REPO_ROOT / 'assets' / 'css' / 'telar.scss').read_text(
            encoding='utf-8'
        )
        assert 'site.data.defaults.themes.trama' in source
        assert not (REPO_ROOT / '_data' / 'defaults').exists()


class TestStylesheetConsumesTheDerivedProperties:
    """The partials must read the derived colour, not the raw theme value.

    The four `--color-*-text` properties stay emitted for anything outside
    this repo that reads them, but nothing in _sass/ may use one, or a theme
    whose choice was replaced would keep rendering the illegible value.
    """

    SUPERSEDED = (
        '--color-button-text',
        '--color-panel-layer1-text',
        '--color-panel-layer2-text',
        '--color-panel-glossary-text',
    )

    # The files allowed to read --color-button-text, and why. The waveform
    # bars are drawn on the accent darkened to 70%, not on the button
    # background, so the colour derived for the button ground does not apply
    # to them. Every other read in assets/js/ is a colour sitting on the
    # button background and belongs on --color-on-button. Paths are relative
    # to assets/js/; the two esbuild bundles mirror their sources.
    JS_BUTTON_TEXT_EXEMPT = {
        'object-theme.js',              # deriveThemeColors, waveform palette
        'object-page/audio-object.js',  # passes it to deriveThemeColors
        'object-audio.js',              # bundle carrying audio-object.js
        'telar-story/audio-card.js',    # deriveThemeColors, waveform palette
        'telar-story.js',               # bundle of telar-story/
    }

    @pytest.mark.parametrize("prop", SUPERSEDED)
    def test_no_partial_uses_a_superseded_property(self, prop):
        hits = subprocess.run(
            ['grep', '-rn', '--', prop, str(SASS_DIR)],
            capture_output=True, text=True,
        )
        assert hits.stdout == '', f'{prop} still used:\n{hits.stdout}'

    @pytest.mark.parametrize("prop", SUPERSEDED)
    def test_no_script_uses_a_superseded_property(self, prop):
        hits = subprocess.run(
            ['grep', '-rln', '--include=*.js', '--', prop, str(JS_DIR)],
            capture_output=True, text=True,
        )
        files = {
            str(Path(line).relative_to(JS_DIR))
            for line in hits.stdout.splitlines() if line
        }
        files -= {f for f in files if f.endswith('.min.js')}
        allowed = (
            self.JS_BUTTON_TEXT_EXEMPT if prop == '--color-button-text' else set()
        )
        assert files <= allowed, f'{prop} still used in:\n{sorted(files - allowed)}'

    @pytest.mark.parametrize("prop", SUPERSEDED)
    def test_the_stylesheet_still_emits_it(self, prop):
        source = (REPO_ROOT / 'assets' / 'css' / 'telar.scss').read_text(
            encoding='utf-8'
        )
        assert f'{prop}:' in source

    @pytest.mark.parametrize("key", DERIVED_BACKGROUNDS)
    def test_the_stylesheet_emits_the_derived_property(self, key):
        source = (REPO_ROOT / 'assets' / 'css' / 'telar.scss').read_text(
            encoding='utf-8'
        )
        prop = '--color-on-' + key.replace('_', '-')
        assert f'{prop}:' in source
        # And falls back to the theme's own value, then to trama's, so a site
        # built without the Python step renders as it did before.
        line = next(l for l in source.splitlines() if l.strip().startswith(prop))
        assert f'theme.colors.text.{key}' in line

    @pytest.mark.parametrize("key", DERIVED_TEXT_GROUNDS)
    def test_the_stylesheet_emits_the_text_ground_property(self, key):
        source = (REPO_ROOT / 'assets' / 'css' / 'telar.scss').read_text(
            encoding='utf-8'
        )
        prop = '--color-on-' + key.replace('_', '-')
        line = next(l for l in source.splitlines() if l.strip().startswith(prop))
        # The ground cannot be its own fallback, so this one falls back to the
        # white the rules hard-coded before the derivation reached them.
        assert '"#FFFFFF"' in line
        assert f'theme.colors.text.{key}' not in line

    def test_the_object_layout_writes_the_panel_ground_from_the_manifest(self):
        """The class comes from the build's own flag, not from the browser.

        `panel_ground` is assigned in the layout and read in the three author
        panels, which are includes now — one per media type, so a page carries
        only its own. Liquid gives an include the including template's scope,
        so the assignment stays where it is and each panel reads it; what this
        checks is that all three still do, since an include that lost the class
        would render an unstyled panel rather than fail.
        """
        layout = (REPO_ROOT / '_layouts' / 'object.html').read_text(
            encoding='utf-8'
        )
        assert "theme_colours.themes[site.telar_theme].light" in layout
        assert "theme_light.button == false" in layout

        tools = REPO_ROOT / '_includes' / 'objects' / 'tools'
        panels = sorted(tools.glob('*.html'))
        assert len(panels) == 3, f'expected one panel per media type, found {panels}'
        for panel in panels:
            assert 'coordinate-panel {{ panel_ground }}' in panel.read_text(
                encoding='utf-8'
            ), f'{panel.name} does not take its ground from the build' 

    def test_no_script_decides_the_panel_ground(self):
        hits = subprocess.run(
            ['grep', '-rln', '--include=*.js', '--',
             'applyPanelContrastClass', str(JS_DIR)],
            capture_output=True, text=True,
        )
        assert hits.stdout == '', (
            'the panel ground is decided in the browser again:\n' + hits.stdout
        )

    def test_the_panel_sets_no_literal_text_colour(self):
        """Its text is --color-on-button, the same property the button uses."""
        source = (SASS_DIR / '_coordinate-panel.scss').read_text(
            encoding='utf-8'
        )
        declarations = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith('color:')
        ]
        assert declarations, 'the partial sets no text colour at all'
        for line in declarations:
            assert 'var(--color-on-button)' in line, line

    @pytest.mark.parametrize("key", DERIVED_TEXT_GROUNDS)
    def test_no_partial_paints_a_literal_colour_on_that_ground(self, key):
        """Wherever a partial paints the ground, the text beside it is derived.

        This is the defect the derivation was extended for: four rules set a
        literal white on the heading, outside the floor, so a theme with a
        mid-tone heading failed there with no signal.
        """
        ground = f'background: var(--color-{key.replace("_", "-")})'
        for path in sorted(SASS_DIR.rglob('*.scss')):
            lines = path.read_text(encoding='utf-8').splitlines()
            for number, line in enumerate(lines):
                if ground not in line:
                    continue
                following = lines[number + 1] if number + 1 < len(lines) else ''
                if 'color:' not in following:
                    continue
                assert 'var(--color-on-' in following, (
                    f'{path.name}:{number + 2} paints {following.strip()} on '
                    f'the {key} ground'
                )
