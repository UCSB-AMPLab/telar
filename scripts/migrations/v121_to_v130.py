"""
Migration from v1.2.1 to v1.3.0.

i18n hygiene plus a sister-file localization convention. Three classes of change:

1. Framework files (layouts, includes, scripts, language packs) — fetched
   fresh from GitHub. Wires up existing-but-unreferenced lang keys in
   index.html / objects-index.html / glossary-index.html (empty_states
   and errors namespaces); wires the IIIF URL warning include to its
   already-translated lang.errors.iiif_mismatch namespace; adds
   sister-file localization in scripts/generate_collections.py.

2. User content cleanup (conditional — preserves customizations):
   - index.md frontmatter: removes stories_heading / objects_heading /
     objects_intro keys IF their values match the v1.2.1 default English
     literals exactly. These keys shadowed the layout's i18n fall-through
     for every existing user since they were added to the template.
   - index.md body, pages/glossary.md, pages/objects.md,
     telar-content/texts/pages/about.md: replaced with the v1.3.0
     lang-key-driven template ONLY if the SHA-256 hash of the user's
     normalized body matches the SHA-256 hash of the v1.2.1 default.
     Any user customization (even whitespace-trimmed) bumps the hash
     and the file is left untouched.

3. Version bump: telar.version 1.2.1 -> 1.3.0 in _config.yml.

The v1.3.0 template repo also ships a Spanish sister of about.md
(telar-content/texts/pages/acerca.md). This migration creates
acerca.md for existing repos ONLY when ALL of these are true:
  - site has telar_language: es
  - the user's about.md hashes to the v1.2.1 default (i.e. they
    haven't customised it)
  - acerca.md does not already exist

That gating prevents an unwanted side effect: if an ES site has a
customised about.md, blindly creating acerca.md would shadow their
customisation at build time (sister-file routing always uses the
sister when active language matches), so we skip the create and
let them keep showing whatever they wrote. EN sites get acerca.md
in fresh template clones but not via this migration (it would just
sit unused).

Version: v1.3.0
"""

import hashlib
import re
import yaml
from typing import Dict, List, Optional, Tuple

from .base import BaseMigration


# =============================================================================
# v1.2.1 default content (for change-detection — preserve user customizations)
# =============================================================================

# v1.2.1 index.md frontmatter keys that shadow the layout's i18n fall-through.
# Removed only when the user's value matches the default exactly.
INDEX_MD_V121_FRONTMATTER_DEFAULTS = {
    'stories_heading': 'Explore the stories',
    'objects_heading': 'See the objects behind the stories',
    'objects_intro': 'Browse {count} objects featured in the stories.',
}

# v1.2.1 index.md body (post-frontmatter). Matched against to decide if we
# can safely install the lang-key-driven v1.3.0 body.
INDEX_MD_V121_BODY = """## Welcome to the Telar Demo Site
This site showcases the features and **capabilities** of Telar (v.[{{ site.telar.version }}](https://github.com/UCSB-AMPLab/telar/releases/tag/v{{ site.telar.version }})). Build your own visual narrative exhibition by visiting:

- Our **[GitHub repository](https://github.com/UCSB-AMPLab/telar)**, where you can copy the template to create your own project
- The **[documentation site](https://telar.org/docs)**, where you can find guides and tutorials

No installation is required: you can manage your content with Google Sheets and publish it for free on GitHub Pages.

***Note:** To remove or replace this message, edit the `index.md` file in your repository.*"""

GLOSSARY_MD_V121_BODY = "Key terms and concepts used in these stories."

OBJECTS_MD_V121_BODY = "Browse {{ site.objects.size }} objects featured in the stories."

ABOUT_MD_V121_BODY = """# About Telar

Telar (Spanish for 'loom') is a static site generator built on Jekyll that weaves together IIIF images, text, and layered contextual information into interactive digital narrative exhibitions. Telar uses the International Image Interoperability Framework (IIIF) to serve high-resolution images that can be zoomed, panned, and explored in detail. The framework combines these images with narrative text and layered contextual panels to create immersive storytelling experiences.

<div class="alert alert-info" role="alert">
<strong>Customize This Page</strong><br>
You can edit this about page by modifying the <code>telar-content/texts/pages/about.md</code> file in your repository. Add your own project description, credits, and acknowledgments to personalize your site.
</div>

## Credits

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Natalie Cobo, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Pedagogy Lab, and [Neogranadina](https://neogranadina.org).

We gratefully acknowledge the support of the [Caribbean Digital Scholarship Collective](https://cdscollective.org), the [Center for Innovative Teaching, Research, and Learning (CITRAL)](https://citral.ucsb.edu/home) at the University of California, Santa Barbara, the [UCSB Library](https://library.ucsb.edu), the [Routes of Enslavement in the Americas University of California MRPI](https://www.humanities.uci.edu/routes-enslavement-americas), and the [Department of History of The University of Texas at Austin](https://liberalarts.utexas.edu/history/).

For more information, visit the [Telar GitHub repository](https://github.com/UCSB-AMPLab/telar).

Telar was built with:

- [Jekyll](https://jekyllrb.com/) - Static site generator
- [Tify](https://tify.rocks/) - IIIF viewer
- [Bootstrap 5](https://getbootstrap.com/) - CSS framework
- [libvips](https://www.libvips.org/) - IIIF tile generator

It is based on [Paisajes Coloniales](https://paisajescoloniales.com/), and inspired by:

- [Wax](https://minicomp.github.io/wax/) - Minimal computing for digital exhibitions
- [CollectionBuilder](https://collectionbuilder.github.io/) - Static digital collections"""


# =============================================================================
# v1.3.0 replacement content (installed when the v1.2.1 default is detected)
# =============================================================================

INDEX_MD_NEW_BODY = """{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
<!--
  EN: Default welcome content for this page comes from your language
  pack (lang.index_page.welcome in _data/languages/<telar_language>.yml).
  To replace it with your own, delete the line that follows and write
  your welcome content here in markdown.

  ES: El contenido de bienvenida predeterminado de esta página viene
  del paquete de idioma (lang.index_page.welcome en _data/languages/<telar_language>.yml).
  Para reemplazarlo con el tuyo, borra la línea que sigue y escribe
  tu contenido de bienvenida aquí en markdown.
-->

{{ lang.index_page.welcome | markdownify }}"""

GLOSSARY_MD_NEW_BODY = """{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
<!--
  EN: Default content for this page comes from your language pack
  (lang.pages.glossary_intro in _data/languages/<telar_language>.yml).
  To use your own intro text, delete the line that follows and write
  it here in markdown.

  ES: El contenido predeterminado de esta página viene del paquete
  de idioma (lang.pages.glossary_intro en _data/languages/<telar_language>.yml).
  Para usar tu propio texto introductorio, borra la línea que sigue
  y escríbelo aquí en markdown.
-->

{{ lang.pages.glossary_intro }}"""

OBJECTS_MD_NEW_BODY = """{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
<!--
  EN: Default content for this page comes from your language pack
  (lang.pages.objects_count in _data/languages/<telar_language>.yml).
  The {count} placeholder is filled in automatically. To use your
  own intro text, delete the two lines that follow and write it
  here in markdown.

  ES: El contenido predeterminado de esta página viene del paquete
  de idioma (lang.pages.objects_count en _data/languages/<telar_language>.yml).
  El marcador {count} se rellena automáticamente. Para usar tu propio
  texto introductorio, borra las dos líneas que siguen y escríbelo
  aquí en markdown.
-->

{% assign objects_intro = lang.pages.objects_count | replace: \"{count}\", site.objects.size %}
{{ objects_intro }}"""

ABOUT_MD_NEW_BODY = """# About Telar

Telar (Spanish for "loom") is a static site generator built on Jekyll for digital storytelling and publishing small digital collections. It weaves IIIF images, video, audio, narrative text, and contextual layers into interactive visual exhibitions, with a card-stacking architecture, fluid scroll navigation, deep linking, and shareable URLs. It follows minimal computing principles: plain text authoring, static generation, and free hosting on GitHub Pages.

<div class="alert alert-info" role="alert">
<strong>Customize this page</strong><br>
You can edit this about page by modifying the <code>telar-content/texts/pages/about.md</code> file in your repository. Add your own project description, credits, and acknowledgments to personalize your site. To localize for other languages, create a sister file alongside this one (for example, <code>acerca.md</code> for Spanish) with frontmatter <code>localized_for: about.md</code> and <code>language: &lt;lang_code&gt;</code>; the build picks the file matching <code>telar_language</code>.
</div>

## Credits

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Natalie Cobo, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Pedagogy Lab, and [Neogranadina](https://neogranadina.org).

We gratefully acknowledge the support of the [Caribbean Digital Scholarship Collective](https://cdscollective.org), the [Center for Innovative Teaching, Research, and Learning (CITRAL)](https://citral.ucsb.edu/home) at the University of California, Santa Barbara, the [UCSB Library](https://library.ucsb.edu), the [Routes of Enslavement in the Americas University of California MRPI](https://www.humanities.uci.edu/routes-enslavement-americas), and the [Department of History of The University of Texas at Austin](https://liberalarts.utexas.edu/history/).

For more information, visit the [Telar GitHub repository](https://github.com/UCSB-AMPLab/telar) or the [Telar Compositor](https://compositor.telar.org).

Telar is built with:

- [Jekyll](https://jekyllrb.com/) — Static site generator
- [Tify](https://tify.rocks/) — IIIF viewer
- [Bootstrap 5](https://getbootstrap.com/) — CSS framework
- [libvips](https://www.libvips.org/) — IIIF tile generator

It is based on [Paisajes Coloniales](https://paisajescoloniales.com/), and inspired by:

- [Wax](https://minicomp.github.io/wax/) — Minimal computing for digital exhibitions
- [CollectionBuilder](https://collectionbuilder.github.io/) — Static digital collections"""

# Full file contents for the new acerca.md, created when telar_language is es,
# about.md is unchanged from v1.2.1, and acerca.md does not already exist
# (see _create_acerca_for_es_with_default_about for the gating logic).
ACERCA_MD_FULL = """---
title: Acerca de Telar
localized_for: about.md
language: es
---

# Acerca de Telar

Telar es un generador de sitios estáticos construido sobre Jekyll, para crear narrativas digitales y publicar pequeñas colecciones en línea. Combina imágenes IIIF, video, audio, texto narrativo y capas de contexto en exhibiciones visuales interactivas, con una arquitectura de tarjetas apiladas, navegación fluida por desplazamiento, enlaces directos a pasos específicos y URLs compartibles. Sigue los principios de computación mínima: autoría en texto plano, generación estática y alojamiento gratuito en GitHub Pages.

<div class="alert alert-info" role="alert">
<strong>Personaliza esta página</strong><br>
Para editar esta página, modifica el archivo <code>telar-content/texts/pages/acerca.md</code> en tu repositorio. Agrega tu propia descripción del proyecto, créditos y agradecimientos para personalizar tu sitio. Esta es la versión en español de <code>about.md</code>; el frontmatter <code>localized_for: about.md</code> y <code>language: es</code> indica al build cuál archivo usar según <code>telar_language</code>.
</div>

## Créditos

Telar es desarrollado por Adelaida Ávila, Juan Cobo Betancourt, Natalie Cobo, Santiago Muñoz, y estudiantes y académicos del [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), del UT Archives, Mapping, and Pedagogy Lab y de [Neogranadina](https://neogranadina.org).

Agradecemos el apoyo del [Caribbean Digital Scholarship Collective](https://cdscollective.org), del [Center for Innovative Teaching, Research, and Learning (CITRAL)](https://citral.ucsb.edu/home) de la University of California, Santa Barbara, de la [UCSB Library](https://library.ucsb.edu), del [Routes of Enslavement in the Americas University of California MRPI](https://www.humanities.uci.edu/routes-enslavement-americas) y del [Department of History of The University of Texas at Austin](https://liberalarts.utexas.edu/history/).

Para más información, visita el [repositorio de Telar en GitHub](https://github.com/UCSB-AMPLab/telar) o el [Telar Compositor](https://compositor.telar.org).

Telar está construido con:

- [Jekyll](https://jekyllrb.com/) — generador de sitios estáticos
- [Tify](https://tify.rocks/) — visor IIIF
- [Bootstrap 5](https://getbootstrap.com/) — marco CSS
- [libvips](https://www.libvips.org/) — generador de teselas IIIF

Está basado en [Paisajes Coloniales](https://paisajescoloniales.com/), y se inspira en:

- [Wax](https://minicomp.github.io/wax/) — computación mínima para exhibiciones digitales
- [CollectionBuilder](https://collectionbuilder.github.io/) — colecciones digitales estáticas
"""


# Frontmatter pattern for parsing user .md files
FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.DOTALL)


def _hash_normalized(text: str) -> str:
    """SHA-256 of text after whitespace/line-ending normalisation.

    Used as the modification-detection mechanism for conditional content
    replacement: the migration computes the user's body hash, compares it
    against the hash of the known v1.2.1 default body, and only replaces
    when they match. Any user edit (text change, added/removed lines,
    even mid-line whitespace) bumps the hash and the file is preserved.
    """
    normalized = text.replace('\r\n', '\n').strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


class Migration121to130(BaseMigration):
    """Migration from v1.2.1 to v1.3.0 — i18n hygiene + sister-file localization."""

    from_version = "1.2.1"
    to_version = "1.3.0"
    description = "i18n hygiene: wire existing lang keys, sister-file localization, multimedia welcome update"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[str]:
        changes: List[str] = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Conditional user-content updates
        print("  Phase 2: Updating user content (only where unchanged from v1.2.1)...")
        changes.extend(self._cleanup_index_frontmatter())
        changes.extend(self._replace_body_if_default(
            'index.md', INDEX_MD_V121_BODY, INDEX_MD_NEW_BODY, 'homepage welcome'
        ))
        changes.extend(self._replace_body_if_default(
            'pages/glossary.md', GLOSSARY_MD_V121_BODY, GLOSSARY_MD_NEW_BODY, 'glossary intro'
        ))
        changes.extend(self._replace_body_if_default(
            'pages/objects.md', OBJECTS_MD_V121_BODY, OBJECTS_MD_NEW_BODY, 'objects intro'
        ))
        # acerca.md create runs BEFORE about.md replacement so the gating check
        # sees the user's actual about.md (not the freshly-written v1.3.0 body)
        changes.extend(self._create_acerca_for_es_with_default_about())
        changes.extend(self._replace_body_if_default(
            'telar-content/texts/pages/about.md',
            ABOUT_MD_V121_BODY, ABOUT_MD_NEW_BODY,
            'about page'
        ))

        # Phase 3: Version bump
        print("  Phase 3: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("1.3.0", today):
            changes.append(f"Updated _config.yml: version 1.3.0 ({today})")

        return changes

    # ------------------------------------------------------------------ #
    # Phase 1: framework file fetch
    # ------------------------------------------------------------------ #

    def _update_framework_files(self) -> List[str]:
        """Fetch updated framework files from GitHub main."""
        changes: List[str] = []

        framework_files = {
            '_layouts/index.html': 'Homepage layout (i18n fall-through + empty_states + JS i18n)',
            '_layouts/objects-index.html': 'Objects index layout (errors + empty_states wiring)',
            '_layouts/glossary-index.html': 'Glossary index layout (empty_states wiring)',
            '_includes/iiif-url-warning.html': 'IIIF URL warning (now references lang.errors.iiif_mismatch)',
            '_data/languages/en.yml': 'English language pack (new keys: glossary_intro, index_page.welcome, etc.)',
            '_data/languages/es.yml': 'Spanish language pack',
            'scripts/generate_collections.py': 'Sister-file localization for pages/ (about.md/acerca.md)',
            'README.md': 'README (v1.3.0 badges and beta notice)',
            'CHANGELOG.md': 'CHANGELOG (v1.3.0 release notes)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} — {description}")
            else:
                changes.append(f"⚠️  Could not fetch {file_path} from GitHub (network or release timing). Update it manually.")

        return changes

    # ------------------------------------------------------------------ #
    # Phase 2: conditional user-content cleanup
    # ------------------------------------------------------------------ #

    def _split_frontmatter(self, content: str) -> Optional[Tuple[str, str]]:
        """Return (frontmatter_text, body) or None if no frontmatter found."""
        match = FRONTMATTER_RE.match(content)
        if not match:
            return None
        return match.group(1), match.group(2)

    def _normalize(self, text: str) -> str:
        """Whitespace/line-ending normalisation. Used by the SHA-256 hash
        helper at module scope (`_hash_normalized`). Kept as a method too
        for tests that exercise the normalisation directly without going
        through the hashing layer."""
        return text.replace('\r\n', '\n').strip()

    def _cleanup_index_frontmatter(self) -> List[str]:
        """Remove stories_heading / objects_heading / objects_intro from index.md
        frontmatter when their values match v1.2.1 defaults exactly. Preserve
        any other frontmatter and any user customisations of these keys."""
        rel_path = 'index.md'
        content = self._read_file(rel_path)
        if content is None:
            return []

        parts = self._split_frontmatter(content)
        if parts is None:
            return [f"⚠️  {rel_path}: no frontmatter found, skipping frontmatter cleanup"]

        frontmatter_text, body = parts

        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError as e:
            return [f"⚠️  {rel_path}: could not parse frontmatter ({e}), skipping cleanup"]

        if not isinstance(frontmatter, dict):
            return []

        removed: List[str] = []
        for key, default_value in INDEX_MD_V121_FRONTMATTER_DEFAULTS.items():
            if key in frontmatter and frontmatter[key] == default_value:
                del frontmatter[key]
                removed.append(key)

        if not removed:
            return []

        # Re-serialise frontmatter, preserving key order best-effort
        new_frontmatter = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
        new_content = f"---\n{new_frontmatter}\n---\n\n{body.lstrip()}"
        self._write_file(rel_path, new_content)
        return [f"Removed stale frontmatter keys from {rel_path}: {', '.join(removed)} (matched v1.2.1 defaults)"]

    def _replace_body_if_default(
        self, rel_path: str, expected_v121_body: str, new_body: str, label: str
    ) -> List[str]:
        """Replace the body of `rel_path` with `new_body` if the current body
        matches `expected_v121_body` exactly. Frontmatter is preserved.

        For files without frontmatter (e.g. an index.md whose frontmatter we
        already cleaned away accidentally), treats the whole file as body.
        """
        content = self._read_file(rel_path)
        if content is None:
            return [f"⚠️  {rel_path}: file missing; skipping {label} update"]

        parts = self._split_frontmatter(content)
        if parts is None:
            # No frontmatter: compare whole file
            current_body = content
            frontmatter_text = None
        else:
            frontmatter_text, current_body = parts

        # SHA-256 hash check: only replace if the user's body is byte-for-byte
        # identical to the v1.2.1 default (after whitespace normalisation).
        # Any modification at all preserves the user's file unchanged.
        if _hash_normalized(current_body) != _hash_normalized(expected_v121_body):
            return [f"Skipped {label} update in {rel_path} (user has customised it; hash differs from v1.2.1 default)"]

        # Compose new file content
        if frontmatter_text is None:
            new_content = new_body + ('\n' if not new_body.endswith('\n') else '')
        else:
            new_content = f"---\n{frontmatter_text}\n---\n\n{new_body}\n"
        self._write_file(rel_path, new_content)
        return [f"Updated {label} in {rel_path} (matched v1.2.1 default; replaced with v1.3.0 lang-key template)"]

    def _create_acerca_for_es_with_default_about(self) -> List[str]:
        """Create telar-content/texts/pages/acerca.md for ES sites whose
        about.md is the v1.2.1 default. Three guards:

          - site has telar_language: es
          - acerca.md doesn't already exist (don't overwrite user's own)
          - about.md exists AND hashes to the v1.2.1 default (don't shadow
            a customised about.md with our generic Spanish content)

        Without this gating an ES site that customised about.md would
        suddenly start showing our default Spanish acerca.md at build time
        (sister-file routing wins when active language matches), throwing
        away the user's customisation. With the gating, customised
        about.md → no acerca created → the user's content keeps rendering."""
        # Guard 1: language must be es
        if self._detect_language() != 'es':
            return []

        acerca_path = 'telar-content/texts/pages/acerca.md'

        # Guard 2: acerca.md must not already exist
        if self._file_exists(acerca_path):
            return [f"Skipped {acerca_path} creation (file already exists)"]

        # Guard 3: about.md must exist AND match v1.2.1 default
        about_path = 'telar-content/texts/pages/about.md'
        about_content = self._read_file(about_path)
        if about_content is None:
            return [f"Skipped {acerca_path} creation (no about.md to mirror)"]

        parts = self._split_frontmatter(about_content)
        about_body = parts[1] if parts else about_content

        if _hash_normalized(about_body) != _hash_normalized(ABOUT_MD_V121_BODY):
            return [f"Skipped {acerca_path} creation (your about.md is customised; sister file would shadow it at build time)"]

        # All guards passed: create acerca.md with default Spanish content
        self._write_file(acerca_path, ACERCA_MD_FULL)
        return [f"Created {acerca_path} (telar_language=es and about.md was unchanged from v1.2.1; site will now render Spanish content at /about/)"]

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**i18n hygiene update applied — most users need to take no action.**

This release wires up Telar's existing language packs in places that previously hardcoded English (homepage empty states, IIIF URL warning, objects-index error messages, JS thumbnail load fallbacks). It also moves the homepage welcome, glossary intro, objects intro, and about page contents into the language pack so Spanish-speaking site owners with `telar_language: es` get sensible defaults.

The migration changed your user-content files **only when a SHA-256 hash check confirmed the file was byte-for-byte identical to the v1.2.1 default**. If you customised any of those pages (welcome paragraph, about description, glossary or objects intros) — even with whitespace edits — the hash differs and your file is preserved untouched.

A new sister-file convention now localizes the about page: a file named `acerca.md` next to `about.md` in `telar-content/texts/pages/`, carrying frontmatter `localized_for: about.md` and `language: es`, is picked up automatically when `telar_language: es`. For sites with `telar_language: es` whose `about.md` is unchanged from the v1.2.1 default, this migration creates `acerca.md` with the default Spanish content automatically. For sites that customised their `about.md`, the migration skips the create — otherwise the new sister file would shadow your customisation at build time. To add another language, create a sister with `language: <code>` (e.g. `language: fr`).''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Actualización de i18n hygiene aplicada — para la mayoría de usuarios no se requieren más pasos.**

Esta versión cablea los paquetes de idioma de Telar en lugares que antes tenían texto en inglés (estados vacíos de la página de inicio, alerta de IIIF, mensajes de error en el índice de objetos, fallbacks de carga de miniaturas en JS). También mueve el contenido de bienvenida, la introducción del glosario, la introducción de objetos y la página acerca al paquete de idioma, para que los sitios con `telar_language: es` muestren valores por defecto en español.

La migración modificó tus archivos de contenido **solo cuando un hash SHA-256 confirmó que el archivo era byte-por-byte idéntico al default de v1.2.1**. Si personalizaste cualquiera de esas páginas (bienvenida, descripción de "Acerca de", introducciones de glosario u objetos) — incluso con cambios de espacios en blanco — el hash difiere y tu archivo se preserva sin tocarlo.

Una nueva convención de "archivo hermano" localiza la página de "Acerca de": un archivo `acerca.md` junto a `about.md` en `telar-content/texts/pages/`, con `localized_for: about.md` y `language: es` en el frontmatter, se usa automáticamente cuando `telar_language: es`. Para sitios con `telar_language: es` cuyo `about.md` no se haya modificado desde el default de v1.2.1, esta migración crea `acerca.md` automáticamente con el contenido español por defecto. Para sitios que personalizaron su `about.md`, la migración no lo crea — si lo hiciera, el nuevo archivo hermano taparía tu personalización al construir el sitio. Para agregar otro idioma, crea un hermano con `language: <código>` (por ejemplo `language: fr`).''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
