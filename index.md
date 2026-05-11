---
layout: index
title: Home
---

{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
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

{{ lang.index_page.welcome | markdownify }}
