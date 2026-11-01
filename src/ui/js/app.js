/**
 * SIP Discovery Engine - Main Application Coordinator & View Router
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Load Data Scope Banner
  loadDataScopeBanner();

  // 2. Navigation Tab Switching
  const navTabs = document.querySelectorAll(".nav-tabs .tab-btn");
  const tabPanels = document.querySelectorAll(".tab-content");

  let opportunitiesLoaded = false;
  let evidenceLogLoaded = false;

  function switchTab(tabId) {
    navTabs.forEach(btn => {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
    });

    tabPanels.forEach(panel => {
      panel.classList.toggle("active", panel.id === `tab-${tabId}`);
    });

    // Lazy load tab data
    if (tabId === "explorer" && !opportunitiesLoaded) {
      loadOpportunities();
      opportunitiesLoaded = true;
    } else if (tabId === "log" && !evidenceLogLoaded) {
      loadEvidenceLog();
      evidenceLogLoaded = true;
    }
  }

  navTabs.forEach(btn => {
    btn.addEventListener("click", () => {
      const tabId = btn.getAttribute("data-tab");
      if (tabId) switchTab(tabId);
    });
  });

  // Also pre-load opportunities in background so they are ready when clicked
  setTimeout(() => {
    if (!opportunitiesLoaded) {
      loadOpportunities();
      opportunitiesLoaded = true;
    }
  }, 1000);
});

