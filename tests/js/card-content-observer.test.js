/**
 * Tests for Telar Story – Side-card fit: what re-runs it
 *
 * watchCardContent against a stubbed ResizeObserver and a hand-driven
 * animation frame: an entry at the height recorded after a card's fit is the
 * fit's own and starts nothing; any other re-fits that card, once per frame
 * however many entries arrive; a font that finishes loading invalidates every
 * card's fit; the embed banner's arrival re-runs the pass.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  watchCardContent, recordContentHeight, fitAnswerText,
} from '../../assets/js/telar-story/card-fit.js';
import { modelCard } from './card-fit-model.js';

class FakeResizeObserver {
  constructor(callback) {
    this.callback = callback;
    this.targets = [];
    FakeResizeObserver.last = this;
  }
  observe(target) { this.targets.push(target); }
  /** Deliver entries at these content heights, px. */
  deliver(...pairs) {
    this.callback(pairs.map(([target, height]) => ({ target, contentRect: { height } })));
  }
}

let frames;
const queueFrame = (cb) => { frames.push(cb); return frames.length; };
function flushFrames() {
  const run = frames;
  frames = [];
  for (const cb of run) cb();
}

let fonts;

/** A card whose content wrapper is `height` px tall, recorded as fitted. */
function fittedCard(height = 200) {
  const m = modelCard();
  m.content.style.height = `${height}px`;
  recordContentHeight(m.card);
  return m;
}

describe('watchCardContent', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    frames = [];
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    fonts = new EventTarget();
    Object.defineProperty(document, 'fonts', { configurable: true, value: fonts });
  });
  afterEach(() => {
    delete FakeResizeObserver.prototype.disconnect;
    vi.unstubAllGlobals();
    delete document.fonts;
  });

  it('stops on teardown: observer disconnected, listeners removed, a scheduled pass dropped', () => {
    const { card } = fittedCard();
    const refit = vi.fn();
    FakeResizeObserver.prototype.disconnect = vi.fn();
    const stop = watchCardContent([card], refit, { raf: queueFrame });
    window.dispatchEvent(new Event('telar:embed-banner'));
    expect(frames).toHaveLength(1);

    stop();
    flushFrames();
    window.dispatchEvent(new Event('telar:embed-banner'));
    fonts.dispatchEvent(new Event('loadingdone'));
    flushFrames();

    expect(refit).not.toHaveBeenCalled();
    expect(FakeResizeObserver.last.disconnect).toHaveBeenCalledTimes(1);
  });

  it('observes each card\'s content wrapper', () => {
    const a = fittedCard();
    const b = fittedCard();
    watchCardContent([a.card, b.card], vi.fn(), { raf: queueFrame });
    expect(FakeResizeObserver.last.targets).toEqual([a.content, b.content]);
  });

  it('starts no pass for an entry at exactly the recorded height', () => {
    const { card, content } = fittedCard(200);
    const refit = vi.fn();
    watchCardContent([card], refit, { raf: queueFrame });

    FakeResizeObserver.last.deliver([content, 200]);

    expect(frames).toHaveLength(0);
    flushFrames();
    expect(refit).not.toHaveBeenCalled();
  });

  it('re-fits a card whose content moved by 0.4px', () => {
    const { card, content } = fittedCard(200);
    const refit = vi.fn();
    watchCardContent([card], refit, { raf: queueFrame });

    FakeResizeObserver.last.deliver([content, 200.4]);
    flushFrames();

    expect(refit).toHaveBeenCalledTimes(1);
    expect(refit).toHaveBeenCalledWith([card]);
  });

  it('re-fits the changed card only, once per frame however many entries arrive', () => {
    const a = fittedCard(200);
    const b = fittedCard(300);
    const c = fittedCard(400);
    const refit = vi.fn();
    watchCardContent([a.card, b.card, c.card], refit, { raf: queueFrame });

    const ro = FakeResizeObserver.last;
    ro.deliver([a.content, 260], [b.content, 300]);
    ro.deliver([a.content, 280]);
    ro.deliver([a.content, 290], [c.content, 400]);
    expect(frames).toHaveLength(1);
    flushFrames();

    expect(refit).toHaveBeenCalledTimes(1);
    expect(refit).toHaveBeenCalledWith([a.card]);
  });

  it('does not loop on the entry its own re-fit causes', () => {
    const { card, content } = fittedCard(200);
    const ro = () => FakeResizeObserver.last;
    const refit = vi.fn(() => {
      // The re-fit shrinks the answer, and records the height it leaves.
      content.style.height = '185.25px';
      recordContentHeight(card);
      ro().deliver([content, 185.25]);
    });
    watchCardContent([card], refit, { raf: queueFrame });

    ro().deliver([content, 230]);
    flushFrames();
    flushFrames();

    expect(refit).toHaveBeenCalledTimes(1);
    expect(frames).toHaveLength(0);
  });

  it('invalidates every card on a font load that changes no height, in one pass', () => {
    const a = fittedCard(200);
    const b = fittedCard(300);
    const cache = new WeakMap();
    fitAnswerText(a.card, 380, cache);
    fitAnswerText(b.card, 380, cache);
    const refit = vi.fn();
    watchCardContent([a.card, b.card], refit, { raf: queueFrame });

    fonts.dispatchEvent(new Event('loadingdone'));
    fonts.dispatchEvent(new Event('loadingdone'));
    flushFrames();

    expect(refit).toHaveBeenCalledTimes(1);
    expect(refit).toHaveBeenCalledWith(null);
    for (const { card } of [a, b]) {
      const set = vi.spyOn(card.style, 'setProperty');
      fitAnswerText(card, 380, cache);
      expect(set, 'the cached fit is measured again').toHaveBeenCalled();
    }
  });

  it('re-runs the pass when the embed banner comes or goes', () => {
    const { card } = fittedCard(200);
    const refit = vi.fn();
    watchCardContent([card], refit, { raf: queueFrame });

    window.dispatchEvent(new CustomEvent('telar:embed-banner'));
    flushFrames();

    expect(refit).toHaveBeenCalledWith(null);
  });
});
