"""
Frontmatter for the generated collection files.

The pattern that splits a markdown source into its frontmatter and body, and
the serialiser every generated object, glossary and page file writes its
frontmatter with. Kept apart from the generators so the glossary and page
modules and generate_collections.py share one of each.

Version: v1.8.0
"""

import re

import yaml


FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)

# What loading an author's frontmatter can raise. YAML that parses can still
# fail to become values: `2024-13-45` is read as a date that does not exist,
# and a tag such as `!!float` or `!` hands its text to a constructor that
# rejects it. PyYAML raises those as the builtin errors, not as YAMLError, so
# a caller that catches YAMLError alone lets them end the build of the file.
FRONTMATTER_LOAD_ERRORS = (yaml.YAMLError, ValueError, TypeError, KeyError)


def _as_text(value):
    """A frontmatter value as the text the author typed.

    Every scalar the build writes is a string as far as the templates are
    concerned, and pandas hands over numpy scalars rather than Python ones.
    Serialising a value's own type is how `1890` reaches a page as a number
    and `true` as a boolean, neither of which is what the cell said.
    """
    return str(value)


# YAML 1.1 line-break characters besides \n and \r. A scalar containing one
# of these must be double-quoted, or the character survives the dump and
# then reads back as something else: YAML 1.1 parsers fold it (and its
# surrounding whitespace) the way they fold a real line break, so the value
# a reader gets back is not the value written.
_YAML_1_1_LINE_BREAKS = ('\x85', ' ', ' ')


class _FrontmatterDumper(yaml.SafeDumper):
    """A Dumper scoped to this module, so the style override below cannot
    reach any other `yaml.safe_dump` call in the codebase."""


def _represent_str(dumper, data):
    style = '"' if any(ch in data for ch in _YAML_1_1_LINE_BREAKS) else None
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=style)


_FrontmatterDumper.add_representer(str, _represent_str)


def _frontmatter_block(fields):
    """Serialise frontmatter fields as YAML.

    `safe_dump` quotes anything that would parse back as another type: an
    `object_id` beginning `*`, or a quote anywhere in `year`.

    `sort_keys=False` keeps the order the build writes, which is the order a
    site owner reading the file expects, and `allow_unicode` keeps accented
    text as itself rather than as escapes. `_FrontmatterDumper` forces
    double-quoted style for a string carrying a YAML 1.1 line-break
    character (see `_YAML_1_1_LINE_BREAKS`) so it is written as an escape
    instead of the raw character; every other string keeps whatever style
    the default representer would have chosen.
    """
    return yaml.dump(fields, Dumper=_FrontmatterDumper, sort_keys=False,
                     allow_unicode=True, default_flow_style=False,
                     width=10 ** 6)
