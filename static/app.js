"use strict";

/* ============================================================
   Procura — Premium Chat Application JavaScript
   Modern, interactive, responsive chatbot with smooth UX
   ============================================================ */

// ─── DOM Elements ───
const app = document.getElementById("app");
const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const welcomeScreen = document.getElementById("welcome-screen");

// Login / Identity Screen
const loginOverlay = document.getElementById("login-overlay");
const loginForm = document.getElementById("login-form");
const loginInput = document.getElementById("login-userid");
const loginBtn = document.getElementById("login-btn");
const loginError = document.getElementById("login-error");

// User Profile Card
const userProfileCard = document.getElementById("user-profile-card");
const userAvatar = document.getElementById("user-avatar");
const userName = document.getElementById("user-name");
const userRole = document.getElementById("user-role");

// Sidebar
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const newChatBtn = document.getElementById("new-chat-btn");
const mobileSidebarBtn = document.getElementById("mobile-sidebar-btn");
const mobileNewChatBtn = document.getElementById("mobile-new-chat-btn");

// Dashboard
const dashboardBtn = document.getElementById("dashboard-btn");
const dashboardCloseBtn = document.getElementById("dashboard-close-btn");
const dashboardPanel = document.getElementById("dashboard-panel");
const dashboardBody = document.getElementById("dashboard-body");

// Suggestion chips
const chipContainer = document.getElementById("suggestion-chips");

// ─── Chart palette ───
const CHART_COLORS = [
  "#3ecf8e", "#4aa3df", "#f0826a", "#b98ee6",
  "#e6c84a", "#5fd0c4", "#e67ea0", "#7a9be6",
  "#ff8c42", "#6fcf97", "#a78bfa", "#f472b6",
];

// ─── State ───
let isWelcomeVisible = true;

// ─── Helpers ──────────────────────────────────────────────────

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function renderText(text) {
  return escapeHtml(text).replace(/\n/g, "<br>");
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: "smooth" });
  });
}

function hideWelcomeScreen() {
  if (!isWelcomeVisible) return;
  isWelcomeVisible = false;
  if (welcomeScreen) {
    welcomeScreen.style.transition = "opacity 0.3s ease, transform 0.3s ease";
    welcomeScreen.style.opacity = "0";
    welcomeScreen.style.transform = "translateY(-10px)";
    setTimeout(() => welcomeScreen.remove(), 300);
  }
}

// ─── Sidebar ──────────────────────────────────────────────────

function openSidebar() {
  sidebar.classList.add("open");
  sidebarOverlay.classList.add("visible");
  document.body.style.overflow = "hidden";
}

function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarOverlay.classList.remove("visible");
  document.body.style.overflow = "";
}

if (sidebarToggle) sidebarToggle.addEventListener("click", () => {
  if (sidebar.classList.contains("open")) closeSidebar();
  else openSidebar();
});
if (mobileSidebarBtn) mobileSidebarBtn.addEventListener("click", openSidebar);
if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);

// ─── Message rendering ───────────────────────────────────────

function addMessage(role, htmlContent, opts = {}) {
  hideWelcomeScreen();

  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;

  // Avatar
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  if (role === "assistant") {
    avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>`;
  } else {
    avatar.textContent = "You";
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble" + (opts.error ? " error" : "");
  bubble.innerHTML = htmlContent;

  if (role === "assistant") {
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
  } else {
    wrap.appendChild(bubble);
    wrap.appendChild(avatar);
  }

  messagesEl.appendChild(wrap);
  scrollToBottom();
  return bubble;
}

function showTyping() {
  hideWelcomeScreen();

  const wrap = document.createElement("div");
  wrap.className = "message assistant";
  wrap.dataset.typing = "1";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
  </svg>`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<span class="typing-bubble"><span></span><span></span><span></span></span>';

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

// ─── Data rendering ───────────────────────────────────────────

function buildTable(table) {
  if (!table || !table.columns || !table.columns.length) return "";
  const head = table.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const body = table.rows
    .map(
      (row) =>
        "<tr>" +
        table.columns
          .map((c) => `<td>${escapeHtml(row[c])}</td>`)
          .join("") +
        "</tr>"
    )
    .join("");
  return `
    <details class="data">
      <summary>View data (${table.rows.length} row${table.rows.length === 1 ? "" : "s"})</summary>
      <div class="table-scroll"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
    </details>`;
}

function renderChart(canvas, chart) {
  const isPie = chart.type === "pie" || chart.type === "doughnut";
  const datasets = chart.datasets.map((ds, i) => {
    if (isPie) {
      return {
        label: ds.label,
        data: ds.data,
        backgroundColor: chart.labels.map(
          (_, idx) => CHART_COLORS[idx % CHART_COLORS.length]
        ),
        borderColor: "#131a23",
        borderWidth: 2,
      };
    }
    const color = CHART_COLORS[i % CHART_COLORS.length];
    return {
      label: ds.label,
      data: ds.data,
      backgroundColor: chart.type === "line" ? "transparent" : color + "cc",
      borderColor: color,
      borderWidth: 2.5,
      tension: 0.35,
      pointRadius: 4,
      pointBackgroundColor: color,
      pointBorderColor: "#131a23",
      pointBorderWidth: 2,
      pointHoverRadius: 6,
      fill: chart.type === "line",
    };
  });

  const showLegend = isPie || chart.datasets.length > 1;

  new Chart(canvas.getContext("2d"), {
    type: chart.type,
    data: { labels: chart.labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 800,
        easing: "easeOutQuart",
      },
      plugins: {
        legend: {
          display: showLegend,
          position: isPie ? "bottom" : "top",
          labels: {
            color: "#8b99a8",
            boxWidth: 12,
            boxHeight: 12,
            borderRadius: 3,
            useBorderRadius: true,
            padding: 14,
            font: { family: "'Inter', sans-serif", size: 12 },
          },
        },
        tooltip: {
          backgroundColor: "rgba(19, 26, 35, 0.95)",
          titleColor: "#e8edf2",
          bodyColor: "#8b99a8",
          borderColor: "rgba(255,255,255,0.08)",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          titleFont: { family: "'Inter', sans-serif", weight: "600" },
          bodyFont: { family: "'Inter', sans-serif" },
        },
      },
      scales: isPie
        ? {}
        : {
            x: {
              ticks: { color: "#5c6b7a", font: { size: 11 } },
              grid: { color: "rgba(255,255,255,0.04)", drawBorder: false },
            },
            y: {
              ticks: { color: "#5c6b7a", font: { size: 11 } },
              grid: { color: "rgba(255,255,255,0.04)", drawBorder: false },
            },
          },
    },
  });
}

function buildChartCard(chart) {
  const chartWrap = document.createElement("div");
  chartWrap.className = "chart-wrap";
  if (chart.title) {
    const t = document.createElement("p");
    t.className = "chart-title";
    t.textContent = chart.title;
    chartWrap.appendChild(t);
  }
  const box = document.createElement("div");
  box.className = "chart-canvas-box";
  const canvas = document.createElement("canvas");
  box.appendChild(canvas);
  chartWrap.appendChild(box);
  try {
    renderChart(canvas, chart);
  } catch (err) {
    console.error("Chart render failed:", err);
    return null;
  }
  return chartWrap;
}

function renderAssistantData(data) {
  const bubble = addMessage("assistant", `<p>${renderText(data.reply)}</p>`);

  if (data.chart) {
    const card = buildChartCard(data.chart);
    if (card) bubble.appendChild(card);
  }

  if (data.table && data.table.rows && data.table.rows.length) {
    bubble.insertAdjacentHTML("beforeend", buildTable(data.table));
  }

  if (data.truncated) {
    bubble.insertAdjacentHTML(
      "beforeend",
      `<p class="muted">Showing the first ${data.table.rows.length} of more rows.</p>`
    );
  }

  if (data.sql) {
    bubble.insertAdjacentHTML(
      "beforeend",
      `<details class="sql"><summary>View SQL</summary><pre class="sql">${escapeHtml(
        data.sql
      )}</pre></details>`
    );
  }
  scrollToBottom();
}

function renderAssistantDashboard(data) {
  const bubble = addMessage("assistant", `<p>${renderText(data.reply)}</p>`);
  const sections = data.sections || [];
  sections.forEach((section) => {
    const heading = document.createElement("p");
    heading.className = "chart-title";
    heading.textContent = `${section.table} — ${section.total_records.toLocaleString()} records`;
    bubble.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "chart-grid";
    (section.charts || []).forEach((chart) => {
      const card = buildChartCard(chart);
      if (card) grid.appendChild(card);
    });
    bubble.appendChild(grid);
  });
  scrollToBottom();
}

// ─── Dashboard panel ──────────────────────────────────────────

function renderDashboardPanel(sections) {
  dashboardBody.innerHTML = "";
  if (!sections.length) {
    dashboardBody.innerHTML = '<p class="muted">No data available to summarise yet.</p>';
    return;
  }
  sections.forEach((section) => {
    const card = document.createElement("div");
    card.className = "dashboard-section";

    const heading = document.createElement("h3");
    heading.textContent = `${section.table} — ${section.total_records.toLocaleString()} records`;
    card.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "chart-grid";
    (section.charts || []).forEach((chart) => {
      const chartCard = buildChartCard(chart);
      if (chartCard) grid.appendChild(chartCard);
    });
    card.appendChild(grid);
    dashboardBody.appendChild(card);
  });
}

async function openDashboard() {
  dashboardPanel.classList.remove("hidden");
  dashboardPanel.setAttribute("aria-hidden", "false");
  dashboardBody.innerHTML = '<p class="muted">Loading overview…</p>';
  closeSidebar();
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    if (data.error) {
      dashboardBody.innerHTML = `<p class="muted">${escapeHtml(data.error)}</p>`;
      return;
    }
    renderDashboardPanel(data.sections || []);
  } catch (err) {
    console.error(err);
    dashboardBody.innerHTML = '<p class="muted">Could not load the dashboard right now.</p>';
  }
}

function closeDashboard() {
  dashboardPanel.classList.add("hidden");
  dashboardPanel.setAttribute("aria-hidden", "true");
}

dashboardBtn.addEventListener("click", openDashboard);
dashboardCloseBtn.addEventListener("click", closeDashboard);

// Close dashboard on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!dashboardPanel.classList.contains("hidden")) {
      closeDashboard();
    } else if (sidebar.classList.contains("open")) {
      closeSidebar();
    }
  }
});

// ─── Suggestion chips ─────────────────────────────────────────

if (chipContainer) {
  chipContainer.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const prompt = chip.dataset.prompt;
    if (!prompt) return;
    inputEl.value = prompt;
    autoGrow();
    sendMessage(prompt);
    inputEl.value = "";
    autoGrow();
  });
}

// ─── Network ──────────────────────────────────────────────────

async function sendMessage(message) {
  addMessage("user", `<p>${renderText(message)}</p>`);
  const typingEl = showTyping();
  sendBtn.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    typingEl.remove();

    if (data.type === "data") {
      renderAssistantData(data);
    } else if (data.type === "dashboard") {
      renderAssistantDashboard(data);
    } else if (data.type === "error") {
      addMessage("assistant", `<p>${renderText(data.reply)}</p>`, { error: true });
    } else {
      addMessage("assistant", `<p>${renderText(data.reply || data.error)}</p>`);
    }
  } catch (err) {
    typingEl.remove();
    addMessage(
      "assistant",
      "<p>Network error — I couldn't reach the server. Please try again.</p>",
      { error: true }
    );
    console.error(err);
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// ─── Input events ─────────────────────────────────────────────

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

inputEl.addEventListener("input", autoGrow);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  inputEl.value = "";
  autoGrow();
  sendMessage(message);
});

// ─── New chat / Reset ─────────────────────────────────────────

async function resetChat() {
  try {
    await fetch("/api/reset", { method: "POST" });
  } catch (err) {
    console.error(err);
  }

  // Clear all messages
  messagesEl.innerHTML = "";

  // Rebuild welcome screen
  isWelcomeVisible = true;
  const ws = document.createElement("div");
  ws.className = "welcome-screen";
  ws.id = "welcome-screen";
  ws.innerHTML = `
    <div class="welcome-icon">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="url(#welcome-grad2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <defs>
          <linearGradient id="welcome-grad2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#3ecf8e"/>
            <stop offset="100%" stop-color="#2aa9c9"/>
          </linearGradient>
        </defs>
        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
        <path d="M2 17l10 5 10-5"/>
        <path d="M2 12l10 5 10-5"/>
      </svg>
    </div>
    <h1 class="welcome-title">How can I help you today?</h1>
    <p class="welcome-subtitle">I'm Procura, your procurement analytics assistant. Ask me anything about your data.</p>
    <div class="suggestion-chips" id="suggestion-chips">
      <button class="chip" data-prompt="Top 10 vendors by total PO value" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
        Top 10 vendors by spend
      </button>
      <button class="chip" data-prompt="Show me PO status distribution" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
        PO status breakdown
      </button>
      <button class="chip" data-prompt="Give me an overview of all materials" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>
        Materials overview
      </button>
      <button class="chip" data-prompt="How many inspections happened this month?" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Recent inspections
      </button>
      <button class="chip" data-prompt="Show dispatch status summary" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 3v5a2 2 0 0 1-2 2h-1"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
        Dispatch summary
      </button>
      <button class="chip" data-prompt="Show me the full data dashboard" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        Full dashboard
      </button>
    </div>
  `;
  messagesEl.appendChild(ws);

  // Re-bind chip clicks on the new chips container
  const newChipContainer = ws.querySelector(".suggestion-chips");
  if (newChipContainer) {
    newChipContainer.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      const prompt = chip.dataset.prompt;
      if (!prompt) return;
      inputEl.value = prompt;
      autoGrow();
      sendMessage(prompt);
      inputEl.value = "";
      autoGrow();
    });
  }

  closeSidebar();
  inputEl.focus();
}

newChatBtn.addEventListener("click", resetChat);
if (mobileNewChatBtn) mobileNewChatBtn.addEventListener("click", resetChat);

// ─── Health check ─────────────────────────────────────────────

(async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const up = data.database === "up";
    statusDot.classList.add(up ? "up" : "down");
    statusText.textContent = up ? `Connected · ${data.model}` : `Database ${data.database}`;
    statusDot.title = up
      ? `Database connected · Model: ${data.model}`
      : `Database: ${data.database}`;
  } catch (err) {
    statusDot.classList.add("down");
    statusText.textContent = "Server unreachable";
    statusDot.title = "Server unreachable";
  }
})();

// ─── Login Logic ──────────────────────────────────────────────

if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userId = loginInput.value.trim();
    if (!userId) return;

    loginBtn.classList.add("loading");
    loginError.classList.add("hidden");
    loginInput.disabled = true;

    try {
      const res = await fetch("/api/user/identify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId }),
      });
      const data = await res.json();

      if (res.ok && data.status === "ok") {
        // Hide login overlay
        loginOverlay.classList.add("hidden");
        
        // Update user profile card
        const p = data.profile || {};
        const name = p.FIRSTNAME || p.NAME || p.USERNAME || p.USER_NAME || p.LOGINNAME || userId;
        const role = p.ROLE || p.DEPARTMENT || p.JOB_TITLE || "User";
        
        userName.textContent = name;
        userRole.textContent = role;
        userAvatar.textContent = name.charAt(0).toUpperCase();
        userProfileCard.classList.remove("hidden");
        
        inputEl.focus();
      } else {
        loginError.textContent = data.error || "Login failed. Please check your User ID.";
        loginError.classList.remove("hidden");
      }
    } catch (err) {
      console.error(err);
      loginError.textContent = "Network error. Please try again.";
      loginError.classList.remove("hidden");
    } finally {
      loginBtn.classList.remove("loading");
      loginInput.disabled = false;
      if (!loginOverlay.classList.contains("hidden")) {
        loginInput.focus();
      }
    }
  });
}

// ─── Focus input on load ──────────────────────────────────────
if (loginOverlay && !loginOverlay.classList.contains("hidden")) {
  loginInput.focus();
} else {
  inputEl.focus();
}
