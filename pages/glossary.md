---
layout: glossary-index
title: Glossary
title_key: navigation.glossary
permalink: /glossary/
---

{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
<!--
  EN: Default content for this page comes from your language pack
  (lang.pages.glossary_intro, or lang.pages.glossary_intro_with_sources
  when your glossary has primary sources, in
  _data/languages/<telar_language>.yml). To use your own intro text,
  delete the line that follows and write it here in markdown.

  ES: El contenido predeterminado de esta página viene del paquete
  de idioma, en _data/languages/<telar_language>.yml: el texto de
  lang.pages.glossary_intro, o el de lang.pages.glossary_intro_with_sources
  si el glosario tiene fuentes primarias. Para usar tu propio texto
  introductorio, borra la línea que sigue y escríbelo aquí en markdown.
-->

{% include glossary-intro.html lang=lang %}
