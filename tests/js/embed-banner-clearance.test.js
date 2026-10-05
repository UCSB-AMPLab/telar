/**
 * Tests for the embed banner's published clearance.
 *
 * embed.js is a standalone script, so each case sets the URL and the banner
 * strings, then loads a fresh copy. While the banner shows the body carries
 * `embed-banner-shown` and `--telar-embed-banner-bottom` holds the banner's
 * measured bottom edge; the stylesheet positions the button column from it.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const STRINGS = {
  text: 'Esta historia forma parte de {site_name}.',
  link: 'Ver el sitio completo',
  siteFallback: 'este sitio',
};

// Full and compact bottoms of the mocked banner; the mock answers by its class.
let bottom;
let compactBottom;
let observers;
let resizeHandlers;

const load = async () => {
  vi.resetModules();
  await import('../../assets/js/embed.js');
};

const banner = () => document.querySelector('.telar-embed-banner');
const property = () => document.body.style.getPropertyValue('--telar-embed-banner-bottom');

describe('embed banner clearance', () => {
  beforeEach(() => {
    document.body.className = '';
    document.body.removeAttribute('style');
    document.body.innerHTML = '';
    window.telarLang = { embedBanner: STRINGS };
    history.replaceState(null, '', '/telar/stories/s/?embed=true');
    bottom = 94.2;
    compactBottom = 60;
    vi.stubGlobal('innerHeight', 768);
    observers = [];
    // Each case loads a fresh copy of the script; take its listener off afterwards
    // so a banner left in an earlier case does not keep answering resizes.
    resizeHandlers = [];
    const add = window.addEventListener.bind(window);
    vi.spyOn(window, 'addEventListener').mockImplementation((type, handler, ...rest) => {
      if (type === 'resize') resizeHandlers.push(handler);
      return add(type, handler, ...rest);
    });
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function() {
      const b = this.classList.contains('is-compact') ? compactBottom : bottom;
      return this.classList.contains('telar-embed-banner')
        ? { top: 20, bottom: b, left: 20, right: 300, width: 280, height: b - 20 }
        : { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
    });
    vi.stubGlobal('ResizeObserver', class {
      constructor(cb) { this.cb = cb; this.disconnected = false; observers.push(this); }
      observe() {}
      disconnect() { this.disconnected = true; }
    });
    // The observer's update waits a frame; here the frame runs at once.
    vi.stubGlobal('requestAnimationFrame', (fn) => { fn(); return 0; });
  });

  afterEach(() => {
    resizeHandlers.forEach((handler) => window.removeEventListener('resize', handler));
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('publishes the banner bottom, rounded up, and the class while the banner shows', async () => {
    await load();
    expect(banner()).not.toBeNull();
    expect(document.body.classList.contains('embed-banner-shown')).toBe(true);
    expect(property()).toBe('95px');
  });

  it('follows the banner when it changes height', async () => {
    await load();
    bottom = 137;
    observers[0].cb();
    expect(property()).toBe('137px');
  });

  it('removes the class and the property, and stops observing, when the banner is dismissed', async () => {
    await load();
    banner().querySelector('.telar-embed-banner-close').click();
    expect(banner()).toBeNull();
    expect(document.body.classList.contains('embed-banner-shown')).toBe(false);
    expect(property()).toBe('');
    expect(observers[0].disconnected).toBe(true);
  });

  it('publishes nothing when the layout has no banner strings', async () => {
    window.telarLang = {};
    await load();
    expect(banner()).toBeNull();
    expect(document.body.classList.contains('embed-banner-shown')).toBe(false);
    expect(property()).toBe('');
  });

  it('publishes nothing outside embed mode', async () => {
    history.replaceState(null, '', '/telar/stories/s/');
    await load();
    expect(banner()).toBeNull();
    expect(property()).toBe('');
  });

  describe('compact banner', () => {
    // Full banner bottom 117, as a wrapped Spanish banner; a column needs
    // 117 + 12 + 102 + 8 = 239px, a row 117 + 12 + 45 + 8 = 182px.
    const shortWindow = async (height) => {
      bottom = 117;
      vi.stubGlobal('innerHeight', height);
      await load();
    };
    const message = () => document.querySelector('.telar-embed-banner-message');

    it('is compact, and publishes the compact bottom, where the full banner and the column do not both fit', async () => {
      await shortWindow(150);
      expect(banner().classList.contains('is-compact')).toBe(true);
      expect(property()).toBe('60px');
      expect(message().title).toBe('Esta historia forma parte de este sitio.');
      expect(banner().querySelector('.telar-embed-banner-link')).not.toBeNull();
      expect(banner().querySelector('.telar-embed-banner-close')).not.toBeNull();
    });

    it('is not compact where both fit', async () => {
      await shortWindow(239);
      expect(banner().classList.contains('is-compact')).toBe(false);
      expect(property()).toBe('117px');
      expect(message().hasAttribute('title')).toBe(false);
    });

    it('is compact one pixel short of fitting a column, judged from the full height', async () => {
      await shortWindow(238);
      expect(banner().classList.contains('is-compact')).toBe(true);
    });

    it('judges a row, not a column, in a window 229px tall or less', async () => {
      await shortWindow(182);
      expect(banner().classList.contains('is-compact')).toBe(false);
      vi.stubGlobal('innerHeight', 181);
      window.dispatchEvent(new Event('resize'));
      expect(banner().classList.contains('is-compact')).toBe(true);
    });

    it('is never compact in a window taller than the column placement covers', async () => {
      bottom = 900;
      vi.stubGlobal('innerHeight', 481);
      await load();
      expect(banner().classList.contains('is-compact')).toBe(false);
      expect(property()).toBe('900px');
    });

    it('is decided again when the window is resized', async () => {
      await shortWindow(150);
      expect(banner().classList.contains('is-compact')).toBe(true);
      vi.stubGlobal('innerHeight', 300);
      window.dispatchEvent(new Event('resize'));
      expect(banner().classList.contains('is-compact')).toBe(false);
      expect(property()).toBe('117px');
      expect(message().hasAttribute('title')).toBe(false);
      vi.stubGlobal('innerHeight', 150);
      window.dispatchEvent(new Event('resize'));
      expect(banner().classList.contains('is-compact')).toBe(true);
      expect(property()).toBe('60px');
    });

    it('does not oscillate: the decision is the same each time the observer fires', async () => {
      await shortWindow(150);
      const seen = [];
      for (let i = 0; i < 6; i++) {
        observers[0].cb();
        seen.push(`${banner().classList.contains('is-compact')} ${property()}`);
      }
      expect(new Set(seen)).toEqual(new Set(['true 60px']));
    });

    it('measures the full height with the class off, whatever the state before', async () => {
      await shortWindow(150);
      const classesAtMeasure = [];
      Element.prototype.getBoundingClientRect.mockImplementation(function() {
        if (this.classList.contains('telar-embed-banner')) {
          classesAtMeasure.push(this.classList.contains('is-compact'));
        }
        const b = this.classList.contains('is-compact') ? compactBottom : bottom;
        return { top: 20, bottom: b, left: 20, right: 300, width: 280, height: b - 20 };
      });
      observers[0].cb();
      // First measure (the decision) is with the class off, the second (the publish) with it on.
      expect(classesAtMeasure).toEqual([false, true]);
    });

    it('stops deciding on resize once the banner is dismissed', async () => {
      await shortWindow(150);
      banner().querySelector('.telar-embed-banner-close').click();
      vi.stubGlobal('innerHeight', 300);
      window.dispatchEvent(new Event('resize'));
      expect(property()).toBe('');
    });
  });
});
