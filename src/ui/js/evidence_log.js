/**
 * SIP Discovery Engine - AI Evidence Log View
 * Pipeline audit trail tracking collection, preprocessing, extraction, and opportunity clustering.
 */

let allLogEntries = [];

async function loadEvidenceLog() {
  const container = document.getElementById("log-timeline");
  const countLabel = document.getElementById("log-count-label");
  if (!container) return;

  container.innerHTML = `
    <div style="text-align: center; padding: 3rem 1rem; color: var(--text-secondary);">
      <div class="typing-indicator" style="justify-content: center; margin-bottom: 0.5rem;">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
      <p>Loading AI Evidence Log audit trail from database...</p>
    </div>
  `;

  try {
    const apiUrl = typeof getApiUrl === "function" ? getApiUrl("/api/v1/evidence-log?limit=100") : "/api/v1/evidence-log?limit=100";
    const res = await fetch(apiUrl);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    allLogEntries = json.data || [];

    applyLogFilter();
  } catch (err) {
    console.error("Failed to load evidence log:", err);
    container.innerHTML = `
      <div style="text-align: center; padding: 3rem 1rem; color: var(--color-danger);">
        <p>Failed to retrieve evidence log entries.</p>
      </div>
    `;
  }
}

function applyLogFilter() {
  const activeBtn = document.querySelector(".pill-btn.active[data-stage]");
  const stage = activeBtn ? activeBtn.getAttribute("data-stage") : "all";
  const countLabel = document.getElementById("log-count-label");

  const filtered = allLogEntries.filter(entry => {
    if (stage === "all") return true;
    return entry.pipeline_stage && entry.pipeline_stage.toLowerCase() === stage.toLowerCase();
  });

  if (countLabel) {
    countLabel.textContent = `Showing ${filtered.length} log events`;
  }

  renderLogEntries(filtered);
}

function renderLogEntries(entries) {
  const container = document.getElementById("log-timeline");
  if (!container) return;

  if (entries.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
        <p>No audit trail events match this stage filter.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = entries.map(entry => {
    const stage = entry.pipeline_stage || "general";
    let stageClass = "stage-analysis";
    if (stage.includes("collect")) stageClass = "stage-collection";
    else if (stage.includes("prep")) stageClass = "stage-preprocessing";
    else if (stage.includes("extract")) stageClass = "stage-extraction";
    else if (stage.includes("synth")) stageClass = "stage-synthesis";
    else if (stage.includes("val")) stageClass = "stage-validation";

    const eventType = entry.event_type || "pipeline_event";
    const loggedAt = entry.logged_at ? entry.logged_at.replace("T", " ").substring(0, 19) : "";
    const detailsJson = JSON.stringify(entry.details || {}, null, 2);

    return `
      <div class="log-entry-card">
        <div class="log-entry-header">
          <div style="display: flex; align-items: center; gap: 0.6rem;">
            <span class="log-stage-tag ${stageClass}">${escapeHtml(stage)}</span>
            <span class="log-event-type">${escapeHtml(eventType.replace(/_/g, " "))}</span>
          </div>
          <span class="log-timestamp">${escapeHtml(loggedAt)}</span>
        </div>
        <pre class="log-details-pre"><code>${escapeHtml(detailsJson)}</code></pre>
      </div>
    `;
  }).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  const stageBtns = document.querySelectorAll(".pill-btn[data-stage]");
  stageBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      stageBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      applyLogFilter();
    });
  });
});

