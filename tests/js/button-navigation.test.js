/**
 * Tests for the current step under button navigation.
 *
 * Vertical layouts and iPads navigate with the previous/next buttons and have
 * no scroll engine. state.currentIndex is still the current step there: the
 * fragment, the layer keys and the nav button all read it. These drive the
 * real navigation and deep-link modules through the buttons, the keyboard and
 * a deep link, with no Lenis, and read what each reader sees. The last block
 * gives the story a Lenis, as embed mode has, and checks the buttons leave
 * currentIndex to the scroll engine there.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  openPanel: vi.fn(),
  activateCard: vi.fn(),
  advanceToStep: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/panels.js', () => ({
  openPanel: mocks.openPanel,
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
  keyboardNav: vi.fn(),
}));

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
  mocks.activateCard.mockClear();
  mocks.advanceToStep.mockClear();
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
    expect(state.currentMobileStep).toBe(2);
    expect(state.currentIndex).toBe(1);
  });

  it('leave it to the engine when leaving the intro', () => {
    boot({ lenis: {} });
    tap('next');
    expect(state.mobileInIntro).toBe(false);
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
const lenisStub = () => ({ stop: vi.fn(), start: vi.fn(), animatedScroll: 0, targetScroll: 0 });

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
      expect(mocks.advanceToStep).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('back to the start from a deep link in embed mode, then next, leaves for step 1', () => {
    vi.stubGlobal('requestAnimationFrame', () => 0);
    try {
      boot({ hash: '#s3', lenis: { ...lenisStub(), scrollTo: vi.fn() } });
      expect(state.currentIndex).toBe(2);

      navigateToIntro();
      expect(disabled()).toEqual({ prev: true, next: false });

      mocks.activateCard.mockClear();
      tap('next');
      expect(mocks.activateCard).toHaveBeenCalledWith(0, 'forward');
      expect(state.currentMobileStep).toBe(0);
      expect(mocks.advanceToStep).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
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
