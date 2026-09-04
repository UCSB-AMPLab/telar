/**
 * Tests for the index pages' thumbnail modules (assets/js/iiif-thumbnails/).
 *
 * These cover the resolver's pure functions, both fetch-driven resolutions
 * with a stubbed fetch, the explicit-thumbnail upgrade, and both pages'
 * wiring in jsdom: which route each card takes, what lands in its
 * placeholder, and the hover prefetch. A browser smoke covers the rest
 * against a served build. One thing here is untestable by design: the prefetch
 * listener's `once` flag, which the prefetched-manifest set already makes
 * invisible -- a second hover is a no-op either way.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  pickThumbnailSize, upgradeIIIFThumbnailUrl, extractManifestImage, isLevel0Profile,
  resolveManifestThumbnail, resolveInfoJsonThumbnail,
} from '../../assets/js/iiif-thumbnails/resolve.js';
import { upgradeExplicitThumbnails } from '../../assets/js/iiif-thumbnails/explicit-thumbnails.js';
import {
  readHomeData, initStoryThumbnails, initFeaturedThumbnails, initManifestPrefetch, initHomePage,
} from '../../assets/js/iiif-thumbnails/home.js';
import {
  readObjectsIndexData, initLocalThumbnails, initManifestThumbnails, initObjectsIndexPage,
} from '../../assets/js/iiif-thumbnails/objects-index.js';
import v2Manifest from '../fixtures/iiif/manifest-v2.json';
import v3Manifest from '../fixtures/iiif/manifest-v3.json';

const SERVICE = 'https://example.invalid/iiif/2/canvas-1';
const V2_FALLBACK = 'https://example.invalid/iiif/2/canvas-1/full/full/0/default.jpg';
const LANG = { thumbnailLoadError: 'Failed to load', noImage: 'No image' };

/** A fetch stub answering from a URL -> body map; anything else rejects. */
function stubFetch(responses) {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn((url) => {
    calls.push(url);
    if (!(url in responses)) return Promise.reject(new Error(`unscripted fetch: ${url}`));
    const body = responses[url];
    if (body instanceof Error) return Promise.reject(body);
    return Promise.resolve({ json: () => Promise.resolve(body) });
  }));
  return calls;
}

async function flush() {
  for (let i = 0; i < 6; i++) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function level0Manifest(fallback = true) {
  const resource = { service: { '@id': SERVICE + '/', profile: 'http://iiif.io/api/image/2/level0.json' } };
  if (fallback) resource['@id'] = V2_FALLBACK;
  return { sequences: [{ canvases: [{ images: [{ resource }] }] }] };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  document.head.innerHTML = '';
});

describe('pickThumbnailSize', () => {
  const sizes = [{ width: 800, height: 600 }, { width: 200, height: 150 }, { width: 400, height: 300 }];

  it('returns null for no sizes', () => {
    expect(pickThumbnailSize([], 400)).toBeNull();
    expect(pickThumbnailSize(undefined, 400)).toBeNull();
  });

  it('picks the smallest size at least minWidth wide', () => {
    expect(pickThumbnailSize(sizes, 300)).toEqual({ width: 400, height: 300 });
  });

  it('falls back to the largest when none is wide enough', () => {
    expect(pickThumbnailSize(sizes, 1000)).toEqual({ width: 800, height: 600 });
  });

  it('defaults minWidth to 400 and leaves the input order alone', () => {
    expect(pickThumbnailSize(sizes)).toEqual({ width: 400, height: 300 });
    expect(sizes[0].width).toBe(800);
  });
});

describe('upgradeIIIFThumbnailUrl', () => {
  it('rewrites the size segment of an Image API URL', () => {
    expect(upgradeIIIFThumbnailUrl('https://x.test/iiif/a/full/!96,96/0/default.jpg'))
      .toBe('https://x.test/iiif/a/full/!600,600/0/default.jpg');
  });

  it('tolerates a backslash-escaped or double-slashed size', () => {
    expect(upgradeIIIFThumbnailUrl('https://x.test/iiif/a/full/\\!96,96/0/default.jpg'))
      .toBe('https://x.test/iiif/a/full/!600,600/0/default.jpg');
    expect(upgradeIIIFThumbnailUrl('https://x.test/iiif/a/full//96,96/0/default.png'))
      .toBe('https://x.test/iiif/a/full/!600,600/0/default.png');
  });

  it('leaves anything else alone', () => {
    expect(upgradeIIIFThumbnailUrl('https://x.test/images/thumb.jpg')).toBe('https://x.test/images/thumb.jpg');
    expect(upgradeIIIFThumbnailUrl('https://x.test/iiif/a/full/96,96/90/default.jpg'))
      .toBe('https://x.test/iiif/a/full/96,96/90/default.jpg');
  });
});

describe('extractManifestImage', () => {
  it('reads a Presentation 2.1 manifest', () => {
    expect(extractManifestImage(v2Manifest)).toEqual({
      imageServiceUrl: SERVICE,
      imageServiceProfile: 'http://iiif.io/api/image/2/level2.json',
      fallbackImageUrl: V2_FALLBACK,
    });
  });

  it('reads a Presentation 3.0 manifest', () => {
    expect(extractManifestImage(v3Manifest)).toEqual({
      imageServiceUrl: 'https://example.invalid/iiif/3/canvas-1',
      imageServiceProfile: 'level2',
      fallbackImageUrl: 'https://example.invalid/iiif/3/canvas-1/full/max/0/default.jpg',
    });
  });

  it('takes the first of a 2.1 service array and its id form', () => {
    const manifest = { sequences: [{ canvases: [{ images: [{ resource: {
      '@id': V2_FALLBACK, service: [{ id: SERVICE, profile: 'level1' }, { id: 'other' }] } }] }] }] };
    expect(extractManifestImage(manifest).imageServiceUrl).toBe(SERVICE);
    expect(extractManifestImage(manifest).imageServiceProfile).toBe('level1');
  });

  it('keeps the direct image URL when there is no service', () => {
    const v2 = { sequences: [{ canvases: [{ images: [{ resource: { '@id': V2_FALLBACK } }] }] }] };
    expect(extractManifestImage(v2)).toEqual({ imageServiceUrl: null, imageServiceProfile: null, fallbackImageUrl: V2_FALLBACK });
    const v3 = { items: [{ items: [{ items: [{ body: { id: 'https://x.test/img.jpg' } }] }] }] };
    expect(extractManifestImage(v3).fallbackImageUrl).toBe('https://x.test/img.jpg');
    expect(extractManifestImage(v3).imageServiceUrl).toBeNull();
  });

  it('prefers the 2.1 walk when a manifest carries both sequences and items', () => {
    const v2 = { sequences: [{ canvases: [{ images: [{ resource: { '@id': V2_FALLBACK } }] }] }] };
    const both = Object.assign({}, v2, { items: [{ items: [{ items: [{ body: { id: 'https://x.test/v3.jpg' } }] }] }] } );
    expect(extractManifestImage(both).fallbackImageUrl).toBe(V2_FALLBACK);
  });

  it('returns nulls for a manifest with no image', () => {
    const empty = { imageServiceUrl: null, imageServiceProfile: null, fallbackImageUrl: null };
    expect(extractManifestImage({})).toEqual(empty);
    expect(extractManifestImage({ sequences: [{ canvases: [] }] })).toEqual(empty);
    expect(extractManifestImage({ items: [{ items: [] }] })).toEqual(empty);
  });
});

describe('isLevel0Profile', () => {
  it('recognises every shape a level0 profile arrives in', () => {
    expect(isLevel0Profile('level0')).toBe(true);
    expect(isLevel0Profile('http://iiif.io/api/image/2/level0.json')).toBe(true);
    expect(isLevel0Profile(['http://iiif.io/api/image/2/level0.json', { formats: ['jpg'] }])).toBe(true);
    expect(isLevel0Profile('http://library.stanford.edu/iiif/image-api/1.1/compliance.html#Level0')).toBe(true);
  });

  it('is false for scaling-capable or missing profiles', () => {
    expect(isLevel0Profile('level2')).toBe(false);
    expect(isLevel0Profile(['http://iiif.io/api/image/2/level1.json'])).toBe(false);
    expect(isLevel0Profile(undefined)).toBe(false);
    expect(isLevel0Profile([{ supports: ['level0'] }])).toBe(false);
  });
});

describe('resolveManifestThumbnail', () => {
  it('asks a Level 1+ service for the requested size', async () => {
    const calls = stubFetch({ 'https://m.test/manifest': v2Manifest });
    await expect(resolveManifestThumbnail('https://m.test/manifest', '!200,200'))
      .resolves.toBe(SERVICE + '/full/!200,200/0/default.jpg');
    expect(calls).toEqual(['https://m.test/manifest']);
  });

  it('defaults the size to !400,400 and strips a trailing slash', async () => {
    const manifest = { items: [{ items: [{ items: [{ body: { service: [{ id: SERVICE + '/', profile: 'level2' }] } }] }] }] };
    stubFetch({ 'https://m.test/manifest': manifest });
    await expect(resolveManifestThumbnail('https://m.test/manifest'))
      .resolves.toBe(SERVICE + '/full/!400,400/0/default.jpg');
  });

  it('reads a Level 0 service\'s info.json and picks a pre-generated size', async () => {
    const calls = stubFetch({
      'https://m.test/manifest': level0Manifest(),
      [SERVICE + '/info.json']: { sizes: [{ width: 1000, height: 800 }, { width: 500, height: 400 }, { width: 100, height: 80 }] },
    });
    await expect(resolveManifestThumbnail('https://m.test/manifest'))
      .resolves.toBe(SERVICE + '/full/500,400/0/default.jpg');
    expect(calls).toEqual(['https://m.test/manifest', SERVICE + '/info.json']);
  });

  it('falls back to the direct image when a Level 0 lookup dead-ends', async () => {
    stubFetch({ 'https://m.test/manifest': level0Manifest(), [SERVICE + '/info.json']: { sizes: [] } });
    await expect(resolveManifestThumbnail('https://m.test/manifest')).resolves.toBe(V2_FALLBACK);
    stubFetch({ 'https://m.test/manifest': level0Manifest(), [SERVICE + '/info.json']: new Error('down') });
    await expect(resolveManifestThumbnail('https://m.test/manifest')).resolves.toBe(V2_FALLBACK);
  });

  it('resolves null when a Level 0 lookup dead-ends with nothing to fall back to', async () => {
    stubFetch({ 'https://m.test/manifest': level0Manifest(false), [SERVICE + '/info.json']: new Error('down') });
    await expect(resolveManifestThumbnail('https://m.test/manifest')).resolves.toBeNull();
  });

  it('uses the direct image when there is no service at all', async () => {
    stubFetch({ 'https://m.test/manifest': { sequences: [{ canvases: [{ images: [{ resource: { '@id': V2_FALLBACK } }] }] }] } });
    await expect(resolveManifestThumbnail('https://m.test/manifest')).resolves.toBe(V2_FALLBACK);
  });

  it('rejects with noImage when the manifest carries no image', async () => {
    stubFetch({ 'https://m.test/manifest': { sequences: [] } });
    await expect(resolveManifestThumbnail('https://m.test/manifest')).rejects.toMatchObject({ noImage: true });
  });

  it('rejects plainly when the manifest cannot be fetched', async () => {
    stubFetch({});
    const error = await resolveManifestThumbnail('https://m.test/manifest').catch((e) => e);
    expect(error).toBeInstanceOf(Error);
    expect(error.noImage).toBeUndefined();
  });
});

describe('resolveInfoJsonThumbnail', () => {
  it('builds the URL from the chosen size and the service id', async () => {
    stubFetch({ '/telar/iiif/objects/a/info.json': { id: 'http://s.test/iiif/objects/a', sizes: [{ width: 300, height: 200 }, { width: 600, height: 400 }] } });
    await expect(resolveInfoJsonThumbnail('/telar/iiif/objects/a/info.json'))
      .resolves.toBe('http://s.test/iiif/objects/a/full/600,400/0/default.jpg');
  });

  it('accepts the @id form and a custom minimum width', async () => {
    stubFetch({ '/i.json': { '@id': 'http://s.test/a', sizes: [{ width: 300, height: 200 }, { width: 600, height: 400 }] } });
    await expect(resolveInfoJsonThumbnail('/i.json', 200)).resolves.toBe('http://s.test/a/full/300,200/0/default.jpg');
  });

  it('resolves null without sizes and rejects when the fetch fails', async () => {
    stubFetch({ '/i.json': { id: 'http://s.test/a' } });
    await expect(resolveInfoJsonThumbnail('/i.json')).resolves.toBeNull();
    stubFetch({});
    await expect(resolveInfoJsonThumbnail('/i.json')).rejects.toBeInstanceOf(Error);
  });
});

describe('upgradeExplicitThumbnails', () => {
  it('upgrades an Image API thumbnail and keeps the original as the error fallback', () => {
    document.body.innerHTML = '<img class="iiif-thumbnail" src="https://x.test/iiif/a/full/!96,96/0/default.jpg">';
    upgradeExplicitThumbnails();
    const img = document.querySelector('img');
    expect(img.src).toBe('https://x.test/iiif/a/full/!600,600/0/default.jpg');
    expect(img.dataset.originalSrc).toBe('https://x.test/iiif/a/full/!96,96/0/default.jpg');
    img.onerror();
    expect(img.src).toBe('https://x.test/iiif/a/full/!96,96/0/default.jpg');
    expect(img.dataset.originalSrc).toBeUndefined();
    expect(img.onerror).toBeNull();
  });

  it('leaves a non-IIIF thumbnail untouched', () => {
    document.body.innerHTML = '<img class="iiif-thumbnail" src="https://x.test/thumb.jpg"><img src="https://x.test/iiif/a/full/!96,96/0/default.jpg">';
    upgradeExplicitThumbnails();
    const [plain, unclassed] = document.querySelectorAll('img');
    expect(plain.src).toBe('https://x.test/thumb.jpg');
    expect(plain.dataset.originalSrc).toBeUndefined();
    expect(plain.onerror).toBeNull();
    expect(unclassed.src).toBe('https://x.test/iiif/a/full/!96,96/0/default.jpg');
  });
});

// ── Home page ────────────────────────────────────────────────────────────────

const OBJECTS = [
  { object_id: 'explicit', thumbnail: 'https://x.test/iiif/e/full/!96,96/0/default.jpg', iiif_manifest: 'https://m.test/e' },
  { object_id: 'plain-thumb', thumbnail: 'https://x.test/e.jpg' },
  { object_id: 'blank-thumb', thumbnail: '   ', iiif_manifest: 'https://m.test/b' },
  { object_id: 'remote', iiif_manifest: 'https://m.test/r' },
  { object_id: 'local' },
];

function storyCard(objectId, title = `Story ${objectId}`, withThumbnail = true) {
  const thumb = withThumbnail
    ? `<div class="story-iiif-thumbnail" data-object-id="${objectId}" data-info-json="/iiif/objects/${objectId}/info.json">
         <div class="manifest-thumbnail-placeholder"><span class="text-muted">Loading...</span></div></div>`
    : '<div class="story-thumbnail-placeholder"></div>';
  return `<a href="/stories/${objectId}/" class="story-card">${thumb}<div class="card-body"><h3>${title}</h3></div></a>`;
}

function featuredCard(objectId, title = `Object ${objectId}`) {
  return `<a href="/objects/${objectId}/" class="collection-item">
    <div class="featured-iiif-thumbnail" data-object-id="${objectId}" data-info-json="/iiif/objects/${objectId}/info.json">
      <span class="thumbnail-placeholder">${title.slice(0, 5)}</span></div>
    <h4 class="collection-title">${title}</h4></a>`;
}

function homeData(objects = OBJECTS) {
  return { objects, lang: LANG };
}

describe('readHomeData', () => {
  it('is null without a block and parses one when present', () => {
    expect(readHomeData()).toBeNull();
    document.body.innerHTML = `<script id="telar-home-data" type="application/json">${JSON.stringify(homeData())}</script>`;
    expect(readHomeData()).toEqual(homeData());
  });

  it('is null and reports when the block is not JSON', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    document.body.innerHTML = '<script id="telar-home-data" type="application/json">{nope</script>';
    expect(readHomeData()).toBeNull();
    expect(error).toHaveBeenCalled();
  });
});

describe('initStoryThumbnails', () => {
  beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}));

  it('uses an explicit thumbnail without fetching, upgraded, with the original as fallback', async () => {
    const calls = stubFetch({});
    document.body.innerHTML = storyCard('explicit', 'Allegory');
    initStoryThumbnails(homeData());
    await flush();
    const img = document.querySelector('.story-iiif-thumbnail img');
    expect(img.src).toBe('https://x.test/iiif/e/full/!600,600/0/default.jpg');
    expect(img.alt).toBe('Allegory');
    expect(img.style.objectFit).toBe('cover');
    expect(document.querySelector('.manifest-thumbnail-placeholder')).toBeNull();
    expect(calls).toEqual([]);
    img.onerror();
    expect(img.src).toBe('https://x.test/iiif/e/full/!96,96/0/default.jpg');
    expect(img.onerror).toBeNull();
  });

  it('sets no fallback when the explicit thumbnail is not upgradable', async () => {
    stubFetch({});
    document.body.innerHTML = storyCard('plain-thumb');
    initStoryThumbnails(homeData());
    const img = document.querySelector('.story-iiif-thumbnail img');
    expect(img.src).toBe('https://x.test/e.jpg');
    expect(img.onerror).toBeNull();
  });

  it('treats a blank thumbnail as absent and resolves the manifest at !400,400', async () => {
    const calls = stubFetch({ 'https://m.test/b': v2Manifest });
    document.body.innerHTML = storyCard('blank-thumb', 'Blank');
    initStoryThumbnails(homeData());
    await flush();
    const img = document.querySelector('.story-iiif-thumbnail img');
    expect(img.src).toBe(SERVICE + '/full/!400,400/0/default.jpg');
    expect(img.alt).toBe('Blank');
    expect(calls).toEqual(['https://m.test/b']);
  });

  it('shows the load error in the placeholder when the manifest fails', async () => {
    stubFetch({});
    document.body.innerHTML = storyCard('remote');
    initStoryThumbnails(homeData());
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').innerHTML)
      .toBe('<span class="text-danger">Failed to load</span>');
    expect(console.error).toHaveBeenCalled();
  });

  it('leaves the placeholder alone when the manifest resolves to nothing', async () => {
    stubFetch({ 'https://m.test/r': level0Manifest(false) });
    document.body.innerHTML = storyCard('remote');
    initStoryThumbnails(homeData());
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').textContent).toBe('Loading...');
    expect(document.querySelector('img')).toBeNull();
  });

  it('resolves the local info.json for an object with neither, or one it does not know', async () => {
    const calls = stubFetch({
      '/iiif/objects/local/info.json': { id: 'http://s.test/local', sizes: [{ width: 400, height: 300 }] },
      '/iiif/objects/unknown/info.json': { id: 'http://s.test/unknown', sizes: [{ width: 500, height: 300 }] },
    });
    document.body.innerHTML = storyCard('local', 'Local') + storyCard('unknown', 'Unknown');
    initStoryThumbnails(homeData());
    await flush();
    const [local, unknown] = document.querySelectorAll('.story-iiif-thumbnail img');
    expect(local.src).toBe('http://s.test/local/full/400,300/0/default.jpg');
    expect(local.alt).toBe('Local');
    expect(unknown.src).toBe('http://s.test/unknown/full/500,300/0/default.jpg');
    expect(calls.sort()).toEqual(['/iiif/objects/local/info.json', '/iiif/objects/unknown/info.json']);
  });

  it('shows the load error when the local info.json fails', async () => {
    stubFetch({});
    document.body.innerHTML = storyCard('local');
    initStoryThumbnails(homeData());
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').innerHTML)
      .toBe('<span class="text-danger">Failed to load</span>');
  });
});

describe('initFeaturedThumbnails', () => {
  beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}));

  it('replaces the card contents with the explicit thumbnail', () => {
    stubFetch({});
    document.body.innerHTML = featuredCard('explicit', 'Allegory');
    initFeaturedThumbnails(homeData());
    const item = document.querySelector('.featured-iiif-thumbnail');
    expect(item.children.length).toBe(1);
    const img = item.firstElementChild;
    expect(img.src).toBe('https://x.test/iiif/e/full/!600,600/0/default.jpg');
    expect(img.alt).toBe('Allegory');
    img.onerror();
    expect(img.src).toBe('https://x.test/iiif/e/full/!96,96/0/default.jpg');
  });

  it('resolves the manifest at !200,200', async () => {
    stubFetch({ 'https://m.test/r': v3Manifest });
    document.body.innerHTML = featuredCard('remote', 'Remote');
    initFeaturedThumbnails(homeData());
    await flush();
    const img = document.querySelector('.featured-iiif-thumbnail img');
    expect(img.src).toBe('https://example.invalid/iiif/3/canvas-1/full/!200,200/0/default.jpg');
    expect(img.alt).toBe('Remote');
    expect(document.querySelector('.thumbnail-placeholder')).toBeNull();
  });

  it('stays silent on an imageless manifest and logs any other failure, leaving the card alone', async () => {
    stubFetch({ 'https://m.test/r': { sequences: [] } });
    document.body.innerHTML = featuredCard('remote');
    initFeaturedThumbnails(homeData());
    await flush();
    expect(document.querySelector('.thumbnail-placeholder')).not.toBeNull();
    expect(console.error).not.toHaveBeenCalled();

    stubFetch({});
    initFeaturedThumbnails(homeData());
    await flush();
    expect(document.querySelector('.thumbnail-placeholder')).not.toBeNull();
    expect(console.error).toHaveBeenCalledTimes(1);
  });

  it('resolves the local info.json otherwise, and logs when that fails', async () => {
    stubFetch({ '/iiif/objects/local/info.json': { id: 'http://s.test/local', sizes: [{ width: 400, height: 300 }] } });
    document.body.innerHTML = featuredCard('local', 'Local');
    initFeaturedThumbnails(homeData());
    await flush();
    expect(document.querySelector('.featured-iiif-thumbnail img').src).toBe('http://s.test/local/full/400,300/0/default.jpg');

    stubFetch({});
    document.body.innerHTML = featuredCard('local', 'Local');
    initFeaturedThumbnails(homeData());
    await flush();
    expect(document.querySelector('.featured-iiif-thumbnail img')).toBeNull();
    expect(console.error).toHaveBeenCalledTimes(1);
  });
});

describe('initManifestPrefetch', () => {
  beforeEach(() => vi.spyOn(console, 'log').mockImplementation(() => {}));

  function hover(card) {
    card.dispatchEvent(new Event('mouseenter'));
  }

  it('adds one prefetch link per manifest, on the first hover only', () => {
    document.body.innerHTML = storyCard('remote') + storyCard('remote') + storyCard('explicit');
    initManifestPrefetch(homeData());
    const cards = document.querySelectorAll('.story-card');
    hover(cards[0]);
    hover(cards[0]);
    hover(cards[1]);
    hover(cards[2]);
    const links = [...document.head.querySelectorAll('link[rel=prefetch]')].map((l) => l.getAttribute('href'));
    expect(links).toEqual(['https://m.test/r', 'https://m.test/e']);
  });

  it('does nothing for a card without a thumbnail, a link, or a manifest', () => {
    document.body.innerHTML = storyCard('local') + storyCard('remote', 'x', false) +
      '<a class="story-card"><div class="story-iiif-thumbnail" data-object-id="remote"></div></a>';
    initManifestPrefetch(homeData());
    document.querySelectorAll('.story-card').forEach(hover);
    expect(document.head.querySelector('link[rel=prefetch]')).toBeNull();
  });
});

describe('initHomePage', () => {
  it('wires every part of the page', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {});
    stubFetch({ '/iiif/objects/local/info.json': { id: 'http://s.test/local', sizes: [{ width: 400, height: 300 }] } });
    document.body.innerHTML = '<img class="iiif-thumbnail" src="https://x.test/iiif/a/full/!96,96/0/default.jpg">' +
      storyCard('remote') + storyCard('explicit') + featuredCard('local');
    initHomePage(homeData());
    await flush();
    expect(document.querySelector('img.iiif-thumbnail').src).toBe('https://x.test/iiif/a/full/!600,600/0/default.jpg');
    expect(document.querySelectorAll('.story-iiif-thumbnail img').length).toBe(1);
    expect(document.querySelector('.featured-iiif-thumbnail img').src).toBe('http://s.test/local/full/400,300/0/default.jpg');
    document.querySelectorAll('.story-card')[0].dispatchEvent(new Event('mouseenter'));
    expect(document.head.querySelector('link[rel=prefetch]').getAttribute('href')).toBe('https://m.test/r');
  });
});

// ── Objects index ────────────────────────────────────────────────────────────

function galleryCard(inner, title = 'Object') {
  return `<a href="/objects/x/" class="collection-item"><div class="collection-item-image"${inner.attrs || ''}>${inner.html}</div><h3>${title}</h3></a>`;
}

const PLACEHOLDER = '<div class="manifest-thumbnail-placeholder"><span class="text-muted">Loading...</span></div>';

function localCard(title) {
  return galleryCard({ html: `<div class="local-iiif-thumbnail" data-info-json="/iiif/objects/l/info.json">${PLACEHOLDER}</div>` }, title);
}

function manifestCard(manifest, title) {
  return galleryCard({ attrs: ` data-iiif-manifest="${manifest}"`, html: PLACEHOLDER }, title);
}

describe('readObjectsIndexData', () => {
  it('is null without a block and parses one when present', () => {
    expect(readObjectsIndexData()).toBeNull();
    document.body.innerHTML = `<script id="telar-objects-index-data" type="application/json">${JSON.stringify({ lang: LANG })}</script>`;
    expect(readObjectsIndexData()).toEqual({ lang: LANG });
  });

  it('is null and reports when the block is not JSON', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    document.body.innerHTML = '<script id="telar-objects-index-data" type="application/json">nope</script>';
    expect(readObjectsIndexData()).toBeNull();
    expect(error).toHaveBeenCalled();
  });
});

describe('initLocalThumbnails', () => {
  beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}));

  it('swaps the placeholder for the resolved image', async () => {
    stubFetch({ '/iiif/objects/l/info.json': { id: 'http://s.test/l', sizes: [{ width: 400, height: 300 }] } });
    document.body.innerHTML = localCard('Leyes');
    initLocalThumbnails({ lang: LANG });
    await flush();
    const img = document.querySelector('.local-iiif-thumbnail img');
    expect(img.src).toBe('http://s.test/l/full/400,300/0/default.jpg');
    expect(img.alt).toBe('Leyes');
    expect(img.getAttribute('class')).toBeNull();
    expect(document.querySelector('.manifest-thumbnail-placeholder')).toBeNull();
  });

  it('keeps the placeholder when there are no sizes and shows the error when the fetch fails', async () => {
    stubFetch({ '/iiif/objects/l/info.json': { id: 'http://s.test/l' } });
    document.body.innerHTML = localCard();
    initLocalThumbnails({ lang: LANG });
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').textContent).toBe('Loading...');

    stubFetch({});
    initLocalThumbnails({ lang: LANG });
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').innerHTML)
      .toBe('<span class="text-danger">Failed to load</span>');
  });
});

describe('initManifestThumbnails', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it('skips a card whose manifest is an info.json', async () => {
    const calls = stubFetch({});
    document.body.innerHTML = manifestCard('https://x.test/iiif/a/info.json');
    initManifestThumbnails({ lang: LANG });
    await flush();
    expect(calls).toEqual([]);
    expect(document.querySelector('.manifest-thumbnail-placeholder').textContent).toBe('Loading...');
  });

  it('swaps the placeholder for the resolved image, classed as a thumbnail', async () => {
    stubFetch({ 'https://m.test/a': v2Manifest });
    document.body.innerHTML = manifestCard('https://m.test/a', 'Atlas');
    initManifestThumbnails({ lang: LANG });
    await flush();
    const img = document.querySelector('.collection-item-image img');
    expect(img.src).toBe(SERVICE + '/full/!400,400/0/default.jpg');
    expect(img.alt).toBe('Atlas');
    expect(img.className).toBe('iiif-thumbnail');
  });

  it('shows "no image" for an imageless manifest and the error otherwise', async () => {
    stubFetch({ 'https://m.test/a': { items: [] } });
    document.body.innerHTML = manifestCard('https://m.test/a');
    initManifestThumbnails({ lang: LANG });
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').innerHTML)
      .toBe('<span class="text-muted">No image</span>');
    expect(console.warn).toHaveBeenCalled();
    expect(console.error).not.toHaveBeenCalled();

    stubFetch({});
    document.body.innerHTML = manifestCard('https://m.test/a');
    initManifestThumbnails({ lang: LANG });
    await flush();
    expect(document.querySelector('.manifest-thumbnail-placeholder').innerHTML)
      .toBe('<span class="text-danger">Failed to load</span>');
    expect(console.error).toHaveBeenCalled();
  });
});

describe('initObjectsIndexPage', () => {
  it('wires every part of the page', async () => {
    stubFetch({
      '/iiif/objects/l/info.json': { id: 'http://s.test/l', sizes: [{ width: 400, height: 300 }] },
      'https://m.test/a': v3Manifest,
    });
    document.body.innerHTML = galleryCard({ html: '<img class="iiif-thumbnail" src="https://x.test/iiif/a/full/!96,96/0/default.jpg">' }) +
      localCard() + manifestCard('https://m.test/a');
    initObjectsIndexPage({ lang: LANG });
    await flush();
    const srcs = [...document.querySelectorAll('.collection-item-image img')].map((img) => img.src);
    expect(srcs).toEqual([
      'https://x.test/iiif/a/full/!600,600/0/default.jpg',
      'http://s.test/l/full/400,300/0/default.jpg',
      'https://example.invalid/iiif/3/canvas-1/full/!400,400/0/default.jpg',
    ]);
  });
});
