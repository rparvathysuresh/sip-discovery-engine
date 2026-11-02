/**
 * SIP Discovery Engine - Chat View (Task 7.3)
 * Evidence-grounded conversational interface with guardrail notices, citations, and markdown rendering.
 */

function simpleMarkdownToHtml(md) {
  if (!md) return "";

  let html = md;

  // Escape HTML tags to prevent XSS
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks: ```...```
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code>${code.trim()}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Headings
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "2<h3>$1</h3>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  // Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Blockquotes
  html = html.replace(/^\> (.*$)/gim, "<blockquote>$1</blockquote>");

  // Tables
  const lines = html.split("\n");
  let inTable = false;
  let tableHtml = "";
  const outputLines = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("|") && line.endsWith("|")) {
      if (!inTable) {
        inTable = true;
        tableHtml = "<table><tbody>";
      }
      if (line.includes("---")) {
        // separator row, skip
        continue;
      }
      const cells = line.split("|").slice(1, -1);
      const isHeader = !tableHtml.includes("<tr>");
      const tag = isHeader ? "th" : "td";
      tableHtml += "<tr>" + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join("") + "</tr>";
    } else {
      if (inTable) {
        tableHtml += "</tbody></table>";
        outputLines.push(tableHtml);
        inTable = false;
        tableHtml = "";
      }
      outputLines.push(lines[i]);
    }
  }
  if (inTable) {
    tableHtml += "</tbody></table>";
    outputLines.push(tableHtml);
  }

  html = outputLines.join("\n");

  // Lists (unordered)
  html = html.replace(/^\s*-\s+(.*$)/gim, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/gms, "<ul>$1</ul>");

  // Paragraphs
  html = html.split("\n\n").map(para => {
    para = para.trim();
    if (!para) return "";
    if (para.startsWith("<h") || para.startsWith("<pre") || para.startsWith("<ul") || para.startsWith("<table") || para.startsWith("<block")) {
      return para;
    }
    return `<p>${para.replace(/\n/g, "<br/>")}</p>`;
  }).join("\n");

  return html;
}

async function sendChatMessage(queryText) {
  const messagesContainer = document.getElementById("chat-messages");
  const inputField = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const welcomeScreen = document.getElementById("chat-welcome");

  const query = (queryText || (inputField ? inputField.value : "")).trim();
  if (!query) return;

  if (welcomeScreen) welcomeScreen.style.display = "none";
  if (inputField) inputField.value = "";
  if (sendBtn) sendBtn.disabled = true;

  // 1. Append User Message
  appendUserMessage(query);

  // 2. Append Typing Skeleton
  const skeletonId = "loading-skeleton-" + Date.now();
  appendSkeletonMessage(skeletonId);
  scrollToChatBottom();

  const startTime = performance.now();

  try {
    const apiUrl = typeof getApiUrl === "function" ? getApiUrl("/api/v1/chat") : "/api/v1/chat";
    const res = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query }),
    });

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

    // Remove skeleton
    const skeletonElem = document.getElementById(skeletonId);
    if (skeletonElem) skeletonElem.remove();

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      appendErrorMessage(errJson.detail || `Server error (${res.status}).`);
      return;
    }

    const data = await res.json();
    appendAssistantMessage(data, elapsed);

  } catch (err) {
    console.error("Chat query error:", err);
    const skeletonElem = document.getElementById(skeletonId);
    if (skeletonElem) skeletonElem.remove();
    appendErrorMessage("Network error: Could not reach chat query endpoint.");
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    if (inputField) inputField.focus();
    scrollToChatBottom();
  }
}

function appendUserMessage(text) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const div = document.createElement("div");
  div.className = "message-row user-message";
  div.innerHTML = `
    <div class="message-avatar user-avatar">U</div>
    <div class="message-bubble">
      ${escapeHtml(text)}
    </div>
  `;
  container.appendChild(div);
}

function appendSkeletonMessage(id) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const div = document.createElement("div");
  div.id = id;
  div.className = "message-row assistant-message";
  div.innerHTML = `
    <div class="message-avatar assistant-avatar">AI</div>
    <div class="message-bubble" style="background: rgba(15, 23, 42, 0.65);">
      <div class="typing-indicator">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.5rem;">Synthesizing evidence across 1,742 records...</span>
      </div>
    </div>
  `;
  container.appendChild(div);
}

function appendAssistantMessage(data, clientElapsed) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const isRefusal = data.intent === "refusal";
  const intentName = (data.intent || "exploration_query").replace(/_/g, " ");
  const level = data.evidence_level || (isRefusal ? "refusal" : "sufficient");
  const matching = data.total_matching !== undefined ? data.total_matching : 0;
  const latency = data.latency_seconds ? data.latency_seconds.toFixed(2) : clientElapsed;
  const citations = data.citations || [];

  let levelBadge = "badge-sufficient";
  if (level === "directional") levelBadge = "badge-directional";
  if (level === "insufficient" || level === "refusal") levelBadge = "badge-insufficient";

  const renderedAnswer = simpleMarkdownToHtml(data.answer);

  const div = document.createElement("div");
  div.className = "message-row assistant-message";

  let citationsHtml = "";
  if (citations.length > 0) {
    citationsHtml = `
      <div class="citations-section">
        <div class="citations-header">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          Grounding Citations (${citations.length})
        </div>
        <div class="citation-cards-list">
          ${citations.map(c => {
            const rawId = escapeHtml(c.raw_id || c.record_id || "item");
            const src = escapeHtml(c.source || "record");
            const shortSpan = escapeHtml((c.evidence_span || "").substring(0, 40));
            return `
              <span class="citation-pill" title="${shortSpan}...">
                [${src}: ${rawId.substring(0, 6)}]
              </span>
            `;
          }).join("")}
        </div>
      </div>
    `;
  }

  let refusalBannerHtml = "";
  if (isRefusal) {
    refusalBannerHtml = `
      <div class="refusal-card" style="margin-bottom: 0.75rem;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <div>
          <strong style="display: block; font-size: 0.82rem; margin-bottom: 0.15rem;">Guardrail Policy Triggered</strong>
          <span style="font-size: 0.76rem;">The discovery engine does not provide investment advice, fund recommendations, or competitor comparisons. Only behavioral research signals are analyzed.</span>
        </div>
      </div>
    `;
  }

  div.innerHTML = `
    <div class="message-avatar assistant-avatar">AI</div>
    <div class="message-bubble">
      <div class="assistant-meta-bar">
        <span class="intent-pill">${intentName}</span>
        ${matching > 0 ? `<span class="matching-count-pill">Matching: ${matching} records</span>` : ''}
        <span class="latency-pill">⚡ ${latency}s</span>
      </div>

      ${refusalBannerHtml}

      <div class="markdown-body">
        ${renderedAnswer}
      </div>

      ${citationsHtml}
    </div>
  `;

  container.appendChild(div);
}

function appendErrorMessage(errText) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const div = document.createElement("div");
  div.className = "message-row assistant-message";
  div.innerHTML = `
    <div class="message-avatar assistant-avatar" style="background: var(--color-danger);">!</div>
    <div class="message-bubble" style="border-color: var(--color-danger-border);">
      <p style="color: var(--color-danger); font-size: 0.85rem;">${escapeHtml(errText)}</p>
    </div>
  `;
  container.appendChild(div);
}

function scrollToChatBottom() {
  const container = document.getElementById("chat-messages");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

// Prompt suggestions setup
document.addEventListener("DOMContentLoaded", () => {
  const inputField = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const chips = document.querySelectorAll(".suggestion-chip");

  if (sendBtn) {
    sendBtn.addEventListener("click", () => sendChatMessage());
  }

  if (inputField) {
    inputField.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      if (prompt) {
        sendChatMessage(prompt);
      }
    });
  });
});

