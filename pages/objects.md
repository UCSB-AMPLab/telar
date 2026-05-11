---
layout: objects-index
title: Objects in the Stories
permalink: /objects/
---

{% assign lang = site.data.languages[site.telar_language] | default: site.data.languages.en %}
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

{% assign objects_intro = lang.pages.objects_count | replace: "{count}", site.objects.size %}
{{ objects_intro }}
