/**
 * Objects Gallery Filter and Search
 *
 * This module powers the browse-and-search interface on the objects index
 * page. It loads `search-data.json` (generated at build time by Python) which
 * contains object metadata and pre-computed facet counts for the filter
 * sidebar. The facets — Type, Creator, Period, Subjects — are populated
 * dynamically with counts like "Early maps (3)" so users know what's available
 * before clicking.
 *
 * Filtering works by reading data attributes on each `.collection-item` card
 * (e.g., `data-creator`, `data-period`) and showing/hiding cards based on
 * active filter selections. Multiple filters within a category use OR logic
 * (show if matches any), while filters across categories use AND logic (must
 * match all). Active filters appear as removable chips above the grid.
 *
 * Search uses Lunr.js for fuzzy full-text matching across title, creator,
 * description, and other fields. The search index is built client-side from
 * the loaded JSON — this keeps the Python build simple and works well for
 * typical collection sizes (under 500 objects). Search input is debounced
 * at 250ms to avoid excessive filtering during typing.
 *
 * Sorting supports Title (A-Z/Z-A) and Year (ascending/descending). Clicking
 * the active sort button toggles direction; clicking an inactive button
 * switches to that field in ascending order. DOM reordering uses appendChild
 * which maintains event listeners on the cards.
 *
 * @version v0.8.0-beta
 */

(function() {
  'use strict';

  // State
  let searchData = null;
  let searchIndex = null;
  let activeFilters = {
    object_type: [],
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
    const objectsLayout = document.querySelector('.objects-layout');
    if (!objectsLayout) {
      return; // Not on objects page or browse_and_search disabled
    }

    // Cache DOM elements
    cacheElements();

    // Load search data
    try {
      const response = await fetch(getBaseUrl() + '/search-data.json');
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
    initSearchIndex();

    // Populate filter sections with facet data
    populateFilters();

    // Bind event listeners
    bindEvents();

    // Initial state
    updateCount();

    console.log('Objects filter initialized');
  }

  /**
   * Get the base URL for the site
   */
  function getBaseUrl() {
    // Get baseurl from the page (set by Jekyll)
    const baseUrlMeta = document.querySelector('meta[name="baseurl"]');
    if (baseUrlMeta) {
      return baseUrlMeta.getAttribute('content') || '';
    }
    // Fallback: try to detect from current URL
    const path = window.location.pathname;
    const match = path.match(/^(\/[^\/]+)?\/objects\//);
    return match ? (match[1] || '') : '';
  }

  /**
   * Cache commonly used DOM elements
   */
  function cacheElements() {
    elements = {
      grid: document.querySelector('.collection-grid'),
      items: document.querySelectorAll('.collection-item'),
      visibleCount: document.getElementById('objects-visible-count'),
      searchInput: document.getElementById('objects-search-input'),
      searchClear: document.getElementById('objects-search-clear'),
      filterSections: document.querySelectorAll('.objects-filter-section'),
      sectionToggles: document.querySelectorAll('.objects-filter-section-toggle'),
      activeFiltersContainer: document.getElementById('objects-active-filters'),
      filterChips: document.getElementById('objects-filter-chips'),
      clearAllBtn: document.getElementById('objects-clear-all'),
      sidebarActiveFilters: document.getElementById('objects-sidebar-active-filters'),
      sidebarFilterChips: document.getElementById('objects-sidebar-filter-chips'),
      sidebarClearAll: document.getElementById('objects-sidebar-clear-all'),
      sortButtons: document.querySelectorAll('.objects-sort-btn'),
      mobileToggle: document.getElementById('objects-filters-mobile-toggle'),
      filtersContent: document.getElementById('objects-filters-content')
    };
  }

  /**
   * Initialize Lunr.js search index
   */
  function initSearchIndex() {
    if (typeof lunr === 'undefined') {
      console.warn('Objects filter: Lunr.js not loaded');
      return;
    }

    searchIndex = lunr(function() {
      this.ref('id');
      this.field('title', { boost: 10 });
      this.field('creator', { boost: 5 });
      this.field('description', { boost: 2 });
      this.field('period');
      this.field('subjects');
      this.field('object_type');

      searchData.objects.forEach(obj => {
        this.add(obj);
      });
    });
  }

  /**
   * Populate filter sections with facet data
   */
  function populateFilters() {
    if (!searchData || !searchData.facets) return;

    const facetMap = {
      'object_type': 'object_type',
      'creator': 'creator',
      'period': 'period',
      'subjects': 'subjects'
    };

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
        const option = document.createElement('label');
        option.className = 'objects-filter-option';
        option.innerHTML = `
          <input type="checkbox" value="${escapeHtml(value)}" data-filter="${filterType}">
          <span class="objects-filter-option-label">${escapeHtml(value)}</span>
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
    document.querySelectorAll('.objects-filter-option input[type="checkbox"]').forEach(checkbox => {
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
        const results = searchIndex.search(searchQuery + '*');
        matchingIds = new Set(results.map(r => r.ref));
      } catch (e) {
        // Invalid search query, show all
        matchingIds = null;
      }
    }

    let visibleCount = 0;

    elements.items.forEach(item => {
      const objectId = item.dataset.objectId;
      let visible = true;

      // Check search match
      if (matchingIds !== null && !matchingIds.has(objectId)) {
        visible = false;
      }

      // Check filters
      if (visible) {
        for (const [filterType, values] of Object.entries(activeFilters)) {
          if (values.length === 0) continue;

          // Convert snake_case to camelCase for dataset access
          // e.g., 'object_type' → 'objectType' (data-object-type → dataset.objectType)
          const datasetKey = filterType.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
          const itemValue = item.dataset[datasetKey] || '';

          // For subjects, check if any match (pipe-separated)
          if (filterType === 'subjects') {
            const itemSubjects = itemValue.split('|').map(s => s.trim());
            const hasMatch = values.some(v => itemSubjects.includes(v));
            if (!hasMatch) {
              visible = false;
              break;
            }
          } else {
            // For other fields, check exact match
            if (!values.includes(itemValue)) {
              visible = false;
              break;
            }
          }
        }
      }

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

    itemsArray.sort((a, b) => {
      let aVal, bVal;

      if (currentSort.field === 'title') {
        aVal = (a.dataset.title || '').toLowerCase();
        bVal = (b.dataset.title || '').toLowerCase();
      } else if (currentSort.field === 'year') {
        aVal = parseInt(a.dataset.year || a.dataset.period || '0', 10) || 0;
        bVal = parseInt(b.dataset.year || b.dataset.period || '0', 10) || 0;
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
        "${escapeHtml(searchQuery)}"
        <button type="button" class="objects-filter-chip-remove" aria-label="Remove">&times;</button>
      </span>`;
    }

    // Filter chips
    for (const [filterType, values] of Object.entries(activeFilters)) {
      values.forEach(value => {
        chipsHtml += `<span class="objects-filter-chip" data-type="${filterType}" data-value="${escapeHtml(value)}">
          ${escapeHtml(value)}
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
      const checkbox = document.querySelector(
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
      object_type: [],
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
    document.querySelectorAll('.objects-filter-option input[type="checkbox"]').forEach(cb => {
      cb.checked = false;
    });

    applyFilters();
    updateActiveFiltersUI();
  }

  /**
   * Escape HTML special characters
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
