---
layout: glossary-index
title: Glossary
permalink: /glossary/
---

{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
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

{{ lang.pages.glossary_intro }}
