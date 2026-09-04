/**
 * Telar — where the objects gallery gets its data and its search index.
 *
 * Two things the filter needs before it can do anything: the address
 * `search-data.json` is served from, and a Lunr index over the objects that
 * file carries.
 *
 * The base URL comes from the `<meta name="baseurl">` tag the default layout
 * injects. When that tag is absent the address is derived from the page path
 * instead, which only holds on an `/objects/` page, so the fallback warns
 * rather than passing silently.
 *
 * The index is built client-side from the loaded JSON: the Python build stays
 * simple, and for a collection of the size Telar targets (under 500 objects)
 * the cost is negligible. Title, creator and description are boosted in that
 * order. Lunr itself is the vendored copy the layout loads in its own script
 * tag before this bundle, read here as an injectable parameter.
 *
 * Version: v1.7.0
 */

/** The site's base URL, from the layout's meta tag or from the page path. */
export function getBaseUrl(doc = document, location = window.location) {
  // Get baseurl from the page (set by Jekyll)
  const baseUrlMeta = doc.querySelector('meta[name="baseurl"]');
  if (baseUrlMeta) {
    return baseUrlMeta.getAttribute('content') || '';
  }
  // Fallback: derive from the current URL. This only runs if the layout did not
  // inject <meta name="baseurl"> — warn so a missing tag is noticed rather than
  // silently relying on the /objects/ path shape.
  console.warn('[Telar] meta[name="baseurl"] not found; deriving the base URL from the page path.');
  const path = location.pathname;
  const match = path.match(/^(\/[^\/]+)?\/objects\//);
  return match ? (match[1] || '') : '';
}

/** A Lunr index over the loaded objects, or null when Lunr is not there. */
export function buildSearchIndex(searchData, lunr = globalThis.lunr) {
  if (typeof lunr === 'undefined') {
    console.warn('Objects filter: Lunr.js not loaded');
    return null;
  }

  return lunr(function() {
    this.ref('id');
    this.field('title', { boost: 10 });
    this.field('creator', { boost: 5 });
    this.field('description', { boost: 2 });
    this.field('period');
    this.field('subjects');
    this.field('medium');

    searchData.objects.forEach(obj => {
      this.add(obj);
    });
  });
}
