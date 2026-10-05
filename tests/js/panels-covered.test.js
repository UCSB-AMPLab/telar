/**
 * Tests for covered panels: what an open panel covers is inert, and the
 * glossary panel is the topmost panel the story's keys close.
 *
 * telar.js is a standalone script (not part of the esbuild bundle); it is
 * loaded once as a side-effect import, started with a DOMContentLoaded event,
 * and read through its window.TelarPanels surface. panels.js is imported as a
 * module. Bootstrap's Offcanvas is replaced by a fake that fires the same
 * bubbling show/hide/hidden events and holds each panel mid-transition until
 * the test finishes it, as the real 0.3s slide does.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import {
  initializePanels,
  openPanel,
  closePanel,
  closeTopPanel,
  closeAllPanels,
} from '../../assets/js/telar-story/panels.js';
import {
  FakeOffcanvas, finishTransitions, finishNextTransition, resetOffcanvas,
} from './fake-offcanvas.js';

const PAGE = `
  <main class="story-container"><button id="story-btn">x</button></main>
  ${['layer1', 'layer2', 'glossary'].map((t) => `
    <div class="offcanvas" id="panel-${t}" data-telar-panel="${t}">
      <button id="panel-${t}-back">Back</button>
      <h1 id="panel-${t}-title"></h1><div id="panel-${t}-content"></div>
    </div>`).join('')}
  <div class="offcanvas" id="share-panel"></div>
`;

const panel = (t) => document.getElementById(`panel-${t}`);
const offcanvas = (t) => FakeOffcanvas.getInstance(panel(t)) || new FakeOffcanvas(panel(t));

/** Which of the panels and <main> carry the inert attribute. */
function inertParts() {
  const parts = ['layer1', 'layer2', 'glossary'].filter((t) => panel(t).hasAttribute('inert'));
  if (document.querySelector('main').hasAttribute('inert')) parts.push('main');
  return parts;
}

/** Open panels the way their callers do: layers on the stack, the glossary by Bootstrap alone. */
function openLayers(...types) {
  types.forEach((t) => {
    state.panelStack.push({ type: t, id: '7' });
    offcanvas(t).show();
  });
  finishTransitions();
}

function openGlossary() {
  offcanvas('glossary').show();
  finishTransitions();
}

beforeAll(async () => {
  window.bootstrap = { Offcanvas: FakeOffcanvas };
  document.body.innerHTML = PAGE;
  await import('../../assets/js/telar.js');
  document.dispatchEvent(new Event('DOMContentLoaded'));
  initializePanels();
});

beforeEach(() => {
  resetOffcanvas();
  document.querySelectorAll('.offcanvas').forEach((el) => {
    el.classList.remove('show', 'showing', 'hiding');
    el.removeAttribute('inert');
  });
  document.querySelector('main').removeAttribute('inert');
  state.panelStack = [];
  state.isPanelOpen = false;
  state.scrollLockActive = false;
  state.currentIndex = 6;
});

// ── What is inert ────────────────────────────────────────────────────────────

describe('covered content', () => {
  it('leaves layer 1 and the story live while layer 1 is the only panel', () => {
    openLayers('layer1');
    expect(inertParts()).toEqual([]);
  });

  it('makes layer 1 inert as layer 2 starts to show, not after the slide', () => {
    openLayers('layer1');
    offcanvas('layer2').show();
    expect(inertParts()).toEqual(['layer1']);
  });

  it('makes both layers and the story inert under the glossary panel', () => {
    openLayers('layer1', 'layer2');
    openGlossary();
    expect(inertParts()).toEqual(['layer1', 'layer2', 'main']);
  });

  it('makes the page inert under a glossary panel with no layer open', () => {
    openGlossary();
    expect(inertParts()).toEqual(['main']);
  });

  it('releases layer 1 as soon as layer 2 starts to close', () => {
    openLayers('layer1', 'layer2');
    offcanvas('layer2').hide();
    expect(inertParts()).toEqual([]);
  });

  it('releases what the glossary panel covered when it closes', () => {
    openLayers('layer1', 'layer2');
    openGlossary();
    offcanvas('glossary').hide();
    finishTransitions();
    expect(inertParts()).toEqual(['layer1']);
  });

  it('closeAllPanels closes each panel as its back button would, and holds the story until the last has gone', () => {
    openLayers('layer1', 'layer2');
    openGlossary();
    history.replaceState(null, '', '#s7l2');
    closeAllPanels();
    expect(state.panelStack).toEqual([]);
    expect(window.location.hash).toBe('#s7');
    expect(state.isPanelOpen, 'the panels are still closing').toBe(true);
    expect(state.scrollLockActive).toBe(true);
    finishTransitions();
    expect(state.isPanelOpen).toBe(false);
    expect(state.scrollLockActive).toBe(false);
  });

  it('leaves nothing inert once closeAllPanels has run', () => {
    openLayers('layer1', 'layer2');
    openGlossary();
    closeAllPanels();
    finishTransitions();
    expect(inertParts()).toEqual([]);
  });

  it('ignores an offcanvas that is not a Telar panel', () => {
    openLayers('layer1', 'layer2');
    const share = new FakeOffcanvas(document.getElementById('share-panel'));
    share.show();
    share.hide();
    finishTransitions();
    expect(inertParts()).toEqual(['layer1']);
  });

  it('can be recomputed from the classes alone', () => {
    panel('layer1').classList.add('show');
    panel('glossary').classList.add('show');
    window.TelarPanels.syncCoveredContent();
    expect(inertParts()).toEqual(['layer1', 'main']);
  });
});

// ── The scroll lock while another panel slides in ────────────────────────────
//
// A panel that is still sliding in is open: the story stays frozen under it.
// Layer 1 closing while layer 2 slides in (a deep link's deferred open landing
// after the reader closed the panels) must not start the story's scroll.

describe('a panel closing while another slides in', () => {
  let lenis;

  beforeEach(() => {
    lenis = {
      isStopped: false,
      stop() { this.isStopped = true; },
      start() { this.isStopped = false; },
    };
    state.lenis = lenis;
    window.telarLang = {};
    window.storyData = { steps: [{ step: '7', layer1_text: '<p>one</p>', layer2_text: '<p>two</p>' }] };
    openPanel('layer1', '7');
    finishTransitions();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    state.lenis = null;
  });

  it('leaves the story frozen when the closing panel has gone', () => {
    closePanel('layer1');
    openPanel('layer2', '7');
    expect(panel('layer2').classList.contains('showing')).toBe(true);
    finishNextTransition();                       // layer 1's slide out ends
    expect(panel('layer2').classList.contains('show'), 'layer 2 still sliding in').toBe(false);
    expect(state.isPanelOpen).toBe(true);
    expect(state.scrollLockActive).toBe(true);
    expect(lenis.isStopped).toBe(true);
  });

  it('leaves the story frozen when the wait after the close runs out', () => {
    closePanel('layer1');
    openPanel('layer2', '7');
    finishNextTransition();                       // layer 1's 0.3s slide ends first
    vi.advanceTimersByTime(350);
    expect(panel('layer2').classList.contains('show'), 'layer 2 still sliding in').toBe(false);
    expect(state.isPanelOpen).toBe(true);
    expect(state.scrollLockActive).toBe(true);
    expect(lenis.isStopped).toBe(true);
  });

  it('leaves the story frozen while panels closed together are still sliding out', () => {
    openPanel('layer2', '7');
    finishTransitions();
    closeAllPanels();
    finishNextTransition();                       // layer 2 has gone, layer 1 has not
    expect(panel('layer1').classList.contains('hiding')).toBe(true);
    expect(state.isPanelOpen).toBe(true);
    expect(lenis.isStopped).toBe(true);
  });

  it('frees the story when an offcanvas that is not one of its panels is shown', () => {
    const other = document.createElement('div');
    other.className = 'offcanvas show';
    document.body.appendChild(other);
    try {
      closePanel('layer1');
      finishTransitions();
      vi.advanceTimersByTime(350);
      expect(state.isPanelOpen).toBe(false);
      expect(lenis.isStopped).toBe(false);
    } finally {
      other.remove();
    }
  });

  it('frees the story once the last panel has gone', () => {
    closePanel('layer1');
    finishTransitions();
    vi.advanceTimersByTime(350);
    expect(state.isPanelOpen).toBe(false);
    expect(lenis.isStopped).toBe(false);
  });
});

// ── The glossary panel on the story's stack ──────────────────────────────────

describe('the glossary panel on the panel stack', () => {
  it('joins the stack on top when it shows, and freezes the story', () => {
    openLayers('layer1');
    openGlossary();
    expect(state.panelStack.map((p) => p.type)).toEqual(['layer1', 'glossary']);
    expect(state.isPanelOpen).toBe(true);
    expect(state.scrollLockActive).toBe(true);
  });

  it('adds no layer to the URL fragment', () => {
    openLayers('layer1', 'layer2');
    history.replaceState(null, '', '#s7l2');
    openGlossary();
    expect(window.location.hash).toBe('#s7l2');
  });

  it('is what closeTopPanel closes, leaving the layer under it open', () => {
    openLayers('layer1');
    openGlossary();
    closeTopPanel();
    finishTransitions();
    expect(offcanvas('glossary').shown).toBe(false);
    expect(offcanvas('layer1').shown).toBe(true);
    expect(state.panelStack.map((p) => p.type)).toEqual(['layer1']);
  });

  it('is still the top while Bootstrap closes it, so a second close in the same key press does not reach layer 1', () => {
    openLayers('layer1');
    openGlossary();
    offcanvas('glossary').hide(); // Bootstrap's own Escape, focus in the panel
    closeTopPanel(); // the story's Escape, on the same key press
    finishTransitions();
    expect(offcanvas('layer1').shown).toBe(true);
    expect(state.panelStack.map((p) => p.type)).toEqual(['layer1']);
  });

  it('leaves the stack when it closes by any path', () => {
    openGlossary();
    offcanvas('glossary').hide();
    finishTransitions();
    expect(state.panelStack).toEqual([]);
    expect(state.isPanelOpen).toBe(false);
    expect(state.scrollLockActive).toBe(false);
  });
});

// ── Glossary links in a layer and the URL fragment ───────────────────────────

describe('a glossary link in a layer', () => {
  // The markup scripts/telar/glossary.py writes for a resolved term and for an
  // unresolved one.
  const LAYER2 = '<p>A <a href="#" class="glossary-inline-link" data-term-id="panel">Panel</a>, '
    + '<span class="glossary-link-error" data-term-id="nope">[[nope]]</span> and a '
    + '<a href="#" class="glossary-inline-link" data-term-id="layer">layer</a>.</p>';

  const links = () => [...document.querySelectorAll('#panel-layer2-content .glossary-inline-link')];

  beforeAll(() => {
    window.telarLang = { goDeeper: 'Go deeper' };
    window.storyData = {
      steps: [{ step: '7', layer1_title: 'L1', layer1_text: '<p>one</p>',
        layer2_title: 'L2', layer2_text: LAYER2 }],
    };
    // telar.js fetches the term's page as the panel shows; the page never arrives here.
    window.fetch = () => new Promise(() => {});
  });

  beforeEach(() => {
    openPanel('layer1', '7');
    openPanel('layer2', '7');
    finishTransitions();
  });

  it('is numbered in document order, and an unresolved term is not', () => {
    expect(links().map((a) => a.dataset.deepLinkN)).toEqual(['1', '2']);
    expect(document.querySelector('#panel-layer2-content .glossary-link-error').dataset.deepLinkN)
      .toBeUndefined();
  });

  it('writes g{n} into the fragment when clicked', () => {
    links()[1].click();
    finishTransitions();
    expect(offcanvas('glossary').shown).toBe(true);
    expect(window.location.hash).toBe('#s7l2g2');
  });

  it('leaves the fragment naming the layer once the glossary panel closes', () => {
    links()[0].click();
    finishTransitions();
    expect(window.location.hash).toBe('#s7l2g1');
    offcanvas('glossary').hide();
    finishTransitions();
    expect(window.location.hash).toBe('#s7l2');
  });

  it('leaves the fragment naming the layer when the story closes the glossary panel', () => {
    links()[0].click();
    finishTransitions();
    expect(window.location.hash).toBe('#s7l2g1');
    closeTopPanel();
    expect(window.location.hash).toBe('#s7l2');
  });
});

// ── Keys on a page with no story ─────────────────────────────────────────────

describe('closeGlossaryOnKey', () => {
  const key = (k) => new KeyboardEvent('keydown', { key: k, cancelable: true });

  it.each(['ArrowLeft', 'Escape'])('%s closes an open glossary panel and is cancelled', (k) => {
    openGlossary();
    const e = key(k);
    window.TelarPanels.closeGlossaryOnKey(e);
    expect(offcanvas('glossary').shown).toBe(false);
    expect(e.defaultPrevented).toBe(true);
  });

  it.each(['ArrowLeft', 'Escape'])('%s is left to the page when no glossary panel is open', (k) => {
    const e = key(k);
    window.TelarPanels.closeGlossaryOnKey(e);
    expect(e.defaultPrevented).toBe(false);
  });

  it('leaves other keys alone', () => {
    openGlossary();
    const e = key('ArrowRight');
    window.TelarPanels.closeGlossaryOnKey(e);
    expect(offcanvas('glossary').shown).toBe(true);
    expect(e.defaultPrevented).toBe(false);
  });
});
