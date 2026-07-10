/**
 * Telar — Christmas Tree Mode warning decorator.
 *
 * "Christmas tree mode" is a development flag (site.development-features.
 * christmas_tree_mode) that scripts/telar/processors/stories.py uses to
 * inject synthetic viewer/panel/glossary warnings into every story, for
 * exercising the warning UI without hand-authoring broken content. This
 * script is the other half of that mode on the client: once the flag is on,
 * it prefixes every rendered warning heading with a small tree emoji, so the
 * synthetic warnings are visually obvious as fixtures rather than mistaken
 * for real authoring problems.
 *
 * It targets every `.alert strong` on the page — the story-config warning
 * heading and each per-step warning's bold step-number lead-in (see the
 * story-intro markup in _layouts/story.html and its `metadata.viewer_warnings`
 * loop) — and skips any heading that already carries the emoji, so repeat runs
 * (e.g. after story-unlock.js injects a decrypted step pool) stay idempotent.
 *
 * Classic script, not a module — loaded by a plain <script> tag from
 * _layouts/story.html, which sets `window.christmasTreeMode` from the
 * Liquid-evaluated site config immediately beforehand.
 *
 * @version v1.6.0
 */

// If Christmas Tree Mode is active, add 🎄 to all warning headings
if (window.christmasTreeMode) {
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.alert strong').forEach(function(heading) {
      if (!heading.textContent.includes('🎄')) {
        heading.textContent = '🎄 ' + heading.textContent;
      }
    });
  });
}
