/**
 * SIP Discovery Engine - Opportunity Explorer (Task 7.4)
 * Ranked list of opportunity cards with multi-dimensional breakdowns and live filtering.
 */

let allOpportunities = [];

async function loadOpportunities() {
  const grid = document.getElementById("opportunities-grid");
  const countLabel = document.getElementById("results-count-label");
  const categorySelect = document.getElementById("explorer-category-filter");

  if (!grid) return;

  grid.innerHTML = `
    <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem;">
      <div class="typing-indicator" style="justify-content: center; margin-bottom: 0.5rem;">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
      <p style="color: var(--text-secondary);">Loading ranked opportunity themes from SQLite engine...</p>
    </div>
  `;

  try {
    const res = await fetch("/api/v1/opportunities?limit=50");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    allOpportunities = json.data || [];

    // Populate category dropdown
    if (categorySelect && allOpportunities.length > 0) {
      const categories = [...new Set(allOpportunities.map(o => o.theme_category).filter(Boolean))].sort();
      categorySelect.innerHTML = `<option value="">All Categories (${categories.length})</option>` +
        categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    }

    applyExplorerFilters();
  } catch (err) {
    console.error("Failed to load opportunities:", err);
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem; color: var(--color-danger);">
        <p>Failed to retrieve opportunity areas. Ensure the FastAPI server is running.</p>
      </div>
    `;
  }
}

function applyExplorerFilters() {
  const searchInput = document.getElementById("explorer-search-input");
  const categorySelect = document.getElementById("explorer-category-filter");
  const minScoreSlider = document.getElementById("explorer-score-slider");
  const sliderValLabel = document.getElementById("score-slider-val");

  const searchTerm = (searchInput ? searchInput.value : "").toLowerCase().trim();
  const selectedCategory = (categorySelect ? categorySelect.value : "").toLowerCase().trim();
  const minScore = minScoreSlider ? parseFloat(minScoreSlider.value) : 0;

  if (sliderValLabel && minScoreSlider) {
    sliderValLabel.textContent = `${Math.round(minScore)}%`;
  }

  const filtered = allOpportunities.filter(item => {
    // Search
    if (searchTerm) {
      const matchName = item.theme_name && item.theme_name.toLowerCase().includes(searchTerm);
      const matchCat = item.theme_category && item.theme_category.toLowerCase().includes(searchTerm);
      if (!matchName && !matchCat) return false;
    }

    // Category
    if (selectedCategory) {
      if (!item.theme_category || item.theme_category.toLowerCase() !== selectedCategory) {
        return false;
      }
    }

    // Score in percentage (minScore is 0..100, item.composite_score is 0..1)
    if (((item.composite_score || 0) * 100) < minScore) {
      return false;
    }

    return true;
  });

  renderOpportunityCards(filtered);
}

function renderOpportunityCards(items) {
  const grid = document.getElementById("opportunities-grid");
  const countLabel = document.getElementById("results-count-label");

  if (!grid) return;

  if (countLabel) {
    countLabel.textContent = `Showing ${items.length} of ${allOpportunities.length} opportunities`;
  }

  if (items.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
        <p>No opportunity areas match the selected filter criteria.</p>
        <button class="btn btn-secondary" style="margin-top: 0.75rem;" onclick="resetExplorerFilters()">Reset Filters</button>
      </div>
    `;
    return;
  }

  grid.innerHTML = items.map((item, idx) => {
    const rank = idx + 1;
    let rankClass = "";
    if (rank === 1) rankClass = "rank-1";
    else if (rank === 2) rankClass = "rank-2";
    else if (rank === 3) rankClass = "rank-3";

    // Show score in percentage
    const compScorePct = Math.round((item.composite_score || 0) * 100) + "%";
    let scoreColor = "#94a3b8";
    if (item.composite_score >= 0.6) scoreColor = "#f87171";
    else if (item.composite_score >= 0.4) scoreColor = "#fbbf24";
    else scoreColor = "#34d399";

    const freqShare = ((item.frequency_share || 0) * 100).toFixed(1);
    const sevScore = (item.severity_score || 0).toFixed(2);
    const brdScore = (item.breadth_score || 0).toFixed(2);

    // Lifecycle breakdown preview (filter out unknown tags)
    const lifecycleKeys = item.lifecycle_breakdown 
      ? Object.keys(item.lifecycle_breakdown)
          .filter(k => k && k.toLowerCase() !== "unknown")
          .slice(0, 3) 
      : [];
    const segmentKeys = item.segment_breakdown 
      ? Object.keys(item.segment_breakdown)
          .filter(s => s && s.toLowerCase() !== "unknown")
          .slice(0, 3) 
      : [];

    const oppIdSafe = escapeHtml(item.opportunity_id);
    const themeNameSafe = escapeHtml(item.theme_name);
    const categorySafe = escapeHtml(item.theme_category);

    return `
      <div class="opportunity-card">
        <div class="card-top-row">
          <span class="rank-badge ${rankClass}">Rank #${rank}</span>
          <div class="card-title-group">
            <div class="card-category">${categorySafe}</div>
            <h3 class="card-theme-name">${themeNameSafe}</h3>
          </div>
          <div class="composite-score-badge">
            <span class="score-num" style="color: ${scoreColor};">${compScorePct}</span>
            <span class="score-lbl">Score</span>
          </div>
        </div>

        <div class="metrics-breakdown">
          <div class="metric-col">
            <div class="metric-top">
              <span>Freq (${item.frequency_count})</span>
              <span>${freqShare}%</span>
            </div>
            <div class="metric-bar-bg">
              <div class="metric-bar-fill bar-freq" style="width: ${Math.min(100, (item.frequency_share || 0) * 200)}%;"></div>
            </div>
          </div>
          <div class="metric-col">
            <div class="metric-top">
              <span>Severity</span>
              <span>${sevScore}</span>
            </div>
            <div class="metric-bar-bg">
              <div class="metric-bar-fill bar-sev" style="width: ${(item.severity_score || 0) * 100}%;"></div>
            </div>
          </div>
          <div class="metric-col">
            <div class="metric-top">
              <span>Breadth</span>
              <span>${brdScore}</span>
            </div>
            <div class="metric-bar-bg">
              <div class="metric-bar-fill bar-brd" style="width: ${(item.breadth_score || 0) * 100}%;"></div>
            </div>
          </div>
        </div>

        <div class="card-tags-row">
          ${lifecycleKeys.map(k => `<span class="sub-tag">${escapeHtml(k.replace(/_/g, ' '))}</span>`).join(" ")}
          ${segmentKeys.map(s => `<span class="sub-tag" style="color: #67e8f9;">${escapeHtml(s)}</span>`).join(" ")}
        </div>

        <div class="card-footer">
          <span style="font-size: 0.72rem; color: var(--text-muted);">
            Evidence: ${item.frequency_count} items
          </span>
          <button class="evidence-drill-btn" onclick="openEvidenceModal('${oppIdSafe}', '${themeNameSafe}', '${categorySafe}')">
            Drill-Down Evidence
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function resetExplorerFilters() {
  const searchInput = document.getElementById("explorer-search-input");
  const categorySelect = document.getElementById("explorer-category-filter");
  const minScoreSlider = document.getElementById("explorer-score-slider");
  const sliderValLabel = document.getElementById("score-slider-val");

  if (searchInput) searchInput.value = "";
  if (categorySelect) categorySelect.value = "";
  if (minScoreSlider) minScoreSlider.value = "0";
  if (sliderValLabel) sliderValLabel.textContent = "0%";

  applyExplorerFilters();
}

// Setup Event Listeners
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("explorer-search-input");
  const categorySelect = document.getElementById("explorer-category-filter");
  const minScoreSlider = document.getElementById("explorer-score-slider");
  const resetBtn = document.getElementById("explorer-reset-btn");

  if (searchInput) searchInput.addEventListener("input", applyExplorerFilters);
  if (categorySelect) categorySelect.addEventListener("change", applyExplorerFilters);
  if (minScoreSlider) minScoreSlider.addEventListener("input", applyExplorerFilters);
  if (resetBtn) resetBtn.addEventListener("click", resetExplorerFilters);
});

