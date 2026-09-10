/**
 * Characterisation tests for the IIIF URL mismatch warning.
 *
 * The banner's whole interface is the DOM: it publishes no global, attaches
 * no handler, and its only output is which of the include's hidden blocks it
 * reveals and what text it writes into them. These pin that output for every
 * branch -- the silent exits, both network failures, the local-development
 * and production fix paths, the singular/plural heading, and the
 * markup-as-text rendering of a title -- so that a refactor is judged by
 * whether the banner still says the same thing.
 *
 * Location and fetch are injected into the check rather than stubbed, and
 * the local-development and production cases below differ only by the origin
 * injected, which is what proves the injection reaches the code under test.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  readWarningData, initIIIFUrlWarning, findAffectedObjects,
  siteUrlFromLocation, isLocalDevOrigin, manifestBaseFromId, sameSite,
  regenerationCommand, configSuggestion,
} from '../../assets/js/iiif-url-warning/main.js';

/** The include's markup with the Liquid stripped and plain text in its place. */
const MARKUP = `
<div id="iiif-url-warning" class="alert alert-warning telar-alert" role="alert" style="display: none;">
  <strong>Images are not loading</strong>
  <p>The site address does not match the IIIF manifests.</p>

  <p class="mb-2"><strong>What is happening</strong></p>
  <ul class="mb-3">
    <li>You are viewing this site at <strong id="current-url"></strong></li>
    <li>The images are configured for <strong id="manifest-url"></strong></li>
  </ul>

  <p class="mb-2"><strong id="affected-images-heading">Affected images</strong></p>
  <ul class="mb-3" id="affected-images">
    <li id="stale-row">A row from a previous run</li>
  </ul>

  <div id="production-fix-instructions" style="display: none;">
    <p class="mb-2"><strong>Common causes</strong></p>
    <ul class="mb-3">
      <li>Incorrect settings</li>
      <li>The site moved</li>
      <li>A preview environment</li>
    </ul>

    <p class="mb-2"><strong>How to fix it</strong></p>
    <ol class="mb-3">
      <li>Check the configuration
        <ul>
          <li>Your site is at <strong id="production-current-url"></strong></li>
          <li>The configuration should be <code id="production-config-suggestion"></code></li>
        </ul>
      </li>
      <li>Commit and push</li>
      <li>The tiles are regenerated automatically</li>
    </ol>

    <p class="mb-2"><small>You can also regenerate them locally</small></p>
    <pre class="bg-light p-2 rounded"><code id="production-local-command"></code></pre>
  </div>

  <div id="local-fix-instructions" style="display: none;">
    <p class="mb-2"><strong>Common causes</strong></p>
    <ul class="mb-3">
      <li>The tiles were generated for another address</li>
      <li>The server is on another port</li>
    </ul>

    <p class="mb-2"><strong>How to fix it</strong></p>
    <pre class="bg-light p-2 rounded mb-3"><code id="local-command"></code></pre>

    <p class="mb-2"><strong>Alternatively</strong></p>
    <ol class="mb-0">
      <li>Check the configuration</li>
      <li>Run the generator with the note</li>
    </ol>
  </div>
</div>
`;

const OBJECTS_URL = '/telar/objects.json';
const IIIF_BASE = '/telar/iiif/objects';
const STRINGS = {
  affectedImagesSingular: '__COUNT__ affected image:',
  affectedImagesPlural: '__COUNT__ affected images:',
};

/**
 * A response the code is meant to skip: reachable, not ok, and carrying a
 * body that would change what the banner says if the status went unchecked.
 * A 404 page that happens to parse is the case a bare `json()` would swallow.
 */
function notOk(body) {
  return { notOk: true, body };
}

/** A fetch stub answering from a URL -> body map; anything else rejects. */
function stubFetch(responses) {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn((url) => {
    calls.push(url);
    if (!(url in responses)) return Promise.reject(new Error(`unscripted fetch: ${url}`));
    const body = responses[url];
    if (body instanceof Error) return Promise.reject(body);
    if (body && body.notOk) {
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve(body.body) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  }));
  return calls;
}

async function flush() {
  for (let round = 0; round < 3; round++) {
    for (let i = 0; i < 20; i++) await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

/** The Liquid-supplied configuration, in the JSON block the include writes. */
function setConfig(config) {
  const block = document.createElement('script');
  block.id = 'telar-iiif-warning-data';
  block.type = 'application/json';
  block.textContent = JSON.stringify(config);
  document.body.appendChild(block);
}

function fullConfig(overrides = {}) {
  return { objectsUrl: OBJECTS_URL, iiifObjectsBase: IIIF_BASE, strings: STRINGS, ...overrides };
}

let location = { origin: 'https://example.org', pathname: '/telar/' };

function atUrl(origin, pathname) {
  location = { origin, pathname };
}

/** Run the check as the bundle's tail does, and let it settle. */
async function runScript() {
  const config = readWarningData(document);
  if (config) {
    await initIIIFUrlWarning(config, { doc: document, fetch: globalThis.fetch, location });
  }
  await flush();
}

const el = (id) => document.getElementById(id);
const display = (id) => el(id).style.display;
const text = (id) => el(id).textContent;
const manifestUrl = (id) => `${IIIF_BASE}/${id}/manifest.json`;
const manifest = (base) => ({ id: `${base}/iiif/objects/x/manifest.json` });

beforeEach(() => {
  document.body.innerHTML = MARKUP;
  vi.spyOn(console, 'log').mockImplementation(() => {});
  atUrl('https://example.org', '/telar/');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('the silent exits', () => {
  it('does nothing without the data block', async () => {
    const calls = stubFetch({});
    await runScript();

    expect(calls).toEqual([]);
    expect(display('iiif-url-warning')).toBe('none');
  });

  it.each([
    ['objectsUrl', { objectsUrl: undefined }],
    ['iiifObjectsBase', { iiifObjectsBase: undefined }],
    ['strings', { strings: undefined }],
  ])('does nothing when the configuration has no %s', async (_field, missing) => {
    setConfig(fullConfig(missing));
    const calls = stubFetch({});
    await runScript();

    expect(calls).toEqual([]);
    expect(display('iiif-url-warning')).toBe('none');
  });

  it('stays hidden when the objects fetch is not ok, body or no body', async () => {
    setConfig(fullConfig());
    const calls = stubFetch({
      [OBJECTS_URL]: notOk([{ object_id: 'a', title: 'A map' }]),
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(calls).toEqual([OBJECTS_URL]);
    expect(display('iiif-url-warning')).toBe('none');
  });

  it('stays hidden when the objects fetch throws', async () => {
    setConfig(fullConfig());
    const calls = stubFetch({ [OBJECTS_URL]: new Error('offline') });
    await runScript();

    expect(calls).toEqual([OBJECTS_URL]);
    expect(display('iiif-url-warning')).toBe('none');
  });

  it('fetches no manifest when every object is remote', async () => {
    setConfig(fullConfig());
    const calls = stubFetch({
      [OBJECTS_URL]: [
        { object_id: 'a', iiif_manifest: 'https://elsewhere.test/a/manifest.json' },
        { object_id: 'b', iiif_manifest: 'https://elsewhere.test/b/manifest.json' },
      ],
    });
    await runScript();

    expect(calls).toEqual([OBJECTS_URL]);
    expect(display('iiif-url-warning')).toBe('none');
  });

  it('stays hidden when every local manifest matches the site', async () => {
    setConfig(fullConfig());
    const calls = stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a' }, { object_id: 'b', iiif_manifest: '' }],
      [manifestUrl('a')]: manifest('https://example.org/telar'),
      [manifestUrl('b')]: manifest('https://example.org/telar'),
    });
    await runScript();

    expect(calls).toEqual([OBJECTS_URL, manifestUrl('a'), manifestUrl('b')]);
    expect(display('iiif-url-warning')).toBe('none');
  });
});

describe('a mismatch in local development', () => {
  beforeEach(() => {
    setConfig(fullConfig());
  });

  it('shows the local instructions and the regeneration command', async () => {
    atUrl('http://127.0.0.1:4001', '/telar/');
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('https://example.org/telar'),
    });
    await runScript();

    expect(display('iiif-url-warning')).toBe('block');
    expect(display('local-fix-instructions')).toBe('block');
    expect(display('production-fix-instructions')).toBe('none');
    expect(text('current-url')).toBe('http://127.0.0.1:4001/telar');
    expect(text('manifest-url')).toBe('https://example.org/telar');
    expect(text('local-command'))
      .toBe('python3 scripts/generate_iiif.py --base-url http://127.0.0.1:4001/telar');
    expect(text('production-current-url')).toBe('');
    expect(text('production-config-suggestion')).toBe('');
    expect(text('production-local-command')).toBe('');
  });

  it('treats a localhost origin the same way', async () => {
    atUrl('http://localhost:4001', '/telar/');
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('https://example.org/telar'),
    });
    await runScript();

    expect(display('local-fix-instructions')).toBe('block');
    expect(display('production-fix-instructions')).toBe('none');
    expect(text('local-command'))
      .toBe('python3 scripts/generate_iiif.py --base-url http://localhost:4001/telar');
  });
});

describe('a mismatch in production', () => {
  beforeEach(() => {
    setConfig(fullConfig());
  });

  it('shows the production instructions, the suggestion and both commands', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(display('iiif-url-warning')).toBe('block');
    expect(display('production-fix-instructions')).toBe('block');
    expect(display('local-fix-instructions')).toBe('none');
    expect(text('current-url')).toBe('https://example.org/telar');
    expect(text('manifest-url')).toBe('http://127.0.0.1:4001/telar');
    expect(text('production-current-url')).toBe('https://example.org/telar');
    expect(text('production-config-suggestion'))
      .toBe('url: "https://example.org" and baseurl: "/telar"');
    expect(text('production-local-command'))
      .toBe('python3 scripts/generate_iiif.py --base-url https://example.org/telar');
    expect(text('local-command')).toBe('');
  });

  it('suggests an empty baseurl for a site served at the origin root', async () => {
    atUrl('https://example.org', '/');
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('https://example.org/telar'),
    });
    await runScript();

    expect(text('current-url')).toBe('https://example.org');
    expect(text('production-config-suggestion'))
      .toBe('url: "https://example.org" and baseurl: "/"');
    expect(text('production-local-command'))
      .toBe('python3 scripts/generate_iiif.py --base-url https://example.org');
  });

  it('takes the baseurl from the first path segment of a deeper page', async () => {
    atUrl('https://example.org', '/telar/objects/a/');
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(text('current-url')).toBe('https://example.org/telar');
  });
});

describe('the affected images list', () => {
  beforeEach(() => {
    setConfig(fullConfig());
  });

  it('uses the singular heading for one object', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(text('affected-images-heading')).toBe('1 affected image:');
    expect([...el('affected-images').children].map((li) => li.textContent))
      .toEqual(['A map (a)']);
  });

  it('uses the plural heading for several', async () => {
    stubFetch({
      [OBJECTS_URL]: [
        { object_id: 'a', title: 'A map' },
        { object_id: 'b', title: 'A letter' },
        { object_id: 'c', title: 'A photograph' },
      ],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
      [manifestUrl('b')]: manifest('http://127.0.0.1:4001/telar'),
      [manifestUrl('c')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(text('affected-images-heading')).toBe('3 affected images:');
    expect([...el('affected-images').children].map((li) => li.textContent))
      .toEqual(['A map (a)', 'A letter (b)', 'A photograph (c)']);
  });

  it('replaces any rows left from a previous run', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(el('stale-row')).toBeNull();
    expect(el('affected-images').children).toHaveLength(1);
  });

  it('lists an object with no title by its id', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a' }, { object_id: 'b', title: '' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
      [manifestUrl('b')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect([...el('affected-images').children].map((li) => li.textContent))
      .toEqual(['a (a)', 'b (b)']);
  });

  it('renders a title containing markup as text', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A <b>map</b>' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    const row = el('affected-images').children[0];
    expect(row.textContent).toBe('A <b>map</b> (a)');
    expect(row.querySelector('b')).toBeNull();
    expect(row.querySelector('strong').textContent).toBe('A <b>map</b>');
  });
});

describe('manifests that cannot be read', () => {
  beforeEach(() => {
    setConfig(fullConfig());
  });

  it('skips a manifest that is not there and checks the rest', async () => {
    const calls = stubFetch({
      [OBJECTS_URL]: [
        { object_id: 'missing', title: 'Not generated' },
        { object_id: 'a', title: 'A map' },
      ],
      [manifestUrl('missing')]: notOk(manifest('http://127.0.0.1:4001/telar')),
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(calls).toEqual([OBJECTS_URL, manifestUrl('missing'), manifestUrl('a')]);
    expect(text('affected-images-heading')).toBe('1 affected image:');
    expect([...el('affected-images').children].map((li) => li.textContent))
      .toEqual(['A map (a)']);
  });

  it('skips a manifest whose fetch throws and checks the rest', async () => {
    const calls = stubFetch({
      [OBJECTS_URL]: [
        { object_id: 'broken', title: 'Unreachable' },
        { object_id: 'a', title: 'A map' },
      ],
      [manifestUrl('broken')]: new Error('offline'),
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(calls).toEqual([OBJECTS_URL, manifestUrl('broken'), manifestUrl('a')]);
    expect([...el('affected-images').children].map((li) => li.textContent))
      .toEqual(['A map (a)']);
  });
});

describe('comparing the manifest base with the site', () => {
  beforeEach(() => {
    setConfig(fullConfig());
  });

  it('treats a trailing slash on the manifest base as no difference', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: { id: 'https://example.org/telar//iiif/objects/a/manifest.json' },
    });
    await runScript();

    expect(display('iiif-url-warning')).toBe('none');
  });

  it('reports a mismatch when only the trailing slash is not the difference', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: { id: 'https://other.test/telar//iiif/objects/a/manifest.json' },
    });
    await runScript();

    expect(display('iiif-url-warning')).toBe('block');
    expect(text('manifest-url')).toBe('https://other.test/telar/');
  });

  it('shows the site with no baseurl segment when the page is at the origin root', async () => {
    atUrl('https://example.org', '/');
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('https://example.org'),
    });
    await runScript();

    expect(display('iiif-url-warning')).toBe('none');
  });

  it('shows the base of the first local manifest, matching or not', async () => {
    stubFetch({
      [OBJECTS_URL]: [
        { object_id: 'first', title: 'Fine' },
        { object_id: 'a', title: 'A map' },
      ],
      [manifestUrl('first')]: manifest('https://example.org/telar'),
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });
    await runScript();

    expect(display('iiif-url-warning')).toBe('block');
    expect(text('manifest-url')).toBe('https://example.org/telar');
    expect([...el('affected-images').children].map((li) => li.textContent))
      .toEqual(['A map (a)']);
  });
});

describe('the pure helpers', () => {
  describe('siteUrlFromLocation', () => {
    it('keeps the first path segment as the baseurl', () => {
      expect(siteUrlFromLocation({ origin: 'https://example.org', pathname: '/telar/' }))
        .toBe('https://example.org/telar');
      expect(siteUrlFromLocation({ origin: 'https://example.org', pathname: '/telar/objects/a/' }))
        .toBe('https://example.org/telar');
    });

    it('adds nothing for a site served at the origin root', () => {
      expect(siteUrlFromLocation({ origin: 'https://example.org', pathname: '/' }))
        .toBe('https://example.org');
      expect(siteUrlFromLocation({ origin: 'https://example.org', pathname: '' }))
        .toBe('https://example.org');
    });
  });

  describe('isLocalDevOrigin', () => {
    it('recognises both local hostnames on any port', () => {
      expect(isLocalDevOrigin('http://localhost:4001')).toBe(true);
      expect(isLocalDevOrigin('http://127.0.0.1:4001')).toBe(true);
    });

    it('treats anything else as production', () => {
      expect(isLocalDevOrigin('https://example.org')).toBe(false);
      expect(isLocalDevOrigin('https://ucsb-amplab.github.io')).toBe(false);
    });
  });

  describe('manifestBaseFromId', () => {
    it('takes everything before the /iiif/ segment', () => {
      expect(manifestBaseFromId('https://example.org/telar/iiif/objects/a/manifest.json'))
        .toBe('https://example.org/telar');
    });

    it('returns the whole id when there is no /iiif/ segment', () => {
      expect(manifestBaseFromId('https://example.org/telar/a.json'))
        .toBe('https://example.org/telar/a.json');
    });

    it('keeps a baseurl segment of its own that begins with iiif', () => {
      expect(manifestBaseFromId('https://example.org/iiif-tiles/iiif/objects/a/manifest.json'))
        .toBe('https://example.org/iiif-tiles');
    });
  });

  describe('sameSite', () => {
    it('ignores a trailing slash on either side', () => {
      expect(sameSite('https://example.org/telar', 'https://example.org/telar/')).toBe(true);
      expect(sameSite('https://example.org/', 'https://example.org')).toBe(true);
    });

    it('reports any other difference', () => {
      expect(sameSite('https://example.org/telar', 'https://other.test/telar')).toBe(false);
      expect(sameSite('https://example.org/telar', 'https://example.org')).toBe(false);
    });
  });

  describe('regenerationCommand', () => {
    it('targets the address given', () => {
      expect(regenerationCommand('http://127.0.0.1:4001/telar'))
        .toBe('python3 scripts/generate_iiif.py --base-url http://127.0.0.1:4001/telar');
    });
  });

  describe('configSuggestion', () => {
    it('splits an address into url and baseurl', () => {
      expect(configSuggestion('https://example.org/telar'))
        .toBe('url: "https://example.org" and baseurl: "/telar"');
    });

    it('keeps the port with the url and gives a root site a bare slash', () => {
      expect(configSuggestion('http://127.0.0.1:4001/telar'))
        .toBe('url: "http://127.0.0.1:4001" and baseurl: "/telar"');
      expect(configSuggestion('https://example.org'))
        .toBe('url: "https://example.org" and baseurl: "/"');
    });
  });
});

describe('detection on its own', () => {
  const config = fullConfig();
  const production = { origin: 'https://example.org', pathname: '/telar/' };

  function find(fetch, location = production) {
    return findAffectedObjects(config, { fetch, location });
  }

  it('returns null when the objects list cannot be read', async () => {
    stubFetch({ [OBJECTS_URL]: notOk([{ object_id: 'a' }]) });
    expect(await find(globalThis.fetch)).toBeNull();

    vi.unstubAllGlobals();
    stubFetch({ [OBJECTS_URL]: new Error('offline') });
    expect(await find(globalThis.fetch)).toBeNull();
  });

  it('returns null when no object uses local tiles', async () => {
    const calls = stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', iiif_manifest: 'https://elsewhere.test/a/manifest.json' }],
    });
    expect(await find(globalThis.fetch)).toBeNull();
    expect(calls).toEqual([OBJECTS_URL]);
  });

  it('returns null when every manifest agrees with the address', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a' }],
      [manifestUrl('a')]: manifest('https://example.org/telar'),
    });
    expect(await find(globalThis.fetch)).toBeNull();
  });

  it('returns null when no manifest could be read at all', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a' }],
      [manifestUrl('a')]: notOk(manifest('http://127.0.0.1:4001/telar')),
    });
    expect(await find(globalThis.fetch)).toBeNull();
  });

  it('reports the affected objects with the context the banner needs', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }, { object_id: 'b' }],
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
      [manifestUrl('b')]: manifest('http://127.0.0.1:4001/telar'),
    });

    expect(await find(globalThis.fetch)).toEqual({
      affectedObjects: [{ id: 'a', title: 'A map' }, { id: 'b', title: 'b' }],
      manifestBaseUrl: 'http://127.0.0.1:4001/telar',
      currentSiteUrl: 'https://example.org/telar',
      isLocalDev: false,
    });
  });

  it('marks a local-development address as such', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'a', title: 'A map' }],
      [manifestUrl('a')]: manifest('https://example.org/telar'),
    });

    const result = await find(globalThis.fetch, { origin: 'http://127.0.0.1:4001', pathname: '/telar/' });
    expect(result.isLocalDev).toBe(true);
    expect(result.currentSiteUrl).toBe('http://127.0.0.1:4001/telar');
  });

  it('skips an unreadable manifest and keeps checking the rest', async () => {
    stubFetch({
      [OBJECTS_URL]: [{ object_id: 'broken' }, { object_id: 'a', title: 'A map' }],
      [manifestUrl('broken')]: new Error('offline'),
      [manifestUrl('a')]: manifest('http://127.0.0.1:4001/telar'),
    });

    const result = await find(globalThis.fetch);
    expect(result.affectedObjects).toEqual([{ id: 'a', title: 'A map' }]);
    expect(result.manifestBaseUrl).toBe('http://127.0.0.1:4001/telar');
  });
});
