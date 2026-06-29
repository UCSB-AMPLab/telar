"""
Migration from v1.5.3 to v1.5.4.

CI/build patch. The GitHub Actions build workflow gains a `concurrency` group
so rapid successive builds of the same repository no longer race on GitHub
Pages' one-in-progress-deployment-per-repo limit. Before this, several build
runs starting within the same second (for example, when the Telar Compositor
creates a new site and pushes two commits plus a manual run together) raced for
the single Pages deployment slot; the losers failed their "Deploy to GitHub
Pages" step and emailed the owner a spurious "build failed" notice, even though
a sibling run deployed the site correctly.

The only changed framework file is `.github/workflows/build.yml`. GitHub does
not permit the `GITHUB_TOKEN` used by the in-Actions upgrade to modify files
under `.github/workflows/`, so this migration cannot install the new workflow
itself — it would make the upgrade pull request fail. The change therefore
reaches sites two other ways:

  - The Telar Compositor replaces framework files (including the workflow) via
    its own tree-diff on upgrade, so Compositor-managed sites get it
    automatically.
  - Sites upgrading through the "Upgrade Telar" Actions workflow, or locally,
    add the `concurrency` block by hand (see the manual step below) or recopy
    `build.yml` from the latest template.

This migration carries no user-content transforms — the story step schema, CSV
formats, configuration keys, and language packs are all unchanged. Its job is
to keep the strict upgrade chain intact (v1.5.3 -> v1.5.4) so upgrade.py reaches
the latest version and stamps it, and to surface the manual workflow step.

The version stamp (telar.version -> 1.5.4) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed step can never
leave the site stamped as a version it is not running.

Version: v1.5.4
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord


class Migration153to154(BaseMigration):
    """Migration from v1.5.3 to v1.5.4 — build-workflow concurrency group; no content changes."""

    from_version = "1.5.3"
    to_version = "1.5.4"
    description = "Add a GitHub Pages concurrency group to the build workflow; no content changes"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        # No framework files are installed: the only change is the build
        # workflow, which GITHUB_TOKEN cannot write. There are no config, CSV,
        # directory, or cleanup changes. Record the workflow update as a soft
        # item so it surfaces in the upgrade summary as a manual step, and let
        # upgrade.py stamp the version once the chain completes.
        return [
            ChangeRecord(
                description=(
                    "Build workflow concurrency group: add the `concurrency` block to "
                    ".github/workflows/build.yml by hand (or recopy the file). The "
                    "in-Actions upgrade cannot modify workflow files; the Telar "
                    "Compositor applies it automatically. See the manual step below."
                ),
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
                'description': '''**If you use the Telar Compositor: no action needed.** The Compositor updates your build workflow automatically when it upgrades your site.''',
                'doc_url': 'https://telar.org/docs'
            },
            {
                'description': '''**If you use GitHub Pages with the "Upgrade Telar" workflow, or work locally:** GitHub does not allow the automated upgrade to change workflow files, so your build workflow is not updated for you. Add the following block to `.github/workflows/build.yml`, just before the `jobs:` line (or recopy the file from the latest template):

```yaml
concurrency:
  group: "pages-${{ github.ref }}"
  cancel-in-progress: true
```

Until you do, your site keeps building and deploying correctly — you may just get an occasional spurious "build failed" email when two builds start at the same time.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Si usas el Compositor de Telar: no tienes que hacer nada.** El Compositor actualiza por ti el flujo de trabajo de construcción cuando actualiza tu sitio.''',
                'doc_url': 'https://telar.org/guia'
            },
            {
                'description': '''**Si usas GitHub Pages con el flujo de trabajo "Upgrade Telar", o trabajas localmente:** GitHub no permite que la actualización automática modifique los archivos de flujo de trabajo, así que el tuyo no se actualiza solo. Agrega el siguiente bloque a `.github/workflows/build.yml`, justo antes de la línea `jobs:` (o vuelve a copiar el archivo desde la plantilla más reciente):

```yaml
concurrency:
  group: "pages-${{ github.ref }}"
  cancel-in-progress: true
```

Mientras tanto, tu sitio se sigue construyendo y publicando sin problemas; solo podrías recibir de vez en cuando un correo de «build failed» que no corresponde a una falla real, cuando dos ejecuciones empiezan al mismo tiempo.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
