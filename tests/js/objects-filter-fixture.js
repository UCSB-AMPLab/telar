/**
 * Shared fixture for the objects gallery filter tests.
 *
 * Holds what `objects-filter.test.js` (the characterisation suite driving
 * `createObjectsFilter` through the DOM) and `objects-filter-units.test.js`
 * (the unit suite for its pure modules) both need: the vendored Lunr global,
 * the fixture records and facet builder, the browse-and-search markup, the
 * fetch stub and `runScript` harness, and the DOM query helpers the
 * assertions read back. Not itself a test file, so vitest does not collect
 * it (see `include` in `vitest.config.js`).
 *
 * The fixture is the browse-and-search markup of `_layouts/objects-index.html`
 * with the Liquid stripped, and the cards are real objects from this
 * repository's `search-data.json` -- ids, titles, creators, periods, media
 * types, mediums, subjects and years copied verbatim, with the facet counts
 * computed from those same records the way `scripts/telar/search.py` computes
 * them. No two objects in that file share a creator or a period, so the
 * overlap the OR and AND cases need comes from `media_type`, where Image and
 * Video each cover several records.
 *
 * Lunr is the page's own vendored copy, evaluated here to provide the global
 * the code reads, because a search test against a different Lunr would pin a
 * different search.
 *
 * @version v1.7.0
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { vi } from 'vitest';

import { createObjectsFilter } from '../../assets/js/objects-filter/main.js';

// The page loads assets/js/lunr.min.js in its own <script> immediately before
// the filter, so the filter reads a bare global. Evaluate the vendored file to
// put the same global in place here. The path is resolved against the vitest
// root, which is the repository root.
const lunrSource = readFileSync(resolve(process.cwd(), 'assets/js/lunr.min.js'), 'utf8');
new Function(lunrSource).call(globalThis);

/** Objects copied verbatim from search-data.json at the repository root. */
export const ATLAS = {
  id: 'atlas-allegory',
  title: 'Aspecto Symbólico del Mundo Hispánico',
  creator: 'Laureano Atlas',
  period: '1761',
  description: 'Allegorical map of the "Hispanic World", engraved by Laureano Atlas and published as the frontispiece to Vicente Memije, Theses Mathematicas de Cosmographia, Geographia y Hydrographia (Manila: 1761)',
  media_type: 'Image',
  medium: '',
  subjects: 'Western Hemisphere—Maps—Early works to 1800',
  year: '1761',
};
export const FIGUEROA = {
  id: 'figueroa', title: 'Figueroa', creator: '', period: '', description: '',
  media_type: 'Image', medium: '', subjects: '', year: '',
};
export const NEWFIELDS = {
  id: 'newfields-test', title: 'Guadalupe', creator: '', period: 'about 1700',
  description: '', media_type: 'Image', medium: 'oil on canvas', subjects: '',
  year: '1700',
};
export const PLACEHOLDER = {
  id: 'telar-placeholder', title: 'Telar', creator: '', period: '',
  description: '', media_type: 'Image', medium: '', subjects: '', year: '',
};
export const VIDEO = {
  id: 'test-video', title: 'Test Video', creator: '', period: '',
  description: 'A test video for development', media_type: 'Video', medium: '',
  subjects: '', year: '',
};
export const VIMEO = {
  id: 'test-vimeo', title: 'Test Vimeo', creator: '', period: '',
  description: 'A Vimeo test video for development', media_type: 'Video',
  medium: '', subjects: '', year: '',
};
export const JARABE = {
  id: 'cusb-cyl11337d', title: 'Jarabe tapatio', creator: 'R.H. Robinson',
  period: '1904',
  description: 'Male vocal with guitar. Edison Gold Moulded Record, Mexican Series.',
  media_type: 'Audio', medium: 'Mexican popular music', subjects: '',
  year: 'Popular music',
};
export const CERAMIC = {
  id: 'demo-ceramic-figure', title: 'Anthropomorphic Ceramic Figure',
  creator: 'Unknown Muisca Artist', period: 'Pre-colonial',
  description: 'Ceramic figure from the Muisca period representing indigenous material culture and ritual practices before Spanish colonization.',
  media_type: 'Image', medium: '',
  subjects: 'indigenous peoples, material culture, Muisca', year: '',
};

export const RECORDS = [ATLAS, FIGUEROA, NEWFIELDS, PLACEHOLDER, VIDEO, VIMEO, JARABE, CERAMIC];

/**
 * Facet counts the way scripts/telar/search.py builds them: empty values
 * skipped, subjects split on pipes, each category ordered by count descending
 * then alphabetically, case-insensitively.
 */
export function buildFacets(records) {
  const facets = { media_type: {}, medium: {}, creator: {}, subjects: {}, period: {} };
  const bump = (category, value) => {
    if (!value) return;
    facets[category][value] = (facets[category][value] || 0) + 1;
  };
  records.forEach((record) => {
    bump('media_type', record.media_type);
    bump('medium', record.medium);
    bump('creator', record.creator);
    bump('period', record.period);
    record.subjects.split('|').map((s) => s.trim()).forEach((s) => bump('subjects', s));
  });
  Object.keys(facets).forEach((category) => {
    const entries = Object.entries(facets[category]).sort(
      (a, b) => (b[1] - a[1]) || a[0].toLowerCase().localeCompare(b[0].toLowerCase()));
    facets[category] = Object.fromEntries(entries);
  });
  return facets;
}

export function searchData(records) {
  return { objects: records, facets: buildFacets(records), total: records.length };
}

export const BASEURL = '/telar';
export const DATA_URL = `${BASEURL}/search-data.json`;

/** One filter section, as the layout writes it with the Liquid resolved. */
function section(filterType, label) {
  return `
    <div class="objects-filter-section" data-filter="${filterType}">
      <button type="button" class="objects-filter-section-toggle" aria-expanded="false">
        <span>${label}</span>
        <span class="objects-filter-indicator">+</span>
      </button>
      <div class="objects-filter-options"></div>
    </div>`;
}

/** The browse-and-search markup of _layouts/objects-index.html, Liquid resolved. */
export function browseMarkup(records) {
  return `
<div class="objects-layout">
  <aside class="objects-sidebar">
    <div class="objects-search-wrapper">
      <input type="text" class="objects-search-input" id="objects-search-input"
             placeholder="Search objects..." aria-label="Search objects">
      <button type="button" class="objects-search-clear" id="objects-search-clear"
              style="display: none;" aria-label="Clear search">&times;</button>
    </div>

    <div class="objects-active-filters" id="objects-sidebar-active-filters" style="display: none;">
      <div class="objects-filter-chips" id="objects-sidebar-filter-chips"></div>
      <button type="button" class="objects-clear-all" id="objects-sidebar-clear-all">Clear all</button>
    </div>

    <div class="objects-filters-wrapper">
      <button type="button" class="objects-filters-mobile-toggle" id="objects-filters-mobile-toggle" aria-expanded="false">
        <span>Filter by</span>
      </button>

      <div class="objects-filters-content" id="objects-filters-content">
        <h3 class="objects-filter-heading">Filter by</h3>
        ${section('media_type', 'Type')}
        ${section('medium', 'Medium/Genre')}
        ${section('creator', 'Creator')}
        ${section('period', 'Period')}
        ${section('subjects', 'Subjects')}
      </div>
    </div>
  </aside>

  <div class="objects-main">
    <div class="objects-header">
      <div class="objects-header-row">
        <div class="objects-results-count">
          Showing <span id="objects-visible-count">${records.length}</span> of ${records.length} objects
        </div>
        <div class="objects-sort">
          <span class="objects-sort-label">Sort by:</span>
          <button type="button" class="objects-sort-btn active" data-sort="title" data-direction="asc">
            Title
            <span class="objects-sort-arrow">↑</span>
          </button>
          <span class="objects-sort-divider">|</span>
          <button type="button" class="objects-sort-btn" data-sort="year" data-direction="asc">
            Year
            <span class="objects-sort-arrow">↑</span>
          </button>
        </div>
      </div>
      <div class="objects-active-filters" id="objects-active-filters" style="display: none;">
        <div class="objects-filter-chips" id="objects-filter-chips"></div>
        <button type="button" class="objects-clear-all" id="objects-clear-all">Clear all</button>
      </div>
    </div>

    <div class="collection-grid"></div>
  </div>
</div>`;
}

/** The plain grid the layout writes when browse_and_search is off. */
export function plainMarkup() {
  return '<div class="collection-grid"></div>';
}

/**
 * One `.collection-item` card, as _includes/object-grid-item.html stamps it
 * with show_filters. Built as nodes rather than markup so a title or
 * description carrying quotes reaches the attribute unaltered.
 */
function addCard(record) {
  const card = document.createElement('a');
  card.className = 'collection-item';
  card.setAttribute('href', `/telar/objects/${record.id}/`);
  card.dataset.objectId = record.id;
  card.dataset.mediaType = record.media_type || 'Image';
  card.dataset.medium = record.medium;
  card.dataset.creator = record.creator;
  card.dataset.period = record.period;
  card.dataset.subjects = record.subjects;
  card.dataset.year = record.year;
  card.dataset.title = record.title;
  card.dataset.description = record.description;
  document.querySelector('.collection-grid').appendChild(card);
}

export function renderPage(records, { browse = true } = {}) {
  document.body.innerHTML = browse ? browseMarkup(records) : plainMarkup();
  records.forEach(addCard);
}

/** The Jekyll-injected baseurl tag from _layouts/default.html. */
export function setBaseUrlMeta(content) {
  const meta = document.createElement('meta');
  meta.setAttribute('name', 'baseurl');
  meta.setAttribute('content', content);
  document.head.appendChild(meta);
}

/** A fetch stub answering from a URL -> body map; anything else rejects. */
export function stubFetch(responses) {
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

/** Build a filter over the page as the bundle's tail does, and let it settle. */
export async function runScript() {
  const filter = createObjectsFilter({
    doc: document,
    fetchFn: globalThis.fetch,
    lunr: globalThis.lunr,
    location: window.location,
  });
  await filter.init();
  await flush();
}

export const el = (id) => document.getElementById(id);
export const cards = () => [...document.querySelectorAll('.collection-item')];
export const order = () => cards().map((card) => card.dataset.objectId);
export const visible = () => cards().filter((c) => c.style.display !== 'none')
  .map((c) => c.dataset.objectId);
export const hidden = () => cards().filter((c) => c.style.display === 'none')
  .map((c) => c.dataset.objectId);
export const count = () => el('objects-visible-count').textContent;

export const sectionEl = (filterType) =>
  document.querySelector(`.objects-filter-section[data-filter="${filterType}"]`);
export const options = (filterType) =>
  [...sectionEl(filterType).querySelectorAll('.objects-filter-option')];
export const optionLabels = (filterType) => options(filterType).map((option) => ({
  value: option.querySelector('input').value,
  filter: option.querySelector('input').dataset.filter,
  label: option.querySelector('.objects-filter-option-label').textContent,
  count: option.querySelector('.objects-filter-option-count').textContent,
}));
export const checkbox = (filterType, value) => document.querySelector(
  `.objects-filter-option input[data-filter="${filterType}"][value="${value}"]`);

export function check(filterType, value, checked = true) {
  const box = checkbox(filterType, value);
  box.checked = checked;
  box.dispatchEvent(new Event('change', { bubbles: true }));
}

export const chips = (id) => [...el(id).querySelectorAll('.objects-filter-chip')].map((chip) => ({
  type: chip.dataset.type,
  value: chip.dataset.value,
  text: chip.textContent.trim().replace(/\s+/g, ' '),
}));

export const sortButton = (field) => document.querySelector(`.objects-sort-btn[data-sort="${field}"]`);
export const sortState = () => [...document.querySelectorAll('.objects-sort-btn')].map((btn) => ({
  field: btn.dataset.sort,
  active: btn.classList.contains('active'),
  arrow: btn.querySelector('.objects-sort-arrow').textContent,
}));

export function search(query) {
  const input = el('objects-search-input');
  input.value = query;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

/** Registered as `beforeEach` by each test file so both share one setup. */
export function mockConsoleAndHistory() {
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  window.history.replaceState({}, '', '/telar/objects/');
}

/** Registered as `afterEach` by each test file so both share one teardown. */
export function resetTimersMocksAndDom() {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  document.head.querySelectorAll('meta[name="baseurl"]').forEach((meta) => meta.remove());
}
