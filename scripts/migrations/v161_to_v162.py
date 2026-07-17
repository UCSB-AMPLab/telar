"""
Migration from v1.6.1 to v1.6.2.

Tooling/workflow repair patch. v1.6.2's first wave (already in the release
branch) fixed the upgrade environment at the source: `.github/workflows/
upgrade.yml` now installs the full `-r requirements.txt` instead of a partial
package list, `.github/workflows/telar-tests.yml` has its user-site guard
restored (it was running Telar's own internal framework tests against forks,
which produced spurious failure emails), `.github/dependabot.yml` was deleted
from the template (dependency-bump PRs are managed centrally by the Telar
release process now, not per-site), `package-lock.json` was regenerated, and
`upgrade.py` gained a step that ensures its own regeneration dependencies are
installed rather than trusting a site's possibly-stale CI environment. None
of that wave reaches an existing site by itself — it only changes what future
releases ship and how the upgrade tooling behaves once it is already running.
This migration carries the site-level pieces of that repair forward:

1. `package.json` / `package-lock.json` (fetched from the v1.6.2 release tag,
   written atomically as a pair via the staged-atomic framework-file helper).
   The lockfile is meaningless without the manifest it was generated from and
   vice versa, so they are listed together in FRAMEWORK_FILES and installed
   through `_apply_framework_files`, whose fetch-then-commit-all-or-nothing
   contract already guarantees neither installs without the other — there is
   no separate pairing mechanism to build.

2. `.github/dependabot.yml` is deleted from the site if present (idempotent —
   a site that already lacks the file, or has already been migrated, is left
   alone). Unlike `.github/workflows/*.yml`, this path is not under
   `.github/workflows/`, so the upgrade's GITHUB_TOKEN *can* commit its
   removal — the long-standing workflow-file restriction (v0.6.3, v0.8.1,
   v0.9.1, v1.0.0, v1.5.0, v1.5.3, v1.6.0, ...) does not apply here. Removal
   is still treated as soft, not hard, though: a permissions quirk or a race
   on some fork's checkout is not worth failing the whole upgrade over a file
   whose only job was opening PRs nobody needs anymore. A failed removal is
   recorded and surfaced as a warning; the site is otherwise unaffected.

`.github/workflows/upgrade.yml` and `.github/workflows/telar-tests.yml`
themselves are NOT delivered here — GitHub does not allow the upgrade's
GITHUB_TOKEN to modify workflow files, the same restriction every migration
since v0.6.3 has documented. See the manual steps below. Because `upgrade.py`
now installs its own regeneration dependencies (part of the same wave, but an
engine change rather than a site-facing file), a site that skips the
`upgrade.yml` manual step is not stuck — its *next* upgrade still runs;
recopying the file is recommended housekeeping, not a prerequisite.

Per the established convention (documented in every migration since
v1.4.0->v1.5.0), `upgrade.py`, the `migrations` package, `base.py`, and
`messages.py` are excluded from FRAMEWORK_FILES — they ship out of band via
the verified release tarball, not through a running migration's own
fetch/write step.

The version stamp (telar.version -> 1.6.2) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed step can
never leave the site stamped as a version it is not running.

Version: v1.6.2
"""

import os
from typing import Dict, List

from .base import BaseMigration, ChangeRecord, ChangeStatus


# Framework files fetched from the v1.6.2 release tag/branch and written
# atomically as a pair — see point 1 in the module docstring. Both entries or
# neither: _apply_framework_files fetches the whole map before writing
# anything, so a fetch failure on either file leaves both untouched.
FRAMEWORK_FILES = {
    'package.json': 'Dependency metadata (version bump, dependency updates for v1.6.2)',
    'package-lock.json': 'Regenerated dependency lockfile matching package.json — always ships with it',
}

# Deleted in v1.6.2 — see point 2 in the module docstring. Not under
# .github/workflows/, so the upgrade token can commit its removal.
DEPENDABOT_PATH = '.github/dependabot.yml'


class Migration161to162(BaseMigration):
    """Migration from v1.6.1 to v1.6.2 — carry the upgrade-environment repair to existing sites: package.json/package-lock.json pair, dependabot.yml removal."""

    from_version = "1.6.1"
    to_version = "1.6.2"
    description = "Upgrade-environment repair — refresh package.json/package-lock.json, remove .github/dependabot.yml"

    # Pin framework-file fetches to the v1.6.2 release tag/branch, not the
    # moving `main` branch, so this migration always installs v1.6.2 files.
    _TARGET_TAG = "v1.6.2"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        changes: List[ChangeRecord] = []

        # Phase 1: install the package.json / package-lock.json pair atomically.
        print("  Phase 1: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Fail closed: if the pair did not install, leave dependabot.yml
        # alone too, so a re-run retries a clean, well-defined starting state.
        if any(c.status == ChangeStatus.FAILED for c in framework_changes):
            return changes

        # Phase 2: remove .github/dependabot.yml if present (soft-fail — see
        # _remove_dependabot).
        print("  Phase 2: Removing .github/dependabot.yml...")
        changes.extend(self._remove_dependabot())

        # No version bump here — upgrade.py stamps once after all steps succeed.
        return changes

    # ------------------------------------------------------------------ #
    # Phase 1: framework file fetch (pinned + atomic)
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install the v1.6.2 package.json/package-lock.json pair from the pinned tag."""
        return self._apply_framework_files(FRAMEWORK_FILES)

    # ------------------------------------------------------------------ #
    # Phase 2: dependabot.yml removal (idempotent, soft-fail)
    # ------------------------------------------------------------------ #

    def _remove_dependabot(self) -> List[ChangeRecord]:
        """Delete `.github/dependabot.yml` if present.

        Idempotent: a site that never had the file, or was already migrated,
        gets a no-op APPLIED record rather than a SKIPPED one — there is
        nothing wrong to flag. A removal failure (permissions, a locked
        working tree, whatever) is deliberately soft: dependabot.yml only
        opened dependency-bump PRs, a job the Telar release process owns
        centrally now, so a site that keeps the file a little longer loses
        nothing but tidiness. Fail soft and let the user clean it up by hand
        rather than sinking the rest of the upgrade over it.
        """
        if not self._file_exists(DEPENDABOT_PATH):
            return [ChangeRecord(
                description=f"No {DEPENDABOT_PATH} to remove (already absent)",
                status=ChangeStatus.APPLIED,
                severity="soft",
            )]

        try:
            os.remove(os.path.join(self.repo_root, DEPENDABOT_PATH))
        except OSError as e:
            return [ChangeRecord(
                description=(
                    f"Could not remove {DEPENDABOT_PATH}: {e}. Non-fatal — "
                    "delete it by hand when convenient. It no longer does "
                    "anything: dependency-bump pull requests are managed by "
                    "the Telar release process, not per-site, and GitHub's "
                    "security alerts are unaffected either way."
                ),
                status=ChangeStatus.FAILED,
                severity="soft",
            )]

        return [ChangeRecord(
            description=(
                f"Removed {DEPENDABOT_PATH} — dependency-bump pull requests are "
                "now managed by the Telar release process, not per-site"
            ),
            status=ChangeStatus.APPLIED,
            severity="soft",
        )]

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Update `.github/workflows/upgrade.yml` by hand (recommended, not urgent).** GitHub does not allow this upgrade to change workflow files, so this step is manual: copy the current `upgrade.yml` from the Telar repository over yours (open it on GitHub, use "Copy raw contents", replace the whole file, commit). Your current copy installs only some of the Python packages the upgrade needs; the repository's version installs them all. Not urgent: the upgrade tooling now installs its own dependencies as it runs, so future upgrades keep working even if you leave this for later.''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/'
            },
            {
                'description': '''**Update `.github/workflows/telar-tests.yml` by hand.** The same restriction applies: GitHub will not let the upgrade modify it for you. Copy the current `telar-tests.yml` from the Telar repository over yours (open it on GitHub, use "Copy raw contents", replace the whole file, commit). The updated workflow stops running Telar's internal framework tests on your site, which ends the emails about failed tests that had nothing to do with your content.''',
                'doc_url': 'https://telar.org/docs/setup/upgrading/'
            },
            {
                'description': '''**No action needed.** This upgrade removed `.github/dependabot.yml` from your site (or the file was already gone). That file only opened automated dependency-update pull requests, a task the Telar release process now handles instead of each site separately. GitHub's security alerts keep working as before.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Actualiza `.github/workflows/upgrade.yml` a mano (recomendado, no urgente).** GitHub no permite que esta actualización modifique archivos de workflow, así que el paso se hace a mano: copia el `upgrade.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). Tu copia actual instala solo una parte de los paquetes de Python que la actualización necesita; la del repositorio los instala todos. No es urgente: la herramienta de actualización ya instala sus dependencias al ejecutarse, así que las próximas actualizaciones seguirán funcionando aunque dejes este paso para después.''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/'
            },
            {
                'description': '''**Actualiza `.github/workflows/telar-tests.yml` a mano.** La restricción es la misma: GitHub no permite que la actualización lo modifique por ti. Copia el `telar-tests.yml` actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). El workflow actualizado deja de ejecutar las pruebas internas de Telar en tu sitio, y con eso se acaban los correos sobre pruebas fallidas que no tienen nada que ver con tu contenido.''',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/'
            },
            {
                'description': '''**No se requiere ninguna acción.** Esta actualización eliminó `.github/dependabot.yml` de tu sitio (o el archivo ya no existía). Ese archivo solo abría solicitudes automáticas para actualizar dependencias, y de esa tarea se encarga ahora el proceso de lanzamiento de Telar, no cada sitio por separado. Las alertas de seguridad de GitHub siguen funcionando igual.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
