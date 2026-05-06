tailwind.config = {
  darkMode: "class",
  theme: {
    extend: {
      "colors": {
          "outline-variant": "#3a494b",
          "primary": "#e1fdff",
          "surface-variant": "#353534",
          "secondary": "#ebb2ff",
          "on-primary": "#00363a",
          "on-secondary": "#520072",
          "surface-container-low": "#1c1b1b",
          "error-container": "#93000a",
          "surface-container-lowest": "#0e0e0e",
          "secondary-container": "#b600f8",
          "surface-bright": "#3a3939",
          "on-tertiary-container": "#007016",
          "surface": "#131313",
          "surface-container-highest": "#353534",
          "on-tertiary-fixed-variant": "#00530e",
          "primary-fixed-dim": "#00dbe7",
          "tertiary-fixed": "#72ff70",
          "tertiary": "#e4ffdb",
          "on-primary-container": "#006a71",
          "on-tertiary-fixed": "#002203",
          "surface-container-high": "#2a2a2a",
          "on-primary-fixed-variant": "#004f54",
          "on-primary-fixed": "#002022",
          "background": "#131313",
          "on-error": "#690005",
          "tertiary-fixed-dim": "#00e639",
          "primary-fixed": "#74f5ff",
          "inverse-surface": "#e5e2e1",
          "on-secondary-fixed": "#320047",
          "primary-container": "#00f2ff",
          "secondary-fixed": "#f8d8ff",
          "inverse-on-surface": "#313030",
          "on-surface": "#e5e2e1",
          "surface-container": "#201f1f",
          "surface-tint": "#00dbe7",
          "on-secondary-fixed-variant": "#74009f",
          "on-error-container": "#ffdad6",
          "on-background": "#e5e2e1",
          "inverse-primary": "#00696f",
          "on-tertiary": "#003907",
          "on-secondary-container": "#fff6fc",
          "error": "#ffb4ab",
          "tertiary-container": "#00fd40",
          "surface-dim": "#131313",
          "secondary-fixed-dim": "#ebb2ff",
          "outline": "#849495",
          "on-surface-variant": "#b9cacb"
      },
      "borderRadius": {
          "DEFAULT": "0.125rem",
          "lg": "0.25rem",
          "xl": "0.5rem",
          "full": "0.75rem"
      },
      "spacing": {
          "xl": "48px",
          "base": "4px",
          "lg": "32px",
          "md": "24px",
          "xs": "8px",
          "sm": "16px",
          "margin": "40px",
          "gutter": "20px"
      },
      "fontFamily": {
          "mono-data": ["Inter"],
          "headline-xl": ["Space Grotesk"],
          "body-sm": ["Inter"],
          "headline-md": ["Space Grotesk"],
          "label-caps": ["Space Grotesk"],
          "body-lg": ["Inter"]
      },
      "fontSize": {
          "mono-data": ["13px", {"lineHeight": "1.4", "letterSpacing": "-0.01em", "fontWeight": "500"}],
          "headline-xl": ["40px", {"lineHeight": "1.2", "letterSpacing": "-0.02em", "fontWeight": "700"}],
          "body-sm": ["14px", {"lineHeight": "1.5", "fontWeight": "400"}],
          "headline-md": ["24px", {"lineHeight": "1.3", "fontWeight": "600"}],
          "label-caps": ["12px", {"lineHeight": "1", "letterSpacing": "0.1em", "fontWeight": "700"}],
          "body-lg": ["18px", {"lineHeight": "1.6", "fontWeight": "400"}]
      }
    }
  }
};

const isAdmin = window.localStorage.getItem("portfolio.isAdmin") === "true";
const API_BASE_URL = window.PORTFOLIO_API_BASE_URL || window.location.origin;
const REQUEST_TIMEOUT_MS = 8000;

if (!isAdmin) {
  const toggle = document.getElementById("open-to-work-toggle");
  if (toggle) {
    toggle.style.display = "none";
  }
}

const identityState = {
  isExpanded: false,
  isConnectOpen: false,
  isPointerOnTrigger: false,
  isPointerOnPanel: false,
};

let identityCloseTimer = null;
let telemetryTimer = null;
let githubStatsTimer = null;
let awsStatusTimer = null;
let dashboardMetricsTimer = null;

const backendTelemetryState = {
  startedAt: null,
  lastHealthyAt: null,
};

function createJsonHeaders(extraHeaders = {}) {
  return Object.assign({
    "Content-Type": "application/json",
  }, extraHeaders);
}

function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const id = window.setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, Object.assign({}, options, { signal: controller.signal }))
    .finally(() => window.clearTimeout(id));
}


const BACKEND_STARTED_AT_KEY = "portfolio.backend.started_at";
const BACKEND_LAST_HEALTHY_AT_KEY = "portfolio.backend.last_healthy_at";

function formatElapsed(milliseconds) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const totalMinutes = Math.floor(totalSeconds / 60);
  if (totalMinutes < 60) {
    return `${totalMinutes}m`;
  }
  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 24) {
    const remainingMinutes = totalMinutes % 60;
    return `${totalHours}h ${remainingMinutes}m`;
  }
  const totalDays = Math.floor(totalHours / 24);
  const remainingHours = totalHours % 24;
  return `${totalDays}d ${remainingHours}h`;
}

async function checkBackendHealth() {
  const startedAt = performance.now();
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/health`, {
      method: "GET",
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`Health check failed with status ${response.status}`);
    }

    const health = await response.json();
    const latencyMs = Math.max(1, Math.round(performance.now() - startedAt));
    return { ok: true, latencyMs, startedAt: health.started_at, uptimeSeconds: health.uptime_seconds };
  } catch (error) {
    return { ok: false, error };
  }
}

function initializeBackendTelemetry() {
  const statusDot = document.getElementById("backend-status-dot");
  const statusText = document.getElementById("backend-status-text");
  const latencyText = document.getElementById("backend-latency-text");
  const uptimeText = document.getElementById("backend-uptime-text");
  const uptimeIcon = document.getElementById("backend-uptime-icon");

  if (!statusDot || !statusText || !latencyText || !uptimeText || !uptimeIcon) {
    return;
  }

  let onlineSince = null;
  let isPolling = false;
  const POLL_INTERVAL_MS = 10000;

  const storedStartedAt = window.localStorage.getItem(BACKEND_STARTED_AT_KEY);
  const storedLastHealthyAt = window.localStorage.getItem(BACKEND_LAST_HEALTHY_AT_KEY);

  if (storedStartedAt) {
    backendTelemetryState.startedAt = storedStartedAt;
  }
  if (storedLastHealthyAt) {
    backendTelemetryState.lastHealthyAt = Number(storedLastHealthyAt);
  }

  function markStable(latencyMs, startedAt, uptimeSeconds) {
    const now = Date.now();
    const backendStartedTime = startedAt ? Date.parse(startedAt) : now - Math.max(0, uptimeSeconds) * 1000;

    backendTelemetryState.startedAt = Number.isFinite(backendStartedTime) ? String(backendStartedTime) : String(now);
    backendTelemetryState.lastHealthyAt = now;
    window.localStorage.setItem(BACKEND_STARTED_AT_KEY, backendTelemetryState.startedAt);
    window.localStorage.setItem(BACKEND_LAST_HEALTHY_AT_KEY, String(now));

    onlineSince = Number.isFinite(backendStartedTime) ? backendStartedTime : now;

    statusDot.classList.remove("bg-red-500");
    statusDot.classList.add("bg-tertiary-container", "animate-pulse");
    statusText.textContent = "SYSTEM:STABLE";
    latencyText.textContent = `LATENCY: ${latencyMs}ms`;
    uptimeIcon.textContent = "cloud_done";
    uptimeText.textContent = `UPTIME: ${formatElapsed(now - onlineSince)}`;
  }

  function markDown() {
    const now = Date.now();
    statusDot.classList.remove("bg-tertiary-container", "animate-pulse");
    statusDot.classList.add("bg-red-500");
    statusText.textContent = "SYSTEM:DOWN";
    latencyText.textContent = "LATENCY: -";
    uptimeIcon.textContent = "cloud_off";

    const lastSeenAt = backendTelemetryState.lastHealthyAt || (storedLastHealthyAt ? Number(storedLastHealthyAt) : null);
    uptimeText.textContent = lastSeenAt
      ? `UPTIME: (online ${formatElapsed(now - lastSeenAt)} ago)`
      : "UPTIME: (online -)";
  }

  async function refreshTelemetry() {
    if (isPolling || document.hidden) {
      return;
    }
    isPolling = true;
    try {
      const health = await checkBackendHealth();
      health.ok ? markStable(health.latencyMs, health.startedAt, health.uptimeSeconds) : markDown();
    } finally {
      isPolling = false;
    }
  }

  refreshTelemetry();
  telemetryTimer = window.setInterval(refreshTelemetry, POLL_INTERVAL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (telemetryTimer) {
        window.clearInterval(telemetryTimer);
        telemetryTimer = null;
      }
    } else if (!telemetryTimer) {
      refreshTelemetry();
      telemetryTimer = window.setInterval(refreshTelemetry, POLL_INTERVAL_MS);
    }
  });
}

async function fetchGitHubStats() {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/github-stats?year=2026`, {
      cache: "no-store",
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(errorBody || `GitHub stats request failed with status ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    throw error;
  }
}

function initializeGitHubCommitCounter() {
  const commitCount = document.getElementById("github-commit-count");
  const commitMeta = document.getElementById("github-commit-meta");

  if (!commitCount || !commitMeta) {
    return;
  }

  let isRefreshing = false;
  const REFRESH_INTERVAL_MS = 300000;

  async function refreshCommitCount() {
    if (isRefreshing || document.hidden) {
      return;
    }
    isRefreshing = true;
    try {
      const stats = await fetchGitHubStats();
      commitCount.textContent = stats.total_commit_contributions.toLocaleString();
      commitMeta.textContent = `Updated ${new Date(stats.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} from @${stats.username}`;
    } catch (error) {
      console.error("GitHub commit counter unavailable", error);
      commitCount.textContent = "--";
      commitMeta.textContent = error instanceof Error && error.message.includes("GITHUB_USERNAME is not configured")
        ? "Set GITHUB_USERNAME in .env to load GitHub commits."
        : (error instanceof Error ? error.message : "GitHub data unavailable.");
    } finally {
      isRefreshing = false;
    }
  }

  refreshCommitCount();
  githubStatsTimer = window.setInterval(refreshCommitCount, REFRESH_INTERVAL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && githubStatsTimer) {
      window.clearInterval(githubStatsTimer);
      githubStatsTimer = null;
    } else if (!document.hidden && !githubStatsTimer) {
      refreshCommitCount();
      githubStatsTimer = window.setInterval(refreshCommitCount, REFRESH_INTERVAL_MS);
    }
  });
}

function initializeAwsConnectionStatus() {
  const statusDot = document.getElementById("aws-status-dot");
  const statusText = document.getElementById("aws-status-text");
  const detailText = document.getElementById("aws-detail-text");
  const regionText = document.getElementById("aws-region-text");
  const arnText = document.getElementById("aws-arn-text");

  if (!statusDot || !statusText || !detailText || !regionText || !arnText) {
    return;
  }

  let isRefreshing = false;
  const REFRESH_INTERVAL_MS = 300000;

  function renderAwsStatus(status) {
    const connected = Boolean(status.connected);
    statusDot.classList.toggle("bg-tertiary-container", connected);
    statusDot.classList.toggle("bg-red-500", !connected);
    statusText.textContent = connected ? "AWS:CONNECTED" : "AWS:NOT READY";
    detailText.textContent = status.message;
    regionText.textContent = `REGION: ${status.region}`;
    arnText.textContent = connected && status.account_id ? `ACCOUNT: ${status.account_id}` : "ACCOUNT: -";
  }

  async function refreshAwsStatus() {
    if (isRefreshing || document.hidden) {
      return;
    }
    isRefreshing = true;
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/aws-status`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`AWS status request failed with status ${response.status}`);
      }
      const data = await response.json();
      renderAwsStatus(data);
    } catch (error) {
      renderAwsStatus({
        connected: false,
        region: "-",
        message: error instanceof Error ? error.message : "AWS status unavailable.",
      });
    } finally {
      isRefreshing = false;
    }
  }

  refreshAwsStatus();
  awsStatusTimer = window.setInterval(refreshAwsStatus, REFRESH_INTERVAL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && awsStatusTimer) {
      window.clearInterval(awsStatusTimer);
      awsStatusTimer = null;
    } else if (!document.hidden && !awsStatusTimer) {
      refreshAwsStatus();
      awsStatusTimer = window.setInterval(refreshAwsStatus, REFRESH_INTERVAL_MS);
    }
  });
}

function initializeDashboardMetrics() {
  const cpuValue = document.getElementById("dashboard-cpu-value");
  const cpuBar = document.getElementById("dashboard-cpu-bar");
  const cpuLoad = document.getElementById("dashboard-cpu-load");
  const cpuStatus = document.getElementById("dashboard-cpu-status");

  const memoryValue = document.getElementById("dashboard-memory-value");
  const memoryBar = document.getElementById("dashboard-memory-bar");
  const memoryLimit = document.getElementById("dashboard-memory-limit");
  const memoryStatus = document.getElementById("dashboard-memory-status");

  const requestValue = document.getElementById("dashboard-request-value");
  const requestBar = document.getElementById("dashboard-request-bar");
  const requestPeak = document.getElementById("dashboard-request-peak");
  const requestStatus = document.getElementById("dashboard-request-status");

  if (
    !cpuValue || !cpuBar || !cpuLoad || !cpuStatus ||
    !memoryValue || !memoryBar || !memoryLimit || !memoryStatus ||
    !requestValue || !requestBar || !requestPeak || !requestStatus
  ) {
    return;
  }

  let isRefreshing = false;
  const REFRESH_INTERVAL_MS = 30000; // 30 seconds

  function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return "-";
    const gb = bytes / (1024 * 1024 * 1024);
    return `${gb.toFixed(1)} GB`;
  }

  function formatRequestCount(count) {
    if (count === null || count === undefined) return "-";
    if (count >= 1000) {
      return `${(count / 1000).toFixed(1)}k`;
    }
    return Math.floor(count).toString();
  }

  function getStatusColor(value, thresholds) {
    // thresholds = { warning: 70, critical: 90 }
    if (value === null || value === undefined) return "text-slate-400";
    if (value >= (thresholds.critical || 90)) return "text-error";
    if (value >= (thresholds.warning || 70)) return "text-secondary";
    return "text-tertiary-container";
  }

  function getStatusText(value, thresholds) {
    if (value === null || value === undefined) return "UNKNOWN";
    if (value >= (thresholds.critical || 90)) return "CRITICAL";
    if (value >= (thresholds.warning || 70)) return "WARNING";
    return "OPTIMAL";
  }

  async function refreshDashboardMetrics() {
    if (isRefreshing || document.hidden) {
      return;
    }
    isRefreshing = true;
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/dashboard-metrics`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Dashboard metrics request failed with status ${response.status}`);
      }
      const data = await response.json();

      // Update CPU metrics
      const cpuVal = data.cpu_utilization?.value || 0;
      cpuValue.textContent = cpuVal !== null ? `${cpuVal}%` : "-";
      cpuBar.style.width = `${Math.min(cpuVal, 100)}%`;
      cpuLoad.textContent = `LOAD: ${(cpuVal / 100).toFixed(2)}`;
      const cpuStatusClass = getStatusColor(cpuVal, { warning: 60, critical: 85 });
      cpuStatus.className = `text-${cpuStatusClass.split("-").pop()} ${cpuStatusClass}`;
      cpuStatus.textContent = getStatusText(cpuVal, { warning: 60, critical: 85 });

      // Update Memory metrics - note: bytes typically come in MBs from network metrics
      const memBytesIn = data.network_metrics?.inbound_bytes || 0;
      const memBytesOut = data.network_metrics?.outbound_bytes || 0;
      const totalMemBytes = memBytesIn + memBytesOut;
      const memPercentage = Math.min((totalMemBytes / (16 * 1024 * 1024 * 1024)) * 100, 100);
      memoryValue.textContent = formatBytes(totalMemBytes);
      memoryBar.style.width = `${memPercentage}%`;
      memoryLimit.textContent = `LIMIT: 16.0 GB`;
      const memStatusClass = getStatusColor(memPercentage, { warning: 70, critical: 85 });
      memoryStatus.className = memStatusClass;
      memoryStatus.textContent = getStatusText(memPercentage, { warning: 70, critical: 85 });

      // Update Request metrics
      const requestVal = data.request_metrics?.requests_per_second || 0;
      requestValue.textContent = formatRequestCount(requestVal);
      const requestPercentage = Math.min((requestVal / 12) * 100, 100);
      requestBar.style.width = `${requestPercentage}%`;
      requestPeak.textContent = `PEAK: 12.0k`;
      const reqStatusClass = requestPercentage > 75 ? "text-primary" : "text-tertiary-container";
      requestStatus.className = reqStatusClass;
      requestStatus.textContent = requestPercentage > 75 ? "INCREASING" : "NORMAL";
    } catch (error) {
      console.error("Dashboard metrics fetch failed", error);
      cpuValue.textContent = "-";
      memoryValue.textContent = "-";
      requestValue.textContent = "-";
      cpuStatus.textContent = "ERROR";
      memoryStatus.textContent = "ERROR";
      requestStatus.textContent = "ERROR";
    } finally {
      isRefreshing = false;
    }
  }

  refreshDashboardMetrics();
  dashboardMetricsTimer = window.setInterval(refreshDashboardMetrics, REFRESH_INTERVAL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && dashboardMetricsTimer) {
      window.clearInterval(dashboardMetricsTimer);
      dashboardMetricsTimer = null;
    } else if (!document.hidden && !dashboardMetricsTimer) {
      refreshDashboardMetrics();
      dashboardMetricsTimer = window.setInterval(refreshDashboardMetrics, REFRESH_INTERVAL_MS);
    }
  });
}

function renderIdentityPanel() {
  const panel = document.getElementById("identity-panel");
  const toggle = document.getElementById("identity-hover-trigger");
  const chevron = document.getElementById("identity-chevron");
  const connectMenu = document.getElementById("connect-menu");
  const connectToggle = document.getElementById("connect-toggle");
  const connectChevron = document.getElementById("connect-chevron");

  if (!panel || !toggle || !chevron || !connectMenu || !connectToggle || !connectChevron) {
    return;
  }

  panel.classList.toggle("is-open", identityState.isExpanded);
  toggle.setAttribute("aria-expanded", String(identityState.isExpanded));
  chevron.textContent = identityState.isExpanded ? "chevron_left" : "chevron_right";

  connectMenu.classList.toggle(
    "is-open",
    identityState.isExpanded && identityState.isConnectOpen,
  );
  connectToggle.setAttribute(
    "aria-expanded",
    String(identityState.isExpanded && identityState.isConnectOpen),
  );
  connectChevron.textContent = identityState.isConnectOpen
    ? "keyboard_arrow_up"
    : "keyboard_arrow_down";

  document.body.classList.toggle("identity-expanded", identityState.isExpanded);
}

function openIdentityPanel() {
  if (identityCloseTimer) {
    window.clearTimeout(identityCloseTimer);
    identityCloseTimer = null;
  }
  if (!identityState.isExpanded) {
    identityState.isExpanded = true;
    renderIdentityPanel();
  }
}

function closeIdentityPanelWithDelay() {
  if (identityState.isPointerOnTrigger || identityState.isPointerOnPanel) {
    return;
  }

  if (identityCloseTimer) {
    window.clearTimeout(identityCloseTimer);
  }
  identityCloseTimer = window.setTimeout(() => {
    if (identityState.isPointerOnTrigger || identityState.isPointerOnPanel) {
      return;
    }
    identityState.isExpanded = false;
    identityState.isConnectOpen = false;
    renderIdentityPanel();
  }, 260);
}

function closeIdentityPanelImmediately() {
  if (identityCloseTimer) {
    window.clearTimeout(identityCloseTimer);
    identityCloseTimer = null;
  }
  identityState.isExpanded = false;
  identityState.isConnectOpen = false;
  identityState.isPointerOnTrigger = false;
  identityState.isPointerOnPanel = false;
  renderIdentityPanel();
}

function initializeIdentityPanel() {
  const toggle = document.getElementById("identity-hover-trigger");
  const panel = document.getElementById("identity-panel");
  const backdrop = document.getElementById("identity-backdrop");
  const closeButton = document.getElementById("identity-close-btn");
  const connectToggle = document.getElementById("connect-toggle");
  const askAiButton = document.getElementById("ask-ai-btn");
  const askAiFeedback = document.getElementById("ask-ai-feedback");
  const aiChatShell = document.getElementById("ai-chat-shell");
  const aiChatForm = document.getElementById("ai-chat-form");
  const aiChatInput = document.getElementById("ai-chat-input");
  const aiChatLog = document.getElementById("ai-chat-log");
  const connectMenu = document.getElementById("connect-menu");

  if (!toggle || !panel || !backdrop || !closeButton || !connectToggle || !askAiButton || !askAiFeedback || !aiChatShell || !aiChatForm || !aiChatInput || !aiChatLog || !connectMenu) {
    return;
  }

  const mobileProfileBtn = document.getElementById("mobile-profile-btn");

  toggle.addEventListener("pointerenter", () => {
    identityState.isPointerOnTrigger = true;
    openIdentityPanel();
  });

  toggle.addEventListener("click", () => {
    if (!identityState.isExpanded) {
      openIdentityPanel();
    }
  });

  toggle.addEventListener("pointerleave", () => {
    identityState.isPointerOnTrigger = false;
    closeIdentityPanelWithDelay();
  });

  if (mobileProfileBtn) {
    mobileProfileBtn.addEventListener("click", () => {
      identityState.isExpanded = !identityState.isExpanded;
      renderIdentityPanel();
    });
  }

  panel.addEventListener("pointerenter", () => {
    identityState.isPointerOnPanel = true;
    openIdentityPanel();
  });

  panel.addEventListener("pointerleave", () => {
    identityState.isPointerOnPanel = false;
    closeIdentityPanelWithDelay();
  });

  closeButton.addEventListener("click", closeIdentityPanelImmediately);
  backdrop.addEventListener("click", closeIdentityPanelImmediately);

  connectToggle.addEventListener("click", () => {
    identityState.isConnectOpen = !identityState.isConnectOpen;
    renderIdentityPanel();
  });

  connectMenu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      identityState.isConnectOpen = false;
      closeIdentityPanelWithDelay();
    });
  });

  askAiButton.addEventListener("click", () => {
    aiChatShell.classList.remove("hidden");
    aiChatInput.focus();
    askAiFeedback.textContent = "";
  });

  function appendChatMessage(text, variant) {
    const message = document.createElement("div");
    message.className = `ai-chat-message ai-chat-message-${variant}`;
    message.textContent = text;
    aiChatLog.appendChild(message);
    aiChatLog.scrollTop = aiChatLog.scrollHeight;
  }

  function isTalkToKartikIntent(text) {
    const normalized = text.toLowerCase().replace(/[^a-z\s]/g, " ").replace(/\s+/g, " ").trim();
    return normalized.includes("i want to talk to kartik") || normalized.includes("talk to kartik");
  }

  function getContactLinks() {
    const links = {
      linkedin: "https://www.linkedin.com/in/kartik-sakhuja-33a67b286/?originalSubdomain=in",
      instagram: "https://www.instagram.com/kartik.devs?igsh=MTJleXE2cDl4dTduMQ==",
      gmail: "mailto:kartik.sakhuja2004@gmail.com?subject=Portfolio%20Connect",
    };

    connectMenu.querySelectorAll("a").forEach((link) => {
      const label = (link.textContent || "").trim().toLowerCase();
      if (label.includes("linkedin")) {
        links.linkedin = link.href;
      } else if (label.includes("instagram")) {
        links.instagram = link.href;
      } else if (label.includes("email") || label.includes("gmail")) {
        links.gmail = link.href;
      }
    });

    return links;
  }

  function appendContactOptionsMessage() {
    const contactLinks = getContactLinks();
    const message = document.createElement("div");
    message.className = "ai-chat-message ai-chat-message-assistant";

    const text = document.createElement("p");
    text.textContent = "Absolutely. Which mode do you prefer to connect with Kartik?";
    message.appendChild(text);

    const actions = document.createElement("div");
    actions.className = "ai-chat-contact-actions";

    const options = [
      { label: "Gmail", href: contactLinks.gmail },
      { label: "Instagram", href: contactLinks.instagram },
      { label: "LinkedIn", href: contactLinks.linkedin },
    ];

    options.forEach((option) => {
      const action = document.createElement("a");
      action.className = "ai-chat-contact-action";
      action.href = option.href;
      action.target = "_blank";
      action.rel = "noopener noreferrer";
      action.textContent = option.label;
      actions.appendChild(action);
    });

    message.appendChild(actions);
    aiChatLog.appendChild(message);
    aiChatLog.scrollTop = aiChatLog.scrollHeight;
  }

  async function requestAiAnswer(question) {
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/ask-ai`, {
        method: "POST",
        headers: createJsonHeaders(),
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        const errorBody = await response.text();
        console.error("AI request failed", {
          url: `${API_BASE_URL}/api/ask-ai`,
          status: response.status,
          statusText: response.statusText,
          body: errorBody,
        });
        throw new Error(errorBody || "AI request failed.");
      }

      const data = await response.json();
      console.info("AI request succeeded", data);
      return data;
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error("Network error: unable to reach AI backend.");
      }
      throw error;
    }
  }

  async function animateAssistantReply(messageNode, text) {
    const cleanText = (text || "").trim();
    const words = cleanText ? cleanText.split(/\s+/) : [];
    const delayMs = words.length > 120 ? 10 : 20;

    messageNode.textContent = "";
    for (let index = 0; index < words.length; index += 1) {
      messageNode.textContent += `${index ? " " : ""}${words[index]}`;
      aiChatLog.scrollTop = aiChatLog.scrollHeight;
      await new Promise((resolve) => {
        window.setTimeout(resolve, delayMs);
      });
    }
  }

  aiChatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const question = aiChatInput.value.trim();
    if (!question) {
      return;
    }

    aiChatShell.classList.remove("hidden");
    appendChatMessage(question, "user");
    aiChatInput.value = "";

    if (isTalkToKartikIntent(question)) {
      appendContactOptionsMessage();
      askAiFeedback.textContent = "";
      return;
    }

    askAiFeedback.textContent = "Thinking...";

    const typingMessage = document.createElement("div");
    typingMessage.className = "ai-chat-message ai-chat-message-assistant";
    typingMessage.textContent = "Thinking...";
    aiChatLog.appendChild(typingMessage);
    aiChatLog.scrollTop = aiChatLog.scrollHeight;

    try {
      const data = await requestAiAnswer(question);
      await animateAssistantReply(typingMessage, data.answer);
      askAiFeedback.textContent = "";
    } catch (error) {
      console.error("AI chat unavailable", error);
      typingMessage.textContent = error instanceof Error ? error.message : "Unable to get an answer right now.";
      askAiFeedback.textContent = error instanceof Error ? `AI service unavailable: ${error.message}` : "AI service unavailable. Start the FastAPI server and Postgres container.";
    }

    aiChatLog.scrollTop = aiChatLog.scrollHeight;
  });

  aiChatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      aiChatForm.requestSubmit();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeIdentityPanelImmediately();
    }
  });

  document.addEventListener("click", (event) => {
    if (!identityState.isExpanded) {
      return;
    }
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    if (!target.closest("#identity-panel") && !target.closest("#identity-hover-trigger")) {
      closeIdentityPanelImmediately();
    }
  });

  renderIdentityPanel();
}

function initializeOpenToWorkToggle() {
  const toggleButton = document.getElementById("open-to-work-toggle");
  if (!toggleButton) {
    console.warn("Open to Work toggle button not found");
    return;
  }

  // Fetch current status on load
  async function fetchOpenToWorkStatus() {
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/user-status`, {
        method: "GET",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Status ${response.status}`);
      }
      const data = await response.json();
      updateOpenToWorkUI(data.open_to_work);
      return true;
    } catch (err) {
      console.warn("Open to Work status fetch failed", err);
      return false;
    }
  }

  function updateOpenToWorkUI(isOpen) {
    toggleButton.classList.toggle("active", Boolean(isOpen));
    toggleButton.setAttribute("aria-pressed", String(Boolean(isOpen)));
  }

  toggleButton.addEventListener("click", async () => {
    const isCurrentlyActive = toggleButton.classList.contains("active");
    const newStatus = !isCurrentlyActive;
    const adminKey = window.localStorage.getItem("portfolio.adminApiKey") || window.prompt("Enter admin key to update status:") || "";

    if (!adminKey) {
      return;
    }

    window.localStorage.setItem("portfolio.adminApiKey", adminKey);

    toggleButton.disabled = true;
    updateOpenToWorkUI(newStatus);

    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/user-status`, {
        method: "POST",
        headers: createJsonHeaders({ "x-admin-key": adminKey }),
        body: JSON.stringify({ open_to_work: newStatus }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Status ${response.status}`);
      }

      const data = await response.json();
      updateOpenToWorkUI(data.open_to_work);
    } catch (err) {
      console.error("Failed to update Open to Work status", err);
      updateOpenToWorkUI(isCurrentlyActive);
    } finally {
      toggleButton.disabled = false;
    }
  });

  fetchOpenToWorkStatus();
  window.setInterval(fetchOpenToWorkStatus, 60000);
}

document.addEventListener("DOMContentLoaded", () => {
  initializeBackendTelemetry();
  initializeGitHubCommitCounter();
  initializeAwsConnectionStatus();
  initializeDashboardMetrics();
  initializeIdentityPanel();
  initializeOpenToWorkToggle();
});
