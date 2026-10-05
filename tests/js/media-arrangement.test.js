/**
 * Tests for the media card below: whether a video or audio step's text card
 * goes beside the player or below it on a horizontal layout, and where the
 * player, the waveform and the card go in each case.
 *
 * The design table (docs, media-card-below.md) was measured with 64px kept
 * clear at the top and a 16:9 video; its chosen column is reproduced here from
 * its card heights.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  chooseVideoArrangement, computeVideoLayout, computeVideoLetterboxRegion,
  computeBelowCardTop, mediaPadding,
} from '../../assets/js/telar-story/video-layout.js';
import {
  chooseAudioArrangement, computeAudioBelowLayout, computeAudioBesideWave,
  AUDIO_CONTROLS_HEIGHT, AUDIO_CONTROLS_GAP,
} from '../../assets/js/telar-story/audio-layout.js';
import {
  arrangeMediaScene, readBelow, readTopBand, placeAudioBelow,
} from '../../assets/js/telar-story/media-arrangement.js';
import { state } from '../../assets/js/telar-story/state.js';

const TABLE_BAND = 64;

// [W, H, card height, beside WxH, below WxH, chosen] — the design table.
const TABLE = [
  [1100, 900, 115, [616, 346], [1056, 594], 'below'],
  [1100, 900, 158, [616, 346], [1056, 594], 'below'],
  [1100, 900, 224, [616, 346], [1010, 568], 'below'],
  [1100, 900, 289, [616, 346], [894, 503], 'below'],
  [1280, 720, 125, [732, 412], [880, 495], 'below'],
  [1280, 720, 173, [732, 412], [795, 447], 'below'],
  [1280, 720, 246, [732, 412], [665, 374], 'beside'],
  [1280, 720, 319, [732, 412], [535, 301], 'beside'],
  [1280, 800, 125, [728, 410], [1015, 571], 'below'],
  [1280, 800, 173, [728, 410], [930, 523], 'below'],
  [1280, 800, 246, [728, 410], [800, 450], 'below'],
  [1280, 800, 319, [728, 410], [670, 377], 'beside'],
  [1440, 757, 125, [826, 465], [942, 530], 'below'],
  [1440, 757, 173, [826, 465], [857, 482], 'beside'],
  [1440, 757, 222, [826, 465], [770, 433], 'beside'],
  [1440, 757, 295, [826, 465], [640, 360], 'beside'],
  [1440, 900, 125, [820, 461], [1186, 667], 'below'],
  [1440, 900, 173, [820, 461], [1100, 619], 'below'],
  [1440, 900, 222, [820, 461], [1013, 570], 'below'],
  [1440, 900, 295, [820, 461], [884, 497], 'below'],
  [1536, 864, 130, [878, 494], [1113, 626], 'below'],
  [1536, 864, 182, [878, 494], [1020, 574], 'below'],
  [1536, 864, 233, [878, 494], [930, 523], 'beside'],
  [1536, 864, 310, [878, 494], [793, 446], 'beside'],
  [1920, 1080, 130, [1098, 618], [1479, 832], 'below'],
  [1920, 1080, 156, [1098, 618], [1433, 806], 'below'],
  [1920, 1080, 207, [1098, 618], [1342, 755], 'below'],
  [1920, 1080, 258, [1098, 618], [1252, 704], 'below'],
  [2560, 1440, 130, [1464, 824], [2087, 1174], 'below'],
  [2560, 1440, 156, [1464, 824], [2041, 1148], 'below'],
  [2560, 1440, 182, [1464, 824], [1995, 1122], 'below'],
  [2560, 1440, 233, [1464, 824], [1904, 1071], 'below'],
];

/** Within 1% of the table's figure: the table rounded its padding by hand. */
const nearTable = (actual, expected) => Math.abs(actual - expected) <= Math.max(3, expected * 0.01);

afterEach(() => { delete state.layoutMode; state.isEmbed = false; });

describe('chooseVideoArrangement reproduces the design table', () => {
  it.each(TABLE)('%ix%i, card %ipx', (W, H, cardH, beside, below, chosen) => {
    expect(chooseVideoArrangement(W, H, 16 / 9, cardH, TABLE_BAND)).toBe(chosen);
    const side = computeVideoLayout(W, H, 16 / 9).video;
    expect(nearTable(side.width, beside[0]) && nearTable(side.height, beside[1]),
      `beside ${side.width}x${side.height}`).toBe(true);
    const bottom = computeVideoLayout(W, H, 16 / 9, {
      cardTop: computeBelowCardTop(W, H, cardH), topBand: TABLE_BAND,
    }).video;
    expect(nearTable(bottom.width, below[0]) && nearTable(bottom.height, below[1]),
      `below ${bottom.width}x${bottom.height}`).toBe(true);
  });

  it('compares at the video\'s own aspect: a portrait video keeps the card beside', () => {
    expect(chooseVideoArrangement(1440, 900, 16 / 9, 125, TABLE_BAND)).toBe('below');
    expect(chooseVideoArrangement(1440, 900, 9 / 16, 125, TABLE_BAND)).toBe('beside');
  });

  it('keeps the card beside when the card leaves no room above it', () => {
    expect(chooseVideoArrangement(1280, 720, 16 / 9, 700, TABLE_BAND)).toBe('beside');
  });
});

describe('the video with the card below', () => {
  const W = 1440;
  const H = 900;
  const pad = mediaPadding(W, H);
  const cardTop = computeBelowCardTop(W, H, 150);
  const below = { cardTop, topBand: 77 };

  it('puts the card one padding above the window\'s bottom edge', () => {
    expect(cardTop).toBe(H - pad - 150);
  });

  it('fits the space between the top band and the card, centred', () => {
    for (const aspect of [16 / 9, 4 / 3, 1.4786, 1, 9 / 16]) {
      const { mode, video, card } = computeVideoLayout(W, H, aspect, below);
      expect(mode).toBe('below');
      expect(video.top, `aspect ${aspect}`).toBeGreaterThanOrEqual(77);
      expect(video.top + video.height, `aspect ${aspect}`).toBeLessThanOrEqual(cardTop - pad);
      expect(video.left, `aspect ${aspect}`).toBeGreaterThanOrEqual(pad);
      expect(video.left + video.width, `aspect ${aspect}`).toBeLessThanOrEqual(W - pad);
      expect(Math.abs(video.left + video.width / 2 - W / 2), `aspect ${aspect}`).toBeLessThanOrEqual(1);
      const midY = (77 + cardTop - pad) / 2;
      expect(Math.abs(video.top + video.height / 2 - midY), `aspect ${aspect}`).toBeLessThanOrEqual(1);
      expect(card).toMatchObject({ left: Math.round(W * 0.03), width: Math.round(W * 0.37), top: cardTop });
    }
  });

  it('fills the same space when the aspect is unknown', () => {
    expect(computeVideoLetterboxRegion(W, H, below)).toEqual({
      left: pad, top: 77, width: W - pad * 2, height: cardTop - pad - 77,
    });
  });

  it('is stacked on a vertical layout whatever the plate says', () => {
    state.layoutMode = 'vertical';
    expect(computeVideoLayout(800, 1200, 16 / 9, below).mode).toBe('stacked');
  });
});

describe('the video with the card beside', () => {
  const SIZES = [[1100, 900], [1280, 720], [1440, 900], [1920, 1080]];
  const ASPECTS = [16 / 9, 4 / 3, 1.4786, 1, 9 / 16];
  const BAND = 77;

  it.each(SIZES)('fills the space under the top band when the aspect is unknown, at %ix%i', (W, H) => {
    const pad = mediaPadding(W, H);
    const left = Math.round(W * 0.4) + pad;
    expect(computeVideoLetterboxRegion(W, H, null, BAND)).toEqual({
      left, top: BAND, width: W - left - pad, height: H - pad - BAND,
    });
  });

  it.each(SIZES)('keeps a known-aspect video under the top band at %ix%i', (W, H) => {
    const pad = mediaPadding(W, H);
    for (const aspect of ASPECTS) {
      const { mode, video } = computeVideoLayout(W, H, aspect, null, BAND);
      expect(mode).toBe('side-by-side');
      expect(video.top, `aspect ${aspect}`).toBeGreaterThanOrEqual(BAND);
      expect(video.top + video.height, `aspect ${aspect}`).toBeLessThanOrEqual(H - pad);
      expect(video.left, `aspect ${aspect}`).toBe(Math.round(W * 0.4) + pad);
    }
  });

  it.each(SIZES)('places a video that already cleared the band as before, at %ix%i', (W, H) => {
    let cleared = 0;
    for (const aspect of [...ASPECTS, 1.2, 1.1, 0.9, 0.8]) {
      const before = computeVideoLayout(W, H, aspect);
      if (before.video.top < BAND) continue;
      cleared += 1;
      expect(computeVideoLayout(W, H, aspect, null, BAND), `aspect ${aspect}`).toEqual(before);
    }
    expect(cleared).toBeGreaterThan(0);
  });

  it('keeps one padding at the top where the band is narrower, and no height where it fills the window', () => {
    const pad = mediaPadding(1440, 900);
    expect(computeVideoLetterboxRegion(1440, 900, null, 0).top).toBe(pad);
    expect(computeVideoLetterboxRegion(1440, 900, null, 2000).height).toBe(0);
  });

  it('shortens a tall video to the space under the band', () => {
    const pad = mediaPadding(1440, 900);
    const without = computeVideoLayout(1440, 900, 9 / 16).video;
    const withBand = computeVideoLayout(1440, 900, 9 / 16, null, 300).video;
    expect(without.height).toBe(900 - pad * 2);
    expect(withBand).toMatchObject({ top: 300, height: 900 - pad - 300 });
  });
});

describe('the threshold comes from the stylesheet', () => {
  it.each([
    // +45% in the table: below at 15%, beside at 50%
    [0.5, 1280, 720, 125, 'beside'],
    // +8% in the table: beside at 15%, below at 5%
    [0.05, 1440, 757, 173, 'below'],
  ])('--telar-media-below-gain: %s', async (gain, W, H, cardH, chosen) => {
    const sheet = document.createElement('style');
    sheet.textContent = `:root { --telar-media-below-gain: ${gain}; }`;
    document.head.appendChild(sheet);
    try {
      vi.resetModules();
      const fresh = await import('../../assets/js/telar-story/video-layout.js');
      expect(fresh.chooseVideoArrangement(W, H, 16 / 9, cardH, TABLE_BAND)).toBe(chosen);
    } finally {
      sheet.remove();
    }
  });
});

describe('audio', () => {
  const sizes = [[1100, 900], [1280, 720], [1440, 900], [1920, 1080]];
  const row = AUDIO_CONTROLS_GAP + AUDIO_CONTROLS_HEIGHT;

  it('beside the card, the waveform is the stylesheet\'s: 59% of the width, half the height', () => {
    expect(computeAudioBesideWave(1440, 900)).toEqual({ width: 850, height: 450 });
  });

  it('beside a card card-fit.js has widened, the waveform starts past its right edge', () => {
    const root = document.documentElement.style;
    root.setProperty('--telar-card-side-width', '624px');
    try {
      // 1440 − (43.2 + 624, rounded to 667) − 1% of 1440 = 758.6
      expect(computeAudioBesideWave(1440, 560)).toEqual({ width: 759, height: 280 });
    } finally {
      root.removeProperty('--telar-card-side-width');
    }
  });

  it.each(sizes)('a short answer at %ix%i puts the card below a full-height waveform', (W, H) => {
    const pad = mediaPadding(W, H);
    expect(chooseAudioArrangement(W, H, 150, 77)).toBe('below');
    const cardTop = computeBelowCardTop(W, H, 150);
    const { wave, controlsBottom } = computeAudioBelowLayout(W, H, { cardTop, topBand: 77 });
    expect(wave).toMatchObject({ left: pad, width: W - pad * 2, height: Math.round(H * 0.5) });
    expect(wave.top).toBeGreaterThanOrEqual(77);
    const controlsTop = H - controlsBottom - AUDIO_CONTROLS_HEIGHT;
    expect(controlsTop).toBe(wave.top + wave.height + AUDIO_CONTROLS_GAP);
    expect(H - controlsBottom).toBeLessThanOrEqual(cardTop - pad);
  });

  it('shrinks the waveform to the space a long answer on a short window leaves', () => {
    const W = 1280;
    const H = 720;
    const pad = mediaPadding(W, H);
    const cardTop = computeBelowCardTop(W, H, 319);
    const { wave } = computeAudioBelowLayout(W, H, { cardTop, topBand: 64 });
    expect(wave.height).toBe(cardTop - pad - 64 - row);
    expect(wave.height).toBeLessThan(360);
  });

  it('keeps the card beside once the waveform below would lose more than the width gains', () => {
    // 1280x720, band 72: below is chosen while the waveform keeps about 257px
    // (0.357 of the window) and beside below that.
    expect(chooseAudioArrangement(1280, 720, 280, 72)).toBe('below');
    expect(chooseAudioArrangement(1280, 720, 330, 72)).toBe('beside');
  });
});

describe('arrangeMediaScene', () => {
  const W = 1440;
  const H = 900;

  function makePlate(type) {
    const el = document.createElement('div');
    el.className = 'viewer-plate';
    el.dataset.cardType = type;
    return el;
  }
  function makeCard(height) {
    const el = document.createElement('div');
    el.className = 'text-card';
    Object.defineProperty(el, 'offsetHeight', { value: height });
    return el;
  }
  const how = (over = {}) => ({ W, H, eligible: true, besideTop: () => 333, ...over });

  it('puts every card of a short scene below, bottom edge one padding above the window\'s', () => {
    const p = makePlate('vimeo');
    const cards = [makeCard(120), makeCard(150)];
    expect(arrangeMediaScene(p, cards, how())).toBe('below');
    const pad = mediaPadding(W, H);
    expect(cards[0].style.getPropertyValue('top')).toBe(`${H - pad - 120}px`);
    expect(cards[1].style.getPropertyValue('top')).toBe(`${H - pad - 150}px`);
    expect(cards[1].style.getPropertyPriority('top')).toBe('important');
    // The player is placed against the tallest card.
    expect(p.dataset.mediaCardTop).toBe(String(H - pad - 150));
    expect(cards.every((c) => c.dataset.mediaArrangement === 'below')).toBe(true);
  });

  it('decides a scene by its tallest card', () => {
    const p = makePlate('vimeo');
    const cards = [makeCard(120), makeCard(560)];
    expect(arrangeMediaScene(p, cards, how())).toBe('beside');
    expect(cards[0].style.getPropertyValue('top')).toBe('333px');
  });

  it('decides with the card height it is given: ignoring it would put a 560px card below', () => {
    const p = makePlate('audio');
    expect(arrangeMediaScene(p, [makeCard(560)], how())).toBe('beside');
    expect(arrangeMediaScene(p, [makeCard(120)], how())).toBe('below');
  });

  it('leaves a scene alone where the cards were not sized to their content', () => {
    const p = makePlate('youtube');
    p.dataset.mediaArrangement = 'below';
    const cards = [makeCard(120)];
    expect(arrangeMediaScene(p, cards, how({ eligible: false }))).toBeNull();
    expect(p.dataset.mediaArrangement).toBeUndefined();
    expect(cards[0].style.getPropertyValue('top')).toBe('');
  });

  it('keeps the card beside in embed mode', () => {
    state.isEmbed = true;
    expect(arrangeMediaScene(makePlate('vimeo'), [makeCard(120)], how())).toBeNull();
  });

  it('does not arrange an image scene', () => {
    expect(arrangeMediaScene(makePlate('iiif'), [makeCard(120)], how())).toBeNull();
  });

  it('hands the player the card top and band only while the card is below', () => {
    const p = makePlate('vimeo');
    arrangeMediaScene(p, [makeCard(120)], how());
    expect(readBelow(p)).toEqual({
      cardTop: Number(p.dataset.mediaCardTop), topBand: Number(p.dataset.mediaTopBand),
    });
    state.layoutMode = 'vertical';
    expect(readBelow(p)).toBeNull();
  });

  describe('the top band', () => {
    let counter;
    beforeEach(() => {
      counter = document.createElement('div');
      counter.className = 'step-counter';
      counter.getBoundingClientRect = () => ({ top: 12, bottom: 45, left: 1347, right: 1428, width: 81, height: 33 });
      document.body.appendChild(counter);
    });
    afterEach(() => { counter.remove(); });

    it('hands the player the band while the card is beside it', () => {
      const p = makePlate('vimeo');
      expect(arrangeMediaScene(p, [makeCard(560)], how())).toBe('beside');
      expect(readTopBand(p)).toBe(45 + mediaPadding(W, H));
    });

    it.each([
      ['a layout the cards are not content-sized on', { eligible: false }, false],
      ['embed mode', {}, true],
      ['a scene with no cards', { cards: [] }, false],
    ])('hands the player the band where the scene is not arranged: %s', (_, over, embed) => {
      state.isEmbed = embed;
      const p = makePlate('google-drive');
      p.dataset.mediaArrangement = 'below';
      const cards = over.cards ?? [makeCard(120)];
      expect(arrangeMediaScene(p, cards, how({ eligible: over.eligible ?? true }))).toBeNull();
      expect(p.dataset.mediaArrangement).toBeUndefined();
      expect(readBelow(p)).toBeNull();
      expect(readTopBand(p)).toBe(45 + mediaPadding(W, H));
    });

    it('hands no band to an image plate, or on a vertical layout', () => {
      const image = makePlate('iiif');
      arrangeMediaScene(image, [makeCard(120)], how());
      expect(readTopBand(image)).toBe(0);
      const p = makePlate('vimeo');
      arrangeMediaScene(p, [makeCard(560)], how());
      state.layoutMode = 'vertical';
      expect(readTopBand(p)).toBe(0);
    });
  });

  it('gives an audio plate its waveform geometry as custom properties, and takes it back', () => {
    // placeAudioBelow reads the window, which jsdom makes 1024x768.
    const size = { W: window.innerWidth, H: window.innerHeight };
    const p = makePlate('audio');
    arrangeMediaScene(p, [makeCard(120)], how(size));
    expect(placeAudioBelow(p)).toBe(Math.round(size.H * 0.5));
    expect(p.style.getPropertyValue('--telar-audio-wave-left')).toBe(`${mediaPadding(size.W, size.H)}px`);
    arrangeMediaScene(p, [makeCard(120)], how({ ...size, eligible: false }));
    expect(placeAudioBelow(p)).toBeNull();
    expect(p.style.getPropertyValue('--telar-audio-wave-left')).toBe('');
  });
});

describe('the stylesheet', () => {
  const readSource = (f) => readFileSync(resolve(process.cwd(), f), 'utf8');

  it('mirrors the threshold and the waveform\'s side geometry to :root', () => {
    const sheet = readSource('_sass/_responsive.scss');
    expect(sheet).toMatch(/--telar-media-below-gain:\s+#\{\$telar-media-below-gain\};/);
    expect(sheet).toMatch(/--telar-audio-wave-side-left:\s+#\{\$telar-audio-wave-side-left\};/);
    expect(sheet).toMatch(/--telar-audio-wave-side-width:\s+#\{\$telar-audio-wave-side-width\};/);
  });

  it('places the waveform beside the card from those variables', () => {
    const rule = readSource('_sass/_story.scss').match(/\n\.waveform-container \{([^}]*)\}/);
    expect(rule[1]).toMatch(/left: \$telar-audio-wave-side-left;/);
    expect(rule[1]).toMatch(/width: \$telar-audio-wave-side-width;/);
  });

  it('builds the waveform\'s side geometry from the card\'s, past the gap audio-layout.js reads', () => {
    const sheet = readSource('_sass/_responsive.scss');
    expect(sheet).toMatch(/\$telar-audio-wave-side-left:\s+calc\(var\(--telar-card-side-left\) \+ var\(--telar-card-side-width\) \+ #\{\$telar-audio-wave-side-gap\}\);/);
    expect(sheet).toMatch(/\$telar-audio-wave-side-width:\s+calc\(100% - var\(--telar-card-side-left\) - var\(--telar-card-side-width\) - #\{\$telar-audio-wave-side-gap\}\);/);
    expect(sheet).toMatch(/--telar-audio-wave-side-gap:\s+#\{\$telar-audio-wave-side-gap\};/);
  });
});
