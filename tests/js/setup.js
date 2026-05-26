/**
 * Vitest global test setup
 *
 * Stubs browser APIs that jsdom does not implement but that are called at
 * module-evaluation time (i.e. before any beforeEach can run).
 *
 * window.matchMedia — required by layout-mode.js _initOnce(), which is
 * triggered when onViewportResize() is called at the module top-level of
 * audio-card.js and video-card.js. Without this stub the module import
 * itself throws "window.matchMedia is not a function".
 *
 * @version v1.4.0
 */

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
