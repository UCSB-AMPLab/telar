/**
 * Tests for Telar Story – Deep Linking
 *
 * Covers the panel-open timer ladder in applyDeepLinkOnLoad and its
 * cancellation on user interaction. The heavy sibling modules
 * (card-pool, navigation, panels, state) are mocked so the module imports
 * cleanly in jsdom and the timing behaviour can be driven with fake timers.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Mocks for the heavy sibling modules ──────────────────────────────────────
// The `state` object is shared by reference with the module under test, so the
// test can read the index the function assigns and mutate it to simulate the
// user navigating away mid-ladder.
vi.mock('../../assets/js/telar-story/state.js', () => ({
  state: {
    steps: [],
    currentIndex: -1,
    currentButtonStep: -1,
    scrollPosition: 0,
    lenis: null,
    snap: null,
    panelStack: [],
    viewerPlates: {},
  },
  moveSeconds: () => 1.2,
}));
vi.mock('../../assets/js/telar-story/card-pool.js', () => ({
  activateCard: vi.fn(),
  reconcileStackForJump: vi.fn(),
  reconcilePlatesForJump: vi.fn(),
}));
vi.mock('../../assets/js/telar-story/navigation.js', () => ({
  goToStep: vi.fn(),
  jumpButtonsTo: vi.fn(),
  putButtonsOnIntro: vi.fn(),
  updateViewerInfo: vi.fn(),
}));
vi.mock('../../assets/js/telar-story/panels.js', () => ({ openPanel: vi.fn(), closeAllPanels: vi.fn(), closePanel: vi.fn() }));
vi.mock('../../assets/js/telar-story/scroll-engine.js', () => ({ jumpScrollTo: vi.fn(), isMoveInFlight: vi.fn(() => false) }));

import { applyDeepLinkOnLoad, handleHashChange, navigateToIntro, navigateToStep, writeHash, writeHashWithGlossary } from '../../assets/js/telar-story/deep-link.js';
import { state } from '../../assets/js/telar-story/state.js';
import { openPanel, closeAllPanels, closePanel } from '../../assets/js/telar-story/panels.js';
import { activateCard, reconcilePlatesForJump } from '../../assets/js/telar-story/card-pool.js';
import { goToStep, jumpButtonsTo, updateViewerInfo } from '../../assets/js/telar-story/navigation.js';
import { jumpScrollTo, isMoveInFlight } from '../../assets/js/telar-story/scroll-engine.js';

function makeSteps(n) {
  return Array.from({ length: n }, (_, i) => ({ dataset: { step: String(i + 1) } }));
}

describe('applyDeepLinkOnLoad — panel-open timer ladder', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    openPanel.mockClear();
    state.steps = makeSteps(5);
    state.currentIndex = -1;
    state.currentButtonStep = -1;
    state.lenis = { scrollTo: vi.fn(), stop: vi.fn(), start: vi.fn() }; // desktop path
    state.scrollStepPx = window.innerHeight;
    state.snap = null;
    window.location.hash = '';
  });

  afterEach(() => {
    // Flush any armed interaction listeners so they don't leak across tests,
    // then drop fake timers.
    window.dispatchEvent(new Event('wheel'));
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('opens the target layer after its delay when the user does not interact', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    expect(state.currentIndex).toBe(2);        // jumped to step 3 (0-based 2)
    expect(openPanel).not.toHaveBeenCalled();  // not yet — still in the ladder
    vi.advanceTimersByTime(100);
    expect(openPanel).toHaveBeenCalledWith('layer1', '3');
  });

  it('in button mode a deep link on load sets the counter with the card and the buttons', () => {
    state.lenis = null;
    updateViewerInfo.mockClear();
    window.location.hash = '#s4';
    applyDeepLinkOnLoad();
    expect(jumpButtonsTo).toHaveBeenCalledWith(3);
    expect(updateViewerInfo).toHaveBeenCalledWith(3);
  });

  it('opens layer1 then layer2 in order for a deeper deep-link', () => {
    window.location.hash = '#s2l2';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(100);
    expect(openPanel).toHaveBeenCalledWith('layer1', '2'); // parent first
    vi.advanceTimersByTime(200);
    expect(openPanel).toHaveBeenCalledWith('layer2', '2'); // target second
    expect(openPanel).toHaveBeenCalledTimes(2);
  });

  it('cancels the ladder when the user scrolls (wheel) before it fires', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    window.dispatchEvent(new Event('wheel')); // user starts scrolling
    vi.advanceTimersByTime(500);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('cancels the ladder on a keydown before it fires', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    window.dispatchEvent(new Event('keydown'));
    vi.advanceTimersByTime(500);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('does not open the panel if the user navigated to a different step (on-target backstop)', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    state.currentIndex = 4; // user moved away without firing wheel/keydown
    vi.advanceTimersByTime(100);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('schedules nothing when the fragment has no layer', () => {
    window.location.hash = '#s3';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(500);
    expect(openPanel).not.toHaveBeenCalled();
  });
});

// Back to Start and a contents link close every open panel before they move.
// A layer the deep link has yet to open would open after that close, onto a
// stack with nothing under it, if the story is back on the linked step by the
// time its timer fires.
describe('applyDeepLinkOnLoad — a move by Back to Start or a contents link', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    openPanel.mockClear();
    state.steps = makeSteps(5);
    state.currentIndex = -1;
    state.lenis = { scrollTo: vi.fn(), stop: vi.fn(), start: vi.fn() };
    state.scrollStepPx = window.innerHeight;
    state.snap = null;
    window.location.hash = '';
  });

  afterEach(() => {
    window.dispatchEvent(new Event('wheel'));
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('a contents link back to the linked step opens no layer the link had yet to open', () => {
    window.location.hash = '#s2l2';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(100);
    expect(openPanel).toHaveBeenCalledWith('layer1', '2');
    navigateToStep(2);
    vi.advanceTimersByTime(500);
    expect(openPanel.mock.calls, 'layer 2 opened after the panels were closed').toEqual([['layer1', '2']]);
  });

  it('Back to Start and then a contents link to the linked step open no layer the link had yet to open', () => {
    window.location.hash = '#s2l2';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(100);
    navigateToIntro();
    navigateToStep(2);
    vi.advanceTimersByTime(500);
    expect(openPanel.mock.calls).toEqual([['layer1', '2']]);
  });

  it('Back to Start and then buttons clicked back to the linked step open no layer the link had yet to open', () => {
    window.location.hash = '#s2l2';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(100);
    navigateToIntro();
    // Two clicks on Next, by mouse: no wheel, key or touch reaches the window.
    state.currentIndex = 1;
    vi.advanceTimersByTime(500);
    expect(openPanel.mock.calls).toEqual([['layer1', '2']]);
  });
});

// A fragment change on a loaded story moves the story to the position the
// fragment names. The story's own moves write with replaceState and fire no
// hashchange, so every case here is a change from outside.
let clockOffset = 0;

describe('handleHashChange — a fragment change on a loaded story', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    openPanel.mockClear();
    closeAllPanels.mockClear();
    activateCard.mockClear();
    goToStep.mockClear();
    reconcilePlatesForJump.mockClear();
    // The handler remembers when it last closed panels; start each test later than any earlier one.
    clockOffset += 60000;
    vi.setSystemTime(Date.now() + clockOffset);
    closePanel.mockClear();
    isMoveInFlight.mockReturnValue(false);
    jumpScrollTo.mockClear();
    jumpButtonsTo.mockClear();
    updateViewerInfo.mockClear();
    document.body.innerHTML = '';
    state.steps = makeSteps(5);
    state.currentIndex = 0;
    state.panelStack = [];
    state.lenis = { scrollTo: vi.fn(), stop: vi.fn(), start: vi.fn() };
    state.scrollStepPx = window.innerHeight;
    state.snap = null;
    window.location.hash = '';
  });

  afterEach(() => {
    window.dispatchEvent(new Event('wheel'));
    vi.clearAllTimers();
    vi.useRealTimers();
    state.panelStack = [];
  });

  it('moves to the step the fragment names', () => {
    window.location.hash = '#s4';
    handleHashChange();
    expect(state.currentIndex).toBe(3);
    expect(activateCard).toHaveBeenCalledWith(3, 'forward');
    expect(reconcilePlatesForJump).toHaveBeenCalledWith(3);
    expect(window.location.hash, 'the address names the step the story is on').toBe('#s4');
  });

  it('does nothing when the fragment names the step already shown', () => {
    state.currentIndex = 3;
    window.location.hash = '#s4';
    handleHashChange();
    expect(activateCard).not.toHaveBeenCalled();
    expect(closeAllPanels).not.toHaveBeenCalled();
    expect(jumpScrollTo).not.toHaveBeenCalled();
  });

  it('goes to the intro for an empty fragment', () => {
    state.currentIndex = 3;
    window.location.hash = '#';
    handleHashChange();
    expect(state.currentIndex).toBe(-1);
    expect(goToStep).toHaveBeenCalledWith(-1, 'backward');
  });

  it('does nothing on the intro for an empty fragment', () => {
    state.currentIndex = -1;
    handleHashChange();
    expect(goToStep).not.toHaveBeenCalled();
    expect(closeAllPanels).not.toHaveBeenCalled();
  });

  it('goes to the intro for #s0', () => {
    state.currentIndex = 2;
    window.location.hash = '#s0';
    handleHashChange();
    expect(state.currentIndex).toBe(-1);
    expect(goToStep).toHaveBeenCalledWith(-1, 'backward');
  });

  it.each(['#fn:1', '#fnref:1', '#credits'])('ignores %s: no move, no panel close, no fragment rewrite', (frag) => {
    state.currentIndex = 2;
    state.panelStack = [{ type: 'layer1', id: '3' }];
    window.location.hash = frag;
    handleHashChange();
    expect(goToStep).not.toHaveBeenCalled();
    expect(closeAllPanels).not.toHaveBeenCalled();
    expect(activateCard).not.toHaveBeenCalled();
    expect(jumpScrollTo).not.toHaveBeenCalled();
    expect(state.currentIndex).toBe(2);
    expect(state.panelStack).toEqual([{ type: 'layer1', id: '3' }]);
    expect(window.location.hash, 'the fragment is left as the link set it').toBe(frag);
    vi.advanceTimersByTime(1000);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('a footnote link inside an open panel leaves the panel open', () => {
    state.currentIndex = 2;
    state.panelStack = [{ type: 'layer1', id: '3' }];
    window.location.hash = '#fn:1';
    handleHashChange();
    expect(closeAllPanels).not.toHaveBeenCalled();
    expect(state.panelStack).toHaveLength(1);
  });

  it('lands on the last step for a step past the end, as on load', () => {
    window.location.hash = '#s99';
    handleHashChange();
    expect(state.currentIndex).toBe(4);
    expect(window.location.hash, 'the address names the step it landed on').toBe('#s5');
  });

  it('does nothing when the story is already on the last step and the fragment is past it', () => {
    state.currentIndex = 4;
    window.location.hash = '#s99';
    handleHashChange();
    expect(activateCard).not.toHaveBeenCalled();
    expect(window.location.hash).toBe('#s5');
  });

  it('closes an open panel before it moves, and opens nothing for a step-only fragment', () => {
    state.panelStack = [{ type: 'layer1', id: '1' }];
    window.location.hash = '#s3';
    handleHashChange();
    expect(closeAllPanels).toHaveBeenCalledTimes(1);
    expect(closeAllPanels.mock.invocationCallOrder[0]).toBeLessThan(activateCard.mock.invocationCallOrder[0]);
    vi.advanceTimersByTime(1000);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('opens the panel layer the fragment names after the step, with the sequence a deep link uses', () => {
    window.location.hash = '#s3l2';
    handleHashChange();
    expect(state.currentIndex).toBe(2);
    expect(openPanel).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(openPanel.mock.calls).toEqual([['layer1', '3']]);
    vi.advanceTimersByTime(200);
    expect(openPanel.mock.calls).toEqual([['layer1', '3'], ['layer2', '3']]);
  });

  it('opens only the panel when the step is already shown', () => {
    state.currentIndex = 2;
    window.location.hash = '#s3l1';
    handleHashChange();
    expect(activateCard).not.toHaveBeenCalled();
    expect(jumpScrollTo).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(openPanel.mock.calls).toEqual([['layer1', '3']]);
  });

  it('waits for an open panel to finish closing before it opens another', () => {
    state.currentIndex = 2;
    state.panelStack = [{ type: 'layer1', id: '3' }];
    window.location.hash = '#s3l2';
    handleHashChange();
    expect(closeAllPanels).toHaveBeenCalled();
    vi.advanceTimersByTime(399);
    expect(openPanel).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(openPanel.mock.calls).toEqual([['layer1', '3']]);
  });

  it('does nothing when the named step and layer are already shown', () => {
    state.currentIndex = 2;
    state.panelStack = [{ type: 'layer1', id: '3' }];
    window.location.hash = '#s3l1';
    handleHashChange();
    expect(closeAllPanels).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('closes the panel only for a step-only fragment on the step with a panel open', () => {
    state.currentIndex = 2;
    state.panelStack = [{ type: 'layer1', id: '3' }];
    window.location.hash = '#s3';
    handleHashChange();
    expect(closeAllPanels).toHaveBeenCalled();
    expect(activateCard).not.toHaveBeenCalled();
  });

  it('a second change while a deep-link ladder is pending drops the first ladder', () => {
    window.location.hash = '#s3l1';
    handleHashChange();
    window.location.hash = '#s4l1';
    handleHashChange();
    vi.advanceTimersByTime(1000);
    expect(openPanel.mock.calls, 'only the second fragment opens a panel').toEqual([['layer1', '4']]);
  });

  it('a change while a scroll move is in flight moves through jumpScrollTo, which stands the move down', () => {
    state.scrollPosition = 1.6; // between steps, mid-animation
    window.location.hash = '#s5';
    handleHashChange();
    expect(jumpScrollTo).toHaveBeenCalledWith(5 * window.innerHeight);
    expect(state.scrollPosition).toBe(5);
  });

  it('moves through navigateToStep, not a direct Lenis scroll', () => {
    window.location.hash = '#s4';
    handleHashChange();
    expect(state.lenis.scrollTo, 'no direct Lenis scroll').not.toHaveBeenCalled();
    expect(jumpScrollTo).toHaveBeenCalledTimes(1);
  });

  it('in button mode it sets the counter and the buttons', () => {
    state.lenis = null;
    window.location.hash = '#s4';
    handleHashChange();
    expect(jumpButtonsTo).toHaveBeenCalledWith(3);
    expect(updateViewerInfo).toHaveBeenCalledWith(3);
  });

  it('two quick changes with a layer open at first open the second layer only after the close settles', () => {
    state.currentIndex = 2;
    state.panelStack = [{ type: 'layer1', id: '3' }];
    window.location.hash = '#s3';
    handleHashChange(); // closes layer 1; the stack is emptied by the real close
    state.panelStack = [];
    vi.advanceTimersByTime(50);
    window.location.hash = '#s4l1';
    handleHashChange();
    vi.advanceTimersByTime(399);
    expect(openPanel, 'refused by Bootstrap while the first offcanvas still hides').not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(openPanel.mock.calls).toEqual([['layer1', '4']]);
  });

  it('waits while an offcanvas is still hiding even with an empty stack', () => {
    document.body.innerHTML = '<div id="panel-layer1" class="offcanvas hiding"></div>';
    window.location.hash = '#s3l1';
    handleHashChange();
    vi.advanceTimersByTime(399);
    expect(openPanel).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(openPanel).toHaveBeenCalledTimes(1);
  });

  describe('sub-link (glossary) positions on the same step', () => {
    function glossaryLinkIn(layer, n) {
      document.body.innerHTML = `<div id="panel-glossary"></div><div id="panel-layer${layer}-content"><a id="gl" data-deep-link-n="${n}"></a></div>`;
      const link = document.getElementById('gl');
      link.click = vi.fn();
      return link;
    }

    it('#s3l1 to #s3l1g2 clicks glossary link 2', () => {
      state.currentIndex = 2;
      state.panelStack = [{ type: 'layer1', id: '3' }];
      const link = glossaryLinkIn(1, 2);
      window.location.hash = '#s3l1g2';
      handleHashChange();
      expect(closeAllPanels).not.toHaveBeenCalled();
      vi.advanceTimersByTime(10);
      expect(link.click).toHaveBeenCalledTimes(1);
    });

    it('#s3l1g1 (glossary open) to #s3l1 closes the glossary and leaves the layer open', () => {
      state.currentIndex = 2;
      state.panelStack = [{ type: 'layer1', id: '3' }];
      glossaryLinkIn(1, 2);
      writeHashWithGlossary(1);
      state.panelStack.push({ type: 'glossary', id: null });
      window.location.hash = '#s3l1';
      handleHashChange();
      expect(closePanel).toHaveBeenCalledWith('glossary');
      expect(closeAllPanels).not.toHaveBeenCalled();
    });

    it('#s3l1g1 to #s3l1g2 closes the glossary, then clicks link 2 after the close settles', () => {
      state.currentIndex = 2;
      state.panelStack = [{ type: 'layer1', id: '3' }];
      const link = glossaryLinkIn(1, 2);
      writeHashWithGlossary(1);
      state.panelStack.push({ type: 'glossary', id: null });
      window.location.hash = '#s3l1g2';
      handleHashChange();
      expect(closePanel).toHaveBeenCalledWith('glossary');
      vi.advanceTimersByTime(399);
      expect(link.click).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1);
      expect(link.click).toHaveBeenCalledTimes(1);
    });

    it('the open entry is read from the glossary panel, so a later write of the layer fragment does not clear it', () => {
      state.currentIndex = 2;
      state.panelStack = [{ type: 'layer1', id: '3' }];
      document.body.innerHTML = '<div id="panel-glossary"></div><div id="panel-layer1-content"></div>';
      writeHashWithGlossary(2);                       // g2 clicked
      state.panelStack.push({ type: 'glossary', id: null });
      writeHash();                                    // g1's hidden handler rewrites the layer fragment
      window.location.hash = '#s3l1';
      handleHashChange();
      expect(closePanel, 'glossary entry 2 is still open and must close').toHaveBeenCalledWith('glossary');
    });

    it('an open glossary entry with no recorded number is closed before another is clicked', () => {
      state.currentIndex = 2;
      state.panelStack = [{ type: 'layer1', id: '3' }, { type: 'glossary', id: null }];
      const link = glossaryLinkIn(1, 2); // no data-deep-link-n on #panel-glossary
      window.location.hash = '#s3l1g2';
      handleHashChange();
      expect(closePanel).toHaveBeenCalledWith('glossary');
      vi.advanceTimersByTime(399);
      expect(link.click).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1);
      expect(link.click).toHaveBeenCalledTimes(1);
    });

    it('the same layer and entry already shown does nothing', () => {
      state.currentIndex = 2;
      state.panelStack = [{ type: 'layer1', id: '3' }];
      const link = glossaryLinkIn(1, 2);
      writeHashWithGlossary(2);
      state.panelStack.push({ type: 'glossary', id: null });
      window.location.hash = '#s3l1g2';
      handleHashChange();
      vi.advanceTimersByTime(1000);
      expect(closePanel).not.toHaveBeenCalled();
      expect(closeAllPanels).not.toHaveBeenCalled();
      expect(link.click).not.toHaveBeenCalled();
    });
  });

  it.each(['#', '#s0'])('goes to the intro for %s while a move away from the intro is in flight', (frag) => {
    state.currentIndex = -1;
    isMoveInFlight.mockReturnValue(true);
    window.location.hash = frag;
    handleHashChange();
    expect(goToStep).toHaveBeenCalledWith(-1, 'backward');
    expect(jumpScrollTo).toHaveBeenCalledWith(0);
  });

  it('stands down an engine move in flight even on the step shown, then opens the panel', () => {
    state.currentIndex = 2;
    isMoveInFlight.mockReturnValue(true);
    window.location.hash = '#s3l1';
    handleHashChange();
    expect(jumpScrollTo, 'the move is stood down through the engine').toHaveBeenCalledWith(3 * window.innerHeight);
    vi.advanceTimersByTime(100);
    expect(openPanel.mock.calls).toEqual([['layer1', '3']]);
  });

  it('does nothing before the story has steps (embed or locked pages)', () => {
    state.steps = [];
    window.location.hash = '#s2';
    expect(() => handleHashChange()).not.toThrow();
    expect(activateCard).not.toHaveBeenCalled();
  });
});
