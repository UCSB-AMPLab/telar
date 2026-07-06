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
 * A second copy of this loading logic (URLs, version pin, delimiter list,
 * trust callback) lives in _includes/katex.html, used by the default layout
 * for non-story pages. Any version bump here must also be made there.
 *
 * Classic script, not a module — loaded by a plain <script> tag from
 * _layouts/story.html, which also sets window.telarKatexConfig immediately
 * beforehand with the Liquid-dependent has_latex flag.
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
        // Load KaTeX CSS
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.css';
        document.head.appendChild(link);

        // Load KaTeX scripts sequentially
        var scripts = [
          'https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.js',
          'https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/contrib/auto-render.min.js',
          'https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/contrib/mhchem.min.js'
        ];

        function loadNext(i) {
          if (i >= scripts.length) {
            var katexDelimiters = [
              { left: "$$", right: "$$", display: true },
              { left: "$", right: "$", display: false },
              { left: "\\(", right: "\\)", display: false },
              { left: "\\[", right: "\\]", display: true },
              { left: "\\begin{align}", right: "\\end{align}", display: true },
              { left: "\\begin{align*}", right: "\\end{align*}", display: true },
              { left: "\\begin{cases}", right: "\\end{cases}", display: true },
              { left: "\\begin{pmatrix}", right: "\\end{pmatrix}", display: true },
              { left: "\\begin{bmatrix}", right: "\\end{bmatrix}", display: true },
              { left: "\\begin{equation}", right: "\\end{equation}", display: true },
              { left: "\\begin{equation*}", right: "\\end{equation*}", display: true }
            ];
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
