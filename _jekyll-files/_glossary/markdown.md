---
term_id: markdown
title: "Markdown"
layout: glossary
---

<p>Markdown is a lightweight markup language created in 2004 by <a href="https://daringfireball.net/">John Gruber</a>, in collaboration with <a href="https://en.wikipedia.org/wiki/Aaron_Swartz">Aaron Swartz</a>, with idea that plain text formatting should be readable as-is, even before being converted to HTML or other output formats. Unlike word processors that hide formatting codes or markup languages like HTML that clutter text with tags, Markdown uses simple, intuitive syntax that mimics how people naturally emphasize text in plain-text emails: asterisks for emphasis (<code>*italic*</code> or <code>**bold**</code>), hash marks for headings (<code># Heading</code>), brackets for links (<code>[text](url)</code>), and dashes for lists.</p>
<p>The original design goal was to make writing for the web as easy as writing an email. Gruber's <a href="https://daringfireball.net/projects/markdown/">original Markdown specification</a> intentionally left some details ambiguous to keep the syntax simple and flexible. This led to multiple "flavors" of Markdown emerging over the years—<a href="https://commonmark.org/">CommonMark</a> (a rigorously specified standard), <a href="https://github.github.com/gfm/">GitHub Flavored Markdown</a> (adding tables, task lists, and code syntax highlighting), <a href="https://python-markdown.github.io/">Python-Markdown</a> (with extensible plugins), and others. Despite variations, they all share the same core syntax and remain readable as plain text.</p>
<p>Telar uses <a href="https://python-markdown.github.io/">Python-Markdown</a> with several extensions enabled: <a href="https://python-markdown.github.io/extensions/footnotes/">footnotes</a> for scholarly citations, <a href="https://python-markdown.github.io/extensions/tables/">tables</a> for structured data, <a href="https://python-markdown.github.io/extensions/definition_lists/">definition lists</a>, and more. This means you can write panel content in a simple text editor, using familiar plain-text conventions, and Jekyll automatically converts it to properly formatted HTML during the site build process.</p>
<p><strong>Learn more:</strong><br />
- <a href="https://daringfireball.net/projects/markdown/">The original Markdown specification by John Gruber</a><br />
- <a href="https://commonmark.org/">CommonMark specification</a><br />
- <a href="https://en.wikipedia.org/wiki/Markdown">Markdown on Wikipedia</a><br />
- <a href="https://python-markdown.github.io/">Python-Markdown documentation</a><br />
- <a href="https://github.github.com/gfm/">GitHub Flavored Markdown specification</a><br />
- <a href="https://www.markdownguide.org/">Markdown Guide - comprehensive reference</a></p>
