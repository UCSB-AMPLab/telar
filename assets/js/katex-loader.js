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
 * is published; story-unlock.js polls for that global (renderLatexWhenReady)
 * after decryption and calls it on the newly-injected step markup, so the
 * loader racing the unlock is expected and already handled downstream.
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
 * @version v1.6.0
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

        // Load KaTeX CSS
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = config.cssUrl;
        document.head.appendChild(link);

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
            // Render LaTeX in step text already in the DOM
            document.querySelectorAll('.story-step').forEach(function(el) {
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
