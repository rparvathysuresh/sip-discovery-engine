/**
 * SIP Discovery Engine - Persistent Data Scope Banner (Task 7.6)
 * Auto-loads corpus metrics, source distributions, dates, and bias warnings from /api/v1/metadata.
 */

async function loadDataScopeBanner() {
  const bannerContainer = document.getElementById("data-scope-banner");
  if (!bannerContainer) return;

  try {
    const res = await fetch("/api/v1/metadata");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const data = json.data;

    const filtered = (data.total_filtered_items || 0).toLocaleString();
    const raw = (data.total_raw_collected || 0).toLocaleString();
    const opps = data.total_opportunity_areas || 0;
    const growwPct = data.groww_percentage || 0;
    const agnosticPct = (100 - growwPct).toFixed(1);
    const dateRange = data.date_range ? `${data.date_range.start} to ${data.date_range.end}` : "2014-09 to 2026-11";
    const sources = data.sources || ["Play Store", "Reddit", "YouTube", "Forums", "Quora", "Twitter", "Curated Corpus"];

    bannerContainer.innerHTML = `
      <div class="banner-top">
        <div class="banner-headline">
          <div class="banner-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
            </svg>
          </div>
          <div class="banner-title-group">
            <h2>Persistent Data Scope & Grounding Context</h2>
            <p>Empirically derived from multi-channel investor discourse snapshot across Indian mutual fund investors</p>
          </div>
        </div>
        <div class="connection-status">
          <span class="status-dot"></span>
          <span>Live SQLite Engine Active</span>
        </div>
      </div>

      <div class="banner-stats">
        <div class="stat-pill">
          <span class="stat-label">Filtered Corpus</span>
          <span class="stat-value">${filtered} <span class="stat-sub">conversations</span></span>
        </div>
        <div class="stat-pill">
          <span class="stat-label">Raw Collected</span>
          <span class="stat-value">${raw} <span class="stat-sub">items</span></span>
        </div>
        <div class="stat-pill">
          <span class="stat-label">Opportunity Themes</span>
          <span class="stat-value">${opps} <span class="stat-sub">ranked areas</span></span>
        </div>
        <div class="stat-pill">
          <span class="stat-label">Observation Window</span>
          <span class="stat-value" style="font-size: 0.95rem;">${dateRange}</span>
        </div>
      </div>

      <div class="platform-split-container">
        <div class="split-labels">
          <span><strong>Groww-Specific:</strong> ${data.groww_specific_count || 0} (${growwPct}%)</span>
          <span><strong>Platform-Agnostic:</strong> ${data.platform_agnostic_count || 0} (${agnosticPct}%)</span>
        </div>
        <div class="split-bar-track">
          <div class="split-bar-groww" style="width: ${growwPct}%" title="Groww-Specific: ${growwPct}%"></div>
          <div class="split-bar-agnostic" style="width: ${agnosticPct}%" title="Platform-Agnostic: ${agnosticPct}%"></div>
        </div>
      </div>

      <div class="sources-row">
        <span>Active Sources:</span>
        ${sources.map(s => `<span class="badge badge-source">${s}</span>`).join(" ")}
      </div>

      <div class="bias-alert">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <div class="bias-content">
          <strong>Known Corpus Biases & Sampling Context:</strong>
          <ul class="bias-list">
            <li>Review-site complaint skew toward transactional mandate & technical failures</li>
            <li>Reddit demographic skew toward urban, male, and high financial literacy investors</li>
            <li>Survivorship bias: dropped investors frequently disengage silently without posting</li>
          </ul>
        </div>
      </div>
    `;
  } catch (err) {
    console.warn("Failed to load metadata banner:", err);
    bannerContainer.innerHTML = `
      <div class="banner-top">
        <div class="banner-title-group">
          <h2>SIP Investor Discovery Engine</h2>
          <p>Connecting to local analytics database...</p>
        </div>
      </div>
    `;
  }
}

