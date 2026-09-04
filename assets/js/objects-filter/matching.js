/**
 * Telar — the two questions asked of every card in the objects gallery.
 *
 * A card is shown when the search allows it and the facets allow it, and
 * these are those two tests, apart from the DOM they are applied to. Both
 * take plain values, so what "matches" means can be read and checked without
 * a page.
 *
 * The facet test is the gallery's filtering rule in one place: OR within a
 * facet (any checked value will do), AND across facets (every facet with
 * something checked has to be satisfied). A facet with nothing checked is not
 * a constraint. Subjects are the one multi-valued field — a card carries them
 * pipe-separated — so there a card matches when any of its subjects is one of
 * the checked values; every other field is compared whole.
 *
 * Facet names are snake_case in the data and camelCase in a card's dataset
 * (`media_type` is `data-media-type` is `dataset.mediaType`), which is the
 * conversion the key does.
 *
 * Version: v1.7.0
 */

/** The dataset key a facet name reads from: media_type -> mediaType. */
function datasetKeyFor(filterType) {
  return filterType.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

/**
 * Whether a card is among the search results. A null set means no query is
 * standing, which every card passes.
 */
export function matchesSearch(objectId, matchingIds) {
  return matchingIds === null || matchingIds.has(objectId);
}

/** Whether a card's data attributes satisfy every facet with a value checked. */
export function matchesFilters(dataset, activeFilters) {
  for (const [filterType, values] of Object.entries(activeFilters)) {
    if (values.length === 0) continue;

    const itemValue = dataset[datasetKeyFor(filterType)] || '';

    if (filterType === 'subjects') {
      const itemSubjects = itemValue.split('|').map(s => s.trim());
      if (!values.some(v => itemSubjects.includes(v))) return false;
    } else if (!values.includes(itemValue)) {
      return false;
    }
  }

  return true;
}
