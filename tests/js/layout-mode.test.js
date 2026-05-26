/**
 * Tests for Telar Story – Layout-Mode Module
 *
 * Tests the dispatch behaviour: mode resolution from the
 * matchMedia query, onLayoutChange firing on flips with the correct payload,
 * dispatch order (onLayoutChange before onViewportResize), 100ms debounce,
 * immediate orientationchange, and getBreakpoints() parsing.
 *
 * Strategy: vi.resetModules() in beforeEach forces ES-module re-evaluation
 * between tests so module-scoped state (_cachedMode, _breakpoints,
 * _initialized) does not leak across tests.
 *
 * matchMedia mock: the global setup.js stub is non-controllable (static
 * matches: false). Each test overrides window.matchMedia with a factory that
 * returns a controllable MediaQueryList — test can set .matches and invoke the
 * stored 'change' callback.
 *
 * @version v1.4.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── matchMedia mock factory ────────────────────────────────────────────────────
//
// Returns a controllable MediaQueryList. The test can:
//   1. Set fakeMql.matches = true/false before importing the module.
//   2. Retrieve the stored change listener via fakeMql._changeListeners and
//      invoke it to simulate a matchMedia 'change' event.

function makeFakeMql(initialMatches = false) {
  const listeners = [];
  const mql = {
    matches: initialMatches,
    media: '',
    onchange: null,
    _changeListeners: listeners,
    addEventListener(type, cb) {
      if (type === 'change') listeners.push(cb);
    },
    removeEventListener(type, cb) {
      if (type === 'change') {
        const i = listeners.indexOf(cb);
        if (i !== -1) listeners.splice(i, 1);
      }
    },
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  };
  return mql;
}

// ── Shared test helpers ────────────────────────────────────────────────────────

function setViewport(width, height) {
  Object.defineProperty(window, 'innerWidth',  { value: width,  configurable: true, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true, writable: true });
}

function stubComputedStyle() {
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    getPropertyValue: (name) => {
      if (name === '--telar-vertical-min-width')  return '1024px';
      if (name === '--telar-vertical-min-aspect') return '0.75';
      return '';
    },
  });
}

// ── Mode resolution + getBreakpoints ───────────────────────────────────────────

describe('getLayoutMode — mode resolution', () => {
  let fakeMql;

  beforeEach(() => {
    vi.resetModules();
    stubComputedStyle();
    // Default: wide viewport, matchMedia does NOT match → horizontal
    setViewport(1440, 900);
    fakeMql = makeFakeMql(false);
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn(() => fakeMql),
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('returns "horizontal" when matchMedia does not match (wide viewport)', async () => {
    fakeMql.matches = false;
    const { getLayoutMode } = await import('../../assets/js/telar-story/layout-mode.js');
    expect(getLayoutMode()).toBe('horizontal');
  });

  it('returns "vertical" when matchMedia matches (narrow viewport)', async () => {
    // Simulate a narrow viewport where the max-width clause would match
    setViewport(800, 900);
    fakeMql.matches = true;
    const { getLayoutMode } = await import('../../assets/js/telar-story/layout-mode.js');
    expect(getLayoutMode()).toBe('vertical');
  });

  it('returns "vertical" when matchMedia matches (tall-narrow: width ≤ 1024)', async () => {
    // 1000 × 1400: width 1000 ≤ 1024 → matchMedia matches
    setViewport(1000, 1400);
    fakeMql.matches = true;
    const { getLayoutMode } = await import('../../assets/js/telar-story/layout-mode.js');
    expect(getLayoutMode()).toBe('vertical');
  });

  it('returns "horizontal" when matchMedia does not match (1280 × 1600, wide enough)', async () => {
    // 1280 > 1024 AND aspect 1280/1600 = 0.8 > 0.75 → no clause matches → horizontal
    setViewport(1280, 1600);
    fakeMql.matches = false;
    const { getLayoutMode } = await import('../../assets/js/telar-story/layout-mode.js');
    expect(getLayoutMode()).toBe('horizontal');
  });
});

describe('getBreakpoints — CSS var parsing', () => {
  beforeEach(() => {
    vi.resetModules();
    stubComputedStyle();
    setViewport(1440, 900);
    const fakeMql = makeFakeMql(false);
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn(() => fakeMql),
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('returns parsed numeric breakpoints from CSS custom properties', async () => {
    const { getBreakpoints } = await import('../../assets/js/telar-story/layout-mode.js');
    const bp = getBreakpoints();
    expect(bp).toEqual({ verticalMinWidth: 1024, verticalMinAspect: 0.75 });
  });

  it('returns numbers, not strings', async () => {
    const { getBreakpoints } = await import('../../assets/js/telar-story/layout-mode.js');
    const bp = getBreakpoints();
    expect(typeof bp.verticalMinWidth).toBe('number');
    expect(typeof bp.verticalMinAspect).toBe('number');
  });

  it('returns a defensive copy (mutating returned object does not affect next call)', async () => {
    const { getBreakpoints } = await import('../../assets/js/telar-story/layout-mode.js');
    const bp1 = getBreakpoints();
    bp1.verticalMinWidth = 9999;
    const bp2 = getBreakpoints();
    expect(bp2.verticalMinWidth).toBe(1024);
  });
});

// ── onLayoutChange, dispatch order, debounce, orientationchange ────────────────

describe('onLayoutChange — mode flip dispatch', () => {
  let fakeMql;

  beforeEach(() => {
    vi.resetModules();
    stubComputedStyle();
    setViewport(1440, 900);
    fakeMql = makeFakeMql(false); // starts horizontal
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn(() => fakeMql),
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('fires on a mode flip (false → true) with the full payload', async () => {
    const { getLayoutMode, onLayoutChange } = await import('../../assets/js/telar-story/layout-mode.js');
    // Initialise the module — mode is horizontal (matches: false)
    expect(getLayoutMode()).toBe('horizontal');

    const handler = vi.fn();
    onLayoutChange(handler);

    // Simulate matchMedia flipping: matches goes true (vertical)
    setViewport(800, 900);
    fakeMql.matches = true;
    // Invoke the change listener the module registered on the MQL
    for (const cb of fakeMql._changeListeners) cb({});

    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      from: 'horizontal',
      to: 'vertical',
      viewport: { w: 800, h: 900 },
    }));
    // isEmbed is a boolean (state.isEmbed defaults to false)
    const call = handler.mock.calls[0][0];
    expect(typeof call.isEmbed).toBe('boolean');
  });

  it('does NOT fire on the initial call / initial subscription (fires-on-change-only)', async () => {
    const { getLayoutMode, onLayoutChange } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onLayoutChange(handler);
    // getLayoutMode reads the current mode — must NOT invoke onLayoutChange handlers
    getLayoutMode();
    expect(handler).not.toHaveBeenCalled();
  });

  it('does NOT fire when the mode stays the same (no genuine flip)', async () => {
    const { getLayoutMode, onLayoutChange } = await import('../../assets/js/telar-story/layout-mode.js');
    expect(getLayoutMode()).toBe('horizontal');

    const handler = vi.fn();
    onLayoutChange(handler);

    // Trigger change but keep matches: false → still horizontal
    fakeMql.matches = false;
    for (const cb of fakeMql._changeListeners) cb({});

    expect(handler).not.toHaveBeenCalled();
  });

  it('returned unsubscribe function stops future deliveries', async () => {
    const { getLayoutMode, onLayoutChange } = await import('../../assets/js/telar-story/layout-mode.js');
    expect(getLayoutMode()).toBe('horizontal');

    const handler = vi.fn();
    const unsub = onLayoutChange(handler);
    unsub();

    fakeMql.matches = true;
    for (const cb of fakeMql._changeListeners) cb({});

    expect(handler).not.toHaveBeenCalled();
  });
});

describe('dispatch order — onLayoutChange fires before onViewportResize', () => {
  let fakeMql;

  beforeEach(() => {
    vi.resetModules();
    stubComputedStyle();
    setViewport(1440, 900);
    fakeMql = makeFakeMql(false);
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn(() => fakeMql),
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('onLayoutChange subscribers run before onViewportResize on orientationchange', async () => {
    // The orientationchange handler (_onOrientationChange) is the only path that
    // fires both surfaces in a guaranteed order: _dispatchLayoutChange() first,
    // then _dispatchViewportResize(). This tests the dispatch order contract.
    // (matchMedia 'change' only fires the layoutChange surface; resize only fires
    //  the viewportResize surface — orientationchange is the single-trigger path.)
    const { getLayoutMode, onLayoutChange, onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');

    // Initialise with horizontal mode
    expect(getLayoutMode()).toBe('horizontal');

    const calls = [];
    onLayoutChange(()   => calls.push('layoutChange'));
    onViewportResize(() => calls.push('viewportResize'));

    // Set up a mode flip so onLayoutChange actually fires (not a no-op)
    setViewport(800, 900);
    fakeMql.matches = true;

    window.dispatchEvent(new Event('orientationchange'));

    expect(calls).toEqual(['layoutChange', 'viewportResize']);
  });
});

describe('onViewportResize — 100ms debounce', () => {
  let fakeMql;

  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    stubComputedStyle();
    setViewport(1440, 900);
    fakeMql = makeFakeMql(false);
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn(() => fakeMql),
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('coalesces 3 rapid resize events into 1 call after 100ms', async () => {
    const { onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onViewportResize(handler);

    window.dispatchEvent(new Event('resize'));
    window.dispatchEvent(new Event('resize'));
    window.dispatchEvent(new Event('resize'));

    vi.advanceTimersByTime(99);
    expect(handler).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(handler).toHaveBeenCalledOnce();
  });

  it('is not called at 99ms', async () => {
    const { onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onViewportResize(handler);

    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(99);
    expect(handler).not.toHaveBeenCalled();
  });

  it('is called exactly once at 100ms even after many resize events', async () => {
    const { onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onViewportResize(handler);

    for (let i = 0; i < 10; i++) {
      window.dispatchEvent(new Event('resize'));
    }
    vi.advanceTimersByTime(100);
    expect(handler).toHaveBeenCalledOnce();
  });

  it('delivers viewport dimensions in the payload', async () => {
    const { onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onViewportResize(handler);

    setViewport(1024, 768);
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(100);

    expect(handler).toHaveBeenCalledWith({ viewport: { w: 1024, h: 768 } });
  });
});

describe('orientationchange — fires immediately, no debounce', () => {
  let fakeMql;

  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    stubComputedStyle();
    setViewport(1440, 900);
    fakeMql = makeFakeMql(false);
    Object.defineProperty(window, 'matchMedia', {
      value: vi.fn(() => fakeMql),
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('onViewportResize fires synchronously on orientationchange (no timer advance)', async () => {
    const { onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onViewportResize(handler);

    window.dispatchEvent(new Event('orientationchange'));
    // No timer advance — should fire synchronously via _onOrientationChange
    expect(handler).toHaveBeenCalledOnce();
  });

  it('orientationchange clears any pending debounce timer', async () => {
    const { onViewportResize } = await import('../../assets/js/telar-story/layout-mode.js');
    const handler = vi.fn();
    onViewportResize(handler);

    // Start a debounce-pending resize
    window.dispatchEvent(new Event('resize'));
    // Then orientationchange fires immediately and clears the pending resize timer
    window.dispatchEvent(new Event('orientationchange'));
    // Handler was called once (by orientationchange)
    expect(handler).toHaveBeenCalledOnce();

    // Advance past the original debounce window — the pending resize was cleared
    vi.advanceTimersByTime(100);
    // Still only one call (the resize timer was cancelled)
    expect(handler).toHaveBeenCalledOnce();
  });
});
