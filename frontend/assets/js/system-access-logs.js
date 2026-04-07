let API_BASE = `${window.location.origin}/api/v1`;

function apiCandidates() {
  const candidates = [`${window.location.origin}/api/v1`];
  if (!window.location.origin.includes(":5555")) {
    candidates.push(`${window.location.protocol}//${window.location.hostname}:5555/api/v1`);
    candidates.push("http://127.0.0.1:5555/api/v1");
    candidates.push("http://localhost:5555/api/v1");
  }
  if (!window.location.origin.includes(":3030")) {
    candidates.push(`${window.location.protocol}//${window.location.hostname}:3030/api/v1`);
    candidates.push("http://127.0.0.1:3030/api/v1");
    candidates.push("http://localhost:3030/api/v1");
  }
  return [...new Set(candidates)];
}

async function resolveApiBase() {
  for (const base of apiCandidates()) {
    try {
      const response = await fetch(`${base}/operators`);
      if (!response.ok) {
        continue;
      }
      const data = await response.json();
      if (data && Array.isArray(data.data)) {
        API_BASE = base;
        return;
      }
    } catch (_) {
      // try next candidate
    }
  }
  throw new Error("无法连接后端API，请确认3030服务可访问");
}

const sinceFilter = document.querySelector("#sinceFilter");
const untilFilter = document.querySelector("#untilFilter");
const ipFilter = document.querySelector("#ipFilter");
const methodFilter = document.querySelector("#methodFilter");
const pathKeywordFilter = document.querySelector("#pathKeywordFilter");
const statusCodeFilter = document.querySelector("#statusCodeFilter");
const pageSizeFilter = document.querySelector("#pageSizeFilter");
const refreshBtn = document.querySelector("#refreshBtn");
const accessTableWrap = document.querySelector("#accessTableWrap");
const accessPagination = document.querySelector("#accessPagination");

const state = {
  page: 1,
  pageSize: 20,
  total: 0,
  isLoading: false,
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || (data.code && data.code !== 0)) {
    const detail =
      typeof data.detail === "object" && data.detail?.message
        ? data.detail.message
        : data.detail;
    throw new Error(detail || data.message || "请求失败");
  }
  return data;
}

function toApiDateTime(value) {
  if (!value) return "";
  return `${value.replace("T", " ")}:00`;
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}

function totalPages() {
  const pages = Math.ceil((state.total || 0) / state.pageSize);
  return Math.max(pages, 1);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toPageInRange(rawPage) {
  const page = Number(rawPage);
  if (!Number.isFinite(page)) return null;
  const normalized = Math.floor(page);
  if (normalized < 1) return null;
  return Math.min(normalized, totalPages());
}

function renderPagination() {
  if (!accessPagination) return;

  if (!state.total) {
    accessPagination.innerHTML = "";
    return;
  }

  const pages = totalPages();
  accessPagination.innerHTML = `
    <div class='pagination-controls'>
      <button type='button' class='pagination-btn pagination-nav-btn' data-page='${state.page - 1}' ${state.page <= 1 ? "disabled" : ""}>上一页</button>
      <span class='pagination-summary'>第 ${state.page}/${pages} 页，共 ${state.total} 条</span>
      <button type='button' class='pagination-btn pagination-nav-btn' data-page='${state.page + 1}' ${state.page >= pages ? "disabled" : ""}>下一页</button>
      <span class='pagination-jump'>
        <span class='pagination-jump-label'>跳转到</span>
        <input class='pagination-jump-input' type='number' min='1' max='${pages}' value='${state.page}' />
        <button type='button' class='pagination-btn pagination-jump-btn' data-action='jump'>前往</button>
      </span>
    </div>
  `;
}

function renderRows(rows) {
  if (!rows.length) {
    accessTableWrap.innerHTML = state.page > 1 ? "<p>当前页暂无记录</p>" : "<p>暂无记录</p>";
    return;
  }

  accessTableWrap.innerHTML = `
    <table class='stats-table log-table'>
      <thead>
        <tr>
          <th>时间</th>
          <th>IP</th>
          <th>方法</th>
          <th>路径</th>
          <th>状态码</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (item) => `
          <tr>
            <td>${formatDateTime(item.timestamp)}</td>
            <td>
              ${
                item.ip
                  ? `<button type='button' class='table-link-btn ip-link-btn' data-ip='${escapeHtml(item.ip)}'>${escapeHtml(item.ip)}</button>`
                  : "-"
              }
            </td>
            <td>${escapeHtml(item.method || "-")}</td>
            <td class='log-message'>${escapeHtml(item.path || "-")}</td>
            <td>${escapeHtml(item.status_code || "-")}</td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function buildQuery() {
  const query = new URLSearchParams();
  query.append("page", String(state.page));
  query.append("page_size", String(state.pageSize));

  const since = toApiDateTime(sinceFilter.value);
  const until = toApiDateTime(untilFilter.value);
  const ip = ipFilter.value.trim();
  const method = methodFilter.value.trim();
  const pathKeyword = pathKeywordFilter.value.trim();
  const statusCode = Number(statusCodeFilter.value || 0);

  if (since) query.append("since", since);
  if (until) query.append("until", until);
  if (ip) query.append("ip", ip);
  if (method) query.append("method", method);
  if (pathKeyword) query.append("path_keyword", pathKeyword);
  if (Number.isFinite(statusCode) && statusCode >= 100 && statusCode <= 599) {
    query.append("status_code", String(statusCode));
  }

  return query;
}

async function loadAccessLogs() {
  if (state.isLoading) return;
  state.isLoading = true;

  accessTableWrap.textContent = "加载中...";
  try {
    const query = buildQuery();
    const result = await fetchJson(`${API_BASE}/system-access-logs?${query.toString()}`);
    const rows = Array.isArray(result.data) ? result.data : [];

    state.total = Number(result.total || rows.length || 0);
    if (state.page > totalPages()) {
      state.page = totalPages();
    }

    renderRows(rows);
    renderPagination();
  } catch (error) {
    accessTableWrap.innerHTML = `<p>加载失败：${error.message}</p>`;
    state.total = 0;
    renderPagination();
  } finally {
    state.isLoading = false;
  }
}

refreshBtn.addEventListener("click", () => {
  state.page = 1;
  state.pageSize = Number(pageSizeFilter.value || 20);
  loadAccessLogs();
});

accessPagination.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  if (target.getAttribute("data-action") === "jump") {
    const input = accessPagination.querySelector(".pagination-jump-input");
    if (!(input instanceof HTMLInputElement)) return;
    const page = toPageInRange(input.value);
    if (!page || page === state.page) return;
    state.page = page;
    loadAccessLogs();
    return;
  }

  const page = Number(target.getAttribute("data-page") || 0);
  if (!Number.isFinite(page) || page < 1 || page === state.page) {
    return;
  }

  state.page = page;
  loadAccessLogs();
});

accessTableWrap.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.classList.contains("ip-link-btn")) return;

  const ip = target.getAttribute("data-ip") || "";
  if (!ip) return;
  window.location.href = `./ip-access-analysis.html?ip=${encodeURIComponent(ip)}`;
});

async function init() {
  try {
    await resolveApiBase();
  } catch (error) {
    accessTableWrap.innerHTML = `<p>${error.message}</p>`;
    return;
  }

  state.pageSize = Number(pageSizeFilter.value || 20);
  await loadAccessLogs();
}

init();
