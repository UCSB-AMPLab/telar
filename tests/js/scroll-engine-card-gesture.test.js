/**
 * Tests for Telar Story – Scroll Engine: a gesture the side card owns
 *
 * card-scroll.js cancels and stops every event of a gesture the side card
 * owns before Lenis sees it. Should one reach the engine's virtual-scroll
 * listener all the same, the engine reads the owner and leaves it alone: no
 * scrub, and no takeover of a keyboard move in flight. A gesture the story
 * owns still stands the move down.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const holds = vi.hoisted(() => ({ value: false }));

vi.mock('lenis', async () => (await import('./scroll-engine-harness.js')).lenisModule);
vi.mock('lenis/snap', async () => (await import('./scroll-engine-harness.js')).snapModule);
vi.mock('../../assets/js/telar-story/card-pool.js',
  async () => (await import('./scroll-engine-harness.js')).cardPoolModule);
vi.mock('../../assets/js/telar-story/iiif-card.js',
  async () => (await import('./scroll-engine-harness.js')).iiifCardModule);
vi.mock('../../assets/js/telar-story/navigation.js',
  async () => (await import('./scroll-engine-harness.js')).navigationModule);
vi.mock('../../assets/js/telar-story/viewer.js',
  async () => (await import('./scroll-engine-harness.js')).viewerModule);
vi.mock('../../assets/js/telar-story/card-scroll.js', () => ({
  cardHoldsGesture: () => holds.value,
}));

import { initScrollEngine, keyboardNav } from '../../assets/js/telar-story/scroll-engine.js';
import { state } from '../../assets/js/telar-story/state.js';
import {
  engineStory, stubEngineGlobals, readerTakesOver, wheelEvent, resetState,
  modelLenis, landMove, cardWheelEvent,
} from './scroll-engine-harness.js';

describe('a gesture the side card owns, reaching the engine', () => {
  let card;
  const stack = () => document.querySelector('.card-stack');

  beforeEach(() => {
    engineStory(5);
    card = document.createElement('div');
    card.className = 'text-card';
    stack().append(card);
    resetState({ currentIndex: -1 });
    stubEngineGlobals();
    vi.useFakeTimers();
    initScrollEngine(5);
    state.lenis = modelLenis();
  });

  afterEach(() => {
    holds.value = false;
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('leaves a keyboard move to land and clear its token, with no scrub', () => {
    holds.value = true;
    keyboardNav('forward');
    readerTakesOver(cardWheelEvent({ card, deltaY: 120 }));

    expect(stack().classList.contains('is-scrubbing')).toBe(false);
    landMove();
    expect(state.scrollPosition).toBe(1);
    expect(state.currentIndex).toBe(0);

    // The token is clear: the next press moves on from the landing.
    keyboardNav('forward');
    expect(state.lenis.inFlight?.px).toBe(2 * window.innerHeight);
  });

  it('carries a second press on from the move the card left running', () => {
    holds.value = true;
    keyboardNav('forward');
    readerTakesOver(cardWheelEvent({ card, deltaY: 120 }));
    keyboardNav('forward');

    expect(state.lenis.inFlight?.px).toBe(2 * window.innerHeight);
  });

  it('stands the move down for a gesture the story owns', () => {
    keyboardNav('forward');
    readerTakesOver(wheelEvent({ deltaY: 120 }));

    expect(stack().classList.contains('is-scrubbing')).toBe(true);
    // The move has let go: the next press reads the scroll, still at 0.
    keyboardNav('forward');
    expect(state.lenis.inFlight?.px).toBe(1 * window.innerHeight);
  });
});
