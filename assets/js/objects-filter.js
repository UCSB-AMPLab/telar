/* GENERATED FILE - do not edit. Bundled from assets/js/objects-filter/ by esbuild. Rebuild: npm run build:js (see assets/js/README.md). */
(() => {
  // assets/js/objects-filter/escape.js
  function escapeHtml(text, doc = document) {
    const div = doc.createElement("div");
    div.textContent = text;
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // assets/js/objects-filter/matching.js
  function datasetKeyFor(filterType) {
    return filterType.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
  }
  function matchesSearch(objectId, matchingIds) {
    return matchingIds === null || matchingIds.has(objectId);
  }
  function matchesFilters(dataset, activeFilters) {
    for (const [filterType, values] of Object.entries(activeFilters)) {
      if (values.length === 0) continue;
      const itemValue = dataset[datasetKeyFor(filterType)] || "";
      if (filterType === "subjects") {
        const itemSubjects = itemValue.split("|").map((s) => s.trim());
        if (!values.some((v) => itemSubjects.includes(v))) return false;
      } else if (!values.includes(itemValue)) {
        return false;
      }
    }
    return true;
  }

  // assets/js/objects-filter/search-index.js
  function getBaseUrl(doc = document, location = window.location) {
    const baseUrlMeta = doc.querySelector('meta[name="baseurl"]');
    if (baseUrlMeta) {
      return baseUrlMeta.getAttribute("content") || "";
    }
    console.warn('[Telar] meta[name="baseurl"] not found; deriving the base URL from the page path.');
    const path = location.pathname;
    const match = path.match(/^(\/[^\/]+)?\/objects\//);
    return match ? match[1] || "" : "";
  }
  function buildSearchIndex(searchData, lunr = globalThis.lunr) {
    if (typeof lunr === "undefined") {
      console.warn("Objects filter: Lunr.js not loaded");
      return null;
    }
    return lunr(function() {
      this.ref("id");
      this.field("title", { boost: 10 });
      this.field("creator", { boost: 5 });
      this.field("description", { boost: 2 });
      this.field("period");
      this.field("subjects");
      this.field("medium");
      searchData.objects.forEach((obj) => {
        this.add(obj);
      });
    });
  }

  // assets/js/objects-filter/main.js
  function createObjectsFilter({
    doc = document,
    fetchFn = (url) => globalThis.fetch(url),
    lunr = globalThis.lunr,
    location = window.location
  } = {}) {
    let searchData = null;
    let searchIndex = null;
    let activeFilters = {
      media_type: [],
      medium: [],
      creator: [],
      period: [],
      subjects: []
    };
    let searchQuery = "";
    let currentSort = { field: "title", direction: "asc" };
    let elements = {};
    async function init() {
      const objectsLayout = doc.querySelector(".objects-layout");
      if (!objectsLayout) {
        return;
      }
      cacheElements();
      try {
        const response = await fetchFn(getBaseUrl(doc, location) + "/search-data.json");
        if (!response.ok) {
          console.warn("Objects filter: search-data.json not found");
          return;
        }
        searchData = await response.json();
      } catch (error) {
        console.warn("Objects filter: Failed to load search data", error);
        return;
      }
      searchIndex = buildSearchIndex(searchData, lunr);
      populateFilters();
      bindEvents();
      updateCount();
      console.log("Objects filter initialized");
    }
    function cacheElements() {
      elements = {
        grid: doc.querySelector(".collection-grid"),
        items: doc.querySelectorAll(".collection-item"),
        visibleCount: doc.getElementById("objects-visible-count"),
        searchInput: doc.getElementById("objects-search-input"),
        searchClear: doc.getElementById("objects-search-clear"),
        filterSections: doc.querySelectorAll(".objects-filter-section"),
        sectionToggles: doc.querySelectorAll(".objects-filter-section-toggle"),
        activeFiltersContainer: doc.getElementById("objects-active-filters"),
        filterChips: doc.getElementById("objects-filter-chips"),
        clearAllBtn: doc.getElementById("objects-clear-all"),
        sidebarActiveFilters: doc.getElementById("objects-sidebar-active-filters"),
        sidebarFilterChips: doc.getElementById("objects-sidebar-filter-chips"),
        sidebarClearAll: doc.getElementById("objects-sidebar-clear-all"),
        sortButtons: doc.querySelectorAll(".objects-sort-btn"),
        mobileToggle: doc.getElementById("objects-filters-mobile-toggle"),
        filtersContent: doc.getElementById("objects-filters-content")
      };
    }
    function populateFilters() {
      if (!searchData || !searchData.facets) return;
      elements.filterSections.forEach((section) => {
        const filterType = section.dataset.filter;
        const facets = searchData.facets[filterType];
        const optionsContainer = section.querySelector(".objects-filter-options");
        if (!facets || !optionsContainer) return;
        optionsContainer.innerHTML = "";
        const entries = Object.entries(facets);
        if (entries.length === 0) {
          optionsContainer.innerHTML = '<span class="objects-filter-empty">No options available</span>';
          return;
        }
        entries.forEach(([value, count]) => {
          const option = doc.createElement("label");
          option.className = "objects-filter-option";
          option.innerHTML = `
          <input type="checkbox" value="${escapeHtml(value, doc)}" data-filter="${filterType}">
          <span class="objects-filter-option-label">${escapeHtml(value, doc)}</span>
          <span class="objects-filter-option-count">(${count})</span>
        `;
          optionsContainer.appendChild(option);
        });
      });
    }
    function bindEvents() {
      elements.sectionToggles.forEach((toggle) => {
        toggle.addEventListener("click", handleSectionToggle);
      });
      doc.querySelectorAll('.objects-filter-option input[type="checkbox"]').forEach((checkbox) => {
        checkbox.addEventListener("change", handleFilterChange);
      });
      if (elements.clearAllBtn) {
        elements.clearAllBtn.addEventListener("click", clearAllFilters);
      }
      if (elements.sidebarClearAll) {
        elements.sidebarClearAll.addEventListener("click", clearAllFilters);
      }
      elements.sortButtons.forEach((btn) => {
        btn.addEventListener("click", handleSortClick);
      });
      if (elements.searchInput) {
        let debounceTimer;
        elements.searchInput.addEventListener("input", (e) => {
          clearTimeout(debounceTimer);
          debounceTimer = setTimeout(() => {
            handleSearch(e.target.value);
          }, 250);
        });
      }
      if (elements.searchClear) {
        elements.searchClear.addEventListener("click", () => {
          elements.searchInput.value = "";
          handleSearch("");
        });
      }
      if (elements.mobileToggle) {
        elements.mobileToggle.addEventListener("click", handleMobileToggle);
      }
    }
    function handleSectionToggle(e) {
      const toggle = e.currentTarget;
      const section = toggle.closest(".objects-filter-section");
      const options = section.querySelector(".objects-filter-options");
      const indicator = toggle.querySelector(".objects-filter-indicator");
      const isExpanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", !isExpanded);
      options.classList.toggle("show", !isExpanded);
      indicator.textContent = isExpanded ? "+" : "\u2212";
    }
    function handleFilterChange(e) {
      const checkbox = e.target;
      const filterType = checkbox.dataset.filter;
      const value = checkbox.value;
      if (checkbox.checked) {
        if (!activeFilters[filterType].includes(value)) {
          activeFilters[filterType].push(value);
        }
      } else {
        activeFilters[filterType] = activeFilters[filterType].filter((v) => v !== value);
      }
      applyFilters();
      updateActiveFiltersUI();
    }
    function handleSortClick(e) {
      const btn = e.currentTarget;
      const sortField = btn.dataset.sort;
      if (currentSort.field === sortField) {
        currentSort.direction = currentSort.direction === "asc" ? "desc" : "asc";
      } else {
        currentSort.field = sortField;
        currentSort.direction = "asc";
      }
      elements.sortButtons.forEach((b) => {
        const isActive = b.dataset.sort === currentSort.field;
        b.classList.toggle("active", isActive);
        const arrow = b.querySelector(".objects-sort-arrow");
        if (arrow) {
          arrow.textContent = currentSort.direction === "asc" ? "\u2191" : "\u2193";
        }
      });
      applySort();
    }
    function handleSearch(query) {
      searchQuery = query.trim();
      if (elements.searchClear) {
        elements.searchClear.style.display = searchQuery ? "block" : "none";
      }
      applyFilters();
      updateActiveFiltersUI();
    }
    function handleMobileToggle() {
      const isExpanded = elements.mobileToggle.getAttribute("aria-expanded") === "true";
      elements.mobileToggle.setAttribute("aria-expanded", !isExpanded);
      elements.filtersContent.classList.toggle("show", !isExpanded);
    }
    function applyFilters() {
      let matchingIds = null;
      if (searchQuery && searchIndex) {
        try {
          const safeQuery = searchQuery.replace(/^[+\-:~^*]+/, "");
          const results = safeQuery ? searchIndex.search(safeQuery + " " + safeQuery + "*") : [];
          matchingIds = new Set(results.map((r) => r.ref));
        } catch (e) {
          matchingIds = /* @__PURE__ */ new Set();
        }
      }
      let visibleCount = 0;
      elements.items.forEach((item) => {
        const visible = matchesSearch(item.dataset.objectId, matchingIds) && matchesFilters(item.dataset, activeFilters);
        item.style.display = visible ? "" : "none";
        if (visible) visibleCount++;
      });
      updateCount(visibleCount);
    }
    function applySort() {
      const itemsArray = Array.from(elements.items);
      const extractYear = (val) => {
        const m = (val || "").match(/\d{3,4}/);
        return m ? parseInt(m[0], 10) : Infinity;
      };
      itemsArray.sort((a, b) => {
        let aVal, bVal;
        if (currentSort.field === "title") {
          aVal = (a.dataset.title || "").toLowerCase();
          bVal = (b.dataset.title || "").toLowerCase();
        } else if (currentSort.field === "year") {
          aVal = extractYear(a.dataset.year || a.dataset.period);
          bVal = extractYear(b.dataset.year || b.dataset.period);
        }
        let result;
        if (typeof aVal === "string") {
          result = aVal.localeCompare(bVal);
        } else {
          result = aVal - bVal;
        }
        return currentSort.direction === "asc" ? result : -result;
      });
      itemsArray.forEach((item) => {
        elements.grid.appendChild(item);
      });
    }
    function updateCount(count) {
      if (count === void 0) {
        count = Array.from(elements.items).filter((item) => item.style.display !== "none").length;
      }
      if (elements.visibleCount) {
        elements.visibleCount.textContent = count;
      }
    }
    function updateActiveFiltersUI() {
      const hasFilters = Object.values(activeFilters).some((arr) => arr.length > 0) || searchQuery;
      let chipsHtml = "";
      if (searchQuery) {
        chipsHtml += `<span class="objects-filter-chip" data-type="search">
        "${escapeHtml(searchQuery, doc)}"
        <button type="button" class="objects-filter-chip-remove" aria-label="Remove">&times;</button>
      </span>`;
      }
      for (const [filterType, values] of Object.entries(activeFilters)) {
        values.forEach((value) => {
          chipsHtml += `<span class="objects-filter-chip" data-type="${filterType}" data-value="${escapeHtml(value, doc)}">
          ${escapeHtml(value, doc)}
          <button type="button" class="objects-filter-chip-remove" aria-label="Remove">&times;</button>
        </span>`;
        });
      }
      [elements.filterChips, elements.sidebarFilterChips].forEach((container) => {
        if (container) {
          container.innerHTML = chipsHtml;
          container.querySelectorAll(".objects-filter-chip-remove").forEach((btn) => {
            btn.addEventListener("click", handleChipRemove);
          });
        }
      });
      [elements.activeFiltersContainer, elements.sidebarActiveFilters].forEach((container) => {
        if (container) {
          container.style.display = hasFilters ? "flex" : "none";
        }
      });
    }
    function handleChipRemove(e) {
      const chip = e.target.closest(".objects-filter-chip");
      const type = chip.dataset.type;
      const value = chip.dataset.value;
      if (type === "search") {
        searchQuery = "";
        if (elements.searchInput) {
          elements.searchInput.value = "";
        }
        if (elements.searchClear) {
          elements.searchClear.style.display = "none";
        }
      } else {
        activeFilters[type] = activeFilters[type].filter((v) => v !== value);
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
    function clearAllFilters() {
      activeFilters = {
        media_type: [],
        medium: [],
        creator: [],
        period: [],
        subjects: []
      };
      searchQuery = "";
      if (elements.searchInput) {
        elements.searchInput.value = "";
      }
      if (elements.searchClear) {
        elements.searchClear.style.display = "none";
      }
      doc.querySelectorAll('.objects-filter-option input[type="checkbox"]').forEach((cb) => {
        cb.checked = false;
      });
      applyFilters();
      updateActiveFiltersUI();
    }
    return { init };
  }
  var objectsFilter = createObjectsFilter();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => objectsFilter.init());
  } else {
    objectsFilter.init();
  }
})();
//# sourceMappingURL=objects-filter.js.map
