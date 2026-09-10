/**
 * Characterisation tests for the objects gallery filter.
 *
 * The gallery filter publishes no global. Its whole interface is the objects
 * index page's DOM: which cards carry `display: none`, what the visible count
 * says, what chips stand above the grid and in the sidebar, which checkboxes
 * are checked, which filter sections are open, which sort button is active and
 * in which direction, and the order the cards sit in the grid. These pin that
 * output for every branch, so that a refactor is judged by whether the gallery
 * still behaves the same way, by driving `createObjectsFilter` over a rendered
 * page rather than calling its pieces directly. The unit tests for those
 * pieces -- `matching.js`, `escape.js`, `search-index.js` -- live in the
 * sibling `objects-filter-units.test.js`; both files share fixtures and
 * helpers from `objects-filter-fixture.js`.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  RECORDS, FIGUEROA, NEWFIELDS, VIDEO,
  BASEURL, DATA_URL, searchData,
  renderPage, setBaseUrlMeta, stubFetch, runScript,
  el, order, visible, hidden, count,
  sectionEl, options, optionLabels, checkbox, check,
  chips, sortButton, sortState, search,
  mockConsoleAndHistory, resetTimersMocksAndDom,
} from './objects-filter-fixture.js';

beforeEach(mockConsoleAndHistory);
afterEach(resetTimersMocksAndDom);

describe('a page without the browse-and-search layout', () => {
  it('fetches nothing and leaves the grid alone', async () => {
    renderPage(RECORDS, { browse: false });
    setBaseUrlMeta(BASEURL);
    const calls = stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();

    expect(calls).toEqual([]);
    expect(el('objects-visible-count')).toBeNull();
    expect(visible()).toEqual(RECORDS.map((r) => r.id));
  });
});

describe('search data that cannot be loaded', () => {
  beforeEach(() => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
  });

  it('warns and touches nothing when the response is not ok', async () => {
    const calls = stubFetch({ [DATA_URL]: { notOk: true, body: searchData(RECORDS) } });
    await runScript();

    expect(calls).toEqual([DATA_URL]);
    expect(console.warn).toHaveBeenCalledWith('Objects filter: search-data.json not found');
    expect(options('media_type')).toEqual([]);
    expect(count()).toBe('8');
    expect(hidden()).toEqual([]);
  });

  it('warns and touches nothing when the fetch throws', async () => {
    const calls = stubFetch({ [DATA_URL]: new Error('offline') });
    await runScript();

    expect(calls).toEqual([DATA_URL]);
    expect(console.warn).toHaveBeenCalledWith(
      'Objects filter: Failed to load search data', expect.any(Error));
    expect(options('media_type')).toEqual([]);
    expect(count()).toBe('8');
  });
});

describe('where the search data is fetched from', () => {
  beforeEach(() => {
    renderPage(RECORDS);
  });

  it('takes the base URL from the meta tag', async () => {
    setBaseUrlMeta(BASEURL);
    const calls = stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();

    expect(calls).toEqual([DATA_URL]);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('takes an empty base URL from a meta tag with none', async () => {
    setBaseUrlMeta('');
    const calls = stubFetch({ '/search-data.json': searchData(RECORDS) });
    await runScript();

    expect(calls).toEqual(['/search-data.json']);
  });

  it('falls back to the page path and warns when the meta tag is absent', async () => {
    const calls = stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();

    expect(calls).toEqual([DATA_URL]);
    expect(console.warn).toHaveBeenCalledWith(
      '[Telar] meta[name="baseurl"] not found; deriving the base URL from the page path.');
  });

  it('derives no base URL for a site served at the origin root', async () => {
    window.history.replaceState({}, '', '/objects/');
    const calls = stubFetch({ '/search-data.json': searchData(RECORDS) });
    await runScript();

    expect(calls).toEqual(['/search-data.json']);
  });
});

describe('the filter sections', () => {
  beforeEach(async () => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();
  });

  it('lists each media type with its count, most common first', () => {
    expect(optionLabels('media_type')).toEqual([
      { value: 'Image', filter: 'media_type', label: 'Image', count: '(5)' },
      { value: 'Video', filter: 'media_type', label: 'Video', count: '(2)' },
      { value: 'Audio', filter: 'media_type', label: 'Audio', count: '(1)' },
    ]);
  });

  it('lists the other facets in the order the data gives them', () => {
    expect(optionLabels('medium').map((o) => `${o.label} ${o.count}`))
      .toEqual(['Mexican popular music (1)', 'oil on canvas (1)']);
    expect(optionLabels('creator').map((o) => `${o.label} ${o.count}`))
      .toEqual(['Laureano Atlas (1)', 'R.H. Robinson (1)', 'Unknown Muisca Artist (1)']);
    expect(optionLabels('period').map((o) => `${o.label} ${o.count}`))
      .toEqual(['1761 (1)', '1904 (1)', 'about 1700 (1)', 'Pre-colonial (1)']);
    expect(optionLabels('subjects').map((o) => `${o.label} ${o.count}`))
      .toEqual(['indigenous peoples, material culture, Muisca (1)',
                'Western Hemisphere—Maps—Early works to 1800 (1)']);
  });

  it('leaves every section closed, with a plus and no options shown', () => {
    const toggle = sectionEl('media_type').querySelector('.objects-filter-section-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.querySelector('.objects-filter-indicator').textContent).toBe('+');
    expect(sectionEl('media_type').querySelector('.objects-filter-options')
      .classList.contains('show')).toBe(false);
  });

  it('opens and closes a section on its toggle', () => {
    const toggle = sectionEl('creator').querySelector('.objects-filter-section-toggle');
    const list = sectionEl('creator').querySelector('.objects-filter-options');
    const indicator = toggle.querySelector('.objects-filter-indicator');

    toggle.click();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(list.classList.contains('show')).toBe(true);
    expect(indicator.textContent).toBe('−');

    toggle.click();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(list.classList.contains('show')).toBe(false);
    expect(indicator.textContent).toBe('+');
  });

  it('counts every object before anything is filtered', () => {
    expect(count()).toBe('8');
    expect(hidden()).toEqual([]);
  });
});

describe('a facet with no values', () => {
  it('says so instead of listing options', async () => {
    const records = [FIGUEROA, NEWFIELDS, VIDEO];
    renderPage(records);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(records) });
    await runScript();

    const list = sectionEl('subjects').querySelector('.objects-filter-options');
    expect(list.innerHTML)
      .toBe('<span class="objects-filter-empty">No options available</span>');
    expect(options('subjects')).toEqual([]);
    expect(optionLabels('medium').map((o) => o.label)).toEqual(['oil on canvas']);
  });
});

describe('filtering by facet', () => {
  beforeEach(async () => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();
  });

  it('shows only the cards matching one checked value', () => {
    check('media_type', 'Video');

    expect(visible()).toEqual(['test-video', 'test-vimeo']);
    expect(hidden()).toEqual([
      'atlas-allegory', 'figueroa', 'newfields-test', 'telar-placeholder',
      'cusb-cyl11337d', 'demo-ceramic-figure',
    ]);
    expect(count()).toBe('2');
    expect(checkbox('media_type', 'Video').checked).toBe(true);
  });

  it('joins two values in the same facet with or', () => {
    check('media_type', 'Video');
    check('media_type', 'Audio');

    expect(visible()).toEqual(['test-video', 'test-vimeo', 'cusb-cyl11337d']);
    expect(count()).toBe('3');
  });

  it('joins two values in the same facet with or when each matches one card', () => {
    check('creator', 'Laureano Atlas');
    check('creator', 'R.H. Robinson');

    expect(visible()).toEqual(['atlas-allegory', 'cusb-cyl11337d']);
    expect(count()).toBe('2');
  });

  it('joins two facets with and', () => {
    check('media_type', 'Image');
    check('medium', 'oil on canvas');

    expect(visible()).toEqual(['newfields-test']);
    expect(count()).toBe('1');
  });

  it('shows nothing when two facets cannot both be satisfied', () => {
    check('media_type', 'Audio');
    check('medium', 'oil on canvas');

    expect(visible()).toEqual([]);
    expect(count()).toBe('0');
  });

  it('matches a subject inside a pipe-separated list', () => {
    check('subjects', 'Western Hemisphere—Maps—Early works to 1800');

    expect(visible()).toEqual(['atlas-allegory']);
    expect(count()).toBe('1');
  });

  it('restores the hidden cards when the box is unchecked', () => {
    check('media_type', 'Video');
    check('media_type', 'Video', false);

    expect(visible()).toEqual(RECORDS.map((r) => r.id));
    expect(count()).toBe('8');
    expect(el('objects-active-filters').style.display).toBe('none');
  });
});

describe('the active filter chips', () => {
  beforeEach(async () => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();
  });

  it('are hidden until something is filtered', () => {
    expect(el('objects-active-filters').style.display).toBe('none');
    expect(el('objects-sidebar-active-filters').style.display).toBe('none');
    expect(chips('objects-filter-chips')).toEqual([]);
  });

  it('appear in both chip areas, above the grid and in the sidebar', () => {
    check('media_type', 'Video');
    check('creator', 'Laureano Atlas');

    const expected = [
      { type: 'media_type', value: 'Video', text: 'Video ×' },
      { type: 'creator', value: 'Laureano Atlas', text: 'Laureano Atlas ×' },
    ];
    expect(chips('objects-filter-chips')).toEqual(expected);
    expect(chips('objects-sidebar-filter-chips')).toEqual(expected);
    expect(el('objects-active-filters').style.display).toBe('flex');
    expect(el('objects-sidebar-active-filters').style.display).toBe('flex');
  });

  it('unchecks the box and re-filters when a chip is removed', () => {
    check('media_type', 'Video');
    check('media_type', 'Audio');
    el('objects-filter-chips')
      .querySelector('.objects-filter-chip[data-value="Video"] .objects-filter-chip-remove')
      .click();

    expect(checkbox('media_type', 'Video').checked).toBe(false);
    expect(checkbox('media_type', 'Audio').checked).toBe(true);
    expect(visible()).toEqual(['cusb-cyl11337d']);
    expect(count()).toBe('1');
    expect(chips('objects-filter-chips')).toEqual([
      { type: 'media_type', value: 'Audio', text: 'Audio ×' },
    ]);
  });

  it('removes a chip from the sidebar copy just as well', () => {
    check('media_type', 'Video');
    el('objects-sidebar-filter-chips').querySelector('.objects-filter-chip-remove').click();

    expect(checkbox('media_type', 'Video').checked).toBe(false);
    expect(visible()).toEqual(RECORDS.map((r) => r.id));
    expect(chips('objects-sidebar-filter-chips')).toEqual([]);
  });

  it('clears everything from the button above the grid', () => {
    check('media_type', 'Video');
    check('creator', 'Laureano Atlas');
    el('objects-clear-all').click();

    expect(visible()).toEqual(RECORDS.map((r) => r.id));
    expect(count()).toBe('8');
    expect(chips('objects-filter-chips')).toEqual([]);
    expect(chips('objects-sidebar-filter-chips')).toEqual([]);
    expect(el('objects-active-filters').style.display).toBe('none');
    expect(el('objects-sidebar-active-filters').style.display).toBe('none');
    expect(document.querySelectorAll('.objects-filter-option input:checked')).toHaveLength(0);
  });

  it('clears everything from the sidebar button too', () => {
    check('media_type', 'Video');
    el('objects-sidebar-clear-all').click();

    expect(visible()).toEqual(RECORDS.map((r) => r.id));
    expect(chips('objects-sidebar-filter-chips')).toEqual([]);
    expect(document.querySelectorAll('.objects-filter-option input:checked')).toHaveLength(0);
  });
});

describe('searching', () => {
  beforeEach(async () => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();
    vi.useFakeTimers();
  });

  it('waits for the typing to stop before filtering', () => {
    search('vimeo');
    vi.advanceTimersByTime(249);
    expect(visible()).toEqual(RECORDS.map((r) => r.id));
    expect(count()).toBe('8');

    vi.advanceTimersByTime(1);
    expect(visible()).toEqual(['test-vimeo']);
    expect(count()).toBe('1');
  });

  it('matches a word in the title', () => {
    search('guadalup');
    vi.advanceTimersByTime(250);

    expect(visible()).toEqual(['newfields-test']);
  });

  it('matches a word in the creator', () => {
    search('robinson');
    vi.advanceTimersByTime(250);

    expect(visible()).toEqual(['cusb-cyl11337d']);
  });

  it('matches a word in the description', () => {
    search('repres');
    vi.advanceTimersByTime(250);

    expect(visible()).toEqual(['demo-ceramic-figure']);
  });

  /**
   * The query is submitted to Lunr as both the bare word and the word with a
   * trailing wildcard, so a whole word the English stemmer shortens still
   * matches through the stemmer even though the wildcard term alone would
   * miss it.
   */
  it('matches a whole word the stemmer shortens, typed in full', () => {
    search('guadalupe');
    vi.advanceTimersByTime(250);
    expect(visible()).toEqual(['newfields-test']);

    search('representing');
    vi.advanceTimersByTime(250);
    expect(visible()).toEqual(['demo-ceramic-figure']);
  });

  it('still matches a prefix shorter than the whole word', () => {
    search('guad');
    vi.advanceTimersByTime(250);
    expect(visible()).toEqual(['newfields-test']);
  });

  it('hides everything when nothing matches', () => {
    search('zzzznothing');
    vi.advanceTimersByTime(250);

    expect(visible()).toEqual([]);
    expect(count()).toBe('0');
  });

  it('shows the clear button while a query stands, and clears on it', () => {
    expect(el('objects-search-clear').style.display).toBe('none');

    search('vimeo');
    vi.advanceTimersByTime(250);
    expect(el('objects-search-clear').style.display).toBe('block');
    expect(chips('objects-filter-chips')).toEqual([
      { type: 'search', value: undefined, text: '"vimeo" ×' },
    ]);

    el('objects-search-clear').click();
    expect(el('objects-search-input').value).toBe('');
    expect(el('objects-search-clear').style.display).toBe('none');
    expect(visible()).toEqual(RECORDS.map((r) => r.id));
    expect(count()).toBe('8');
    expect(chips('objects-filter-chips')).toEqual([]);
  });

  /**
   * The query is the one string in the gallery that comes from whoever is
   * looking, so the chip that echoes it is where markup could reach the page.
   */
  it('shows a query containing markup in its chip as text', () => {
    search('<b>&"\'');
    vi.advanceTimersByTime(250);

    const chip = el('objects-filter-chips')
      .querySelector('.objects-filter-chip[data-type="search"]');
    expect(chip.textContent.trim().replace(/\s+/g, ' ')).toBe('"<b>&"\'" ×');
    expect(chip.querySelector('b')).toBeNull();
    expect(el('objects-sidebar-filter-chips').querySelector('b')).toBeNull();
  });

  it('drops the query when its chip is removed', () => {
    search('vimeo');
    vi.advanceTimersByTime(250);
    el('objects-filter-chips')
      .querySelector('.objects-filter-chip[data-type="search"] .objects-filter-chip-remove')
      .click();

    expect(el('objects-search-input').value).toBe('');
    expect(el('objects-search-clear').style.display).toBe('none');
    expect(visible()).toEqual(RECORDS.map((r) => r.id));
  });

  it('narrows a query with a facet, and both chips stand', () => {
    search('test');
    vi.advanceTimersByTime(250);
    expect(visible()).toEqual(['test-video', 'test-vimeo']);

    check('media_type', 'Audio');
    expect(visible()).toEqual([]);
    expect(count()).toBe('0');
    expect(chips('objects-filter-chips')).toEqual([
      { type: 'search', value: undefined, text: '"test" ×' },
      { type: 'media_type', value: 'Audio', text: 'Audio ×' },
    ]);
  });

  it('keeps the query when only the facet is cleared', () => {
    search('test');
    vi.advanceTimersByTime(250);
    check('media_type', 'Video');
    expect(visible()).toEqual(['test-video', 'test-vimeo']);

    check('media_type', 'Video', false);
    expect(visible()).toEqual(['test-video', 'test-vimeo']);
    expect(chips('objects-filter-chips')).toEqual([
      { type: 'search', value: undefined, text: '"test" ×' },
    ]);
  });
});

describe('sorting', () => {
  beforeEach(async () => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();
  });

  it('leaves the grid in the order the page rendered it', () => {
    expect(order()).toEqual(RECORDS.map((r) => r.id));
    expect(sortState()).toEqual([
      { field: 'title', active: true, arrow: '↑' },
      { field: 'year', active: false, arrow: '↑' },
    ]);
  });

  it('turns the active title sort around on a click', () => {
    sortButton('title').click();

    expect(sortState()).toEqual([
      { field: 'title', active: true, arrow: '↓' },
      { field: 'year', active: false, arrow: '↓' },
    ]);
    expect(order()).toEqual([
      'test-vimeo', 'test-video', 'telar-placeholder', 'cusb-cyl11337d',
      'newfields-test', 'figueroa', 'atlas-allegory', 'demo-ceramic-figure',
    ]);
  });

  it('comes back to ascending on a second click', () => {
    sortButton('title').click();
    sortButton('title').click();

    expect(sortState()).toEqual([
      { field: 'title', active: true, arrow: '↑' },
      { field: 'year', active: false, arrow: '↑' },
    ]);
    expect(order()).toEqual([
      'demo-ceramic-figure', 'atlas-allegory', 'figueroa', 'newfields-test',
      'cusb-cyl11337d', 'telar-placeholder', 'test-video', 'test-vimeo',
    ]);
  });

  it('sorts by year ascending on the first click, undated objects last', () => {
    sortButton('year').click();

    expect(sortState()).toEqual([
      { field: 'title', active: false, arrow: '↑' },
      { field: 'year', active: true, arrow: '↑' },
    ]);
    expect(order()).toEqual([
      'newfields-test', 'atlas-allegory', 'figueroa', 'telar-placeholder',
      'test-video', 'test-vimeo', 'cusb-cyl11337d', 'demo-ceramic-figure',
    ]);
  });

  it('turns the year sort around on a second click', () => {
    sortButton('year').click();
    sortButton('year').click();

    expect(sortState()).toEqual([
      { field: 'title', active: false, arrow: '↓' },
      { field: 'year', active: true, arrow: '↓' },
    ]);
    expect(order()).toEqual([
      'figueroa', 'telar-placeholder', 'test-video', 'test-vimeo',
      'cusb-cyl11337d', 'demo-ceramic-figure', 'atlas-allegory', 'newfields-test',
    ]);
  });

  it('keeps the hidden cards hidden through a sort', () => {
    check('media_type', 'Video');
    sortButton('year').click();

    expect(visible()).toEqual(['test-video', 'test-vimeo']);
    expect(count()).toBe('2');
  });
});

describe('the mobile filter panel', () => {
  beforeEach(async () => {
    renderPage(RECORDS);
    setBaseUrlMeta(BASEURL);
    stubFetch({ [DATA_URL]: searchData(RECORDS) });
    await runScript();
  });

  it('opens and closes on its toggle', () => {
    const toggle = el('objects-filters-mobile-toggle');
    const content = el('objects-filters-content');

    toggle.click();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(content.classList.contains('show')).toBe(true);

    toggle.click();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(content.classList.contains('show')).toBe(false);
  });
});
