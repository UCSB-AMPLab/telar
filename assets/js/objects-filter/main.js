/**
 * Telar — objects gallery filter and search.
 *
 * This module powers the browse-and-search interface on the objects index
 * page. It loads `search-data.json` (generated at build time by Python) which
 * contains object metadata and pre-computed facet counts for the filter
 * sidebar. The facets — Type (auto-detected media type), Medium/Genre, Creator,
 * Period, Subjects — are populated dynamically with counts like "Early maps (3)"
 * so users know what's available before clicking.
 *
 * Filtering works by reading data attributes on each `.collection-item` card
 * (e.g., `data-creator`, `data-period`) and showing/hiding cards based on
 * active filter selections. Multiple filters within a category use OR logic
 * (show if matches any), while filters across categories use AND logic (must
 * match all); both tests live in `matching.js`, so what makes a card match is
 * separate from the pass that hides it. Active filters appear as removable
 * chips above the grid.
 *
 * Search uses Lunr.js for full-text matching across title, creator,
 * description, and other fields, and is debounced at 250ms so typing does not
 * refilter on every keystroke. The index is built in `search-index.js`. Each
 * query is submitted to Lunr as both the bare word and the word with a
 * trailing wildcard, so a whole word the stemmer shortens still matches
 * through the stemmer while a shorter prefix still matches through the
 * wildcard.
 *
 * Sorting supports Title (A-Z/Z-A) and Year (ascending/descending). Clicking
 * the active sort button toggles direction; clicking an inactive button
 * switches to that field in ascending order. DOM reordering uses appendChild
 * which maintains event listeners on the cards.
 *
 * The whole thing is a factory rather than a file-scope closure: the state it
 * keeps (the loaded data, the search index, the active filters, the current
 * sort, the cached elements) belongs to one gallery, so a test can build one
 * over its own document and leave no state behind. The document, fetch, Lunr
 * and location are parameters with browser defaults.
 *
 * Bundled by esbuild into assets/js/objects-filter.js; see assets/js/README.md.
 *
 * Version: v1.7.0
 */

import { escapeHtml } from './escape.js';
import { matchesFilters, matchesSearch } from './matching.js';
import { getBaseUrl, buildSearchIndex } from './search-index.js';

/** One gallery's filter, search and sort over the page it is given. */
export function createObjectsFilter({
  doc = document,
  fetchFn = (url) => globalThis.fetch(url),
  lunr = globalThis.lunr,
  location = window.location,
} = {}) {
  // State
  let searchData = null;
  let searchIndex = null;
  let activeFilters = {
    media_type: [],
    medium: [],
    creator: [],
    period: [],
    subjects: []
  };
  let searchQuery = '';
  let currentSort = { field: 'title', direction: 'asc' };

  // DOM elements (cached on init)
  let elements = {};

  /**
   * Initialize the filter system
   */
  async function init() {
    // Check if we're on the objects page with browse_and_search enabled
    const objectsLayout = doc.querySelector('.objects-layout');
    if (!objectsLayout) {
      return; // Not on objects page or browse_and_search disabled
    }

    // Cache DOM elements
    cacheElements();

    // Load search data
    try {
      const response = await fetchFn(getBaseUrl(doc, location) + '/search-data.json');
      if (!response.ok) {
        console.warn('Objects filter: search-data.json not found');
        return;
      }
      searchData = await response.json();
    } catch (error) {
      console.warn('Objects filter: Failed to load search data', error);
      return;
    }

    // Initialize Lunr.js search index
    searchIndex = buildSearchIndex(searchData, lunr);

    // Populate filter sections with facet data
    populateFilters();

    // Bind event listeners
    bindEvents();

    // Initial state
    updateCount();

    console.log('Objects filter initialized');
  }

  /**
   * Cache commonly used DOM elements
   */
  function cacheElements() {
    elements = {
      grid: doc.querySelector('.collection-grid'),
      items: doc.querySelectorAll('.collection-item'),
      visibleCount: doc.getElementById('objects-visible-count'),
      searchInput: doc.getElementById('objects-search-input'),
      searchClear: doc.getElementById('objects-search-clear'),
      filterSections: doc.querySelectorAll('.objects-filter-section'),
      sectionToggles: doc.querySelectorAll('.objects-filter-section-toggle'),
      activeFiltersContainer: doc.getElementById('objects-active-filters'),
      filterChips: doc.getElementById('objects-filter-chips'),
      clearAllBtn: doc.getElementById('objects-clear-all'),
      sidebarActiveFilters: doc.getElementById('objects-sidebar-active-filters'),
      sidebarFilterChips: doc.getElementById('objects-sidebar-filter-chips'),
      sidebarClearAll: doc.getElementById('objects-sidebar-clear-all'),
      sortButtons: doc.querySelectorAll('.objects-sort-btn'),
      mobileToggle: doc.getElementById('objects-filters-mobile-toggle'),
      filtersContent: doc.getElementById('objects-filters-content')
    };
  }

  /**
   * Populate filter sections with facet data
   */
  function populateFilters() {
    if (!searchData || !searchData.facets) return;

    elements.filterSections.forEach(section => {
      const filterType = section.dataset.filter;
      const facets = searchData.facets[filterType];
      const optionsContainer = section.querySelector('.objects-filter-options');

      if (!facets || !optionsContainer) return;

      // Clear existing options
      optionsContainer.innerHTML = '';

      // Add options
      const entries = Object.entries(facets);
      if (entries.length === 0) {
        optionsContainer.innerHTML = '<span class="objects-filter-empty">No options available</span>';
        return;
      }

      entries.forEach(([value, count]) => {
        const option = doc.createElement('label');
        option.className = 'objects-filter-option';
        option.innerHTML = `
          <input type="checkbox" value="${escapeHtml(value, doc)}" data-filter="${filterType}">
          <span class="objects-filter-option-label">${escapeHtml(value, doc)}</span>
          <span class="objects-filter-option-count">(${count})</span>
        `;
        optionsContainer.appendChild(option);
      });
    });
  }

  /**
   * Bind event listeners
   */
  function bindEvents() {
    // Filter section expand/collapse
    elements.sectionToggles.forEach(toggle => {
      toggle.addEventListener('click', handleSectionToggle);
    });

    // Filter checkbox changes
    doc.querySelectorAll('.objects-filter-option input[type="checkbox"]').forEach(checkbox => {
      checkbox.addEventListener('change', handleFilterChange);
    });

    // Clear all buttons
    if (elements.clearAllBtn) {
      elements.clearAllBtn.addEventListener('click', clearAllFilters);
    }
    if (elements.sidebarClearAll) {
      elements.sidebarClearAll.addEventListener('click', clearAllFilters);
    }

    // Sort buttons
    elements.sortButtons.forEach(btn => {
      btn.addEventListener('click', handleSortClick);
    });

    // Search input
    if (elements.searchInput) {
      let debounceTimer;
      elements.searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          handleSearch(e.target.value);
        }, 250);
      });
    }

    // Search clear button
    if (elements.searchClear) {
      elements.searchClear.addEventListener('click', () => {
        elements.searchInput.value = '';
        handleSearch('');
      });
    }

    // Mobile toggle
    if (elements.mobileToggle) {
      elements.mobileToggle.addEventListener('click', handleMobileToggle);
    }
  }

  /**
   * Handle filter section expand/collapse
   */
  function handleSectionToggle(e) {
    const toggle = e.currentTarget;
    const section = toggle.closest('.objects-filter-section');
    const options = section.querySelector('.objects-filter-options');
    const indicator = toggle.querySelector('.objects-filter-indicator');
    const isExpanded = toggle.getAttribute('aria-expanded') === 'true';

    toggle.setAttribute('aria-expanded', !isExpanded);
    options.classList.toggle('show', !isExpanded);
    indicator.textContent = isExpanded ? '+' : '−';
  }

  /**
   * Handle filter checkbox change
   */
  function handleFilterChange(e) {
    const checkbox = e.target;
    const filterType = checkbox.dataset.filter;
    const value = checkbox.value;

    if (checkbox.checked) {
      if (!activeFilters[filterType].includes(value)) {
        activeFilters[filterType].push(value);
      }
    } else {
      activeFilters[filterType] = activeFilters[filterType].filter(v => v !== value);
    }

    applyFilters();
    updateActiveFiltersUI();
  }

  /**
   * Handle sort button click
   */
  function handleSortClick(e) {
    const btn = e.currentTarget;
    const sortField = btn.dataset.sort;

    if (currentSort.field === sortField) {
      // Toggle direction
      currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
      // Change field, default to ascending
      currentSort.field = sortField;
      currentSort.direction = 'asc';
    }

    // Update button UI
    elements.sortButtons.forEach(b => {
      const isActive = b.dataset.sort === currentSort.field;
      b.classList.toggle('active', isActive);
      const arrow = b.querySelector('.objects-sort-arrow');
      if (arrow) {
        arrow.textContent = currentSort.direction === 'asc' ? '↑' : '↓';
      }
    });

    applySort();
  }

  /**
   * Handle search input
   */
  function handleSearch(query) {
    searchQuery = query.trim();

    // Toggle clear button visibility
    if (elements.searchClear) {
      elements.searchClear.style.display = searchQuery ? 'block' : 'none';
    }

    applyFilters();
    updateActiveFiltersUI();
  }

  /**
   * Handle mobile filter toggle
   */
  function handleMobileToggle() {
    const isExpanded = elements.mobileToggle.getAttribute('aria-expanded') === 'true';
    elements.mobileToggle.setAttribute('aria-expanded', !isExpanded);
    elements.filtersContent.classList.toggle('show', !isExpanded);
  }

  /**
   * Apply all filters and search to the grid
   */
  function applyFilters() {
    let matchingIds = null;

    // Apply search first
    if (searchQuery && searchIndex) {
      try {
        // Strip leading Lunr query operators (+ - : ~ ^ *) so a query like
        // "C++" or "+foo" isn't mis-parsed; an empty remainder means no match.
        const safeQuery = searchQuery.replace(/^[+\-:~^*]+/, '');
        const results = safeQuery ? searchIndex.search(safeQuery + ' ' + safeQuery + '*') : [];
        matchingIds = new Set(results.map(r => r.ref));
      } catch (e) {
        // Still unparseable: an honest empty result set, not "show everything"
        matchingIds = new Set();
      }
    }

    let visibleCount = 0;

    elements.items.forEach(item => {
      const visible = matchesSearch(item.dataset.objectId, matchingIds)
        && matchesFilters(item.dataset, activeFilters);

      item.style.display = visible ? '' : 'none';
      if (visible) visibleCount++;
    });

    updateCount(visibleCount);
  }

  /**
   * Apply current sort to the grid
   */
  function applySort() {
    const itemsArray = Array.from(elements.items);

    // Extract a 3–4 digit year from a possibly-prose period string (e.g.
    // "c. 1650", "1650-1700", "siglo XVII"). Non-numeric periods sort last in
    // ascending order (Infinity) instead of collapsing to year 0.
    const extractYear = (val) => {
      const m = (val || '').match(/\d{3,4}/);
      return m ? parseInt(m[0], 10) : Infinity;
    };

    itemsArray.sort((a, b) => {
      let aVal, bVal;

      if (currentSort.field === 'title') {
        aVal = (a.dataset.title || '').toLowerCase();
        bVal = (b.dataset.title || '').toLowerCase();
      } else if (currentSort.field === 'year') {
        aVal = extractYear(a.dataset.year || a.dataset.period);
        bVal = extractYear(b.dataset.year || b.dataset.period);
      }

      let result;
      if (typeof aVal === 'string') {
        result = aVal.localeCompare(bVal);
      } else {
        result = aVal - bVal;
      }

      return currentSort.direction === 'asc' ? result : -result;
    });

    // Reorder DOM
    itemsArray.forEach(item => {
      elements.grid.appendChild(item);
    });
  }

  /**
   * Update the visible count display
   */
  function updateCount(count) {
    if (count === undefined) {
      count = Array.from(elements.items).filter(item => item.style.display !== 'none').length;
    }
    if (elements.visibleCount) {
      elements.visibleCount.textContent = count;
    }
  }

  /**
   * Update the active filters UI (chips)
   */
  function updateActiveFiltersUI() {
    const hasFilters = Object.values(activeFilters).some(arr => arr.length > 0) || searchQuery;

    // Build chips HTML
    let chipsHtml = '';

    // Search chip
    if (searchQuery) {
      chipsHtml += `<span class="objects-filter-chip" data-type="search">
        "${escapeHtml(searchQuery, doc)}"
        <button type="button" class="objects-filter-chip-remove" aria-label="Remove">&times;</button>
      </span>`;
    }

    // Filter chips
    for (const [filterType, values] of Object.entries(activeFilters)) {
      values.forEach(value => {
        chipsHtml += `<span class="objects-filter-chip" data-type="${filterType}" data-value="${escapeHtml(value, doc)}">
          ${escapeHtml(value, doc)}
          <button type="button" class="objects-filter-chip-remove" aria-label="Remove">&times;</button>
        </span>`;
      });
    }

    // Update both chip containers
    [elements.filterChips, elements.sidebarFilterChips].forEach(container => {
      if (container) {
        container.innerHTML = chipsHtml;
        // Bind remove handlers
        container.querySelectorAll('.objects-filter-chip-remove').forEach(btn => {
          btn.addEventListener('click', handleChipRemove);
        });
      }
    });

    // Show/hide containers
    [elements.activeFiltersContainer, elements.sidebarActiveFilters].forEach(container => {
      if (container) {
        container.style.display = hasFilters ? 'flex' : 'none';
      }
    });
  }

  /**
   * Handle chip remove click
   */
  function handleChipRemove(e) {
    const chip = e.target.closest('.objects-filter-chip');
    const type = chip.dataset.type;
    const value = chip.dataset.value;

    if (type === 'search') {
      searchQuery = '';
      if (elements.searchInput) {
        elements.searchInput.value = '';
      }
      if (elements.searchClear) {
        elements.searchClear.style.display = 'none';
      }
    } else {
      activeFilters[type] = activeFilters[type].filter(v => v !== value);
      // Uncheck the corresponding checkbox
      const checkbox = doc.querySelector(
        `.objects-filter-option input[data-filter="${type}"][value="${value}"]`
      );
      if (checkbox) {
        checkbox.checked = false;
      }
    }

    applyFilters();
    updateActiveFiltersUI();
  }

  /**
   * Clear all filters and search
   */
  function clearAllFilters() {
    // Reset state
    activeFilters = {
      media_type: [],
      medium: [],
      creator: [],
      period: [],
      subjects: []
    };
    searchQuery = '';

    // Reset UI
    if (elements.searchInput) {
      elements.searchInput.value = '';
    }
    if (elements.searchClear) {
      elements.searchClear.style.display = 'none';
    }

    // Uncheck all checkboxes
    doc.querySelectorAll('.objects-filter-option input[type="checkbox"]').forEach(cb => {
      cb.checked = false;
    });

    applyFilters();
    updateActiveFiltersUI();
  }

  return { init };
}

// Initialize on DOM ready
const objectsFilter = createObjectsFilter();
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => objectsFilter.init());
} else {
  objectsFilter.init();
}
