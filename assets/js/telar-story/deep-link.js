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
 *
 * Step numbers are 1-based in the fragment. state.currentIndex is 0-based.
 * state.steps[index].dataset.step is the CSV step number used by openPanel().
 *
 * All hash writes use history.replaceState exclusively — no pushState calls
 * anywhere, so the story's own moves add no history entries and fire no
 * hashchange. A fragment change from outside (the address bar, a same-page
 * link, Back/Forward across an entry such a link created) is handled by
 * handleHashChange. scrollRestoration is already set to 'manual' in
 * scroll-engine.js, which prevents browser scroll restoration from interfering.
 *
 * @version v1.8.1
 */

import { state, moveSeconds } from './state.js';
import { setMoveSeconds } from './card-height.js';
import { activateCard, reconcileStackForJump, reconcilePlatesForJump } from './card-pool.js';
import { goToStep, jumpButtonsTo, putButtonsOnIntro, updateViewerInfo } from './navigation.js';
import { closeAllPanels, closePanel, openPanel } from './panels.js';
import { jumpScrollTo, isMoveInFlight } from './scroll-engine.js';

// ── Deep-link panel-open timer ladder ───────────────────────────────────────────

/**
 * Pending panel-open timers scheduled by applyDeepLinkOnLoad. The panel sequence
 * runs as a short setTimeout ladder so the card stack can render before Bootstrap
 * Offcanvas opens; if the reader starts navigating during that window, the
 * deferred opens would pop panels over a now-different step. We track the timer
 * IDs so a genuine user interaction can cancel the whole ladder.
 */
let _deepLinkTimers = [];

/** When a hashchange last closed panels, for the delay before another opens. */
let _lastPanelCloseAt = -Infinity;

/**
 * Clear any pending deep-link panel-open timers and the listeners armed to
 * clear them. Safe to call when nothing is pending.
 */
function _cancelDeepLinkTimers() {
  _deepLinkTimers.forEach(clearTimeout);
  _deepLinkTimers = [];
  window.removeEventListener('wheel', _cancelDeepLinkTimers);
  window.removeEventListener('keydown', _cancelDeepLinkTimers);
  window.removeEventListener('touchstart', _cancelDeepLinkTimers);
}

/**
 * Cancel the deep-link timer ladder on the first genuine user interaction.
 * Listens for wheel / keydown / touchstart — all user-initiated. We deliberately
 * do not listen for the Lenis 'scroll' event: applyDeepLinkOnLoad's own
 * immediate jump emits a 'scroll', which would self-cancel the ladder before any
 * panel opened. Must be armed after the jump's scrollTo so it can't be tripped
 * by the jump.
 *
 * A click reaches none of these, so Back to Start and a contents link cancel
 * the ladder themselves: they close every panel, and a layer the ladder opened
 * afterwards would sit on a stack with nothing under it.
 */
function _armDeepLinkCancellation() {
  window.addEventListener('wheel', _cancelDeepLinkTimers, { passive: true });
  window.addEventListener('keydown', _cancelDeepLinkTimers);
  window.addEventListener('touchstart', _cancelDeepLinkTimers, { passive: true });
}

// ── Fragment regex ────────────────────────────────────────────────────────────

/**
 * Matches all defined fragment formats:
 *   #s{step}
 *   #s{step}l{layer}
 *   #s{step}l{layer}g{n}
 */
const FRAGMENT_RE = /^#s(\d+)(?:l(\d+)(?:(g)(\d+))?)?$/;

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
    subType: m[3] || null,                 // 'g' or null
    subN: m[4] ? parseInt(m[4], 10) : null,
  };
}

/**
 * Build fragment from current state and write via replaceState.
 *
 * Reads state.currentIndex (0-based), the current step in every navigation
 * mode. If < 0, removes the fragment entirely
 * (intro state). Otherwise builds #s{N} (1-based), and appends l{layer} if
 * a numbered layer panel is open at the top of the panel stack.
 *
 * Glossary panels are not reflected in the layer segment — they overlay any
 * layer and do not receive their own l{} token. writeHashWithGlossary()
 * handles writing the g{n} sub-token when a glossary link is activated.
 */
export function writeHash() {
  _writeHashFragment(null);
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
  // The glossary panel carries the entry it shows, so a later fragment change
  // reads which is open from the panel and not from the last fragment written.
  document.getElementById('panel-glossary')?.setAttribute('data-deep-link-n', String(n));
  _writeHashFragment(n);
}

/**
 * Internal helper — builds and writes the fragment.
 *
 * @param {number|null} glossaryN - 1-based glossary sub-link running number, or null.
 */
function _writeHashFragment(glossaryN) {
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
          // Append glossary sub-link token if provided (g{n})
          if (glossaryN !== null) {
            hash += `g${glossaryN}`;
          }
          break;
        }
      }
    }
  }

  if (hash) {
    history.replaceState(null, '', hash);
  } else {
    // Intro state — remove fragment entirely
    history.replaceState(null, '', window.location.pathname + window.location.search);
  }
}

/**
 * Navigate back to the intro / title card from within the story.
 *
 * Closes any open panel first, and cancels any panel a deep link has yet to
 * open: a panel freezes the story, and the button stays live above one. Then
 * scrolls to position 0 where the scroll engine runs, restores the intro card
 * via goToStep(-1), puts the navigation buttons on the intro, hides all
 * viewer plates, and clears the hash.
 */
export function navigateToIntro() {
  _cancelDeepLinkTimers();
  closeAllPanels();
  // A jump carries no camera travel: the cards move over the base.
  setMoveSeconds(moveSeconds(0));

  // Every card and plate goes where a walk back to the intro would leave it.
  // Without this, the cards above step 0 stay stacked and the current step's
  // card and plate stay on screen over the intro.
  reconcileStackForJump(-1);
  reconcilePlatesForJump(-1);

  if (state.lenis) {
    // Through Lenis, which writes the offset with behavior: instant. A direct
    // scrollTop write is animated under the page's scroll-behavior: smooth,
    // and WebKit can abandon that animation part way, leaving the story on the
    // intro and the scroll on the step. The index is stated first, so the
    // jump's own scroll frame finds the story already on the intro.
    state.currentIndex = -1;
    state.scrollPosition = 0;
    jumpScrollTo(0);
    if (state.snap) state.snap.currentSnapIndex = 0;
    state.lenis.stop();
    // A panel still closing holds the scroll stopped, and its close starts it.
    requestAnimationFrame(() => { if (!state.isPanelOpen) state.lenis.start(); });
  }

  // Use the navigation module to restore intro card visuals
  goToStep(-1, 'backward');
  // Buttons are present in button navigation and in embed mode, where the
  // scroll engine runs beside them and does not move them.
  putButtonsOnIntro();
  writeHash();
}

/**
 * Navigate to a specific step from within the story (e.g. TOC links).
 *
 * Unlike applyDeepLinkOnLoad (which runs once at page load), this can be
 * called at any time during the story. It closes any open panel and cancels
 * any a deep link has yet to open, as Back to Start does, then jumps the
 * scroll position and activates the target card, then updates the URL hash.
 *
 * @param {number} stepNumber - 1-based step number (matches CSV step column).
 */
export function navigateToStep(stepNumber) {
  const targetIndex = stepNumber - 1;
  if (targetIndex < 0 || targetIndex >= state.steps.length) return;

  _cancelDeepLinkTimers();
  closeAllPanels();
  setMoveSeconds(moveSeconds(0));

  // Close every plate but the target's before jumping, or one the reader
  // walked onto earlier is still open behind the step they land on.
  reconcilePlatesForJump(targetIndex);

  if (state.lenis) {
    const targetPx = (targetIndex + 1) * state.scrollStepPx;

    // scrollTo must jump straight to the target with no animation. An animated
    // scroll drives the per-frame IIIF interpolation (lerpIiifPosition) at each
    // intermediate frame; lerpIiifPosition only skips interpolating once
    // progress is within 0.001 of the integer step, so an animated approach
    // can leave the viewer on the last interpolated (not authored) x/y/zoom
    // instead of landing exactly on the target position. immediate:true removes
    // the intermediate frames entirely; force:true overrides the Snap plugin's
    // lock/stopped state so the jump isn't blocked.
    jumpScrollTo(targetPx);
    if (state.snap) state.snap.currentSnapIndex = targetIndex + 1; // keep Snap aligned (matches keyboardNav)

    reconcileStackForJump(targetIndex);
    activateCard(targetIndex, 'forward');
    state.currentIndex = targetIndex;
    state.scrollPosition = targetIndex + 1;
  } else {
    reconcileStackForJump(targetIndex);
    activateCard(targetIndex, 'forward');
    jumpButtonsTo(targetIndex);
    updateViewerInfo(targetIndex); // the scroll engine sets the counter in Lenis mode
  }

  writeHash();
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
 * Panel applied after step position: step first, then panel via
 * setTimeout to let the card stack render before Bootstrap Offcanvas opens.
 *
 * Sub-panel links (g{n}):
 *   Glossary sub-links (g{n}) are activated here: after the panel opens,
 *   the glossary link with matching data-deep-link-n is clicked. Best-effort.
 */
export function applyDeepLinkOnLoad() {
  const parsed = parseFragment(window.location.hash);
  if (!parsed) return; // No fragment = intro — nothing to do

  // Clamp to valid step range
  const targetIndex = Math.min(parsed.step - 1, state.steps.length - 1);
  if (targetIndex < 0) return;

  _jumpToIndex(targetIndex);
  _scheduleLayerOpen(parsed, targetIndex, 100);
}

/**
 * Jump the story to a step with no animation and activate its card.
 *
 * Desktop Lenis mode: instant scroll jump to the correct viewport position.
 * Position model: intro = 0, step 0 = 1 step height, step 1 = 2 …, where a
 * step's height is the one the scroll surface is laid out in.
 *
 * scrollTo must jump straight to the target with no animation — see
 * navigateToStep for why (an animated scroll can leave the per-frame IIIF
 * lerp on an interpolated position instead of the authored one).
 *
 * @param {number} targetIndex - 0-based step index, already in range.
 */
function _jumpToIndex(targetIndex) {
  setMoveSeconds(moveSeconds(0));
  if (state.lenis) {
    const targetPx = (targetIndex + 1) * state.scrollStepPx;
    state.lenis.scrollTo(targetPx, { immediate: true, force: true });
    if (state.snap) state.snap.currentSnapIndex = targetIndex + 1; // keep Snap aligned

    // Stack the cards jumped over, then activate the card and sync state
    reconcileStackForJump(targetIndex);
    activateCard(targetIndex, 'forward');
    state.currentIndex = targetIndex;
    state.scrollPosition = targetIndex + 1;
  } else {
    // Button navigation (phones, embeds, iOS): no scroll surface — activate card directly
    reconcileStackForJump(targetIndex);
    activateCard(targetIndex, 'forward');
    jumpButtonsTo(targetIndex);
    updateViewerInfo(targetIndex); // the scroll engine sets the counter in Lenis mode
  }
}

/**
 * Activate the glossary link a fragment names, after the layer holding it is
 * open: find the link with the matching running number and click it to open
 * the glossary entry. Best-effort — if the panel content hasn't loaded in time
 * the click target won't exist and the sub-link is silently skipped.
 */
function _scheduleGlossaryClick(parsed, targetIndex, delay) {
  _deepLinkTimers.push(setTimeout(() => {
    if (state.currentIndex !== targetIndex) return;
    const panelContent = document.getElementById('panel-layer' + parsed.layer + '-content');
    const target = panelContent?.querySelector(`[data-deep-link-n="${parsed.subN}"]`);
    if (target) target.click();
  }, delay));
  _armDeepLinkCancellation();
}

/**
 * Open the panel layers a fragment names, after the step is in place.
 *
 * Panel applied after step position: step first, then panel via setTimeout to
 * let the card stack render before Bootstrap Offcanvas opens. Parent layers
 * open underneath the target: layer2 needs layer1 open first, and glossary
 * sub-links need their parent layer open underneath.
 *
 * @param {{ layer: number|null, subType: string|null, subN: number|null }} parsed
 * @param {number} targetIndex - 0-based step index the layers belong to.
 * @param {number} delay - Milliseconds before the first open.
 */
function _scheduleLayerOpen(parsed, targetIndex, delay) {
  if (parsed.layer === null) return;
  const stepNumber = state.steps[targetIndex].dataset.step;
  if (!stepNumber) return;

  // Each deferred open also re-checks that we are still on the deep-link
  // target before acting — a backstop that covers navigation paths the
  // interaction listener can't (e.g. a nav-button tap).
  const onTarget = () => state.currentIndex === targetIndex;

  // Open layer1 first if the target is layer2 or deeper
  if (parsed.layer >= 2) {
    _deepLinkTimers.push(setTimeout(() => {
      if (onTarget()) openPanel('layer1', stepNumber);
    }, delay));
    delay += 200;
  }

  // Open the target layer
  _deepLinkTimers.push(setTimeout(() => {
    if (onTarget()) openPanel('layer' + parsed.layer, stepNumber);
  }, delay));
  delay += 200;

  if (parsed.subType === 'g' && parsed.subN !== null) {
    _scheduleGlossaryClick(parsed, targetIndex, delay);
    return;
  }

  // Arm cancellation only now that timers are scheduled — and after the jump,
  // so the jump's own scroll can't trip it.
  _armDeepLinkCancellation();
}

// ── Fragment changes on a loaded story ────────────────────────────────────────

/** Time for a closing panel's slide-out to end before another opens. */
const PANEL_CLOSE_WAIT_MS = 400;

/**
 * The numbered layer on top of the panel stack, or null when none is open.
 * Glossary entries carry no layer number and are skipped, as in the fragment.
 */
function _openLayerNumber() {
  for (let i = state.panelStack.length - 1; i >= 0; i--) {
    const m = state.panelStack[i].type.match(/^layer(\d+)$/);
    if (m) return parseInt(m[1], 10);
  }
  return null;
}

/** Whether a fragment names the intro: empty, `#`, or a step below 1. */
function _namesIntro(hash, parsed) {
  if (hash === '' || hash === '#') return true;
  return parsed !== null && parsed.step < 1;
}

/** Go to the intro unless the story is already there with no panel open. */
function _moveToIntroFromFragment() {
  if (state.currentIndex !== -1 || state.panelStack.length > 0 || isMoveInFlight()) navigateToIntro();
}

/** Rewrite a fragment that named a step past the end with the step shown. */
function _nameLandedStep(parsed, targetIndex) {
  if (parsed.step - 1 !== targetIndex) writeHash();
}

/** The glossary entry open over a layer: its running number, -1 if open with none recorded, null if none open. */
function _openGlossaryN() {
  if (!state.panelStack.some((p) => p.type === 'glossary')) return null;
  const n = parseInt(document.getElementById('panel-glossary')?.dataset.deepLinkN, 10);
  return Number.isNaN(n) ? -1 : n;
}

/**
 * Whether a panel is open, opening or closing. Bootstrap refuses a show while
 * an offcanvas is still hiding, so an open waits while any of these holds.
 * The stack drops a panel when its close is asked for, so the offcanvas classes
 * and the time since this handler last closed panels are read as well.
 */
function _panelsBusy() {
  if (state.panelStack.length > 0) return true;
  if (Date.now() - _lastPanelCloseAt < PANEL_CLOSE_WAIT_MS) return true;
  return !!document.querySelector('#panel-layer1, #panel-layer2, #panel-glossary')
    && !!document.querySelector('.offcanvas.show, .offcanvas.showing, .offcanvas.hiding');
}

/** Delay before an open that follows a possible close, noting a close if one is under way. */
function _openDelayAfterClose() {
  if (!_panelsBusy()) return 100;
  _lastPanelCloseAt = Date.now();
  return PANEL_CLOSE_WAIT_MS;
}

/**
 * The story is on the step the fragment names: bring the panels to the layer
 * and glossary entry it names, comparing the whole position (layer and
 * sub-link), and touching only what differs.
 */
function _settleOnStep(parsed, targetIndex) {
  const wantG = parsed.subType === 'g' ? parsed.subN : null;
  const curG = _openGlossaryN();
  if (_openLayerNumber() !== parsed.layer) {
    _cancelDeepLinkTimers();
    const delay = _openDelayAfterClose();
    closeAllPanels();
    writeHash();
    _scheduleLayerOpen(parsed, targetIndex, delay);
    return;
  }
  if (curG === wantG) {
    _nameLandedStep(parsed, targetIndex);
    return;
  }
  _cancelDeepLinkTimers();
  if (curG !== null) {
    closePanel('glossary');
    _lastPanelCloseAt = Date.now();
  }
  writeHash();
  if (wantG !== null) _scheduleGlossaryClick(parsed, targetIndex, curG !== null ? PANEL_CLOSE_WAIT_MS : 0);
}

/**
 * React to a fragment change the reader did not make by moving the story:
 * typing a fragment, following a same-page link, or Back/Forward across
 * entries such a link created.
 *
 * The story's own moves write the fragment with replaceState, which fires no
 * hashchange, so this runs only for a change that came from outside. It moves
 * through navigateToStep and navigateToIntro, as a contents link and Back to
 * Start do: they stand down any move in flight, close open panels, and set the
 * buttons and the counter. Panels the fragment names open through the deep-link
 * ladder. An empty fragment, `#`, or a step below 1 (`#s0`) is the intro; one
 * past the last step lands on the last step, as on load. A fragment that is
 * not a story fragment (`#fn:1` or `#fnref:1` from a kramdown footnote in an
 * answer or panel, `#credits`) is ignored: no move, no panel close, no
 * fragment rewrite, because any in-page anchor fires hashchange.
 * popstate is not listened for: Back across such an entry fires it together
 * with hashchange, and hashchange alone carries the new fragment.
 */
export function handleHashChange() {
  if (!state.steps.length) return;

  const hash = window.location.hash;
  const parsed = parseFragment(hash);
  if (_namesIntro(hash, parsed)) {
    _moveToIntroFromFragment();
    return;
  }
  if (!parsed) return;

  const targetIndex = Math.min(parsed.step - 1, state.steps.length - 1);
  if (state.currentIndex === targetIndex && !isMoveInFlight()) {
    _settleOnStep(parsed, targetIndex);
    return;
  }
  const delay = _openDelayAfterClose();
  navigateToStep(targetIndex + 1);
  _scheduleLayerOpen(parsed, targetIndex, delay);
}
