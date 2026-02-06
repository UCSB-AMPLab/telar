# Telar

![Version](https://img.shields.io/badge/version-0.8.0--beta-orange) ![License](https://img.shields.io/badge/license-MIT-blue)

**[Versión en español abajo](#español)** | **[English version](#telar)**

A minimal-computing framework for creating layered IIIF visual narratives for digital scholarship, public exhibitions, community storytelling, and classroom projects.

---

**[Full Documentation](https://telar.org/docs)** | **[Example Site](https://ampl.clair.ucsb.edu/telar)** | **[Report Issues](https://github.com/UCSB-AMPLab/telar/issues)**

---

> **⚠️ Beta Release - v0.8.0-beta**
> This is a beta release for testing and feedback. For detailed documentation, visit **[telar.org/docs](https://telar.org/docs)**.

> **Warning:** If upgrading from v0.3.4 or earlier, see the [Upgrading Telar Guide](https://telar.org/docs/2-workflows/3-upgrading/) for instructions.

## Overview

Telar (Spanish for "loom") is a static site generator built on Jekyll that weaves together IIIF images, narrative text, and layered contextual information into interactive visual narrative exhibitions. It follows minimal computing principles: plain text authoring, static generation, and sustainable hosting.

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

We gratefully acknowledge the support of the [Caribbean Digital Scholarship Collective](https://cdscollective.org), the [Center for Innovative Teaching, Research, and Learning (CITRAL)](https://citral.ucsb.edu/home) at the University of California, Santa Barbara, the [UCSB Library](https://library.ucsb.edu), the [Routes of Enslavement in the Americas University of California MRPI](https://www.humanities.uci.edu/routes-enslavement-americas), and the [Department of History of The University of Texas at Austin](https://liberalarts.utexas.edu/history/).

## Key Features

- **IIIF integration**: Support for both local images (auto-generated tiles) and external IIIF resources with automatic metadata extraction
- **Scrollytelling**: Discrete step-based scrolling with support for multiple IIIF objects in a single story - each object preloaded in its own viewer card
- **Interactive widgets**: Carousel, tabs, and accordion components for rich content presentation
- **Layered panels**: Progressive disclosure with three content layers plus glossary auto-linking
- **Multilingual UI**: Complete interface support for English and Spanish
- **Objects gallery**: Browsable object grid with detail pages
- **Minimal computing**: Plain text, static generation, GitHub Pages hosting

---

## Quick Start

**For comprehensive step-by-step guides, see the [full documentation site](https://telar.org/docs).** This Quick Start provides the essential steps to get your site running—detailed workflows and advanced topics are covered in the docs.

### Before You Begin

Plan your narrative structure before building. Sketch out your stories, identify key moments, choose anchor images, and decide what information belongs in brief answers versus deeper layers. Browse the [example site](https://ampl.clair.ucsb.edu/telar) for inspiration.

### Setup Steps

1. **Create your repository**
   - Click the green "Use this template" button above
   - Name your repository and create it

2. **Choose your content management approach**
   - **Google Sheets** (recommended): Use [our template](https://bit.ly/telar-template) to manage content via spreadsheet
   - **CSV files**: Edit CSV files directly in your repository

3. **Add your content**
   - Upload images to `components/images/` or use IIIF manifests from institutions
   - Create markdown files in `components/texts/stories/` for your narrative text
   - Configure your objects and stories in Google Sheets or CSV files

4. **Enable GitHub Pages**
   - Go to repository **Settings** → **Pages**
   - Set source to **GitHub Actions**
   - Save and wait 2-5 minutes for deployment

5. **Configure and customize**
   - Edit `_config.yml` to set your site title and theme
   - For Google Sheets: Add your sheet URLs to the `google_sheets` section
   - View your site at `https://[username].github.io/[repository]/`

---

## Documentation

For comprehensive guides and references, visit **[telar.org/docs](https://telar.org/docs)**:

- **Workflows**: [GitHub Web Interface](https://telar.org/docs/2-workflows/1-github-web), [Local Development](https://telar.org/docs/2-workflows/2-local-dev), [Upgrading](https://telar.org/docs/2-workflows/3-upgrading/)
- **Content Structure**: [Organizing your content](https://telar.org/docs/3-content-structure)
- **IIIF Integration**: [Working with images](https://telar.org/docs/4-iiif-integration)
- **Configuration**: [Site settings and themes](https://telar.org/docs/5-configuration)
- **Customization**: [Themes and styling](https://telar.org/docs/6-customization)
- **Reference**: [GitHub Actions](https://telar.org/docs/7-reference/1-github-actions), [CSV Schemas](https://telar.org/docs/7-reference/2-csv-schemas)

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

**Note:** This license covers the Telar framework code and documentation. It does NOT cover user-created content (stories, images, object metadata, narrative text) which remains the property of content creators and may have separate licenses.

## Credits

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

Telar is built with:
- [Jekyll](https://jekyllrb.com/) - Static site generator
- [UniversalViewer](https://universalviewer.io/) - IIIF viewer
- [Bootstrap 5](https://getbootstrap.com/) - CSS framework
- [iiif-static](https://github.com/bodleian/iiif-static-choices) - IIIF tile generator

It is based on [Paisajes Coloniales](https://paisajescoloniales.com/), and inspired by:
- [Wax](https://minicomp.github.io/wax/) - Minimal computing for digital exhibitions
- [CollectionBuilder](https://collectionbuilder.github.io/) - Static digital collections

## Support

- **Documentation:** [telar.org/docs](https://telar.org/docs)
- **Report Issues:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)
- **Example Site:** [ampl.clair.ucsb.edu/telar](https://ampl.clair.ucsb.edu/telar)

---
---

# Español

![Versión](https://img.shields.io/badge/versi%C3%B3n-0.8.0--beta-orange) ![Licencia](https://img.shields.io/badge/licencia-MIT-blue)

**[Versión en español](#español)** | **[English version above](#telar)**

Un marco de computación mínima para crear narrativas visuales con capas de texto e imágenes IIIF para humanidades digitales, exposiciones públicas y contextos educativos y comunitarios.

---

**[Documentación completa](https://telar.org/guia)** | **[Sitio de ejemplo](https://ampl.clair.ucsb.edu/telar)** | **[Reportar problemas](https://github.com/UCSB-AMPLab/telar/issues)**

---

> **⚠️ Versión Beta - v0.8.0-beta**
> Esta es una versión beta para pruebas y retroalimentación. Para documentación detallada, visita **[telar.org/guia](https://telar.org/guia)**.

> **Advertencia:** Si estás actualizando desde v0.3.4 o anterior, consulta la [Guía de Actualización de Telar](https://telar.org/guia/flujos-de-trabajo/actualizacion/) para obtener instrucciones.

## Descripción general

Telar es un generador de sitios estáticos construido sobre Jekyll que entreteje imágenes IIIF, texto narrativo e información contextual en capas en exhibiciones narrativas visuales interactivas. Sigue los principios de computación mínima: autoría en texto plano, generación estática y alojamiento sostenible.

Telar es desarrollado por Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, y estudiantes e investigadores en el [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), el UT Archives, Mapping, and Preservation Lab, y [Neogranadina](https://neogranadina.org).

Agradecemos el apoyo del [Caribbean Digital Scholarship Collective](https://cdscollective.org), el [Center for Innovative Teaching, Research, and Learning (CITRAL)](https://citral.ucsb.edu/home) de la University of California, Santa Barbara, la [UCSB Library](https://library.ucsb.edu), el [Routes of Enslavement in the Americas University of California MRPI](https://www.humanities.uci.edu/routes-enslavement-americas), y el [Department of History of The University of Texas at Austin](https://liberalarts.utexas.edu/history/).

## Características principales

- **Integración IIIF**: Soporte para imágenes locales con teselas (*tiles*) generadas automáticamente y recursos IIIF externos con extracción automática de metadatos
- **Scrollytelling**: Desplazamiento basado en pasos discretos con soporte para múltiples objetos IIIF en una sola historia - cada objeto precargado en su propia tarjeta de visualización
- **Widgets interactivos**: Componentes de carrusel, pestañas y acordeón para presentar contenido de forma más rica
- **Paneles en capas**: Despliegue progresivo con tres capas de contenido más enlace automático del glosario
- **Interfaz multilingüe**: Soporte completo de interfaz para inglés y español
- **Galería de objetos**: Cuadrícula navegable de objetos con páginas de detalle
- **Computación mínima**: Texto plano, generación estática, alojamiento en GitHub Pages

---

## Inicio rápido

**Para guías paso a paso completas, consulta el [sitio de documentación completo](https://telar.org/guia).** Este inicio rápido proporciona los pasos esenciales para poner en marcha tu sitio—los flujos de trabajo detallados y temas avanzados están cubiertos en la documentación.

### Antes de comenzar

Planifica tu estructura narrativa antes de construir. Esboza tus historias, identifica momentos clave, elige imágenes ancla y decide qué información pertenece a respuestas breves versus capas más profundas. Explora el [sitio de ejemplo](https://ampl.clair.ucsb.edu/telar) para inspirarte.

### Pasos de configuración

1. **Crea tu repositorio**
   - Haz clic en el botón verde **Use this template** arriba
   - Nombra tu repositorio y créalo

2. **Elige tu enfoque de gestión de contenido**
   - **Google Sheets** (recomendado): Usa [nuestra plantilla](https://bit.ly/telar-template) para gestionar contenido vía hoja de cálculo
   - **Archivos CSV**: Edita archivos CSV directamente en tu repositorio

3. **Añade tu contenido**
   - Sube imágenes a `components/images/` o usa manifiestos IIIF de instituciones
   - Crea archivos markdown en `components/texts/stories/` para tu texto narrativo
   - Configura tus objetos e historias en Google Sheets o archivos CSV

4. **Habilita GitHub Pages**
   - Ve a **Settings** → **Pages** del repositorio
   - Establece la fuente como **GitHub Actions**
   - Guarda y espera 2-5 minutos para el despliegue

5. **Configura y personaliza**
   - Edita `_config.yml` para establecer el título y tema de tu sitio
   - Para Google Sheets: Añade las URLs de tus hojas a la sección `google_sheets`
   - Visualiza tu sitio en `https://[usuario].github.io/[repositorio]/`

---

## Documentación

Para guías y referencias completas, visita **[telar.org/guia](https://telar.org/guia)**:

- **Flujos de trabajo**: [Interfaz web de GitHub](https://telar.org/guia/flujos-de-trabajo/interfaz-web-github/), [Desarrollo local](https://telar.org/guia/flujos-de-trabajo/desarrollo-local/), [Actualizar](https://telar.org/guia/flujos-de-trabajo/actualizacion/)
- **Estructura de contenido**: [Organizar tu contenido](https://telar.org/guia/estructura-de-contenido/)
- **Integración IIIF**: [Trabajar con imágenes](https://telar.org/guia/integracion-iiif/)
- **Configuración**: [Ajustes del sitio y temas](https://telar.org/guia/configuracion/)
- **Personalización**: [Temas y estilos](https://telar.org/guia/personalizacion/)
- **Referencia**: [GitHub Actions](https://telar.org/guia/referencia/github-actions/), [Esquemas CSV](https://telar.org/guia/referencia/esquemas-csv/)

---

## Licencia

Licencia MIT - consulta el archivo [LICENSE](LICENSE) para más detalles.

**Nota:** Esta licencia cubre el código del marco Telar y la documentación. NO cubre el contenido creado por usuarios (historias, imágenes, metadatos de objetos, texto narrativo) que permanece como propiedad de los creadores de contenido y puede tener licencias separadas.

## Créditos

Telar es desarrollado por Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, y estudiantes e investigadores en el [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), el UT Archives, Mapping, and Preservation Lab, y [Neogranadina](https://neogranadina.org).

Telar está construido con:
- [Jekyll](https://jekyllrb.com/) - Generador de sitios estáticos
- [UniversalViewer](https://universalviewer.io/) - Visor IIIF
- [Bootstrap 5](https://getbootstrap.com/) - Marco CSS
- [iiif-static](https://github.com/bodleian/iiif-static-choices) - Generador de teselas IIIF

Está basado en [Paisajes Coloniales](https://paisajescoloniales.com/), e inspirado por:
- [Wax](https://minicomp.github.io/wax/) - Computación mínima para exhibiciones digitales
- [CollectionBuilder](https://collectionbuilder.github.io/) - Colecciones digitales estáticas

## Soporte

- **Documentación:** [telar.org/guia](https://telar.org/guia)
- **Reportar problemas:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)
- **Sitio de ejemplo:** [ampl.clair.ucsb.edu/telar](https://ampl.clair.ucsb.edu/telar)
