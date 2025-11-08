---
term_id: markdown
title: "Markdown"
layout: glossary
---

Markdown is a lightweight markup language created in 2004 by [John Gruber](https://daringfireball.net/), in collaboration with [Aaron Swartz](https://en.wikipedia.org/wiki/Aaron_Swartz), with idea that plain text formatting should be readable as-is, even before being converted to HTML or other output formats. Unlike word processors that hide formatting codes or markup languages like HTML that clutter text with tags, Markdown uses simple, intuitive syntax that mimics how people naturally emphasize text in plain-text emails: asterisks for emphasis (`*italic*` or `**bold**`), hash marks for headings (`# Heading`), brackets for links (`[text](url)`), and dashes for lists.

The original design goal was to make writing for the web as easy as writing an email. Gruber's [original Markdown specification](https://daringfireball.net/projects/markdown/) intentionally left some details ambiguous to keep the syntax simple and flexible. This led to multiple "flavors" of Markdown emerging over the years—[CommonMark](https://commonmark.org/) (a rigorously specified standard), [GitHub Flavored Markdown](https://github.github.com/gfm/) (adding tables, task lists, and code syntax highlighting), [Python-Markdown](https://python-markdown.github.io/) (with extensible plugins), and others. Despite variations, they all share the same core syntax and remain readable as plain text.

Telar uses [Python-Markdown](https://python-markdown.github.io/) with several extensions enabled: [footnotes](https://python-markdown.github.io/extensions/footnotes/) for scholarly citations, [tables](https://python-markdown.github.io/extensions/tables/) for structured data, [definition lists](https://python-markdown.github.io/extensions/definition_lists/), and more. This means you can write panel content in a simple text editor, using familiar plain-text conventions, and Jekyll automatically converts it to properly formatted HTML during the site build process.

**Learn more:**
- [The original Markdown specification by John Gruber](https://daringfireball.net/projects/markdown/)
- [CommonMark specification](https://commonmark.org/)
- [Markdown on Wikipedia](https://en.wikipedia.org/wiki/Markdown)
- [Python-Markdown documentation](https://python-markdown.github.io/)
- [GitHub Flavored Markdown specification](https://github.github.com/gfm/)
- [Markdown Guide - comprehensive reference](https://www.markdownguide.org/)
