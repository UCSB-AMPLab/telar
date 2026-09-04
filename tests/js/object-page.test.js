/**
 * Tests for the object page modules (assets/js/object-page/).
 *
 * These cover what jsdom can reach: the data block, dispatch, provider
 * detection, the copy helper and the panels it serves, the video embed and
 * clip picker with stubbed players, the audio helpers, and the viewer
 * wiring with a stubbed wrapper. A browser smoke covers the rest against a
 * served build.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../assets/js/telar-story/iiif-viewer.js', () => {
  class IiifViewer {
    constructor(options) {
      IiifViewer.last = this;
      this.options = options;
      this.pages = IiifViewer.pages;
      this.currentPage = 0;
      this.viewer = {
        handlers: {},
        addHandler(name, fn) { this.handlers[name] = fn; },
        world: { getItemCount: () => 1, addHandler() {} },
        viewport: { goHome: vi.fn() },
      };
      this.ready = IiifViewer.fail ? Promise.reject(new Error('no')) : Promise.resolve();
    }
  }
  IiifViewer.pages = [{}];
  IiifViewer.fail = false;
  return {
    IiifViewer,
    normalizedViewportPosition: () => ({ x: 0.25, y: 0.75, zoom: 2 }),
  };
});

import { readObjectData, publishLanguageGlobals, initObjectPage } from '../../assets/js/object-page/main.js';
import { copyWithFeedback, CHECK_ICON } from '../../assets/js/object-page/copy-feedback.js';
import { initClipPanelToggle, initClipCopyButtons } from '../../assets/js/object-page/clip-panel.js';
import { videoProvider, initVideoEmbed, initClipPicker, initCopyEmbedUrl } from '../../assets/js/object-page/video-object.js';
import { formatTime, findAudioUrl, controlsMarkup } from '../../assets/js/object-page/audio-object.js';
import { manifestUrlFor, initImageViewer, initCoordinatePanel } from '../../assets/js/object-page/image-object.js';
import { IiifViewer } from '../../assets/js/telar-story/iiif-viewer.js';

const LANG = {
  copied: '...copied',
  viewer: { prev_page: 'Previous', next_page: 'Next' },
  embedUnavailable: 'This video could not be loaded.',
  openOnDrive: 'Open it on Google Drive.',
  audioNotFound: 'Audio file not available.',
  play: 'Play audio', pause: 'Pause audio', restart: 'Restart',
  mute: 'Mute audio', unmute: 'Unmute audio',
};

function data(overrides = {}) {
  return { mediaType: 'Image', objectId: 'figueroa', sourceUrl: '', externalSource: '',
           baseUrl: '/telar', videoFrameTitle: 'Video: Test', waveformLabel: 'Waveform',
           lang: LANG, ...overrides };
}

let clipboard;

beforeEach(() => {
  document.body.innerHTML = '';
  clipboard = [];
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: (text) => { clipboard.push(text); return Promise.resolve(); } },
  });
  window.telarObjectTheme = { applyPanelContrastClass: vi.fn(), deriveThemeColors: vi.fn() };
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  delete window.ytPlayer;
  delete window._vimeoPlayer;
  delete window.onYouTubeIframeAPIReady;
});

const flush = () => Promise.resolve().then(() => Promise.resolve());

// ── The data block ──────────────────────────────────────────────────────────

describe('readObjectData', () => {
  it('is null on a page with no data block', () => {
    expect(readObjectData()).toBeNull();
  });

  it('parses the block the layout writes', () => {
    document.body.innerHTML = '<script id="telar-object-data" type="application/json">{"mediaType":"Audio","objectId":"a"}</script>';
    expect(readObjectData()).toEqual({ mediaType: 'Audio', objectId: 'a' });
  });

  it('is null, not a throw, when the block is not JSON', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    document.body.innerHTML = '<script id="telar-object-data" type="application/json">{nope</script>';
    expect(readObjectData()).toBeNull();
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });
});

describe('publishLanguageGlobals', () => {
  it('sets the two globals the viewer wrapper and coordinate panel read', () => {
    const win = {};
    publishLanguageGlobals(data(), win);
    expect(win.telarCoordLang).toEqual({ copied: '...copied' });
    expect(win.telarViewerLang).toBe(LANG.viewer);
  });
});

// ── Copy feedback ───────────────────────────────────────────────────────────

describe('copyWithFeedback', () => {
  it('writes the text, shows the feedback for two seconds, then restores the button', async () => {
    document.body.innerHTML = '<button id="b">Copy</button>';
    await copyWithFeedback('hello', 'b', CHECK_ICON + ' done');
    expect(clipboard).toEqual(['hello']);
    expect(document.getElementById('b').innerHTML).toContain('done');
    vi.advanceTimersByTime(2000);
    expect(document.getElementById('b').innerHTML).toBe('Copy');
  });
});

// ── Clip panel ──────────────────────────────────────────────────────────────

describe('clip panel', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="clip-panel" id="clipPanel"></div><div id="clipPickerButton"></div>
      <span id="clip-start-display">1.500</span><span id="clip-end-display">4.250</span>
      <button id="copy-clip-csv">csv</button><button id="copy-clip-sheets">sheets</button>`;
  });

  it('hides its button while the panel is open', () => {
    initClipPanelToggle();
    document.getElementById('clipPanel').dispatchEvent(new Event('show.bs.collapse'));
    expect(document.getElementById('clipPickerButton').style.display).toBe('none');
    document.getElementById('clipPanel').dispatchEvent(new Event('hide.bs.collapse'));
    expect(document.getElementById('clipPickerButton').style.display).toBe('block');
    expect(window.telarObjectTheme.applyPanelContrastClass).toHaveBeenCalledWith(document.querySelector('.clip-panel'));
  });

  it('copies the clip as CSV and as tab-separated text', async () => {
    initClipCopyButtons('...copied');
    document.getElementById('copy-clip-csv').click();
    document.getElementById('copy-clip-sheets').click();
    await flush();
    expect(clipboard).toEqual(['1.500,4.250', '1.500\t4.250']);
    expect(document.getElementById('copy-clip-csv').innerHTML).toContain('...copied');
  });
});

// ── Video ───────────────────────────────────────────────────────────────────

describe('videoProvider', () => {
  it.each([
    ['https://www.youtube.com/watch?v=x', 'youtube'],
    ['https://youtu.be/x', 'youtube'],
    ['https://vimeo.com/1', 'vimeo'],
    ['https://drive.google.com/file/d/1/view', 'gdrive'],
    ['https://example.org/video.mp4', null],
  ])('%s is %s', (url, provider) => {
    expect(videoProvider(url)).toBe(provider);
  });
});

describe('initVideoEmbed', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="object-viewer"></div><span id="embed-url-display"></span>';
    window.telarVideoEmbed = {
      resolveVideoEmbed: vi.fn(() => ({ iframeHtml: '<iframe id="video-player-iframe"></iframe>', embedUrl: 'https://e/embed' })),
    };
  });

  it('injects the resolved iframe and shows the embed URL', () => {
    initVideoEmbed(data({ mediaType: 'Video', sourceUrl: 'https://vimeo.com/1' }));
    expect(window.telarVideoEmbed.resolveVideoEmbed).toHaveBeenCalledWith('https://vimeo.com/1', 'Video: Test');
    expect(document.getElementById('video-player-iframe')).not.toBeNull();
    expect(document.getElementById('embed-url-display').textContent).toBe('https://e/embed');
  });

  it('does nothing when the URL resolves to no embed', () => {
    window.telarVideoEmbed.resolveVideoEmbed = () => null;
    initVideoEmbed(data({ mediaType: 'Video', sourceUrl: 'x' }));
    expect(document.getElementById('object-viewer').innerHTML).toBe('');
  });

  it('replaces a Google Drive frame that never loads with a warning and a link', () => {
    const url = 'https://drive.google.com/file/d/1/view';
    initVideoEmbed(data({ mediaType: 'Video', sourceUrl: url }));
    expect(document.getElementById('embed-url-display').textContent).toBe('');
    vi.advanceTimersByTime(10000);
    const link = document.querySelector('#object-viewer .alert a');
    expect(link.getAttribute('href')).toBe(url);
    expect(link.getAttribute('rel')).toBe('noopener');
    expect(document.querySelector('#object-viewer .alert').textContent).toContain('This video could not be loaded.');
  });

  it('keeps a Drive frame that loads in time', () => {
    initVideoEmbed(data({ mediaType: 'Video', sourceUrl: 'https://drive.google.com/file/d/1/view' }));
    document.getElementById('video-player-iframe').dispatchEvent(new Event('load'));
    vi.advanceTimersByTime(10000);
    expect(document.getElementById('video-player-iframe')).not.toBeNull();
  });

  it('renders no link for a source that is not http(s)', () => {
    window.telarVideoEmbed.resolveVideoEmbed = () => ({ iframeHtml: '<iframe id="video-player-iframe"></iframe>', embedUrl: '' });
    initVideoEmbed(data({ mediaType: 'Video', sourceUrl: 'javascript:alert(1)//drive.google.com' }));
    vi.advanceTimersByTime(10000);
    expect(document.querySelector('#object-viewer .alert a')).toBeNull();
  });
});

describe('initClipPicker', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <iframe id="video-player-iframe"></iframe>
      <button id="set-clip-start" disabled>s</button><button id="set-clip-end" disabled>e</button>
      <span id="clip-start-display">0.000</span><span id="clip-end-display">0.000</span>`;
  });

  it('loads the YouTube API and reads the player time into the clip', async () => {
    initClipPicker(data({ sourceUrl: 'https://youtu.be/x' }));
    expect(document.head.querySelector('script[src="https://www.youtube.com/iframe_api"]')).not.toBeNull();
    window.YT = { Player: class { constructor(id, opts) { opts.events.onReady(); } } };
    window.onYouTubeIframeAPIReady();
    expect(document.getElementById('set-clip-start').disabled).toBe(false);
    window.ytPlayer = { getCurrentTime: () => 12.3456 };
    document.getElementById('set-clip-end').click();
    await flush();
    expect(document.getElementById('clip-end-display').textContent).toBe('12.346');
    delete window.YT;
  });

  it('writes zero when no player is ready', async () => {
    initClipPicker(data({ sourceUrl: 'https://example.org/v.mp4' }));
    document.getElementById('set-clip-start').click();
    await flush();
    expect(document.getElementById('clip-start-display').textContent).toBe('0.000');
  });

  it('loads the Vimeo player script for a Vimeo source', () => {
    initClipPicker(data({ sourceUrl: 'https://vimeo.com/1' }));
    expect(document.head.querySelector('script[src="https://player.vimeo.com/api/player.js"]')).not.toBeNull();
  });
});

describe('initCopyEmbedUrl', () => {
  it('copies the displayed embed URL', async () => {
    document.body.innerHTML = '<span id="embed-url-display">https://e/embed</span><button id="copy-embed-url">c</button>';
    initCopyEmbedUrl();
    document.getElementById('copy-embed-url').click();
    await flush();
    expect(clipboard).toEqual(['https://e/embed']);
  });
});

// ── Audio ───────────────────────────────────────────────────────────────────

describe('audio helpers', () => {
  it('formats seconds as m:ss', () => {
    expect(formatTime(0)).toBe('0:00');
    expect(formatTime(65.9)).toBe('1:05');
    expect(formatTime(141.596)).toBe('2:21');
  });

  it('tries the extensions in order and takes the first the server answers for', async () => {
    const asked = [];
    const fetchFn = async (url) => { asked.push(url); return { ok: url.endsWith('.ogg') }; };
    expect(await findAudioUrl('/telar', 'cusb', fetchFn)).toBe('/telar/telar-content/objects/cusb.ogg');
    expect(asked).toEqual(['/telar/telar-content/objects/cusb.mp3', '/telar/telar-content/objects/cusb.ogg']);
  });

  it('is null when nothing answers, and a failed request is not an answer', async () => {
    expect(await findAudioUrl('/t', 'x', async () => { throw new Error('offline'); })).toBeNull();
  });

  it('renders the three controls with their labels', () => {
    const markup = controlsMarkup(data({ mediaType: 'Audio' }));
    document.body.innerHTML = markup;
    expect(document.getElementById('audio-waveform').getAttribute('aria-label')).toBe('Waveform');
    expect(document.getElementById('audio-play-btn').getAttribute('aria-label')).toBe('Play audio');
    expect(document.getElementById('audio-mute-btn').getAttribute('aria-label')).toBe('Mute audio');
    expect(document.getElementById('audio-time-display').textContent).toBe('0:00 / --:--');
  });
});

// ── Image ───────────────────────────────────────────────────────────────────

describe('manifestUrlFor', () => {
  it('prefers the external source', () => {
    expect(manifestUrlFor(data({ externalSource: 'https://x/manifest' }))).toBe('https://x/manifest');
  });
  it('builds the site path from the object id', () => {
    expect(manifestUrlFor(data())).toBe('/telar/iiif/objects/figueroa/manifest.json');
  });
  it('is null with neither', () => {
    expect(manifestUrlFor(data({ objectId: null }))).toBeNull();
  });
});

describe('initImageViewer', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="coordinate-panel"></div><div id="object-viewer"></div>
      <div class="coord-page-row" style="display:none"></div>
      <p class="coord-instructions-single"></p><p class="coord-instructions-multi" style="display:none"></p>
      <span id="coord-x"></span><span id="coord-y"></span><span id="coord-zoom"></span><span id="coord-page"></span>`;
    IiifViewer.pages = [{}];
    IiifViewer.fail = false;
  });

  it('mounts the wrapper on the manifest and writes the first coordinates', async () => {
    await initImageViewer(data());
    expect(IiifViewer.last.options).toMatchObject({ container: '#object-viewer', manifestUrl: '/telar/iiif/objects/figueroa/manifest.json', showChrome: true, allowZoomGestures: true });
    expect(document.getElementById('coord-x').textContent).toBe('0.250');
    expect(document.getElementById('coord-zoom').textContent).toBe('2.0');
    expect(document.getElementById('object-viewer').classList.contains('multipage')).toBe(false);
  });

  it('turns on the page row and page instructions for a multi-page manifest', async () => {
    IiifViewer.pages = [{}, {}, {}];
    await initImageViewer(data());
    expect(document.getElementById('object-viewer').classList.contains('multipage')).toBe(true);
    expect(document.querySelector('.coord-page-row').style.display).toBe('flex');
    expect(document.querySelector('.coord-instructions-multi').style.display).toBe('block');
    expect(document.getElementById('coord-page').textContent).toBe('1');
  });

  it('logs and stops when the wrapper fails to initialise', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    IiifViewer.fail = true;
    await initImageViewer(data());
    expect(error).toHaveBeenCalledWith('IiifViewer failed to initialise:', expect.any(Error));
    expect(document.getElementById('coord-x').textContent).toBe('');
    error.mockRestore();
  });

  it('logs and stops with no source at all', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    IiifViewer.last = null;
    await initImageViewer(data({ objectId: null }));
    expect(error).toHaveBeenCalledWith('No IIIF source specified');
    expect(IiifViewer.last).toBeNull();
    error.mockRestore();
  });
});

describe('initCoordinatePanel', () => {
  beforeEach(() => {
    window.telarCoordLang = { copied: '...copied' };
    document.body.innerHTML = `
      <div id="coordinatePanel"></div><div id="coordinateButton"></div>
      <div id="object-viewer"></div><div class="coord-page-row"></div>
      <span id="coord-x">0.500</span><span id="coord-y">0.250</span><span id="coord-zoom">1.0</span><span id="coord-page">3</span>
      <button id="copy-coords-csv">csv</button><button id="copy-coords-sheets">sheets</button>
      <button id="copy-manifest" data-manifest="https://m/manifest.json">m</button>
      <button id="copy-x">x</button><button id="copy-page">p</button>`;
  });

  it('copies x, y and zoom without the page for a single-page object', async () => {
    // The row is hidden by a stylesheet class, not an inline style, and
    // that must not read as "shown".
    expect(document.querySelector('.coord-page-row').style.display).toBe('');
    initCoordinatePanel();
    document.getElementById('copy-coords-csv').click();
    document.getElementById('copy-coords-sheets').click();
    await flush();
    expect(clipboard).toEqual(['0.500,0.250,1.0', '0.500\t0.250\t1.0']);
    expect(document.getElementById('copy-coords-csv').innerHTML).toContain('...copied');
  });

  it('appends the page once the viewer has marked the object multi-page', async () => {
    document.getElementById('object-viewer').classList.add('multipage');
    initCoordinatePanel();
    document.getElementById('copy-coords-csv').click();
    await flush();
    expect(clipboard).toEqual(['0.500,0.250,1.0,3']);
  });

  it('copies the manifest URL and single values with the checkmark alone', async () => {
    initCoordinatePanel();
    document.getElementById('copy-manifest').click();
    document.getElementById('copy-x').click();
    document.getElementById('copy-page').click();
    await flush();
    expect(clipboard).toEqual(['https://m/manifest.json', '0.500', '3']);
    expect(document.getElementById('copy-x').innerHTML).toContain('<svg');
    expect(document.getElementById('copy-x').innerHTML).not.toContain('...copied');
  });

  it('hides its button while the panel is open', () => {
    initCoordinatePanel();
    document.getElementById('coordinatePanel').dispatchEvent(new Event('show.bs.collapse'));
    expect(document.getElementById('coordinateButton').style.display).toBe('none');
  });
});

// ── Dispatch ────────────────────────────────────────────────────────────────

describe('initObjectPage', () => {
  it('wires an audio page: the player and the clip panel, and no viewer', async () => {
    document.body.innerHTML = '<div id="object-viewer"></div><div id="clipPanel" class="clip-panel"></div><div id="clipPickerButton"></div>';
    vi.stubGlobal('fetch', async () => ({ ok: false }));
    IiifViewer.last = null;
    initObjectPage(data({ mediaType: 'Audio' }));
    await flush(); await flush(); await flush(); await flush();
    expect(document.getElementById('object-viewer').textContent).toContain('Audio file not available.');
    expect(IiifViewer.last).toBeNull();
    vi.unstubAllGlobals();
  });

  it('wires nothing for a media type it does not know', () => {
    document.body.innerHTML = '<div id="object-viewer">untouched</div>';
    initObjectPage(data({ mediaType: '3D' }));
    expect(document.getElementById('object-viewer').textContent).toBe('untouched');
  });
});
