/**
 * SIP Discovery Engine - Evidence Drill-Down Viewer (Task 7.5)
 * Verbatim evidence items with highlighted evidence spans, source, and date metadata.
 */

let currentEvidenceItems = [];

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function openEvidenceModal(opportunityId, themeName, themeCategory) {
  const modalOverlay = document.getElementById("evidence-modal-overlay");
  const modalTitle = document.getElementById("modal-theme-title");
  const modalCategory = document.getElementById("modal-theme-category");
  const modalBody = document.getElementById("modal-evidence-list");
  const modalCount = document.getElementById("modal-count-info");
  const modalSearch = document.getElementById("modal-evidence-search");

  if (!modalOverlay || !modalBody) return;

  modalTitle.textContent = themeName || "Opportunity Evidence Drill-Down";
  modalCategory.textContent = themeCategory || "CATEGORY";
  modalBody.innerHTML = `
    <div class="evidence-empty">
      <div class="typing-indicator" style="justify-content: center; margin-bottom: 0.5rem;">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
      <p>Retrieving verbatim source records from database...</p>
    </div>
  `;
  modalCount.textContent = "Loading citations...";
  if (modalSearch) modalSearch.value = "";

  modalOverlay.classList.add("active");
  document.body.style.overflow = "hidden";

  try {
    const res = await fetch(`/api/v1/opportunities/${encodeURIComponent(opportunityId)}/evidence?limit=50`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    currentEvidenceItems = json.data || [];
    renderEvidenceItems(currentEvidenceItems);
  } catch (err) {
    console.error("Failed to load evidence:", err);
    modalBody.innerHTML = `
      <div class="evidence-empty">
        <p style="color: var(--color-danger);">Failed to load evidence items. Please check local database connection.</p>
      </div>
    `;
    modalCount.textContent = "0 items";
  }
}

function renderEvidenceItems(items) {
  const modalBody = document.getElementById("modal-evidence-list");
  const modalCount = document.getElementById("modal-count-info");
  if (!modalBody) return;

  if (!items || items.length === 0) {
    modalBody.innerHTML = `
      <div class="evidence-empty">
        <p>No matching verbatim evidence records found for this view.</p>
      </div>
    `;
    if (modalCount) modalCount.textContent = "0 records";
    return;
  }

  if (modalCount) modalCount.textContent = `Showing ${items.length} verbatim record${items.length === 1 ? '' : 's'}`;

  const html = items.map(item => {
    const isGroww = item.groww_specific;
    const stage = item.lifecycle_stage ? item.lifecycle_stage.replace(/_/g, " ") : "Unknown";
    const emotion = item.emotion ? item.emotion.toUpperCase() : "NEUTRAL";
    const outcome = item.outcome || "unknown";
    const source = item.source || "general";
    const recordId = item.record_id || "rec-id";
    const date = item.extracted_at ? item.extracted_at.substring(0, 10) : "";

    // Highlight evidence span
    const spanText = escapeHtml(item.evidence_span || "");
    const barrierText = escapeHtml(item.barrier || "N/A");
    const confusionText = escapeHtml(item.confusion || "N/A");

    let outcomeClass = "badge-directional";
    if (outcome === "continued") outcomeClass = "badge-sufficient";
    if (["stopped", "paused", "reduced"].includes(outcome)) outcomeClass = "badge-insufficient";

    return `
      <div class="evidence-item-card">
        <div class="evidence-meta-row">
          <span class="evidence-id-tag">[ID: ${recordId.substring(0, 8)}...]</span>
          <span class="badge ${isGroww ? 'badge-groww' : 'badge-agnostic'}">${isGroww ? 'Groww User' : 'Industry Agnostic'}</span>
          <span class="badge badge-source">${source}</span>
          ${outcome && outcome.toLowerCase() !== 'unknown' ? `<span class="badge ${outcomeClass}">Outcome: ${outcome}</span>` : ''}
          ${stage && stage.toLowerCase() !== 'unknown' ? `<span class="badge badge-directional">${stage}</span>` : ''}
          ${emotion && emotion.toLowerCase() !== 'neutral' && emotion.toLowerCase() !== 'unknown' ? `<span class="badge" style="background: rgba(255,255,255,0.06); color: #cbd5e1;">Emotion: ${emotion}</span>` : ''}
          ${date ? `<span style="margin-left: auto; color: var(--text-muted); font-size: 0.7rem;">${date}</span>` : ''}
        </div>

        <div class="evidence-quote-box">
          <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem;">Verbatim Evidence Quote:</div>
          <mark class="highlight-span">"${spanText}"</mark>
        </div>

        <div class="evidence-details-grid">
          <div class="detail-col">
            <span class="detail-label">Reported Barrier / Churn Trigger:</span>
            <span class="detail-val">${barrierText}</span>
          </div>
          <div class="detail-col">
            <span class="detail-label">Reported In-App Confusion:</span>
            <span class="detail-val">${confusionText}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");

  modalBody.innerHTML = html;
}

function filterModalEvidence(searchTerm) {
  if (!currentEvidenceItems) return;
  const term = searchTerm.toLowerCase().trim();
  if (!term) {
    renderEvidenceItems(currentEvidenceItems);
    return;
  }
  const filtered = currentEvidenceItems.filter(item => {
    return (
      (item.evidence_span && item.evidence_span.toLowerCase().includes(term)) ||
      (item.barrier && item.barrier.toLowerCase().includes(term)) ||
      (item.confusion && item.confusion.toLowerCase().includes(term)) ||
      (item.source && item.source.toLowerCase().includes(term)) ||
      (item.record_id && item.record_id.toLowerCase().includes(term))
    );
  });
  renderEvidenceItems(filtered);
}

function closeEvidenceModal() {
  const modalOverlay = document.getElementById("evidence-modal-overlay");
  if (modalOverlay) {
    modalOverlay.classList.remove("active");
    document.body.style.overflow = "";
  }
}

// Global modal triggers
document.addEventListener("DOMContentLoaded", () => {
  const modalOverlay = document.getElementById("evidence-modal-overlay");
  const modalCloseBtn = document.getElementById("modal-close-btn");
  const modalSearch = document.getElementById("modal-evidence-search");

  if (modalCloseBtn) {
    modalCloseBtn.addEventListener("click", closeEvidenceModal);
  }

  if (modalOverlay) {
    modalOverlay.addEventListener("click", (e) => {
      if (e.target === modalOverlay) closeEvidenceModal();
    });
  }

  if (modalSearch) {
    modalSearch.addEventListener("input", (e) => {
      filterModalEvidence(e.target.value);
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeEvidenceModal();
  });
});

