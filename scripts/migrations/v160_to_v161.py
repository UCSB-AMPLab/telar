"""
Migration from v1.6.0 to v1.6.1.

Upgrade-tooling patch. v1.6.0 shipped scripts/migrations/v154_to_v160.py
without registering it in scripts/upgrade.py — the import block, the
LATEST_VERSION constant, and the MIGRATIONS list are three hand-synced
places with no auto-discovery, and only two of the three were updated. The
result: LATEST_VERSION was left at "1.5.4" and Migration154to160 was never
imported or appended to MIGRATIONS, so upgrades silently stopped at 1.5.4 —
reporting success — even though the migration file itself was correct. v1.6.1 wires
both omissions in: Migration154to160 is now imported and appended, and
Migration160to161 (this migration) is imported and appended immediately
after it, with LATEST_VERSION set to "1.6.1".

This is a tooling-only patch — no layout, include, style, script, or
language-pack file changes, no `_config.yml` key changes, and no CSV/story
schema changes. Existing stories, objects, and configuration keep working
without edits.

Per the established convention for this upgrade engine (documented in every
migration since v1.4.0->v1.5.0: upgrade.py, the migrations package, base.py,
and messages.py are excluded from FRAMEWORK_FILES and ship out of band, via
the verified release tarball, rather than through a running migration's own
fetch/write step), this migration does not re-fetch or rewrite upgrade.py or
itself. By the time any migration in the chain executes, the site is already
running the target version's engine code — that engine code is exactly what
this migration's own fix lives in, and it reaches a site the same way every
other engine change has: as part of the v1.6.1 release, not as a
FRAMEWORK_FILES entry. There is nothing else for this migration to change on
a site, so apply() only records that the fix is internal to the upgrade
tooling.

The version stamp (telar.version -> 1.6.1) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed step can
never leave the site stamped as a version it is not running.

Version: v1.6.1
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus


class Migration160to161(BaseMigration):
    """Migration from v1.6.0 to v1.6.1 — fix the upgrade-chain wiring gap left by v1.6.0; tooling-only."""

    from_version = "1.6.0"
    to_version = "1.6.1"
    description = "Register the missing v1.5.4 -> v1.6.0 migration and repair the upgrade chain; tooling-only, no site changes"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        # No framework files, directories, config, or CSV changes: the entire
        # fix is the upgrade.py registration wiring, which ships with the
        # engine itself rather than through a site-facing file write. Record
        # this as a single informational, already-applied change so it is
        # visible in UPGRADE_SUMMARY.md without implying anything to install.
        return [
            ChangeRecord(
                description=(
                    "Upgrade-chain wiring fix (internal): the v1.5.4 -> v1.6.0 migration "
                    "is now registered in scripts/upgrade.py, so upgrades starting below "
                    "v1.6.0 no longer stop early at 1.5.4. No files in this site changed."
                ),
                status=ChangeStatus.APPLIED,
                severity="soft",
            ),
        ]

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No action needed.** v1.6.1 only fixes the upgrade tooling itself (a missing registration that made upgrades stop at v1.5.4 and report success, instead of continuing to v1.6.0); it does not change anything in your site.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No se requiere ninguna acción.** v1.6.1 solo corrige la propia herramienta de actualización (un registro que faltaba y hacía que las actualizaciones se detuvieran en v1.5.4 y reportaran éxito, en lugar de continuar hasta v1.6.0); no cambia nada en tu sitio.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
