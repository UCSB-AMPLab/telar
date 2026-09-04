/**
 * Characterisation tests for the share panel.
 *
 * The share panel publishes no global. Its whole interface is the DOM of
 * `_includes/share-panel.html`: what the three read-only inputs and the embed
 * textarea hold, which warnings and which sections carry `d-none`, which key
 * button is `active`, what options the story selector holds and what each is
 * flagged with, whether the copy buttons are disabled, and what a copy writes
 * to the clipboard. These pin that output for every branch, so that a refactor
 * is judged by whether the panel still says the same thing.
 *
 * Two pages render two different panels, so both are exercised: a story page
 * (`body.story-page`, a path under `/stories/`, the story branch's markup) and
 * the home page (no class, `/telar/`, the branch every other page renders,
 * with the stories JSON block `_layouts/index.html` writes). The path moves
 * between them with `history.replaceState`, which is what the script reads for
 * the story URL, the deep-link fragment and the site URL alike.
 *
 * @version v1.7.0
 */

// @vitest-environment-options { "url": "https://example.org/telar/" }

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  ORIGIN, BASEURL, ALLEGORICAL, LOCKED, CHECK_ICON,
  storyPanelMarkup, otherPanelMarkup, storiesBlock, storiesBlockFor,
  renderPage, setOgTitle, addUnlockOverlay,
  stubClipboard, removeClipboard, stubAlert,
  runScript, openPanel, el, value, hasClass, icon, selectOptions,
  chooseStory, choosePreset, typeDimension,
  silenceConsole, resetTimersMocksAndDom,
} from './share-panel-fixture.js';

const STORY_PATH = `${BASEURL}/stories/allegorical-woman/`;
const STORY_URL = `${ORIGIN}${STORY_PATH}`;
const SITE_URL = `${ORIGIN}${BASEURL}/`;
const KEY = 's3cr3tkey';

/** The iframe the embed section writes, as a string the assertions compare to. */
function iframe({ src, width = '100%', height = '800px', title }) {
  return `<iframe src="${src}"\n  width="${width}" height="${height}" title="${title}"\n  frameborder="0">\n</iframe>`;
}

/** A story page with the story branch's panel on it. */
function storyPage({ path = STORY_PATH, title = 'Telar' } = {}) {
  renderPage({ path, bodyClass: 'story-page', title, markup: storyPanelMarkup() });
}

/** The home page with the other branch's panel and the stories block on it. */
function homePage({ block = storiesBlockFor() } = {}) {
  renderPage({
    path: `${BASEURL}/`,
    bodyClass: '',
    title: 'Telar',
    markup: otherPanelMarkup() + block,
  });
}

/** Let the clipboard promise settle without letting the feedback timer run. */
async function settle() {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}

let consoles;

beforeEach(() => {
  consoles = silenceConsole();
});

afterEach(() => {
  resetTimersMocksAndDom();
});

describe('binding', () => {
  it('binds nothing when the panel is absent', async () => {
    renderPage({
      path: `${BASEURL}/`,
      markup: otherPanelMarkup().replace('id="panel-share"', 'id="panel-share-elsewhere"')
        + storiesBlockFor(),
    });
    const writes = stubClipboard();

    await runScript();

    expect(selectOptions()).toEqual([{ value: '', text: 'Choose a story...', protected: undefined }]);
    el('share-copy-link-btn').click();
    expect(writes).toEqual([]);
  });
});

describe('story page, an open story', () => {
  beforeEach(async () => {
    storyPage({ path: `${STORY_PATH}?step=3#step-3` });
    setOgTitle(ALLEGORICAL.title);
    await runScript();
    openPanel();
  });

  it('shares the page URL without its query or hash', () => {
    expect(value('share-url-input')).toBe(STORY_URL);
  });

  it('carries the current hash into the view URL', () => {
    expect(value('share-view-url-input')).toBe(`${STORY_URL}#step-3`);
  });

  it('shares the site as the origin and the first path segment', () => {
    expect(value('share-site-url-input')).toBe(SITE_URL);
  });

  it('embeds the story at its default preset size', () => {
    expect(value('embed-code-textarea')).toBe(iframe({
      src: `${STORY_URL}?embed=true`,
      title: ALLEGORICAL.title,
    }));
  });

  it('keeps the privacy section and both key warnings hidden', () => {
    expect(hasClass('story-privacy-section', 'd-none')).toBe(true);
    expect(hasClass('share-key-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-key-warning', 'd-none')).toBe(true);
  });
});

describe('story page, the embed title', () => {
  it('prefers og:title over the document title', async () => {
    storyPage({ title: 'Telar' });
    setOgTitle(ALLEGORICAL.title);
    await runScript();
    openPanel();

    expect(value('embed-code-textarea')).toContain(`title="${ALLEGORICAL.title}"`);
  });

  it('falls back to the document title when there is no og:title', async () => {
    storyPage({ title: ALLEGORICAL.title });
    await runScript();
    openPanel();

    expect(value('embed-code-textarea')).toContain(`title="${ALLEGORICAL.title}"`);
  });

  it('escapes quotes, angle brackets and ampersands in the title', async () => {
    // A synthetic probe over the three characters escapeAttr covers, built on
    // the real story title Título, not a story this repository holds.
    storyPage({ title: `Título & <b>"tag"</b> 'x'` });
    await runScript();
    openPanel();

    expect(value('embed-code-textarea')).toContain(
      'title="Título &amp; &lt;b&gt;&quot;tag&quot;&lt;/b&gt; &#39;x&#39;"');
  });
});

describe('story page, the embed URL', () => {
  beforeEach(async () => {
    storyPage({ title: ALLEGORICAL.title });
    await runScript();
  });

  const cases = [
    ['a bare URL', STORY_PATH],
    ['a URL with a query', `${STORY_PATH}?step=3`],
    ['a URL with a hash', `${STORY_PATH}#step-3`],
    ['a URL with both', `${STORY_PATH}?step=3#step-3`],
  ];

  cases.forEach(([name, path]) => {
    it(`adds embed=true alone to ${name}`, () => {
      window.history.replaceState({}, '', path);
      openPanel();

      expect(value('embed-code-textarea')).toContain(`src="${STORY_URL}?embed=true"`);
    });
  });
});

describe('story page, a protected story before unlock', () => {
  beforeEach(async () => {
    storyPage({ title: LOCKED.title });
    // Split so this file never carries the literal stub token: the encryptor
    // scans the whole built site for it, and Jekyll copies tests/ into _site/.
    const PENDING = '__TELAR_' + 'PENDING__';
    window.storyData = { encrypted: true, salt: '', iv: '', ciphertext: PENDING };
    addUnlockOverlay();
    await runScript();
    openPanel();
  });

  it('keeps the privacy section hidden without a key', () => {
    expect(hasClass('story-privacy-section', 'd-none')).toBe(true);
  });

  it('keeps both key warnings hidden', () => {
    expect(hasClass('share-key-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-key-warning', 'd-none')).toBe(true);
  });

  it('shares a URL and an embed with no key on them', () => {
    expect(value('share-url-input')).toBe(STORY_URL);
    expect(value('embed-code-textarea')).toContain(`src="${STORY_URL}?embed=true"`);
  });
});

describe('story page, a protected story after unlock', () => {
  beforeEach(async () => {
    storyPage({ path: `${STORY_PATH}#step-3`, title: LOCKED.title });
    window.storyData = { steps: [], firstObject: '' };
    window.telarStoryKey = KEY;
    addUnlockOverlay();
    await runScript();
    openPanel();
  });

  it('shows the privacy section', () => {
    expect(hasClass('story-privacy-section', 'd-none')).toBe(false);
  });

  it('opens on Without key, with no key anywhere', () => {
    expect(hasClass('share-key-without', 'active')).toBe(true);
    expect(hasClass('share-key-with', 'active')).toBe(false);
    expect(value('share-url-input')).toBe(STORY_URL);
    expect(value('share-view-url-input')).toBe(`${STORY_URL}#step-3`);
    expect(value('embed-code-textarea')).toContain(`src="${STORY_URL}?embed=true"`);
    expect(hasClass('share-key-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-key-warning', 'd-none')).toBe(true);
  });

  it('appends the key to all three outputs and warns twice on With key', () => {
    el('share-key-with').click();

    expect(hasClass('share-key-with', 'active')).toBe(true);
    expect(hasClass('share-key-without', 'active')).toBe(false);
    expect(value('share-url-input')).toBe(`${STORY_URL}?key=${KEY}`);
    expect(value('share-view-url-input')).toBe(`${STORY_URL}?key=${KEY}#step-3`);
    expect(value('embed-code-textarea')).toContain(`src="${STORY_URL}?embed=true&key=${KEY}"`);
    expect(hasClass('share-key-warning', 'd-none')).toBe(false);
    expect(hasClass('embed-key-warning', 'd-none')).toBe(false);
  });

  it('takes the key back off on Without key', () => {
    el('share-key-with').click();
    el('share-key-without').click();

    expect(hasClass('share-key-without', 'active')).toBe(true);
    expect(hasClass('share-key-with', 'active')).toBe(false);
    expect(value('share-url-input')).toBe(STORY_URL);
    expect(value('embed-code-textarea')).toContain(`src="${STORY_URL}?embed=true"`);
    expect(hasClass('share-key-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-key-warning', 'd-none')).toBe(true);
  });

  it('resets the toggle to Without key on each open', () => {
    el('share-key-with').click();
    openPanel();

    expect(hasClass('share-key-without', 'active')).toBe(true);
    expect(hasClass('share-key-with', 'active')).toBe(false);
    expect(value('share-url-input')).toBe(STORY_URL);
    expect(hasClass('share-key-warning', 'd-none')).toBe(true);
  });
});

describe('story page, a key without a protected story', () => {
  beforeEach(async () => {
    storyPage({ title: ALLEGORICAL.title });
    window.telarStoryKey = KEY;
    await runScript();
    openPanel();
  });

  it('keeps the privacy section hidden', () => {
    expect(hasClass('story-privacy-section', 'd-none')).toBe(true);
  });

  it('still appends the key when the hidden toggle is pressed, and warns about nothing', () => {
    el('share-key-with').click();

    expect(value('share-url-input')).toBe(`${STORY_URL}?key=${KEY}`);
    expect(value('embed-code-textarea')).toContain(`src="${STORY_URL}?embed=true&key=${KEY}"`);
    expect(hasClass('share-key-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-key-warning', 'd-none')).toBe(true);
  });
});

describe('embed dimensions', () => {
  beforeEach(async () => {
    storyPage({ title: ALLEGORICAL.title });
    await runScript();
    openPanel();
  });

  const presets = [
    ['canvas', '100%', '800'],
    ['moodle', '100%', '700'],
    ['wordpress', '100%', '600'],
    ['squarespace', '100%', '600'],
    ['wix', '100%', '550'],
    ['mobile', '375', '500'],
    ['fixed', '800', '600'],
  ];

  presets.forEach(([preset, width, height]) => {
    it(`sets ${width} by ${height} for the ${preset} preset`, () => {
      choosePreset(preset);

      expect(value('embed-width-input')).toBe(width);
      expect(value('embed-height-input')).toBe(height);
      expect(value('embed-code-textarea')).toContain(
        `width="${/^\d+$/.test(width) ? `${width}px` : width}" height="${height}px"`);
    });
  });

  it('leaves the dimensions alone for the custom preset', () => {
    choosePreset('mobile');
    choosePreset('custom');

    expect(value('embed-width-input')).toBe('375');
    expect(value('embed-height-input')).toBe('500');
  });

  it('regenerates the embed code as a width is typed', () => {
    typeDimension('embed-width-input', '640');

    expect(value('embed-code-textarea')).toContain('width="640px" height="800px"');
  });

  it('regenerates the embed code as a height is typed', () => {
    typeDimension('embed-height-input', '55%');

    expect(value('embed-code-textarea')).toContain('width="100%" height="55%"');
  });

  it('appends px to a bare number and leaves a unit alone', () => {
    typeDimension('embed-width-input', ' 800 ');
    typeDimension('embed-height-input', '30em');

    expect(value('embed-code-textarea')).toContain('width="800px" height="30em"');
  });

  it('falls back to 100% by 800 when a dimension is emptied', () => {
    typeDimension('embed-width-input', '');
    typeDimension('embed-height-input', '');

    expect(value('embed-code-textarea')).toContain('width="100%" height="800px"');
  });
});

describe('home page', () => {
  beforeEach(async () => {
    homePage();
    await runScript();
    openPanel();
  });

  it('fills the selector from the stories block, placeholder first', () => {
    expect(selectOptions()).toEqual([
      { value: '', text: 'Choose a story...', protected: undefined },
      { value: ALLEGORICAL.url, text: 'The Allegorical Woman', protected: 'false' },
      { value: `${ORIGIN}${BASEURL}/stories/colonial-landscapes/`, text: 'Colonial Landscapes', protected: 'false' },
      { value: LOCKED.url, text: '🔒 Locked Fixture Story', protected: 'true' },
    ]);
  });

  it('opens with nothing chosen and both copy buttons disabled', () => {
    expect(el('share-story-select').value).toBe('');
    expect(value('share-url-input')).toBe('');
    expect(value('embed-code-textarea')).toBe('');
    expect(el('share-copy-link-btn').disabled).toBe(true);
    expect(el('embed-copy-code-btn').disabled).toBe(true);
  });

  it('shares the whole site regardless of what is chosen', () => {
    expect(value('share-site-url-input')).toBe(SITE_URL);
  });

  it('shares an open story once it is chosen', () => {
    chooseStory(ALLEGORICAL.url);

    expect(value('share-url-input')).toBe(ALLEGORICAL.url);
    expect(value('embed-code-textarea')).toBe(iframe({
      src: `${ALLEGORICAL.url}?embed=true`,
      title: ALLEGORICAL.title,
    }));
    expect(el('share-copy-link-btn').disabled).toBe(false);
    expect(el('embed-copy-code-btn').disabled).toBe(false);
    expect(hasClass('share-protected-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-protected-warning', 'd-none')).toBe(true);
  });

  it('warns twice when the chosen story is protected, and drops the lock from the title', () => {
    chooseStory(LOCKED.url);

    expect(value('share-url-input')).toBe(LOCKED.url);
    expect(value('embed-code-textarea')).toBe(iframe({
      src: `${LOCKED.url}?embed=true`,
      title: LOCKED.title,
    }));
    expect(hasClass('share-protected-warning', 'd-none')).toBe(false);
    expect(hasClass('embed-protected-warning', 'd-none')).toBe(false);
  });

  it('clears and disables again when the placeholder is chosen back', () => {
    chooseStory(LOCKED.url);
    chooseStory('');

    expect(value('share-url-input')).toBe('');
    expect(value('embed-code-textarea')).toBe('');
    expect(el('share-copy-link-btn').disabled).toBe(true);
    expect(el('embed-copy-code-btn').disabled).toBe(true);
    expect(hasClass('share-protected-warning', 'd-none')).toBe(true);
    expect(hasClass('embed-protected-warning', 'd-none')).toBe(true);
  });

  it('clears the chosen story on each open', () => {
    chooseStory(LOCKED.url);
    openPanel();

    expect(el('share-story-select').value).toBe('');
    expect(value('share-url-input')).toBe('');
    expect(value('embed-code-textarea')).toBe('');
    expect(hasClass('share-protected-warning', 'd-none')).toBe(true);
  });
});

describe('home page, a stories block that gives nothing', () => {
  it('warns and adds no options when the JSON is malformed', async () => {
    homePage({ block: storiesBlock('[{"title": ') });
    await runScript();
    openPanel();

    expect(consoles.warn).toHaveBeenCalledWith('[Telar Share] Could not parse stories data');
    expect(selectOptions()).toEqual([{ value: '', text: 'Choose a story...', protected: undefined }]);
  });

  it('adds no options when the block holds an empty array', async () => {
    homePage({ block: storiesBlock('[]') });
    await runScript();
    openPanel();

    expect(selectOptions()).toEqual([{ value: '', text: 'Choose a story...', protected: undefined }]);
  });

  it('adds no options when there is no block at all', async () => {
    homePage({ block: '' });
    await runScript();
    openPanel();

    expect(selectOptions()).toEqual([{ value: '', text: 'Choose a story...', protected: undefined }]);
  });
});

describe('copying', () => {
  let writes;

  beforeEach(async () => {
    vi.useFakeTimers();
    writes = stubClipboard();
    storyPage({ path: `${STORY_PATH}#step-3`, title: ALLEGORICAL.title });
    await runScript();
    openPanel();
  });

  const buttons = [
    ['share-copy-link-btn', () => value('share-url-input')],
    ['share-copy-view-btn', () => value('share-view-url-input')],
    ['share-copy-site-btn', () => value('share-site-url-input')],
    ['embed-copy-code-btn', () => value('embed-code-textarea')],
  ];

  buttons.forEach(([id, expected]) => {
    it(`${id} writes what its field holds`, async () => {
      const before = icon(id).outerHTML;
      el(id).click();
      await settle();

      expect(writes).toEqual([expected()]);
      expect(icon(id).outerHTML).toBe(CHECK_ICON);

      vi.advanceTimersByTime(2000);
      expect(icon(id).outerHTML).toBe(before);
    });
  });

  it('keeps the checkmark until the two seconds are up', async () => {
    el('share-copy-link-btn').click();
    await settle();

    vi.advanceTimersByTime(1999);
    expect(icon('share-copy-link-btn').outerHTML).toBe(CHECK_ICON);
  });

  it('writes nothing when the field is empty', async () => {
    el('share-url-input').value = '';
    el('share-copy-link-btn').click();
    await settle();

    expect(writes).toEqual([]);
    expect(icon('share-copy-link-btn').outerHTML).not.toBe(CHECK_ICON);
  });
});

describe('copying without a working clipboard', () => {
  let alerts;

  beforeEach(async () => {
    vi.useFakeTimers();
    alerts = stubAlert();
    storyPage({ title: ALLEGORICAL.title });
  });

  it('asks the reader to copy by hand when there is no Clipboard API', async () => {
    removeClipboard();
    await runScript();
    openPanel();

    el('share-copy-link-btn').click();

    expect(alerts).toEqual(['Please manually copy the text']);
    expect(icon('share-copy-link-btn').outerHTML).not.toBe(CHECK_ICON);
  });

  it('asks the reader to copy by hand when the write is rejected', async () => {
    stubClipboard(() => Promise.reject(new Error('denied')));
    await runScript();
    openPanel();

    el('share-copy-link-btn').click();
    await settle();

    expect(alerts).toEqual(['Please manually copy the text']);
    expect(consoles.error).toHaveBeenCalledWith(
      '[Telar Share] Failed to copy:', expect.any(Error));
    expect(icon('share-copy-link-btn').outerHTML).not.toBe(CHECK_ICON);
  });
});
