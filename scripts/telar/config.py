"""
Language and Configuration Loading

This module deals with loading localized strings so that Telar's build
pipeline can produce error messages, warnings, and UI text in the site's
configured language. It reads the `telar_language` setting from `_config.yml`
(defaulting to English) and loads the corresponding YAML language file from
`_data/languages/` (e.g., `en.yml` or `es.yml`).

The loaded strings are cached in the module-level `_lang_data` dictionary to
avoid repeated file reads during a build. The main entry point for the rest
of the codebase is `get_lang_string()`, which takes a dot-separated key path
like `'errors.object_warnings.iiif_503'` and walks the nested dictionary to
find the matching string. It also supports variable interpolation using
`{{ var }}` syntax — for example, `get_lang_string('errors.missing', id=obj_id)`
replaces `{{ id }}` in the template with the value of `obj_id`.

`load_site_language()` is a lighter utility that just returns the language
code ('en', 'es', etc.) without loading the full string dictionary. This is
used by IIIF metadata extraction to choose the preferred language when
reading multilingual manifests.

Version: v0.7.0-beta
"""

from pathlib import Path
import yaml

# Global language data cache
_lang_data = None


def load_language_data():
    """
    Load language strings from _config.yml and corresponding language file.

    Returns:
        dict: Language strings, or None if loading fails
    """
    global _lang_data

    # Return cached data if already loaded
    if _lang_data is not None:
        return _lang_data

    try:
        # Read _config.yml to get telar_language setting
        config_path = Path('_config.yml')
        if not config_path.exists():
            return None

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Get language setting, default to English
        language = config.get('telar_language', 'en')

        # Load language file
        lang_file = Path(f'_data/languages/{language}.yml')

        # Fall back to English if language file doesn't exist
        if not lang_file.exists():
            lang_file = Path('_data/languages/en.yml')

        if not lang_file.exists():
            return None

        with open(lang_file, 'r', encoding='utf-8') as f:
            _lang_data = yaml.safe_load(f)

        return _lang_data

    except Exception as e:
        print(f"  [WARN] Could not load language data: {e}")
        return None


def get_lang_string(key_path, **kwargs):
    """
    Get a language string by key path and optionally interpolate variables.

    Args:
        key_path: Dot-separated path to string (e.g., 'errors.object_warnings.iiif_503')
        **kwargs: Variables to interpolate into the string

    Returns:
        str: Localized string with variables interpolated, or key_path if not found
    """
    lang = load_language_data()

    if lang is None:
        return key_path

    # Navigate through nested dict using key path
    keys = key_path.split('.')
    value = lang

    try:
        for key in keys:
            value = value[key]

        # Interpolate variables if provided
        if kwargs:
            # Replace {{ var }} syntax with Python format strings
            for var_name, var_value in kwargs.items():
                value = value.replace(f'{{{{ {var_name} }}}}', str(var_value))

        return value

    except (KeyError, TypeError):
        # Key not found - return the key path itself as fallback
        return key_path


def load_site_language():
    """
    Load telar_language setting from _config.yml.

    Returns:
        str: Language code (default: 'en')
    """
    try:
        config_path = Path('_config.yml')
        if not config_path.exists():
            return 'en'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config.get('telar_language', 'en')
    except Exception:
        return 'en'
