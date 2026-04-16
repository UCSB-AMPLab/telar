/**
 * Telar Story – Deep Linking
 *
 * This module manages URL fragment deep linking for the story page. URL
 * fragments encode the user's current navigation position — which step they
 * are on and which panel layer (if any) is open — so that a URL can be
 * copied and shared to send a recipient directly to a specific point in the
 * story.
 *
 * Fragment format:
 *   #s{step}             — step only (e.g. #s3 = third content step)
 *   #s{step}l{layer}     — step + open panel layer (e.g. #s3l1)
 *   #s{step}l{layer}g{n} — step + layer + nth glossary link open
 *   #s{step}l{layer}ps{n}— step + layer + nth primary source link
 *
 * Step numbers are 1-based in the fragment. state.currentIndex is 0-based.
 * state.steps[index].dataset.step is the CSV step number used by openPanel().
 *
 * All hash writes use history.replaceState exclusively — no pushState calls
 * anywhere. This means back/forward navigation exits the story
 * to the previous page rather than navigating between steps. scrollRestoration
 * is already set to 'manual' in scroll-engine.js, which prevents browser
 * scroll restoration from interfering.
 *
 * The _isScrollDrivenHashUpdate guard prevents feedback loops between the
 * hash writes here and any hashchange listener.
 *
 * @version v1.1.0
 */

import { state } from './state.js';
import { activateCard } from './card-pool.js';
import { openPanel } from './panels.js';

// ── Guard flag ────────────────────────────────────────────────────────────────

/**
 * Set true just before replaceState and cleared in a microtask after.
 * A hashchange listener should check this flag and return early if set
 * to prevent the write→hashchange→navigate feedback loop.
 */
let _isScrollDrivenHashUpdate = false;

// ── Fragment regex ────────────────────────────────────────────────────────────

/**
 * Matches all defined fragment formats:
 *   #s{step}
 *   #s{step}l{layer}
 *   #s{step}l{layer}g{n}
 *   #s{step}l{layer}ps{n}
 */
const FRAGMENT_RE = /^#s(\d+)(?:l(\d+)(?:(g|ps)(\d+))?)?$/;

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Parse a URL fragment string into a structured navigation target.
 *
 * Returns null for empty, missing, or malformed hashes — null means the
 * intro state (no step is targeted). No hash = intro.
 *
 * @param {string} hash - The URL fragment string (e.g. '#s3l1').
 * @returns {{ step: number, layer: number|null, subType: string|null, subN: number|null }|null}
 */
export function parseFragment(hash) {
  if (!hash || hash === '#') return null;
  const m = FRAGMENT_RE.exec(hash);
  if (!m) return null;
  return {
    step: parseInt(m[1], 10),              // 1-based step number
    layer: m[2] ? parseInt(m[2], 10) : null,
    subType: m[3] || null,                 // 'g' or 'ps'
    subN: m[4] ? parseInt(m[4], 10) : null,
  };
}

/**
 * Build fragment from current state and write via replaceState.
 *
 * Reads state.currentIndex (0-based). If < 0, removes the fragment entirely
 * (intro state). Otherwise builds #s{N} (1-based), and appends l{layer} if
 * a numbered layer panel is open at the top of the panel stack.
 *
 * Glossary panels are not reflected in the layer segment — they overlay any
 * layer and do not receive their own l{} token. writeHashWithGlossary()
 * handles writing the g{n} sub-token when a glossary link is activated.
 *
 * Sets _isScrollDrivenHashUpdate to true before replaceState and clears it
 * in a microtask so a hashchange listener can detect scroll-driven updates.
 */
export function writeHash() {
  _writeHashFragment(null, null);
}

/**
 * Write fragment with a glossary sub-link token (g{n} format).
 *
 * Reads current step and panel layer from state, then appends g{n} to encode
 * which glossary link within the panel was activated. The integer n is taken
 * directly from the data-deep-link-n attribute assigned at panel render time
 * (parseInt validates it as a number before this call).
 *
 * @param {number} n - 1-based running number of the clicked glossary link.
 */
export function writeHashWithGlossary(n) {
  _writeHashFragment('g', n);
}

/**
 * Internal helper — builds and writes the fragment.
 *
 * @param {string|null} subType - Sub-link type token ('g', 'ps', or null).
 * @param {number|null} subN    - Sub-link running number (or null).
 */
function _writeHashFragment(subType, subN) {
  const idx = state.currentIndex;

  let hash = '';

  if (idx >= 0) {
    hash = `#s${idx + 1}`; // 1-based step number

    if (state.panelStack.length > 0) {
      // Find the topmost numbered layer panel (ignores 'glossary' entries which
      // are not numbered layers and do not get their own l{} token).
      for (let i = state.panelStack.length - 1; i >= 0; i--) {
        const layerMatch = state.panelStack[i].type.match(/^layer(\d+)$/);
        if (layerMatch) {
          hash += `l${layerMatch[1]}`;
          // Append sub-link token if provided (e.g. g{n} for glossary links)
          if (subType !== null && subN !== null) {
            hash += `${subType}${subN}`;
          }
          break;
        }
      }
    }
  }

  _isScrollDrivenHashUpdate = true;

  if (hash) {
    history.replaceState(null, '', hash);
  } else {
    // Intro state — remove fragment entirely
    history.replaceState(null, '', window.location.pathname + window.location.search);
  }

  Promise.resolve().then(() => { _isScrollDrivenHashUpdate = false; });
}

/**
 * Return the current value of the scroll-driven hash update guard flag.
 *
 * Exported so a hashchange listener in another module can check whether a
 * replaceState call triggered the event, and return early if so.
 *
 * @returns {boolean}
 */
export function isScrollDrivenHashUpdate() {
  return _isScrollDrivenHashUpdate;
}

/**
 * Read the URL fragment on page load and jump to the encoded position.
 *
 * Must be called after initCardPool() and after the navigation mode is
 * initialised (initScrollEngine or initializeButtonNavigation), and after
 * initializePanels() — because it may call openPanel() which requires panels
 * to be ready.
 *
 * Instant jump: uses duration: 0 for no scroll animation on load.
 * Panel applied after step position (D-10): step first, then panel via
 * setTimeout to let the card stack render before Bootstrap Offcanvas opens.
 *
 * Sub-panel links (g{n}, ps{n}):
 *   Glossary sub-links (g{n}) are activated here: after the panel opens,
 *   the glossary link with matching data-deep-link-n is clicked. Best-effort.
 *   Primary source sub-links (ps{n}) are not yet implemented.
 */
export function applyDeepLinkOnLoad() {
  const parsed = parseFragment(window.location.hash);
  if (!parsed) return; // No fragment = intro — nothing to do

  // Clamp to valid step range
  const targetIndex = Math.min(parsed.step - 1, state.steps.length - 1);
  if (targetIndex < 0) return;

  if (state.lenis) {
    // Desktop Lenis mode: instant scroll jump to the correct viewport position
    // Position model: intro = 0, step 0 = 1 * innerHeight, step 1 = 2 * innerHeight …
    // Bypass Lenis scrollTo entirely — the Snap plugin's lock mode prevents
    // multi-step jumps via scrollTo. Instead, set the DOM scroll position
    // directly and sync Lenis's internal state to match.
    const targetPx = (targetIndex + 1) * window.innerHeight;
    state.lenis.stop();
    document.documentElement.scrollTop = targetPx;
    // Sync Lenis internal position to match the DOM
    state.lenis.animatedScroll = targetPx;
    state.lenis.targetScroll = targetPx;

    // Activate card and sync state
    activateCard(targetIndex, 'forward');
    state.currentIndex = targetIndex;
    state.scrollPosition = targetIndex + 1;

    // Restart Lenis after a frame so the Snap plugin sees the final position
    requestAnimationFrame(() => { state.lenis.start(); });
  } else {
    // Button/mobile/iOS mode: no scroll surface — activate card directly
    state.currentMobileStep = targetIndex;
    state.mobileInIntro = false;
    activateCard(targetIndex, 'forward');

    // Ensure the correct step has the mobile-active class
    state.steps.forEach((step, i) => {
      if (i === targetIndex) {
        step.classList.add('mobile-active');
      } else {
        step.classList.remove('mobile-active');
      }
    });
  }

  // Panel state (D-10): apply after step position, with delay for card render.
  // Open parent layers underneath the target: layer2 needs layer1 open first,
  // and glossary sub-links need their parent layer open underneath.
  if (parsed.layer !== null) {
    const stepNumber = state.steps[targetIndex]?.dataset?.step;
    if (stepNumber) {
      let delay = 100;

      // Open layer1 first if the target is layer2 or deeper
      if (parsed.layer >= 2) {
        setTimeout(() => { openPanel('layer1', stepNumber); }, delay);
        delay += 200;
      }

      // Open the target layer
      setTimeout(() => { openPanel('layer' + parsed.layer, stepNumber); }, delay);
      delay += 200;

      // Glossary sub-link activation: after the panel opens, find the
      // glossary link with the matching running number and click it to open
      // the glossary entry. Best-effort — if the panel content hasn't loaded
      // in time the click target won't exist and the sub-link is silently
      // skipped.
      if (parsed.subType === 'g' && parsed.subN !== null) {
        setTimeout(() => {
          const panelContent = document.getElementById('panel-layer' + parsed.layer + '-content');
          if (panelContent) {
            const target = panelContent.querySelector(`[data-deep-link-n="${parsed.subN}"]`);
            if (target) target.click();
          }
        }, delay);
      }
    }
  }

  // Primary source sub-link activation (ps{n}) — not yet implemented
}
