"""
Shared helpers for the Telar upgrade engine.

The site's console language, today's date, and the exit code csv_to_json.py
uses for a protected story the build cannot encrypt. telar_upgrade.py and
both of its sibling modules need them, and neither sibling imports the
engine itself, which runs as __main__.

Ships in the release tooling tarball beside telar_upgrade.py, never in a
site.

Version: v1.8.0
"""

import os

import yaml


# The exit code csv_to_json.py uses for "protected stories cannot be
# encrypted downstream". Declared as a literal rather than imported:
# the scripts/telar package eagerly imports pandas and PIL, and this script
# runs before _ensure_regeneration_dependencies() has had a chance to
# install them. tests/unit/test_upgrade_protected_prerequisite.py reads
# both definitions and fails if they diverge.
PROTECTED_PREREQUISITE_EXIT = 3


def _get_lang(repo_root: str) -> str:
    """Read the site's telar_language from _config.yml for console output.

    Defaults to English when the config is missing/unreadable or the key is
    absent. messages.py recognises 'en' and 'es'; anything else falls back to
    English there.
    """
    config_path = os.path.join(repo_root, '_config.yml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if isinstance(config, dict):
            lang = config.get('telar_language')
            if isinstance(lang, str) and lang.strip():
                return lang.strip()
    except Exception:
        pass
    return 'en'


def _get_date() -> str:
    """Today, for the things that are genuinely about now.

    The summary's own date and the state file's timestamp record when this
    run happened. The version stamp does not — see `_stamp_date`.
    """
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d')
