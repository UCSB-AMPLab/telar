/**
 * Telar — lazy KaTeX loader for story pages.
 *
 * Story pages don't load KaTeX by default — most stories carry no LaTeX, and
 * the library (CSS + three scripts) is pure overhead for them. This script
 * decides, once per page load, whether the current story needs it and pulls
 * it in from the CDN only when it does.
 *
 * has_latex detection — two sources, either is enough to trigger a load.
 * Open stories publish it on window.storyData.steps[0]._metadata.has_latex
 * once telar-story.js has parsed the step data. Protected (encrypted)
 * stories carry no readable steps before unlock, so their flag rides
 * page.has_latex frontmatter instead, stamped at generation time and handed
 * in here via window.telarKatexConfig — see the include below for how that
 * config is built. The check runs on a zero-delay setTimeout after
 * DOMContentLoaded so window.storyData has had a tick to populate.
 *
 * Protected-story path — this loader does not wait for the unlock event. It
 * loads KaTeX (or not) based on page.has_latex alone, in parallel with the
 * user entering their key. Once the CDN scripts resolve, window.telarRenderLatex
 * is published and every step and text card on the page is rendered. The unlock
 * renders the injected step markup itself when KaTeX is already there, before
 * the cards are cloned from it; when KaTeX arrives later, the cards exist and
 * this loader renders them with the step pool.
 *
 * CDN URLs, version pin, and the delimiter list come from _data/katex.yml,
 * the single source shared with _includes/katex.html (used by the default
 * layout for non-story pages) — story.html jsonifies that data into
 * window.telarKatexConfig (cssUrl, urls, delimiters) below. To bump the
 * KaTeX version, edit _data/katex.yml only.
 *
 * The trust callback (which \href URL schemes are permitted) is logic, not
 * data, so it stays hand-written here and in katex.html — the two copies
 * are identical; keep them in sync if the policy changes.
 *
 * Classic script, not a module — loaded by a plain <script> tag from
 * _layouts/story.html, which also sets window.telarKatexConfig immediately
 * beforehand with the Liquid-dependent has_latex flag plus the CDN/delimiter
 * config.
 *
 * The stylesheet arrives as an @import inside a <style>, not as a <link>,
 * because a <link rel="stylesheet"> is unlayered and an unlayered declaration
 * outranks every layered one whatever the order or specificity. Linked that
 * way, KaTeX's own .katex font-size and .katex-display margin beat
 * _sass/_latex.scss, which sits in @layer telar-components. @import ...
 * layer() is the only way to put a remote stylesheet in a layer; there is no
 * layer attribute for <link>. _includes/katex.html does the same.
 *
 * @version v1.8.0
 */

document.addEventListener("DOMContentLoaded", function() {
  // Check after storyData is available
  setTimeout(function() {
    var config = window.telarKatexConfig || {};
    // Protected pages carry an envelope (no readable steps), so their
    // LaTeX flag rides frontmatter, stamped at generation time.
    var pageHasLatex = !!config.hasLatex;
    var metaHasLatex = false;
    if (window.storyData && window.storyData.steps) {
      var meta = window.storyData.steps[0];
      metaHasLatex = !!(meta && meta._metadata && meta.has_latex);
    }
      if (pageHasLatex || metaHasLatex) {
        // Fail-safe: if story.html didn't hand us the CDN config (e.g. an
        // older build, or window.telarKatexConfig got clobbered), warn loudly
        // rather than silently rendering no LaTeX — silent-blank is the
        // failure mode this codebase documents and avoids elsewhere.
        if (!config.urls) {
          console.warn('Telar: KaTeX config missing (window.telarKatexConfig.urls) — LaTeX will not be loaded on this page.');
          return;
        }

        // Load KaTeX CSS into the third-party layer (see the note above).
        var css = document.createElement('style');
        css.textContent = '@import url("' + config.cssUrl + '") layer(third-party);';
        document.head.appendChild(css);

        // Load KaTeX scripts sequentially
        var scripts = config.urls;

        function loadNext(i) {
          if (i >= scripts.length) {
            var katexDelimiters = config.delimiters;
            window.telarRenderLatex = function(element) {
              if (typeof renderMathInElement === 'function') {
                renderMathInElement(element, {
                  delimiters: katexDelimiters,
                  throwOnError: false,
                  // Permit \href only for safe URL schemes; other trust-gated
                  // commands render as literal text.
                  trust: function (ctx) { return ctx.command === '\\href' && /^(https?:|mailto:)/.test(ctx.url); }
                });
              }
            };
            // Render LaTeX in the step text already in the DOM: the hidden
            // step pool, and the text cards the story has already built from
            // it. Text cards are built once, when the story starts, which for
            // a protected story is the moment it is unlocked; KaTeX arriving
            // after that reaches them here or not at all. Title cards are
            // plain text and are left alone.
            document.querySelectorAll('.story-step, .text-card').forEach(function(el) {
              window.telarRenderLatex(el);
            });
            return;
          }
          var s = document.createElement('script');
          s.src = scripts[i];
          s.onload = function() { loadNext(i + 1); };
          document.head.appendChild(s);
        }
        loadNext(0);
      }
  }, 0);
});
