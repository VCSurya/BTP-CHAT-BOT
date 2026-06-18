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

// Visualization Panel (Workbench)
const vizPanel = document.getElementById("viz-panel");
const vizCloseBtn = document.getElementById("viz-close-btn");
const tabDashboardBtn = document.getElementById("tab-dashboard");
const tabExplorerBtn = document.getElementById("tab-explorer");
const panelDashboard = document.getElementById("panel-dashboard-content");
const panelExplorer = document.getElementById("panel-explorer-content");
const dashboardBody = document.getElementById("dashboard-body");
const explorerBody = document.getElementById("explorer-body");
const exportDashboardBtn = document.getElementById("dashboard-export-btn");

const dashboardBtn = document.getElementById("dashboard-btn");

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
  sidebar.classList.add("translate-x-0");
  sidebar.classList.remove("-translate-x-full");
  sidebarOverlay.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeSidebar() {
  sidebar.classList.remove("translate-x-0");
  sidebar.classList.add("-translate-x-full");
  sidebarOverlay.classList.add("hidden");
  document.body.style.overflow = "";
}

if (sidebarToggle) sidebarToggle.addEventListener("click", () => {
  if (sidebar.classList.contains("translate-x-0")) closeSidebar();
  else openSidebar();
});
if (mobileSidebarBtn) mobileSidebarBtn.addEventListener("click", openSidebar);
if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);

// ─── Message rendering ───────────────────────────────────────

function addMessage(role, htmlContent, opts = {}) {
  hideWelcomeScreen();

  const wrap = document.createElement("div");
  wrap.className = `flex gap-3 max-w-3xl w-full mx-auto animate-fadeInUp ${role === "user" ? "justify-end" : "justify-start"}`;

  // Avatar
  const avatar = document.createElement("div");
  if (role === "assistant") {
    avatar.className = "w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-600 to-brand-700 text-white flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm";
    avatar.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>`;
  } else {
    avatar.className = "w-8 h-8 rounded-lg bg-slate-200 border border-slate-300 text-slate-600 flex items-center justify-center flex-shrink-0 mt-0.5 font-bold text-xs shadow-sm";
    avatar.textContent = "You";
  }

  const bubble = document.createElement("div");
  if (role === "assistant") {
    bubble.className = "max-w-[85%] min-w-0 bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4.5 py-3 text-slate-800 text-sm shadow-sm leading-relaxed" + (opts.error ? " border-red-200 bg-red-50/30 text-red-800" : "");
  } else {
    bubble.className = "max-w-[85%] min-w-0 bg-gradient-to-tr from-brand-50 to-brand-100/50 border border-brand-100 rounded-2xl rounded-tr-sm px-4.5 py-3 text-brand-950 text-sm shadow-sm leading-relaxed";
  }
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
  wrap.className = "flex gap-3 max-w-3xl w-full mx-auto animate-fadeInUp justify-start";
  wrap.dataset.typing = "1";

  const avatar = document.createElement("div");
  avatar.className = "w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-600 to-brand-700 text-white flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm";
  avatar.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
    <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
  </svg>`;

  const bubble = document.createElement("div");
  bubble.className = "max-w-[85%] min-w-0 bg-white border border-slate-200/80 rounded-2xl rounded-tl-sm px-4 py-3 text-slate-800 text-sm shadow-sm";
  bubble.innerHTML = `<div class="flex items-center gap-1">
    <span class="w-1.5 h-1.5 rounded-full bg-brand-600 animate-bounce" style="animation-delay: 0.1s"></span>
    <span class="w-1.5 h-1.5 rounded-full bg-brand-600 animate-bounce" style="animation-delay: 0.2s"></span>
    <span class="w-1.5 h-1.5 rounded-full bg-brand-600 animate-bounce" style="animation-delay: 0.3s"></span>
  </div>`;

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

// ─── Data rendering ───────────────────────────────────────────

function buildTable(table) {
  if (!table || !table.columns || !table.columns.length) return "";
  const head = table.columns.map((c) => `<th class="px-4 py-2.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider bg-slate-50 border-b border-slate-200 sticky top-0">${escapeHtml(c)}</th>`).join("");
  const body = table.rows
    .map(
      (row) =>
        `<tr class="hover:bg-slate-50/50 border-b border-slate-100 transition-colors">` +
        table.columns
          .map((c) => `<td class="px-4 py-2.5 text-sm text-slate-700 whitespace-nowrap">${escapeHtml(row[c])}</td>`)
          .join("") +
        "</tr>"
    )
    .join("");
  return `
    <details class="border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-sm mt-3" open>
      <summary class="cursor-pointer px-4 py-3 bg-slate-50 hover:bg-slate-100/80 text-sm font-semibold text-slate-700 select-none flex items-center gap-2 list-none transition-colors border-b border-slate-200/50">
        <span class="text-xs text-slate-400">▼</span>
        View Data Table (${table.rows.length} row${table.rows.length === 1 ? "" : "s"})
      </summary>
      <div class="overflow-x-auto max-h-80">
        <table class="min-w-full divide-y divide-slate-200">
          <thead><tr>${head}</tr></thead>
          <tbody class="divide-y divide-slate-100 bg-white">${body}</tbody>
        </table>
      </div>
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
        borderColor: "#ffffff",
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
      pointBorderColor: "#ffffff",
      pointBorderWidth: 2,
      pointHoverRadius: 6,
      fill: chart.type === "line",
    };
  });

  const showLegend = isPie || chart.datasets.length > 1;

  if (canvas.chartInstance) {
    try {
      canvas.chartInstance.destroy();
    } catch (err) {
      console.warn("Chart destroy failed:", err);
    }
  }

  canvas.chartInstance = new Chart(canvas.getContext("2d"), {
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
            color: "#475569",
            boxWidth: 12,
            boxHeight: 12,
            borderRadius: 3,
            useBorderRadius: true,
            padding: 14,
            font: { family: "'Inter', sans-serif", size: 12 },
          },
        },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.95)",
          titleColor: "#f8fafc",
          bodyColor: "#94a3b8",
          borderColor: "rgba(0,0,0,0.05)",
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
              ticks: { color: "#475569", font: { size: 11 } },
              grid: { color: "rgba(0,0,0,0.06)", drawBorder: false },
            },
            y: {
              ticks: { color: "#475569", font: { size: 11 } },
              grid: { color: "rgba(0,0,0,0.06)", drawBorder: false },
            },
          },
    },
  });
}

function buildChartCard(chart) {
  const chartWrap = document.createElement("div");
  chartWrap.className = "bg-slate-50 border border-slate-200/80 rounded-2xl p-4 shadow-sm hover:border-slate-300 hover:shadow-md transition-all duration-200 flex flex-col mt-3";

  // Card Header Container
  const header = document.createElement("div");
  header.className = "chart-card-header flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 mb-3";

  const t = document.createElement("p");
  t.className = "text-xs font-bold text-slate-500 uppercase tracking-wider";
  t.textContent = chart.title || "Chart Overview";
  header.appendChild(t);

  // Controls container
  const controls = document.createElement("div");
  controls.className = "flex items-center gap-1.5 flex-wrap";

  // Chart Type Selector
  const typeSelect = document.createElement("select");
  typeSelect.className = "text-[10px] font-semibold text-slate-600 bg-white border border-slate-200 rounded-lg px-2 py-1 outline-none cursor-pointer hover:bg-slate-50 active:scale-95 transition-all duration-150 max-w-[92px] truncate";
  typeSelect.title = "Chart Type";
  const types = [
    { label: "Bar Chart", value: "bar" },
    { label: "Line Chart", value: "line" },
    { label: "Pie Chart", value: "pie" },
    { label: "Donut Chart", value: "doughnut" }
  ];
  types.forEach(opt => {
    const option = document.createElement("option");
    option.value = opt.value;
    option.textContent = opt.label;
    if (opt.value === chart.type) option.selected = true;
    typeSelect.appendChild(option);
  });
  controls.appendChild(typeSelect);

  // Sort Order Selector
  const sortSelect = document.createElement("select");
  sortSelect.className = "text-[10px] font-semibold text-slate-600 bg-white border border-slate-200 rounded-lg px-2 py-1 outline-none cursor-pointer hover:bg-slate-50 active:scale-95 transition-all duration-150 max-w-[92px] truncate";
  sortSelect.title = "Sort order";
  const sorts = [
    { label: "Original Sort", value: "original" },
    { label: "High → Low", value: "desc" },
    { label: "Low → High", value: "asc" }
  ];
  sorts.forEach(opt => {
    const option = document.createElement("option");
    option.value = opt.value;
    option.textContent = opt.label;
    sortSelect.appendChild(option);
  });
  controls.appendChild(sortSelect);

  // Item Limit Selector
  const limitSelect = document.createElement("select");
  limitSelect.className = "text-[10px] font-semibold text-slate-600 bg-white border border-slate-200 rounded-lg px-2 py-1 outline-none cursor-pointer hover:bg-slate-50 active:scale-95 transition-all duration-150 max-w-[92px] truncate";
  limitSelect.title = "Item limit";
  const limits = [
    { label: "All Items", value: "all" },
    { label: "Top 5", value: "5" },
    { label: "Top 10", value: "10" },
    { label: "Top 20", value: "20" }
  ];
  limits.forEach(opt => {
    const option = document.createElement("option");
    option.value = opt.value;
    option.textContent = opt.label;
    limitSelect.appendChild(option);
  });
  controls.appendChild(limitSelect);

  // Download PNG Button
  const exportBtn = document.createElement("button");
  exportBtn.className = "flex items-center justify-center w-7 h-7 rounded-lg border border-slate-200 text-slate-500 bg-white hover:bg-slate-50 hover:text-slate-700 active:scale-95 transition-all duration-150 cursor-pointer";
  exportBtn.title = "Download Chart (PNG)";
  exportBtn.type = "button";
  exportBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
    <polyline points="7 10 12 15 17 10"/>
    <line x1="12" y1="15" x2="12" y2="3"/>
  </svg>`;
  controls.appendChild(exportBtn);

  header.appendChild(controls);
  chartWrap.appendChild(header);

  const box = document.createElement("div");
  box.className = "chart-canvas-box";
  const canvas = document.createElement("canvas");
  box.appendChild(canvas);
  chartWrap.appendChild(box);

  // Deep clone original chart data to keep it immutable
  const originalChartData = {
    type: chart.type,
    title: chart.title || "Chart Overview",
    labels: [...(chart.labels || [])],
    datasets: (chart.datasets || []).map(ds => ({
      label: ds.label || "",
      data: [...(ds.data || [])]
    }))
  };

  // Re-renderer function
  function updateChart() {
    const typeVal = typeSelect.value;
    const sortVal = sortSelect.value;
    const limitVal = limitSelect.value;

    let labels = [...originalChartData.labels];
    let datasets = originalChartData.datasets.map(ds => ({
      label: ds.label,
      data: [...ds.data]
    }));

    // Apply sorting if needed
    if (sortVal !== "original" && labels.length > 0 && datasets.length > 0) {
      const indices = Array.from({ length: labels.length }, (_, idx) => idx);
      indices.sort((a, b) => {
        const valA = Number(datasets[0].data[a]) || 0;
        const valB = Number(datasets[0].data[b]) || 0;
        return sortVal === "desc" ? valB - valA : valA - valB;
      });

      labels = indices.map(idx => labels[idx]);
      datasets = datasets.map(ds => ({
        ...ds,
        data: indices.map(idx => ds.data[idx])
      }));
    }

    // Apply item limits
    if (limitVal !== "all") {
      const limitNum = parseInt(limitVal, 10);
      labels = labels.slice(0, limitNum);
      datasets = datasets.map(ds => ({
        ...ds,
        data: ds.data.slice(0, limitNum)
      }));
    }

    const updatedConfig = {
      type: typeVal,
      title: originalChartData.title,
      labels: labels,
      datasets: datasets
    };

    try {
      renderChart(canvas, updatedConfig);
    } catch (err) {
      console.error("Failed to re-render chart:", err);
    }
  }

  // Bind change events
  typeSelect.addEventListener("change", updateChart);
  sortSelect.addEventListener("change", updateChart);
  limitSelect.addEventListener("change", updateChart);

  // Bind export button click
  exportBtn.addEventListener("click", () => {
    try {
      const link = document.createElement("a");
      const titleClean = (chart.title || "chart").toLowerCase().replace(/[^a-z0-9]+/g, "_");
      link.download = `${titleClean}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch (err) {
      console.error("Failed to export chart to image:", err);
    }
  });

  // Initial draw
  try {
    renderChart(canvas, chart);
  } catch (err) {
    console.error("Initial chart render failed:", err);
    return null;
  }

  return chartWrap;
}

function renderAssistantData(data) {
  // Always render the reply text in the chat bubble
  addMessage("assistant", `<p>${renderText(data.reply)}</p>`);

  explorerBody.innerHTML = "";
  let hasViz = false;

  if (data.chart) {
    const card = buildChartCard(data.chart);
    if (card) {
      explorerBody.appendChild(card);
      hasViz = true;
    }
  }

  if (data.table && data.table.rows && data.table.rows.length) {
    explorerBody.insertAdjacentHTML("beforeend", buildTable(data.table));
    hasViz = true;
  }

  if (data.truncated) {
    explorerBody.insertAdjacentHTML(
      "beforeend",
      `<p class="text-xs text-slate-500 font-medium italic mt-2">Showing the first ${data.table.rows.length} of more rows.</p>`
    );
  }

  if (data.sql) {
    explorerBody.insertAdjacentHTML(
      "beforeend",
      `<details class="sql"><summary>View SQL</summary><pre class="sql">${escapeHtml(
        data.sql
      )}</pre></details>`
    );
  }

  if (hasViz) {
    openVizPanel("explorer");
  }
  scrollToBottom();
}

// ─── Business insight helpers ──────────────────────────────────

const CATEGORY_ICONS = {
  "Procurement": '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>',
  "Quality & Inspection": '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  "Service Orders": '<rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 3v5a2 2 0 0 1-2 2h-1"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
  "Change Management": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 15h6M9 11h6"/>',
  "Queries & Issues": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  "Projects & Budgets": '<path d="M3 3v18h18"/><path d="M18.4 8.6 12 15 8.5 11.5 5 15"/>',
  "Documents & Comments": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  "Administration": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
};
const DEFAULT_ICON = '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>';

function iconSvg(paths, size = 16) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}

function formatKpiValue(kpi) {
  const n = Number(kpi.value) || 0;
  if (kpi.format === "decimal") {
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return Math.round(n).toLocaleString();
}

function buildKpiTile(kpi) {
  return `
    <div class="flex flex-col gap-1 p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl min-w-[120px] transition-all hover:bg-slate-100/50">
      <span class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">${escapeHtml(kpi.label)}</span>
      <span class="text-lg font-extrabold text-slate-900 leading-tight">${formatKpiValue(kpi)}</span>
    </div>`;
}

function buildTrendBadge(trend) {
  if (!trend) return "";
  const up = trend.change_pct >= 0;
  const arrow = up ? "M12 19V5M5 12l7-7 7 7" : "M12 5v14M5 12l7 7 7-7";
  const badgeColor = up ? "text-emerald-700 bg-emerald-50 border-emerald-100" : "text-rose-700 bg-rose-50 border-rose-100";
  return `
    <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badgeColor}" title="Last 30 days: ${trend.current_30d.toLocaleString()} vs previous 30 days: ${trend.previous_30d.toLocaleString()}">
      ${iconSvg(`<path d="${arrow}"/>`, 12)}
      ${Math.abs(trend.change_pct).toLocaleString(undefined, { maximumFractionDigits: 1 })}% vs prior 30d
    </span>`;
}

function buildSectionCard(section) {
  const card = document.createElement("div");
  card.className = "bg-white border border-slate-200 border-l-4 border-l-brand-600 rounded-2xl p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-slate-300";

  const kpiTiles = (section.kpis || []).map(buildKpiTile).join("");
  const trendHtml = buildTrendBadge(section.trend);
  const highlightHtml = section.highlight
    ? `<div class="flex items-start gap-2.5 p-3 rounded-xl bg-amber-50/50 border border-amber-100 text-amber-800 text-xs font-medium leading-relaxed mb-4">
        <span class="text-amber-500 mt-0.5">${iconSvg('<path d="M13 2 3 14h7l-1 8 11-12h-7l1-8z"/>', 14)}</span>
        <span class="text-slate-700">${escapeHtml(section.highlight)}</span>
       </div>`
    : "";

  card.innerHTML = `
    <div class="flex items-center justify-between gap-4 flex-wrap mb-2">
      <div class="flex items-center gap-2.5">
        <span class="flex items-center justify-center w-7 h-7 rounded-lg bg-brand-50 text-brand-600">${iconSvg(CATEGORY_ICONS[section.category] || DEFAULT_ICON, 14)}</span>
        <h4 class="text-sm font-bold text-slate-900 tracking-tight">${escapeHtml(section.name)}</h4>
      </div>
      ${trendHtml}
    </div>
    ${section.description ? `<p class="text-xs text-slate-500 leading-relaxed mb-4">${escapeHtml(section.description)}</p>` : ""}
    <div class="flex flex-wrap gap-2.5 mb-4">${kpiTiles}</div>
    ${highlightHtml}
  `;

  const grid = document.createElement("div");
  grid.className = "grid grid-cols-1 sm:grid-cols-2 gap-3";
  (section.charts || []).forEach((chart) => {
    const chartCard = buildChartCard(chart);
    if (chartCard) grid.appendChild(chartCard);
  });
  card.appendChild(grid);
  return card;
}

function buildCategoryBlock(category, anchorPrefix) {
  const slug = (anchorPrefix || "cat") + "-" + category.name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const block = document.createElement("section");
  block.className = "space-y-4 scroll-mt-6";
  block.id = slug;

  const heading = document.createElement("div");
  heading.className = "flex items-center gap-3.5 pb-2 border-b border-slate-100";
  heading.innerHTML = `
    <span class="flex items-center justify-center w-8 h-8 rounded-xl bg-brand-50 text-brand-600 shadow-sm">${iconSvg(CATEGORY_ICONS[category.name] || DEFAULT_ICON, 16)}</span>
    <h3 class="text-base font-extrabold text-slate-900 tracking-tight">${escapeHtml(category.name)}</h3>
    <span class="px-2.5 py-0.5 rounded-full text-xs font-bold text-slate-500 bg-slate-100 border border-slate-200/60">${category.sections.length} area${category.sections.length === 1 ? "" : "s"}</span>
  `;
  block.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "grid grid-cols-1 xl:grid-cols-2 gap-5";
  category.sections.forEach((section) => grid.appendChild(buildSectionCard(section)));
  block.appendChild(grid);
  return block;
}

function buildSummaryStrip(summary) {
  const strip = document.createElement("div");
  strip.className = "grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6";
  const items = [
    { label: "Total Records", value: summary.total_records },
    { label: "Business Areas", value: summary.business_areas },
    { label: "Categories", value: summary.categories },
  ];
  strip.innerHTML = items
    .map(
      (item) => `
      <div class="relative flex flex-col gap-1 p-5 rounded-2xl bg-gradient-to-br from-brand-50/50 to-slate-100 border border-slate-200 shadow-sm overflow-hidden group">
        <span class="text-2xl font-black text-slate-900 tracking-tight">${Math.round(item.value).toLocaleString()}</span>
        <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider">${escapeHtml(item.label)}</span>
      </div>`
    )
    .join("");
  return strip;
}

function buildCategoryNav(categories, anchorPrefix) {
  const nav = document.createElement("div");
  nav.className = "flex flex-wrap gap-2 pb-4 mb-6 border-b border-slate-200/80";
  categories.forEach((category) => {
    const slug = (anchorPrefix || "cat") + "-" + category.name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    const pill = document.createElement("a");
    pill.className = "inline-flex items-center px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 hover:bg-brand-50 hover:text-brand-700 hover:border-brand-200 border border-slate-200 text-slate-600 transition-all duration-150 shadow-sm";
    pill.href = `#${slug}`;
    pill.textContent = category.name;
    nav.appendChild(pill);
  });
  return nav;
}

function formatCurrency(val) {
  if (val == null) return "₹0";
  const n = Number(val) || 0;
  if (n >= 100000000) { // Cr (Crore, 10M) - e.g. 5,000,000,000 / 10,000,000 = 500 Cr
    return "₹" + (n / 10000000).toFixed(2) + " Cr";
  }
  if (n >= 10000000) { // Cr
    return "₹" + (n / 10000000).toFixed(2) + " Cr";
  }
  if (n >= 100000) { // Lakh
    return "₹" + (n / 100000).toFixed(2) + " L";
  }
  return "₹" + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function buildBusinessKpiGrid(bs) {
  const grid = document.createElement("div");
  grid.className = "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 mb-6";

  if (!bs) {
    grid.innerHTML = '<p class="text-sm text-slate-500 font-medium italic">No KPI metrics data available.</p>';
    return grid;
  }

  const poCount = bs.po_count != null ? Number(bs.po_count) : 0;
  const vendorCount = bs.vendor_count != null ? Number(bs.vendor_count) : 0;
  const inspectionCount = bs.inspection_count != null ? Number(bs.inspection_count) : 0;
  const ncrCount = bs.ncr_count != null ? Number(bs.ncr_count) : 0;
  const queryCount = bs.query_count != null ? Number(bs.query_count) : 0;

  const cards = [
    {
      label: "Total Spend",
      value: formatCurrency(bs.total_spend),
      desc: "Cumulative value of all active purchase contracts",
      icon: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
      colorClass: "border-t-brand-600 text-brand-600 bg-brand-50"
    },
    {
      label: "Active POs",
      value: poCount.toLocaleString(),
      desc: "Unique purchase orders currently being executed",
      icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8"/>',
      colorClass: "border-t-cyan-600 text-cyan-600 bg-cyan-50"
    },
    {
      label: "Approved Vendors",
      value: vendorCount.toLocaleString(),
      desc: "Contracted suppliers delivering raw materials",
      icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
      colorClass: "border-t-purple-600 text-purple-600 bg-purple-50"
    },
    {
      label: "Quality Checks",
      value: inspectionCount.toLocaleString(),
      desc: "Inspections scheduled at manufacturer sites",
      icon: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
      colorClass: "border-t-emerald-600 text-emerald-600 bg-emerald-50"
    },
    {
      label: "Quality Defects (NCR)",
      value: ncrCount.toLocaleString(),
      desc: "Active non-conformance reports registered",
      icon: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
      colorClass: "border-t-rose-600 text-rose-600 bg-rose-50"
    },
    {
      label: "Pending Queries",
      value: queryCount.toLocaleString(),
      desc: "Clarifications/RFIs currently open for POs",
      icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
      colorClass: "border-t-amber-500 text-amber-600 bg-amber-50"
    }
  ];

  grid.innerHTML = cards.map(c => `
    <div class="flex flex-col gap-3.5 p-5 bg-white border border-slate-200 border-t-4 ${c.colorClass.split(' ')[0]} rounded-2xl shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-slate-300">
      <div class="flex items-center justify-between gap-4">
        <span class="flex items-center justify-center w-9 h-9 rounded-xl ${c.colorClass.split(' ').slice(1).join(' ')}">${iconSvg(c.icon, 18)}</span>
        <span class="text-xl font-extrabold text-slate-900">${c.value}</span>
      </div>
      <div class="space-y-0.5">
        <h4 class="text-xs font-bold text-slate-800 uppercase tracking-wider">${escapeHtml(c.label)}</h4>
        <p class="text-xs text-slate-400 font-medium leading-relaxed">${escapeHtml(c.desc)}</p>
      </div>
    </div>
  `).join("");

  return grid;
}

function buildBusinessAnalyticsRow(bs) {
  const row = document.createElement("div");
  row.className = "grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6";

  if (!bs) {
    row.innerHTML = '<p class="text-sm text-slate-500 font-medium italic">No supplier analytics data available.</p>';
    return row;
  }

  const topVendors = bs.top_vendors || [];
  const topCategories = bs.top_categories || [];

  const maxSpend = topVendors.length ? Math.max(...topVendors.map(v => Number(v.spend) || 0)) : 1;
  const maxCount = topCategories.length ? Math.max(...topCategories.map(c => Number(c.count) || 0)) : 1;

  const vendorItems = topVendors.map(v => {
    const spendVal = Number(v.spend) || 0;
    const pct = Math.max(5, (spendVal / maxSpend) * 100);
    return `
      <div class="space-y-1.5">
        <div class="flex items-center justify-between text-xs font-semibold gap-4">
          <span class="text-slate-700 truncate" title="${escapeHtml(v.vendor)}">${escapeHtml(v.vendor)}</span>
          <span class="text-slate-900 font-bold tabular-nums">${formatCurrency(spendVal)}</span>
        </div>
        <div class="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
          <div class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-500 transition-all duration-500" style="width: ${pct}%"></div>
        </div>
      </div>
    `;
  }).join("");

  const categoryItems = topCategories.map(c => {
    const countVal = Number(c.count) || 0;
    const pct = Math.max(5, (countVal / maxCount) * 100);
    return `
      <div class="space-y-1.5">
        <div class="flex items-center justify-between text-xs font-semibold gap-4">
          <span class="text-slate-700 truncate">${escapeHtml(c.category)}</span>
          <span class="text-slate-900 font-bold tabular-nums">${countVal} POs</span>
        </div>
        <div class="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
          <div class="h-full rounded-full bg-gradient-to-r from-purple-400 to-rose-400 transition-all duration-500" style="width: ${pct}%"></div>
        </div>
      </div>
    `;
  }).join("");

  row.innerHTML = `
    <div class="flex flex-col gap-4 p-5 bg-white border border-slate-200 rounded-2xl shadow-sm">
      <div class="flex items-center gap-2.5 pb-3 border-b border-slate-100">
        <span class="text-emerald-500">${iconSvg('<circle cx="12" cy="8" r="7"/><path d="M5.21 14A10 10 0 0 0 12 22a10 10 0 0 0 6.79-8M3 10h18"/>', 16)}</span>
        <h4 class="text-sm font-extrabold text-slate-800 tracking-tight">Top Suppliers by Spend</h4>
      </div>
      <div class="flex flex-col gap-3.5">
        ${vendorItems || '<p class="text-xs text-slate-400 italic">No supplier spend data available.</p>'}
      </div>
    </div>
    <div class="flex flex-col gap-4 p-5 bg-white border border-slate-200 rounded-2xl shadow-sm">
      <div class="flex items-center gap-2.5 pb-3 border-b border-slate-100">
        <span class="text-purple-500">${iconSvg('<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>', 16)}</span>
        <h4 class="text-sm font-extrabold text-slate-800 tracking-tight">Top Product Categories</h4>
      </div>
      <div class="flex flex-col gap-3.5">
        ${categoryItems || '<p class="text-xs text-slate-400 italic">No product category data available.</p>'}
      </div>
    </div>
  `;

  return row;
}

function buildAiInsightsBlock(ai) {
  if (!ai) return document.createElement("div");
  const card = document.createElement("div");
  card.className = "flex flex-col gap-4 p-6 bg-gradient-to-br from-brand-900 to-slate-950 text-white rounded-3xl border border-brand-950 shadow-xl shadow-brand-950/10 mb-6";

  const observations = ai.key_observations || [];
  const obsHtml = observations.map(obs => `
    <div class="flex items-start gap-3 text-xs leading-relaxed text-slate-300 font-medium">
      <span class="text-cyan-400 mt-0.5">${iconSvg('<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>', 12)}</span>
      <p class="flex-1">${escapeHtml(obs)}</p>
    </div>
  `).join("");

  card.innerHTML = `
    <div class="flex items-center justify-between gap-4 pb-4 border-b border-brand-800/40">
      <div class="flex items-center gap-2.5">
        <span class="flex items-center justify-center w-8 h-8 rounded-lg bg-brand-800/60 border border-brand-700/40 text-cyan-400 shadow shadow-brand-500/10">${iconSvg('<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>', 16)}</span>
        <h4 class="text-sm font-extrabold tracking-tight">AI Procurement Intelligence Analysis</h4>
      </div>
      <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider text-cyan-300 bg-cyan-950/80 border border-cyan-800/40">Executive Report</span>
    </div>
    <div class="space-y-4">
      ${ai.executive_summary ? `<p class="text-sm leading-relaxed text-slate-200 font-medium">${escapeHtml(ai.executive_summary)}</p>` : ""}
      <div class="flex flex-col gap-3">${obsHtml}</div>
      ${ai.recommendation ? `
        <div class="flex items-start gap-3 p-4 rounded-2xl bg-cyan-950/40 border border-cyan-900/40 text-cyan-100">
          <span class="text-cyan-400 mt-0.5">${iconSvg('<path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3Z"/>', 16)}</span>
          <div class="space-y-1">
            <strong class="text-xs font-bold uppercase tracking-wider text-cyan-400">Strategic Recommendation</strong>
            <p class="text-xs leading-relaxed text-cyan-100/90 font-medium">${escapeHtml(ai.recommendation)}</p>
          </div>
        </div>
      ` : ""}
    </div>
  `;

  return card;
}

function renderAssistantDashboard(data) {
  // Render the reply text in the chat bubble
  addMessage("assistant", `<p>${renderText(data.reply)}</p>`);
  
  // Render the actual dashboard widgets directly in the Dashboard tab of the right panel
  renderDashboardPanel(data);
  
  // Open the visualization panel, focused on the Executive Dashboard
  openVizPanel("dashboard");
  scrollToBottom();
}

// ─── Dashboard panel ──────────────────────────────────────────

function renderDashboardPanel(data) {
  dashboardBody.innerHTML = "";
  const categories = data.categories || [];
  
  if (data.ai_insights) {
    dashboardBody.appendChild(buildAiInsightsBlock(data.ai_insights));
  }
  
  if (data.business_summary) {
    const heading = document.createElement("h2");
    heading.className = "text-base font-extrabold text-slate-900 tracking-tight mb-4 flex items-center gap-2 mt-4";
    heading.textContent = "Executive Business Insights";
    dashboardBody.appendChild(heading);
    
    dashboardBody.appendChild(buildBusinessKpiGrid(data.business_summary));
    dashboardBody.appendChild(buildBusinessAnalyticsRow(data.business_summary));
    
    const divider = document.createElement("hr");
    divider.className = "border-slate-200/80 my-8";
    dashboardBody.appendChild(divider);
  }

  if (!categories.length) {
    dashboardBody.innerHTML += '<p class="text-sm text-slate-500 font-medium italic">No data available to summarise yet.</p>';
    return;
  }
  
  const secHeading = document.createElement("h2");
  secHeading.className = "text-base font-extrabold text-slate-900 tracking-tight mb-4 flex items-center gap-2";
  secHeading.textContent = "Business Domain Exploration";
  dashboardBody.appendChild(secHeading);

  dashboardBody.appendChild(buildCategoryNav(categories, "panel"));
  categories.forEach((category) => dashboardBody.appendChild(buildCategoryBlock(category, "panel")));
}

function openVizPanel(activeTab = "dashboard") {
  app.classList.add("viz-open");
  vizPanel.setAttribute("aria-hidden", "false");
  switchVizTab(activeTab);
  closeSidebar();
}

function closeVizPanel() {
  app.classList.remove("viz-open");
  vizPanel.setAttribute("aria-hidden", "true");
}

function switchVizTab(tabName) {
  if (tabName === "dashboard") {
    tabDashboardBtn.classList.add("active");
    tabExplorerBtn.classList.remove("active");
    panelDashboard.classList.remove("hidden");
    panelExplorer.classList.add("hidden");
    if (exportDashboardBtn) exportDashboardBtn.style.display = "flex";
  } else {
    tabDashboardBtn.classList.remove("active");
    tabExplorerBtn.classList.add("active");
    panelDashboard.classList.add("hidden");
    panelExplorer.classList.remove("hidden");
    if (exportDashboardBtn) exportDashboardBtn.style.display = "none";
  }
}

async function openDashboard() {
  openVizPanel("dashboard");
  dashboardBody.innerHTML = '<p class="text-sm text-slate-500 font-medium italic">Crunching the latest numbers…</p>';
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    if (data.error) {
      dashboardBody.innerHTML = `<p class="text-sm text-slate-500 font-medium italic">${escapeHtml(data.error)}</p>`;
      return;
    }
    renderDashboardPanel(data);
  } catch (err) {
    console.error(err);
    dashboardBody.innerHTML = '<p class="text-sm text-slate-500 font-medium italic">Could not load the dashboard right now.</p>';
  }
}

// Bind tabs click event listeners
if (tabDashboardBtn) tabDashboardBtn.addEventListener("click", () => switchVizTab("dashboard"));
if (tabExplorerBtn) tabExplorerBtn.addEventListener("click", () => switchVizTab("explorer"));
if (vizCloseBtn) vizCloseBtn.addEventListener("click", closeVizPanel);

if (dashboardBtn) dashboardBtn.addEventListener("click", openDashboard);

if (exportDashboardBtn) {
  exportDashboardBtn.addEventListener("click", () => {
    window.print();
  });
}

// Close panel on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (app.classList.contains("viz-open")) {
      closeVizPanel();
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
    <h1 class="welcome-title">Adani Procurement Analytics</h1>
    <p class="welcome-subtitle">I'm Adani Procura, your procurement analytics assistant. Ask me anything about purchase orders, vendors, dispatches, and inspections.</p>
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
