/**
 * Tests for Telar Story – Navigation: the story keys and a side card that
 * scrolls inside itself
 *
 * cardTakesKey (card-scroll.js) is replaced by a spy whose answer each test
 * sets. The keys pass it their direction and reach; a card that scrolled
 * cancels the key and nothing steps; a card at its edge hands the key to the
 * story, with Lenis and on the button path; a held key over a scroll-mode
 * card is cancelled and never steps; an open panel still takes the key first.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  cardTakesKey: vi.fn(() => 'none'),
  keyboardNav: vi.fn(),
  activateCard: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/card-scroll.js', () => ({
  cardTakesKey: mocks.cardTakesKey,
}));
vi.mock('../../assets/js/telar-story/panels.js', () => ({
  openPanel: vi.fn(),
  closeTopPanel: vi.fn(),
  stepHasLayer1Content: vi.fn(() => false),
  stepHasLayer2Content: vi.fn(() => false),
  closeAllPanels: vi.fn(),
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
  updateObjectCredits: vi.fn(),
}));
vi.mock('../../assets/js/telar-story/scroll-engine.js', () => ({
  advanceToStep: vi.fn(),
  keyboardNav: mocks.keyboardNav,
  buttonHeading: vi.fn(() => 0),
  jumpScrollTo: vi.fn(),
}));

import { initKeyboardNavigation } from '../../assets/js/telar-story/navigation.js';
import { state } from '../../assets/js/telar-story/state.js';

initKeyboardNavigation();

function pressCardKey(key, extras = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...extras });
  document.dispatchEvent(event);
  return event;
}

function storyOnStep(index, { lenis = true } = {}) {
  state.steps = Array.from({ length: 5 }, (_, i) => {
    const el = document.createElement('div');
    el.className = 'story-step';
    el.dataset.step = String(i + 1);
    return el;
  });
  state.currentIndex = index;
  state.currentMobileStep = index;
  state.mobileInIntro = false;
  state.mobileNavigationCooldown = false;
  state.mobileNavButtons = null;
  state.scrollLockActive = false;
  state.isPanelOpen = false;
  state.panelStack = [];
  state.viewerPlates = {};
  state.lenis = lenis ? {} : null;
}

beforeEach(() => {
  mocks.cardTakesKey.mockReset();
  mocks.cardTakesKey.mockReturnValue('none');
  mocks.keyboardNav.mockClear();
  mocks.activateCard.mockClear();
  storyOnStep(2);
});

describe('the reach each key asks the card for', () => {
  const cases = [
    ['ArrowDown', {}, 'forward', 'line'],
    ['PageDown', {}, 'forward', 'page'],
    ['ArrowUp', {}, 'backward', 'line'],
    ['PageUp', {}, 'backward', 'page'],
    [' ', {}, 'forward', 'page'],
    [' ', { shiftKey: true }, 'backward', 'page'],
  ];
  for (const [key, extras, direction, kind] of cases) {
    it(`${JSON.stringify(key)}${extras.shiftKey ? ' with Shift' : ''} asks for a ${kind} ${direction}`, () => {
      pressCardKey(key, extras);
      expect(mocks.cardTakesKey).toHaveBeenCalledWith(direction, kind);
    });
  }
});

describe('a card that scrolled', () => {
  beforeEach(() => { mocks.cardTakesKey.mockReturnValue('scrolled'); });

  for (const key of ['ArrowDown', 'PageDown', ' ', 'ArrowUp']) {
    it(`cancels ${JSON.stringify(key)} and moves no step, with Lenis`, () => {
      const ev = pressCardKey(key);
      expect(ev.defaultPrevented).toBe(true);
      expect(mocks.keyboardNav).not.toHaveBeenCalled();
    });
  }

  it('moves no step on the button path either', () => {
    storyOnStep(2, { lenis: false });
    const ev = pressCardKey('ArrowDown');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.activateCard).not.toHaveBeenCalled();
    expect(state.currentIndex).toBe(2);
  });
});

describe('a card at its edge', () => {
  beforeEach(() => { mocks.cardTakesKey.mockReturnValue('at-edge'); });

  it('hands ArrowDown to the story, with Lenis', () => {
    const ev = pressCardKey('ArrowDown');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.keyboardNav).toHaveBeenCalledWith('forward');
  });

  it('hands ArrowUp at the top back a step', () => {
    pressCardKey('ArrowUp');
    expect(mocks.keyboardNav).toHaveBeenCalledWith('backward');
  });

  it('hands the key to the buttons\' move without Lenis', () => {
    storyOnStep(2, { lenis: false });
    pressCardKey('PageDown');
    expect(mocks.activateCard).toHaveBeenCalledWith(3, 'forward');
    expect(state.currentIndex).toBe(3);
  });
});

describe('a held key', () => {
  it('is cancelled at the card\'s edge and moves no step', () => {
    mocks.cardTakesKey.mockReturnValue('at-edge');
    const ev = pressCardKey('ArrowDown', { repeat: true });
    expect(mocks.cardTakesKey).toHaveBeenCalledWith('forward', 'line');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.keyboardNav).not.toHaveBeenCalled();
  });

  it('scrolls the card and is cancelled while the card has room', () => {
    mocks.cardTakesKey.mockReturnValue('scrolled');
    const ev = pressCardKey(' ', { repeat: true });
    expect(mocks.cardTakesKey).toHaveBeenCalledWith('forward', 'page');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.keyboardNav).not.toHaveBeenCalled();
  });

  it('is left alone where no card scrolls', () => {
    const ev = pressCardKey('ArrowDown', { repeat: true });
    expect(ev.defaultPrevented).toBe(false);
    expect(mocks.keyboardNav).not.toHaveBeenCalled();
  });
});

describe('an open panel', () => {
  it('takes the key before the card', () => {
    const panel = document.createElement('div');
    panel.id = 'panel-layer1';
    const body = document.createElement('div');
    body.className = 'offcanvas-body';
    body.scrollBy = vi.fn();
    panel.append(body);
    document.body.append(panel);
    state.isPanelOpen = true;
    state.panelStack = [{ type: 'layer1' }];

    pressCardKey('ArrowDown');

    expect(body.scrollBy).toHaveBeenCalled();
    expect(mocks.cardTakesKey).not.toHaveBeenCalled();
    panel.remove();
  });
});
