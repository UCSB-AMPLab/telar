/**
 * Tests for the current step under button navigation.
 *
 * Vertical layouts and iPads navigate with the previous/next buttons and have
 * no scroll engine. state.currentIndex is still the current step there: the
 * fragment, the layer keys and the nav button all read it. These drive the
 * real navigation and deep-link modules through the buttons, the keyboard and
 * a deep link, with no Lenis, and read what each reader sees. The blocks that
 * give the story a Lenis, as embed mode has, check that the buttons leave
 * currentIndex to the scroll engine there, move the story through it, and
 * follow the steps it reports.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  openPanel: vi.fn(),
  closeAllPanels: vi.fn(),
  activateCard: vi.fn(),
  advanceToStep: vi.fn(() => true),
  buttonHeading: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/panels.js', () => ({
  openPanel: mocks.openPanel,
  closeAllPanels: mocks.closeAllPanels,
  closeTopPanel: vi.fn(),
  stepHasLayer1Content: (step) => !!step.layer1_title,
  stepHasLayer2Content: () => false,
}));

vi.mock('../../assets/js/telar-story/card-pool.js', () => ({
  activateCard: mocks.activateCard,
  releaseTitleCardsForIntro: vi.fn(),
  reconcileStackForJump: vi.fn(),
  reconcilePlatesForJump: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/viewer.js', () => ({
  initializeLoadingShimmer: vi.fn(),
  showViewerSkeletonState: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/scroll-engine.js', () => ({
  advanceToStep: mocks.advanceToStep,
  buttonHeading: mocks.buttonHeading,
  keyboardNav: vi.fn(),
  jumpScrollTo: vi.fn(),
}));

import * as navigation from '../../assets/js/telar-story/navigation.js';
import { initializeButtonNavigation } from '../../assets/js/telar-story/navigation.js';
import { applyDeepLinkOnLoad, navigateToStep, navigateToIntro } from '../../assets/js/telar-story/deep-link.js';
import { state } from '../../assets/js/telar-story/state.js';

const STEPS = 5;

/** A story page: the intro, five steps, and the counter the steps update. */
function buildButtonPage() {
  document.body.innerHTML = `
    <div class="story-intro"></div>
    <div id="step-counter"></div><div id="current-object-title"></div>
    ${Array.from({ length: STEPS }, (_, i) =>
      `<div class="story-step" data-step="${i + 1}"></div>`).join('')}`;
  window.telarLang = {};
  // Step 4 carries a layer 1; the others do not.
  window.storyData = {
    steps: Array.from({ length: STEPS }, (_, i) =>
      ({ step: String(i + 1), ...(i === 3 ? { layer1_title: 'More' } : {}) })),
  };
}

/** Reset what a page load starts from, then start button navigation. */
function boot({ hash = '', lenis = null } = {}) {
  buildButtonPage();
  history.replaceState(null, '', `/telar/stories/s/${hash}`);
  Object.assign(state, {
    currentIndex: -1,
    currentMobileStep: 0,
    mobileInIntro: false,
    mobileNavButtons: null,
    mobileNavigationCooldown: false,
    lenis: null,
    panelStack: [],
    isPanelOpen: false,
    scrollLockActive: false,
    viewerPlates: {},
    stepToScene: {},
    textCards: {},
    onStepChange: vi.fn(),
  });
  initializeButtonNavigation();
  state.lenis = lenis;
  applyDeepLinkOnLoad();
}

/** Tap a button; the tap cooldown is a timer, so it is lifted between taps. */
function tap(which) {
  state.mobileNavigationCooldown = false;
  document.querySelector(which === 'next' ? '.mobile-next' : '.mobile-prev').click();
}

function press(key) {
  state.mobileNavigationCooldown = false;
  document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
}

const lastNavButtonIndex = () => state.onStepChange.mock.calls.at(-1)?.[0];

beforeEach(() => {
  mocks.openPanel.mockClear();
  mocks.closeAllPanels.mockClear();
  mocks.activateCard.mockClear();
  mocks.advanceToStep.mockClear();
  // The engine, as the buttons see it: at rest on the current step.
  mocks.buttonHeading.mockReset();
  mocks.buttonHeading.mockImplementation(() => state.currentIndex);
  document.querySelectorAll('.mobile-nav').forEach((el) => el.remove());
});

describe('button navigation: the current step', () => {
  it('starts on the intro', () => {
    boot();
    expect(state.currentIndex).toBe(-1);
    expect(location.hash).toBe('');
  });

  it('a deep link puts the current step on its step', () => {
    boot({ hash: '#s3' });
    expect(state.currentIndex).toBe(2);
    expect(location.hash).toBe('#s3');
  });

  it('the next button moves the current step and writes the fragment', () => {
    boot({ hash: '#s3' });
    tap('next');
    expect(state.currentIndex).toBe(3);
    expect(state.currentMobileStep).toBe(3);
    expect(location.hash).toBe('#s4');
    expect(lastNavButtonIndex()).toBe(3);
  });

  it('a deep link enables the previous button', () => {
    boot({ hash: '#s3' });
    expect(document.querySelector('.mobile-prev').disabled).toBe(false);
  });

  it('the previous button moves it back', () => {
    boot({ hash: '#s3' });
    tap('prev');
    expect(state.currentIndex).toBe(1);
    expect(location.hash).toBe('#s2');
  });

  it('leaving the intro puts the reader on step 1', () => {
    boot();
    tap('next');
    expect(state.currentIndex).toBe(0);
    expect(location.hash).toBe('#s1');
    expect(lastNavButtonIndex()).toBe(0);
  });

  it('returning to the intro clears the step and the fragment', () => {
    boot({ hash: '#s1' });
    tap('prev');
    expect(state.mobileInIntro).toBe(true);
    expect(state.currentIndex).toBe(-1);
    expect(location.hash).toBe('');
    expect(lastNavButtonIndex()).toBe(-1);
  });

  it('a jump from within the story moves the current step', () => {
    boot();
    navigateToStep(5);
    expect(state.currentIndex).toBe(4);
    expect(location.hash).toBe('#s5');
    expect(lastNavButtonIndex()).toBe(4);
  });
});

describe('button navigation: the keyboard', () => {
  it('Right arrow opens layer 1 of the deep-linked step', () => {
    boot({ hash: '#s4' });
    press('ArrowRight');
    expect(mocks.openPanel).toHaveBeenCalledWith('layer1', '4');
  });

  it('Right arrow opens layer 1 of a step reached by the button', () => {
    boot({ hash: '#s3' });
    tap('next');
    press('ArrowRight');
    expect(mocks.openPanel).toHaveBeenCalledWith('layer1', '4');
  });

  it('Down arrow makes the next button\'s move', () => {
    boot({ hash: '#s3' });
    press('ArrowDown');
    expect(state.currentIndex).toBe(3);
    expect(document.querySelector('.story-step[data-step="4"]').classList.contains('mobile-active')).toBe(true);
    expect(location.hash).toBe('#s4');
  });

  it('Up arrow on step 1 returns to the intro', () => {
    boot({ hash: '#s1' });
    press('ArrowUp');
    expect(state.currentIndex).toBe(-1);
    expect(state.mobileInIntro).toBe(true);
  });
});

describe('buttons with a scroll engine (embed mode)', () => {
  it('leave the current step to the engine', () => {
    boot({ lenis: {} });
    state.mobileInIntro = false;
    state.currentMobileStep = 1;
    state.currentIndex = 1;
    tap('next');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(2);
    expect(state.currentMobileStep).toBe(1);
    expect(state.currentIndex).toBe(1);
  });

  it('leave it to the engine when leaving the intro', () => {
    boot({ lenis: {} });
    tap('next');
    expect(state.mobileInIntro).toBe(true);
    expect(state.currentIndex).toBe(-1);
    expect(state.onStepChange).not.toHaveBeenCalled();
  });
});

/** Whether each button is disabled. */
const disabled = () => ({
  prev: document.querySelector('.mobile-prev').disabled,
  next: document.querySelector('.mobile-next').disabled,
});

/** A scroll engine's Lenis, as far as the return to the intro touches it. */
const lenisStub = () => ({ stop: vi.fn(), start: vi.fn(), scrollTo: vi.fn(), animatedScroll: 0, targetScroll: 0 });

describe('the intro, however the buttons arrive at it', () => {
  it('back to the start from a step walked to disables the previous button', () => {
    boot();
    const onLoad = disabled();
    tap('next');
    tap('next');
    expect(disabled().prev).toBe(false);

    navigateToIntro();
    expect(state.mobileInIntro).toBe(true);
    expect(disabled()).toEqual(onLoad);
    expect(onLoad.prev).toBe(true);
  });

  it('back to the start from a deep link disables the previous button', () => {
    boot({ hash: '#s3' });
    navigateToIntro();
    expect(disabled()).toEqual({ prev: true, next: false });
    expect(location.hash).toBe('');
  });

  it('next after back to the start leaves the intro for step 1', () => {
    boot({ hash: '#s3' });
    navigateToIntro();
    mocks.activateCard.mockClear();
    tap('next');
    expect(mocks.activateCard).toHaveBeenCalledWith(0, 'forward');
    expect(state.currentIndex).toBe(0);
    expect(location.hash).toBe('#s1');
    expect(disabled().prev).toBe(false);
  });

  it('back to the start in embed mode disables the previous button', () => {
    vi.stubGlobal('requestAnimationFrame', () => 0);
    try {
      boot({ lenis: lenisStub() });
      state.mobileInIntro = false;
      state.currentMobileStep = 2;
      state.currentIndex = 2;
      navigateToIntro();
      expect(disabled()).toEqual({ prev: true, next: false });

      tap('next');
      expect(state.currentMobileStep).toBe(0);
      expect(mocks.advanceToStep).toHaveBeenCalledWith(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('back to the start from a deep link in embed mode, then next, leaves for step 1', () => {
    vi.stubGlobal('requestAnimationFrame', () => 0);
    try {
      boot({ hash: '#s3', lenis: lenisStub() });
      expect(state.currentIndex).toBe(2);

      navigateToIntro();
      expect(disabled()).toEqual({ prev: true, next: false });

      tap('next');
      expect(state.currentMobileStep).toBe(0);
      expect(mocks.advanceToStep).toHaveBeenCalledWith(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

// With a panel open, Back to Start and a contents link close it first, as its
// own back button would, and only then move the story.
describe('back to the start or a contents link with a panel open', () => {
  /** The order of the close and the first move after it, from the mocks. */
  const closedFirst = (moved) =>
    mocks.closeAllPanels.mock.invocationCallOrder[0] < moved.mock.invocationCallOrder.at(-1);

  it('back to the start closes the panels before the story returns to the intro', () => {
    boot({ hash: '#s4' });
    state.onStepChange.mockClear();
    navigateToIntro();
    expect(mocks.closeAllPanels).toHaveBeenCalledTimes(1);
    expect(closedFirst(state.onStepChange)).toBe(true);
    expect(state.currentIndex).toBe(-1);
  });

  it('a contents link closes the panels before the story moves to its step', () => {
    boot({ hash: '#s2' });
    mocks.activateCard.mockClear();
    navigateToStep(4);
    expect(mocks.closeAllPanels).toHaveBeenCalledTimes(1);
    expect(closedFirst(mocks.activateCard)).toBe(true);
    expect(state.currentIndex).toBe(3);
  });
});

// In an embed the scroll engine moves the story, whether a button, a key, the
// wheel or a link started the move, and the buttons carry on from wherever it
// put the reader.
describe('buttons beside a scroll engine (embed mode)', () => {
  it('next from the intro moves the engine to step 1', () => {
    boot({ lenis: {} });
    tap('next');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(0);
  });

  it('a tap leaves the step counter to the engine, hidden on the intro until the move lands', () => {
    boot({ lenis: {} });
    const counter = document.getElementById('step-counter');
    counter.classList.add('d-none');
    tap('next');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(0);
    expect(counter.classList.contains('d-none')).toBe(true);
    expect(mocks.activateCard).not.toHaveBeenCalled();
  });

  it('a tap does not move the buttons before the engine does', () => {
    boot({ lenis: {} });
    tap('next');
    expect(state.mobileInIntro).toBe(true);
    expect(disabled()).toEqual({ prev: true, next: false });

    navigation.followEngine(0);                 // the scroll reaches step 1
    expect(disabled()).toEqual({ prev: false, next: false });
  });

  it('previous from step 1 moves the engine to the intro', () => {
    boot({ lenis: {} });
    state.currentIndex = 0;
    navigation.followEngine(0);
    tap('prev');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(-1);
  });

  it('a second tap goes on from where the engine is heading', () => {
    boot({ lenis: {} });
    state.currentIndex = 1;
    navigation.followEngine(1);
    mocks.buttonHeading.mockReturnValue(2);     // a first tap still in flight
    tap('next');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(3);
  });

  it('a tap the engine refuses leaves the buttons where they were, and the next tap is taken', () => {
    boot({ lenis: {} });
    state.currentIndex = 1;
    navigation.followEngine(1);
    mocks.advanceToStep.mockReturnValueOnce(false);
    state.mobileNavigationCooldown = false;
    document.querySelector('.mobile-next').click();
    expect(state.currentMobileStep).toBe(1);
    expect(state.mobileNavigationCooldown).toBe(false);
  });

  it('the buttons follow a step the engine reached, and next goes on from it', () => {
    boot({ lenis: {} });
    state.currentIndex = 2;
    navigation.followEngine(2);
    expect(state.mobileInIntro).toBe(false);
    expect(state.currentMobileStep).toBe(2);
    expect(document.querySelector('.story-step[data-step="3"]').classList.contains('mobile-active')).toBe(true);
    expect(disabled()).toEqual({ prev: false, next: false });

    tap('next');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(3);
  });

  it('the buttons follow the engine onto the last step', () => {
    boot({ lenis: {} });
    navigation.followEngine(STEPS - 1);
    expect(disabled()).toEqual({ prev: false, next: true });
  });

  it('the buttons follow the engine back to the intro, and next leaves it', () => {
    boot({ lenis: {} });
    navigation.followEngine(2);
    navigation.followEngine(-1);
    expect(state.mobileInIntro).toBe(true);
    expect(disabled()).toEqual({ prev: true, next: false });

    tap('next');
    expect(mocks.advanceToStep).toHaveBeenCalledWith(0);
  });

  it('a story with no buttons has nothing to follow', () => {
    buildButtonPage();
    Object.assign(state, { mobileNavButtons: null, currentMobileStep: 0, mobileInIntro: false });
    state.steps = Array.from(document.querySelectorAll('.story-step'));
    navigation.followEngine(2);
    expect(document.querySelectorAll('.mobile-active')).toHaveLength(0);
    expect(state.currentMobileStep).toBe(0);
  });
});

// The intro's hint is chosen in CSS from this marker, so it names the buttons
// wherever they are the navigation in use: an iPad held either way, an embed,
// and a window opened narrow and then widened.
describe('the document says button navigation is in use', () => {
  beforeEach(() => {
    delete document.documentElement.dataset.navigation;
  });

  it('is unmarked before button navigation starts', () => {
    buildButtonPage();
    expect(document.documentElement.dataset.navigation).toBeUndefined();
  });

  it('is marked once button navigation starts', () => {
    boot();
    expect(document.documentElement.dataset.navigation).toBe('buttons');
  });

  it('stays marked when the buttons already exist', () => {
    boot();
    delete document.documentElement.dataset.navigation;
    initializeButtonNavigation();
    expect(document.querySelectorAll('.mobile-nav')).toHaveLength(1);
    expect(document.documentElement.dataset.navigation).toBe('buttons');
  });
});
