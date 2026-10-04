/**
 * Tests for Telar Story – Navigation: the story keys
 *
 * A step key moves the step at once, with Lenis and on the button path; a held
 * key is cancelled and never steps again; Home and End go to the ends of the
 * story; an open panel or dialog still takes the key first.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  keyboardNav: vi.fn(),
  activateCard: vi.fn(),
  navigateToIntro: vi.fn(),
  navigateToStep: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/deep-link.js', () => ({
  writeHash: vi.fn(),
  navigateToIntro: mocks.navigateToIntro,
  navigateToStep: mocks.navigateToStep,
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
  mocks.keyboardNav.mockClear();
  mocks.activateCard.mockClear();
  mocks.navigateToIntro.mockClear();
  mocks.navigateToStep.mockClear();
  storyOnStep(2);
});

describe('a key held down', () => {
  const held = [
    ['ArrowDown', {}, 'forward'],
    ['PageDown', {}, 'forward'],
    [' ', {}, 'forward'],
    ['ArrowUp', {}, 'backward'],
    ['PageUp', {}, 'backward'],
    [' ', { shiftKey: true }, 'backward'],
  ];
  for (const [key, extras, direction] of held) {
    it(`${JSON.stringify(key)}${extras.shiftKey ? ' with Shift' : ''} moves one step and every repeat is cancelled`, () => {
      const first = pressCardKey(key, extras);
      const repeats = Array.from({ length: 39 }, () => pressCardKey(key, { ...extras, repeat: true }));

      expect(first.defaultPrevented).toBe(true);
      expect(repeats.every((ev) => ev.defaultPrevented)).toBe(true);
      expect(mocks.keyboardNav).toHaveBeenCalledTimes(1);
      expect(mocks.keyboardNav).toHaveBeenCalledWith(direction);
    });
  }

  it('moves one step on the button path too', () => {
    storyOnStep(2, { lenis: false });
    pressCardKey('ArrowDown');
    for (let i = 0; i < 39; i++) pressCardKey('ArrowDown', { repeat: true });
    expect(state.currentIndex).toBe(3);
  });

  it('leaves Space on a focused control to the control', () => {
    const button = document.createElement('button');
    document.body.append(button);
    const ev = new KeyboardEvent('keydown', { key: ' ', repeat: true, bubbles: true, cancelable: true });
    button.dispatchEvent(ev);
    button.remove();
    expect(ev.defaultPrevented).toBe(false);
    expect(mocks.keyboardNav).not.toHaveBeenCalled();
  });

  it('still cancels Space on a link', () => {
    const link = document.createElement('a');
    link.href = '#';
    document.body.append(link);
    const ev = new KeyboardEvent('keydown', { key: ' ', repeat: true, bubbles: true, cancelable: true });
    link.dispatchEvent(ev);
    link.remove();
    expect(ev.defaultPrevented).toBe(true);
  });

  const heldOn = (el, key) => {
    document.body.append(el);
    const ev = new KeyboardEvent('keydown', { key, repeat: true, bubbles: true, cancelable: true });
    el.dispatchEvent(ev);
    el.remove();
    return ev;
  };

  for (const [name, make] of [
    ['a select', () => document.createElement('select')],
    ['a text input', () => document.createElement('input')],
    ['a textarea', () => document.createElement('textarea')],
    ['an editable element', () => {
      const div = document.createElement('div');
      div.setAttribute('contenteditable', 'true');
      return div;
    }],
  ]) {
    for (const key of ['ArrowDown', 'PageDown']) {
      it(`cancels ${key} held on ${name} outside a dialog, which would scroll the page at its edge`, () => {
        const ev = heldOn(make(), key);
        expect(ev.defaultPrevented).toBe(true);
        expect(mocks.keyboardNav).not.toHaveBeenCalled();
      });
    }
  }

  it('leaves ArrowDown held on a select inside an open dialog to the select', () => {
    const dialog = document.createElement('div');
    dialog.className = 'modal show';
    const select = document.createElement('select');
    dialog.append(select);
    document.body.append(dialog);
    const ev = new KeyboardEvent('keydown', { key: 'ArrowDown', repeat: true, bubbles: true, cancelable: true });
    select.dispatchEvent(ev);
    dialog.remove();
    expect(ev.defaultPrevented).toBe(false);
  });

  for (const [name, make] of [
    ['a button', () => document.createElement('button')],
    ['a summary', () => document.createElement('summary')],
    ...['checkbox', 'button', 'submit', 'reset', 'image', 'file', 'color'].map((type) => [
      `a ${type} input`, () => Object.assign(document.createElement('input'), { type }),
    ]),
  ]) {
    it(`cancels ArrowDown held on ${name}, which does not read arrows`, () => {
      const ev = heldOn(make(), 'ArrowDown');
      expect(ev.defaultPrevented).toBe(true);
      expect(mocks.keyboardNav).not.toHaveBeenCalled();
    });
  }

  it('leaves ArrowDown held inside an open dialog to the dialog', () => {
    const dialog = document.createElement('div');
    dialog.className = 'modal show';
    const inner = document.createElement('div');
    inner.tabIndex = -1;
    dialog.append(inner);
    document.body.append(dialog);
    const ev = new KeyboardEvent('keydown', { key: 'ArrowDown', repeat: true, bubbles: true, cancelable: true });
    inner.dispatchEvent(ev);
    dialog.remove();
    expect(ev.defaultPrevented).toBe(false);
  });

  it('leaves a key the story does not read to the browser', () => {
    for (const key of ['PageLeft', 'a']) {
      expect(pressCardKey(key, { repeat: true }).defaultPrevented).toBe(false);
    }
  });
});

describe('an open panel', () => {
  it('takes the key before the story', () => {
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
    panel.remove();
  });
});

function openDialogTarget() {
  const dialog = document.createElement('div');
  dialog.className = 'modal show';
  const inner = document.createElement('div');
  inner.tabIndex = -1;
  dialog.append(inner);
  document.body.append(dialog);
  return { dialog, inner };
}

function pressOn(el, key, extras = {}) {
  const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...extras });
  el.dispatchEvent(ev);
  return ev;
}

describe('Home and End', () => {
  it('Home goes to the intro through the engine and cancels the native jump', () => {
    const ev = pressCardKey('Home');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.navigateToIntro).toHaveBeenCalledTimes(1);
    expect(mocks.navigateToStep).not.toHaveBeenCalled();
  });

  it('End goes to the last step through the engine and cancels the native jump', () => {
    const ev = pressCardKey('End');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.navigateToStep).toHaveBeenCalledWith(5);
    expect(mocks.navigateToIntro).not.toHaveBeenCalled();
  });

  it('moves the same way on the button path', () => {
    storyOnStep(2, { lenis: false });
    pressCardKey('Home');
    pressCardKey('End');
    expect(mocks.navigateToIntro).toHaveBeenCalledTimes(1);
    expect(mocks.navigateToStep).toHaveBeenCalledWith(5);
  });

  it('cancels the key and moves nothing under a scroll lock', () => {
    state.scrollLockActive = true;
    const ev = pressCardKey('End');
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.navigateToStep).not.toHaveBeenCalled();
  });

  for (const key of ['Home', 'End']) {
    it(`a held ${key} takes no further action and is cancelled`, () => {
      const repeats = Array.from({ length: 39 }, () => pressCardKey(key, { repeat: true }));
      expect(repeats.every((ev) => ev.defaultPrevented)).toBe(true);
      expect(mocks.navigateToIntro).not.toHaveBeenCalled();
      expect(mocks.navigateToStep).not.toHaveBeenCalled();
    });

    it(`leaves ${key} alone in an open dialog, first press and repeat`, () => {
      const { dialog, inner } = openDialogTarget();
      const first = pressOn(inner, key);
      const repeat = pressOn(inner, key, { repeat: true });
      dialog.remove();
      expect(first.defaultPrevented).toBe(false);
      expect(repeat.defaultPrevented).toBe(false);
      expect(mocks.navigateToIntro).not.toHaveBeenCalled();
      expect(mocks.navigateToStep).not.toHaveBeenCalled();
    });

    it(`leaves ${key} alone in an open panel, first press and repeat`, () => {
      state.isPanelOpen = true;
      state.panelStack = [{ type: 'layer1' }];
      const first = pressCardKey(key);
      const repeat = pressCardKey(key, { repeat: true });
      expect(first.defaultPrevented).toBe(false);
      expect(repeat.defaultPrevented).toBe(false);
      expect(mocks.navigateToIntro).not.toHaveBeenCalled();
      expect(mocks.navigateToStep).not.toHaveBeenCalled();
    });
  }
});

describe('the first press inside an open dialog', () => {
  for (const [key, extras] of [
    ['ArrowDown', {}], ['ArrowUp', {}], ['PageDown', {}], ['PageUp', {}],
    [' ', {}], [' ', { shiftKey: true }],
  ]) {
    it(`leaves ${JSON.stringify(key)}${extras.shiftKey ? ' with Shift' : ''} to the dialog and steps nothing`, () => {
      const { dialog, inner } = openDialogTarget();
      const ev = pressOn(inner, key, extras);
      dialog.remove();
      expect(ev.defaultPrevented).toBe(false);
      expect(mocks.keyboardNav).not.toHaveBeenCalled();
      });
  }

  it('leaves ArrowDown on a select in the dialog to the select', () => {
    const { dialog, inner } = openDialogTarget();
    const select = document.createElement('select');
    inner.append(select);
    const ev = pressOn(select, 'ArrowDown');
    dialog.remove();
    expect(ev.defaultPrevented).toBe(false);
    expect(mocks.keyboardNav).not.toHaveBeenCalled();
  });

  it('still steps on ArrowDown from a field outside a dialog', () => {
    const input = document.createElement('input');
    document.body.append(input);
    const ev = pressOn(input, 'ArrowDown');
    input.remove();
    expect(ev.defaultPrevented).toBe(true);
    expect(mocks.keyboardNav).toHaveBeenCalledWith('forward');
  });
});

describe('ArrowLeft, ArrowRight and Escape inside an open dialog', () => {
  function panelOpenBehind() {
    state.isPanelOpen = true;
    state.panelStack = [{ type: 'layer1' }];
  }

  for (const withPanel of [false, true]) {
    for (const key of ['ArrowLeft', 'ArrowRight', 'Escape']) {
      it(`leaves ${key} to the dialog and acts on no panel${withPanel ? ' with a panel open behind' : ''}`, async () => {
        const panels = await import('../../assets/js/telar-story/panels.js');
        panels.openPanel.mockClear();
        panels.closeTopPanel.mockClear();
        panels.stepHasLayer1Content.mockReturnValue(true);
        panels.stepHasLayer2Content.mockReturnValue(true);
        window.storyData = { steps: [{ step: 3 }] };
        if (withPanel) panelOpenBehind();
        const { dialog, inner } = openDialogTarget();
        const input = document.createElement('input');
        inner.append(input);
        const ev = pressOn(input, key);
        dialog.remove();
        panels.stepHasLayer1Content.mockReturnValue(false);
        panels.stepHasLayer2Content.mockReturnValue(false);
        expect(ev.defaultPrevented).toBe(false);
        expect(panels.openPanel).not.toHaveBeenCalled();
        expect(panels.closeTopPanel).not.toHaveBeenCalled();
      });
    }
  }

  it('still opens the next layer on ArrowRight outside a dialog', async () => {
    const panels = await import('../../assets/js/telar-story/panels.js');
    panels.openPanel.mockClear();
    panels.stepHasLayer1Content.mockReturnValue(true);
    window.storyData = { steps: [{ step: 3 }] };
    const ev = pressCardKey('ArrowRight');
    panels.stepHasLayer1Content.mockReturnValue(false);
    expect(ev.defaultPrevented).toBe(true);
    expect(panels.openPanel).toHaveBeenCalledWith('layer1', '3');
  });

  for (const key of ['ArrowLeft', 'Escape']) {
    it(`still closes the top panel on ${key} outside a dialog`, async () => {
      const panels = await import('../../assets/js/telar-story/panels.js');
      panels.closeTopPanel.mockClear();
      state.isPanelOpen = true;
      state.panelStack = [{ type: 'layer1' }];
      const ev = pressCardKey(key);
      expect(ev.defaultPrevented).toBe(true);
      expect(panels.closeTopPanel).toHaveBeenCalledTimes(1);
    });
  }
});
