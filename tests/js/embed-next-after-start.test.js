/**
 * Tests for Next after Back to Start in an embed.
 *
 * The real buttons, navigation, deep-link and scroll-engine modules run
 * together over the harness's modelled Lenis. After Back to Start the tap on
 * Next is a button move like any other: the engine's step, the counter and the
 * address must all agree with step 1, the card drawn.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('lenis', async () => (await import('./scroll-engine-harness.js')).lenisModule);
vi.mock('lenis/snap', async () => (await import('./scroll-engine-harness.js')).snapModule);
vi.mock('../../assets/js/telar-story/card-pool.js', async () => ({
  ...(await import('./scroll-engine-harness.js')).cardPoolModule,
  releaseTitleCardsForIntro: vi.fn(),
}));
vi.mock('../../assets/js/telar-story/iiif-card.js',
  async () => (await import('./scroll-engine-harness.js')).iiifCardModule);
vi.mock('../../assets/js/telar-story/camera-travel.js',
  async () => (await import('./scroll-engine-harness.js')).cameraTravelModule);
vi.mock('../../assets/js/telar-story/viewer.js',
  async () => (await import('./scroll-engine-harness.js')).viewerModule);

import { initScrollEngine } from '../../assets/js/telar-story/scroll-engine.js';
import { initializeButtonNavigation } from '../../assets/js/telar-story/navigation.js';
import { navigateToIntro, applyDeepLinkOnLoad } from '../../assets/js/telar-story/deep-link.js';
import { state } from '../../assets/js/telar-story/state.js';
import {
  mocks, stubEngineGlobals, resetState, modelLenis, landMove, restAt,
} from './scroll-engine-harness.js';

const STEPS = 5;

describe('Next after Back to Start in an embed', () => {
  let frames;

  beforeEach(() => {
    document.body.innerHTML = `
      <div class="scroll-surface"></div>
      <div class="story-intro"></div>
      <div id="step-counter"></div><div id="current-object-title"></div>
      <div class="card-stack">${Array.from({ length: STEPS }, (_, i) =>
        `<div class="story-step" data-step="${i + 1}"></div>`).join('')}</div>`;
    window.telarLang = {};
    window.storyData = { steps: Array.from({ length: STEPS }, (_, i) => ({ step: String(i + 1) })) };
    history.replaceState(null, '', '/telar/stories/s/#s3');
    mocks.mockActivateCard.mockClear();
    resetState({
      currentIndex: -1, viewerPlates: {}, stepToScene: {}, textCards: {}, panelStack: [],
      isPanelOpen: false, scrollLockActive: false, mobileNavButtons: null,
      mobileNavigationCooldown: false, onStepChange: vi.fn(),
    });
    state.steps = Array.from(document.querySelectorAll('.story-step'));
    document.querySelectorAll('.mobile-nav').forEach((el) => el.remove());
    stubEngineGlobals();
    vi.useFakeTimers();
    frames = [];
    vi.stubGlobal('requestAnimationFrame', vi.fn((cb) => { frames.push(cb); }));
    initializeButtonNavigation();
    initScrollEngine(STEPS);
    state.lenis = modelLenis();
    restAt(3);                                    // deep link: step 3
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('puts the engine, the counter and the address on step 1', () => {
    expect(state.currentIndex).toBe(2);
    navigateToIntro();
    frames.splice(0).forEach((cb) => cb(0));
    expect(state.currentIndex).toBe(-1);
    expect(location.hash).toBe('');

    state.mobileNavigationCooldown = false;
    document.querySelector('.mobile-next').click();
    landMove();

    expect(mocks.mockActivateCard).toHaveBeenLastCalledWith(0, 'forward');
    expect(state.currentIndex).toBe(0);
    expect(document.getElementById('current-object-title').textContent).toBe('Step 1 / 5');
    expect(document.getElementById('step-counter').classList.contains('d-none')).toBe(false);
    expect(location.hash).toBe('#s1');
  });
});
