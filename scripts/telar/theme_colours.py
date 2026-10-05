"""
Derived On-Colours for Theme Backgrounds

A theme in `_data/themes/*.yml` hand-picks a text colour for each of its
backgrounds — `colors.text.panel_layer1` to sit on
`colors.background.panel_layer1`, and so on. This module reads every
theme file and works out, for each background, a text colour that reaches a
contrast ratio of 4.5:1 against it, writing the result to
`_data/telar-build/theme-colours.json` for `assets/css/telar.scss` to emit as
`--color-on-*` custom properties.

The derivation runs here rather than in Liquid because Liquid has no hex
parsing and no logarithm.

**Which backgrounds are derived.** The four keys under `colors.background`:
`button`, `panel_layer1`, `panel_layer2` and `panel_glossary`. Each is emitted
as a `--color-*-bg` custom property that `_sass/` paints behind text:
`_panels.scss` sets `--color-panel-layer1-bg` and `--color-panel-layer2-bg` on
the two panels and `--color-panel-glossary-bg` on the glossary panel, whose
titles, bodies and headings take a colour in the same rules; `--color-button-bg`
carries the buttons in `_panels.scss`, `_layout.scss`, `_story.scss`,
`_widgets.scss` and `_coordinate-panel.scss`, each of which sets a text colour
beside it.

**A text colour used as a ground.** `colors.text.heading` is a text colour in
the theme schema, and `_sass/` also paints it behind text: the objects filter
chip in `_layout.scss`, and the share modal's active tabs and copy button in
`_share.scss`. It gets an on-colour like the four backgrounds do, emitted as
`--color-on-heading`. The schema names no text colour to sit on it, so its
candidate order starts at the second step below and no explicit choice can be
overruled.

`colors.text.link` is not derived for. It reaches the stylesheet as
`--color-link` and `--color-accent`, and neither is used as a background
anywhere in `_sass/` — they are only ever a text, border or outline colour, so
no text sits on them and there is nothing to derive an on-colour against.

**Candidate order.** For each background, in order, the first candidate that
reaches the floor wins:

1. The theme's own explicit text colour for that context. An author's choice
   is design, and it is replaced only when it would be illegible.
2. Whichever of `colors.text.heading` and `colors.text.button` has the higher
   contrast against the background. `text.button` stands for "the light text
   colour the theme defines": every shipped theme sets it, and every one sets
   it to a colour meant for a dark ground, so it is the one light value a
   theme can be relied on to have named itself.
3. White or black, whichever has the higher contrast. This candidate is the
   highest contrast any colour can reach against that background, so it is
   also what gets chosen when nothing reaches the floor.

**What is left alone.** A background whose value is missing, or is not a
`#rgb` or `#rrggbb` hex colour, gets no entry at all: a named colour or an
`rgb()` call is a value this module cannot read, not a value to replace, and
the stylesheet falls back to the theme's own text colour for that context. A
candidate colour that is present but unreadable is dropped from the ordering.
A candidate a theme simply does not set is skipped in silence — the theme has
named nothing wrong.

**Is the chosen colour a light one.** Beside `on`, each theme records `light`:
for every ground, whether the colour derived for it is a light colour. A
surface that also needs to know which way its ground runs — the object page's
author panels, whose translucent wells and close icon differ on a dark ground
from a light one — reads that flag rather than measuring the colour again in
the browser. Two contrast decisions on one background can disagree; one
decision, taken here, cannot.

**Warnings.** Two cases, both recorded in the JSON under the theme and printed
by the generate step, and neither says anything about a theme that is fine:

- *A choice overruled.* Whenever the derivation replaces an explicit colour
  the author wrote, it says so: one line naming the key, the author's value
  with its ratio, and the value used instead with its. An author's colour is
  never silently swapped, because silence about a replaced choice is what
  leaves a theme looking broken to the person who wrote it.
- *A value that cannot be read.* Named colours and `rgb()` calls, reported
  once per value and left as the theme wrote them.

There is no third case for "nothing reached the floor". White and black meet
at 4.58:1 at worst, so the last candidate always clears 4.5:1 and the
derivation always has a colour to take.

Version: v1.8.0
"""

import json
import re
from pathlib import Path

import yaml

# Where the derived colours land, relative to the data directory. Nested
# under `telar-build` alongside the story page manifest so it can never
# collide with `_data/<identifier>.json`; Jekyll loads it as
# `site.data['telar-build']['theme-colours']`.
MANIFEST_RELATIVE_PATH = Path('telar-build') / 'theme-colours.json'

# WCAG 2.1 AA for normal-size text. Panel titles and button labels are not
# reliably large text, so the large-text 3:1 floor does not apply.
CONTRAST_FLOOR = 4.5

# The keys under `colors.background` an on-colour is derived for, and the key
# under `colors.text` that names the theme's own choice for each. The two
# share their names, which is what lets the stylesheet emit
# `--color-on-panel-layer1` beside `--color-panel-layer1-bg`.
DERIVED_BACKGROUNDS = ('button', 'panel_layer1', 'panel_layer2', 'panel_glossary')

# The two theme colours that stand in when the explicit choice fails.
FALLBACK_TEXT_KEYS = ('heading', 'button')

# Keys under `colors.text` that `_sass/` also paints as a ground. Their
# on-colour is emitted as `--color-on-<key>` beside the four above. A theme
# names no text colour to sit on one of these, so the derivation has nothing
# of the author's to honour and nothing of the author's to overrule.
DERIVED_TEXT_GROUNDS = ('heading',)

LAST_RESORT_COLOURS = ('#FFFFFF', '#000000')

# The luminance at which black text starts to out-contrast white text under
# the WCAG formula. A chosen on-colour above it is a light colour, which is
# the same as saying the ground it was chosen for is a dark one.
LIGHT_COLOUR_LUMINANCE = 0.179

HEX_PATTERN = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')

# Theme files Jekyll would load from `_data/themes/`. Keyed by file stem,
# which is the key `site.telar_theme` names.
THEME_FILE_PATTERNS = ('*.yml', '*.yaml')


def parse_hex(value):
    """Return (r, g, b) for a `#rgb` or `#rrggbb` colour, else None.

    Case-insensitive. Anything else — a named colour, an `rgb()` call, a
    missing value — returns None rather than a guess.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not HEX_PATTERN.match(text):
        return None
    digits = text[1:]
    if len(digits) == 3:
        digits = ''.join(ch * 2 for ch in digits)
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def relative_luminance(colour):
    """Relative luminance of a hex colour, per WCAG 2.1.

    Raises ValueError on a colour `parse_hex` cannot read, so a caller that
    has not checked gets an error rather than a number derived from nothing.
    """
    rgb = parse_hex(colour)
    if rgb is None:
        raise ValueError(f'not a hex colour: {colour!r}')
    channels = []
    for value in rgb:
        srgb = value / 255.0
        channels.append(
            srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground, background):
    """Contrast ratio between two hex colours, per WCAG 2.1: 1.0 to 21.0."""
    lighter = relative_luminance(foreground)
    darker = relative_luminance(background)
    if lighter < darker:
        lighter, darker = darker, lighter
    return (lighter + 0.05) / (darker + 0.05)


def _format_ratio(ratio):
    return f'{ratio:.2f}'


def _not_hex_warning(theme, where, value):
    return (
        f'Theme "{theme}": {where} is "{value}", which is not a hex color '
        'like #FFFFFF or #FFF. Telar could not read it, so it was left as '
        'the theme wrote it.'
    )


def _unreadable_background_warning(theme, key):
    return (
        f'Theme "{theme}": no text color was worked out for the {key} '
        'background, because Telar could not read the background color.'
    )


def _missing_background_warning(theme, key):
    return (
        f'Theme "{theme}": no text color was worked out for the {key} '
        'background, because the theme does not set colors.background.'
        f'{key}.'
    )


def _replacement_warning(theme, key, ground, explicit, chosen):
    return (
        f'Theme "{theme}": colors.text.{key} is {explicit}, a contrast ratio '
        f'of {_format_ratio(contrast_ratio(explicit, ground))}:1 on its '
        f'{ground} background, below the {CONTRAST_FLOOR}:1 that text needs. Telar used '
        f'{chosen} instead, {_format_ratio(contrast_ratio(chosen, ground))}:1. '
        f'To keep your own color, choose a lighter or darker '
        f'colors.background.{key}.'
    )


def _readable(theme, where, value, warnings):
    """Return the colour when it is hex, else None with a warning recorded.

    A value the theme does not set at all is not a mistake to report: the
    theme has named nothing wrong, and the caller skips the candidate.
    """
    if value is None:
        return None
    if parse_hex(value) is None:
        warnings.append(_not_hex_warning(theme, where, value))
        return None
    return value


def _candidates(ground, explicit, fallbacks):
    """The colours to try against a ground, the strongest claim first.

    A ground that is one of the fallbacks — the heading, painted behind text
    — reaches 1:1 against itself, so `max` never returns it while the theme
    names any other candidate, and the floor rejects it when it does.
    """
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    if fallbacks:
        candidates.append(max(fallbacks, key=lambda c: contrast_ratio(c, ground)))
    # White or black, whichever is higher. The two meet at 4.58:1 at worst,
    # so this candidate always reaches the floor and the caller always has a
    # colour to take.
    candidates.append(
        max(LAST_RESORT_COLOURS, key=lambda c: contrast_ratio(c, ground))
    )
    return candidates


def _chosen(ground, explicit, fallbacks):
    """The first candidate that reaches the floor."""
    return next(
        colour for colour in _candidates(ground, explicit, fallbacks)
        if contrast_ratio(colour, ground) >= CONTRAST_FLOOR
    )


def derive_theme(theme, colours):
    """Return (on_colours, warnings) for one theme's `colors` block."""
    text = colours.get('text') or {}
    background = colours.get('background') or {}
    warnings = []

    # Read each colour once, so a theme that names one bad value is told
    # about it once rather than once per background. `heading` is both a
    # fallback and a ground, which is why this reads the union rather than
    # either list.
    readable_text = {}
    for key in dict.fromkeys(FALLBACK_TEXT_KEYS + DERIVED_TEXT_GROUNDS):
        colour = _readable(theme, f'colors.text.{key}', text.get(key), warnings)
        if colour is not None:
            readable_text[key] = colour
    fallbacks = [readable_text[key] for key in FALLBACK_TEXT_KEYS
                 if key in readable_text]

    on_colours = {}
    for key in DERIVED_BACKGROUNDS:
        raw_background = background.get(key)
        if raw_background is None:
            warnings.append(_missing_background_warning(theme, key))
            continue
        ground = _readable(
            theme, f'colors.background.{key}', raw_background, warnings
        )
        if ground is None:
            warnings.append(_unreadable_background_warning(theme, key))
            continue

        explicit = _readable(
            theme, f'colors.text.{key}', text.get(key), warnings
        )
        chosen = _chosen(ground, explicit, fallbacks)
        if explicit is not None and chosen != explicit:
            warnings.append(
                _replacement_warning(theme, key, ground, explicit, chosen)
            )
        on_colours[key] = chosen

    for key in DERIVED_TEXT_GROUNDS:
        ground = readable_text.get(key)
        # A theme that sets no heading colour has named nothing wrong, and
        # one that set an unreadable value was told so when it was read. The
        # stylesheet's own fallback carries both.
        if ground is None:
            continue
        on_colours[key] = _chosen(ground, None, fallbacks)

    return on_colours, warnings


def light_colours(on_colours):
    """Which of the derived colours are light ones.

    A pure reading of what the derivation already chose, not a second
    decision: a light colour was chosen because the ground is dark, so this
    is how a surface asks which way its ground runs.
    """
    return {key: relative_luminance(colour) > LIGHT_COLOUR_LUMINANCE
            for key, colour in on_colours.items()}


def theme_files(themes_dir):
    """Every theme file in `_data/themes/`, in a stable order."""
    directory = Path(themes_dir)
    if not directory.is_dir():
        return []
    found = []
    for pattern in THEME_FILE_PATTERNS:
        found.extend(directory.glob(pattern))
    return sorted(found)


def build_manifest(themes_dir):
    """Derive on-colours for every theme file, keyed by file stem."""
    themes = {}
    for path in theme_files(themes_dir):
        with open(path, 'r', encoding='utf-8') as f:
            document = yaml.safe_load(f) or {}
        colours = document.get('colors') or {}
        on_colours, warnings = derive_theme(path.stem, colours)
        themes[path.stem] = {'on': on_colours,
                             'light': light_colours(on_colours),
                             'warnings': warnings}
    return {'themes': themes}


def manifest_warnings(manifest):
    """Every theme's warnings, flattened in theme order."""
    collected = []
    for name in sorted(manifest['themes']):
        collected.extend(manifest['themes'][name]['warnings'])
    return collected


def manifest_path(data_dir):
    return Path(data_dir) / MANIFEST_RELATIVE_PATH


def write_manifest(data_dir, manifest):
    path = manifest_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    return path


def generate(data_dir='_data', announce=print):
    """Derive and write, unless the site has no themes directory.

    Returns the path written, or None when there is nothing to derive from.
    A site without `_data/themes/` is not a site with broken themes, so it
    gets no file and no warning; the stylesheet's own fallbacks cover it.
    """
    themes_dir = Path(data_dir) / 'themes'
    if not themes_dir.is_dir():
        return None
    manifest = build_manifest(themes_dir)
    for warning in manifest_warnings(manifest):
        announce(warning)
    return write_manifest(data_dir, manifest)
