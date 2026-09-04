/**
 * Unit tests for the objects gallery filter's pure modules.
 *
 * Covers `matching.js` (matchesFilters, matchesSearch), `escape.js`
 * (escapeHtml) and `search-index.js` (getBaseUrl) directly, by argument and
 * return value rather than through the DOM. The characterisation suite that
 * drives `createObjectsFilter` over a rendered page instead lives in the
 * sibling `objects-filter.test.js`; both import shared fixtures and helpers
 * from `objects-filter-fixture.js`.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { escapeHtml } from '../../assets/js/objects-filter/escape.js';
import { matchesFilters, matchesSearch } from '../../assets/js/objects-filter/matching.js';
import { getBaseUrl } from '../../assets/js/objects-filter/search-index.js';

import {
  ATLAS, JARABE, VIDEO, NEWFIELDS,
  setBaseUrlMeta, mockConsoleAndHistory, resetTimersMocksAndDom,
} from './objects-filter-fixture.js';

beforeEach(mockConsoleAndHistory);
afterEach(resetTimersMocksAndDom);

describe('the vendored search library', () => {
  it('is the global the filter reads', () => {
    expect(typeof lunr).toBe('function');
  });
});

describe('what a card is judged by', () => {
  const NONE = { media_type: [], medium: [], creator: [], period: [], subjects: [] };
  const withFilters = (overrides) => ({ ...NONE, ...overrides });

  /** A card's dataset, in the camelCase the filters have to reach it by. */
  const datasetOf = (record) => ({
    objectId: record.id,
    mediaType: record.media_type,
    medium: record.medium,
    creator: record.creator,
    period: record.period,
    subjects: record.subjects,
    year: record.year,
    title: record.title,
  });

  describe('matchesSearch', () => {
    it('passes every card when no query is standing', () => {
      expect(matchesSearch('atlas-allegory', null)).toBe(true);
      expect(matchesSearch('anything', null)).toBe(true);
    });

    it('passes only the cards the query returned', () => {
      const results = new Set(['test-video', 'test-vimeo']);
      expect(matchesSearch('test-video', results)).toBe(true);
      expect(matchesSearch('atlas-allegory', results)).toBe(false);
    });

    it('passes nothing when the query returned nothing', () => {
      expect(matchesSearch('test-video', new Set())).toBe(false);
    });
  });

  describe('matchesFilters', () => {
    it('passes every card when nothing is checked', () => {
      expect(matchesFilters(datasetOf(ATLAS), NONE)).toBe(true);
      expect(matchesFilters(datasetOf(JARABE), NONE)).toBe(true);
    });

    it('compares a single-valued field whole', () => {
      const images = withFilters({ media_type: ['Image'] });
      expect(matchesFilters(datasetOf(ATLAS), images)).toBe(true);
      expect(matchesFilters(datasetOf(JARABE), images)).toBe(false);
    });

    it('takes any checked value in one facet', () => {
      const twoTypes = withFilters({ media_type: ['Video', 'Audio'] });
      expect(matchesFilters(datasetOf(VIDEO), twoTypes)).toBe(true);
      expect(matchesFilters(datasetOf(JARABE), twoTypes)).toBe(true);
      expect(matchesFilters(datasetOf(ATLAS), twoTypes)).toBe(false);
    });

    it('requires every facet that has something checked', () => {
      const both = withFilters({ media_type: ['Image'], medium: ['oil on canvas'] });
      expect(matchesFilters(datasetOf(NEWFIELDS), both)).toBe(true);
      expect(matchesFilters(datasetOf(ATLAS), both)).toBe(false);
      expect(matchesFilters(datasetOf(JARABE), both)).toBe(false);
    });

    /**
     * Both subject strings are verbatim object metadata from this
     * repository -- the first from atlas-allegory, the second from
     * demo-atlas-allegory in `_data/objects.json`. No object here carries two
     * subjects at once, so the card that does is the pairing, not the values.
     */
    it('matches any one of a card\'s pipe-separated subjects', () => {
      const maps = 'Western Hemisphere—Maps—Early works to 1800';
      const colonial = 'colonialism, cartography, allegory';
      const card = { subjects: `${maps}| ${colonial}` };

      expect(matchesFilters(card, withFilters({ subjects: [maps] }))).toBe(true);
      expect(matchesFilters(card, withFilters({ subjects: [colonial] }))).toBe(true);
      expect(matchesFilters({ subjects: maps }, withFilters({ subjects: [colonial] })))
        .toBe(false);
    });

    it('takes any checked subject, not all of them', () => {
      const maps = 'Western Hemisphere—Maps—Early works to 1800';
      const colonial = 'colonialism, cartography, allegory';

      expect(matchesFilters({ subjects: maps }, withFilters({ subjects: [colonial, maps] })))
        .toBe(true);
    });

    it('treats a missing attribute as an empty value', () => {
      expect(matchesFilters({}, withFilters({ creator: ['Laureano Atlas'] }))).toBe(false);
      expect(matchesFilters({}, withFilters({ creator: [''] }))).toBe(true);
    });

    it('reads a snake_case facet from its camelCase attribute', () => {
      expect(matchesFilters({ mediaType: 'Audio' }, withFilters({ media_type: ['Audio'] })))
        .toBe(true);
      expect(matchesFilters({ media_type: 'Audio' }, withFilters({ media_type: ['Audio'] })))
        .toBe(false);
    });
  });
});

describe('escapeHtml', () => {
  it('escapes the characters that would break out of markup or an attribute', () => {
    expect(escapeHtml('<b>&"\'', document)).toBe('&lt;b&gt;&amp;&quot;&#39;');
  });

  it('leaves ordinary text, accents and dashes alone', () => {
    expect(escapeHtml('Aspecto Symbólico del Mundo Hispánico', document))
      .toBe('Aspecto Symbólico del Mundo Hispánico');
    expect(escapeHtml('Western Hemisphere—Maps—Early works to 1800', document))
      .toBe('Western Hemisphere—Maps—Early works to 1800');
  });
});

describe('getBaseUrl', () => {
  const at = (pathname) => ({ pathname });

  it('prefers the meta tag over the page path', () => {
    setBaseUrlMeta('/telar');
    expect(getBaseUrl(document, at('/somewhere/else/'))).toBe('/telar');
  });

  it('reads an empty meta tag as an empty base URL', () => {
    setBaseUrlMeta('');
    expect(getBaseUrl(document, at('/telar/objects/'))).toBe('');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('derives the base URL from an objects path when the tag is absent', () => {
    expect(getBaseUrl(document, at('/telar/objects/'))).toBe('/telar');
    expect(getBaseUrl(document, at('/telar/objects/atlas-allegory/'))).toBe('/telar');
    expect(console.warn).toHaveBeenCalledWith(
      '[Telar] meta[name="baseurl"] not found; deriving the base URL from the page path.');
  });

  it('derives nothing from a path with no baseurl segment', () => {
    expect(getBaseUrl(document, at('/objects/'))).toBe('');
  });

  it('derives nothing from a path that is not an objects page', () => {
    expect(getBaseUrl(document, at('/telar/stories/one/'))).toBe('');
  });
});
