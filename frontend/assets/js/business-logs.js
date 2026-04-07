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

const operatorNameFilter = document.querySelector("#operatorNameFilter");
const sourceFilter = document.querySelector("#sourceFilter");
const actionTypeFilter = document.querySelector("#actionTypeFilter");
const targetTypeFilter = document.querySelector("#targetTypeFilter");
const pageSizeFilter = document.querySelector("#pageSizeFilter");
const refreshBtn = document.querySelector("#refreshBtn");
const logTableWrap = document.querySelector("#logTableWrap");
const logPagination = document.querySelector("#logPagination");

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

function formatDateTime(value) {
  if (!value) return "-";
  const raw = String(value).trim();
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}

function totalPages() {
  const pages = Math.ceil((state.total || 0) / state.pageSize);
  return Math.max(pages, 1);
}

function toPageInRange(rawPage) {
  const page = Number(rawPage);
  if (!Number.isFinite(page)) return null;
  const normalized = Math.floor(page);
  if (normalized < 1) return null;
  return Math.min(normalized, totalPages());
}

function renderPagination() {
  if (!logPagination) return;
  if (!state.total) {
    logPagination.innerHTML = "";
    return;
  }

  const pages = totalPages();
  logPagination.innerHTML = `
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
    logTableWrap.innerHTML = state.page > 1 ? "<p>当前页暂无记录</p>" : "<p>暂无记录</p>";
    return;
  }

  logTableWrap.innerHTML = `
    <table class='stats-table log-table'>
      <thead>
        <tr>
          <th>ID</th>
          <th>时间</th>
          <th>操作员</th>
          <th>来源</th>
          <th>动作</th>
          <th>目标</th>
          <th>结果</th>
          <th>说明</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (item) => `
          <tr>
            <td>${item.id ?? "-"}</td>
            <td>${formatDateTime(item.created_at)}</td>
            <td>${item.operator_name || "-"}</td>
            <td>${item.source || "-"}</td>
            <td>${item.action_type || "-"}</td>
            <td>${item.target_type || "-"}${item.target_id ? `#${item.target_id}` : ""}</td>
            <td>${item.result_status || "-"}</td>
            <td class='log-message'>${item.message || "-"}</td>
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

  const operatorName = operatorNameFilter.value.trim();
  const source = sourceFilter.value.trim();
  const actionType = actionTypeFilter.value.trim();
  const targetType = targetTypeFilter.value.trim();

  if (operatorName) query.append("operator_name", operatorName);
  if (source) query.append("source", source);
  if (actionType) query.append("action_type", actionType);
  if (targetType) query.append("target_type", targetType);

  return query;
}

async function loadLogs() {
  if (state.isLoading) return;
  state.isLoading = true;

  logTableWrap.textContent = "加载中...";
  try {
    const query = buildQuery();
    const result = await fetchJson(`${API_BASE}/logs?${query.toString()}`);
    const rows = Array.isArray(result.data) ? result.data : [];

    state.total = Number(result.total || rows.length || 0);
    if (state.page > totalPages()) {
      state.page = totalPages();
    }

    renderRows(rows);
    renderPagination();
  } catch (error) {
    logTableWrap.innerHTML = `<p>加载失败：${error.message}</p>`;
    state.total = 0;
    renderPagination();
  } finally {
    state.isLoading = false;
  }
}

refreshBtn.addEventListener("click", () => {
  state.page = 1;
  state.pageSize = Number(pageSizeFilter.value || 20);
  loadLogs();
});

logPagination.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  if (target.getAttribute("data-action") === "jump") {
    const input = logPagination.querySelector(".pagination-jump-input");
    if (!(input instanceof HTMLInputElement)) return;
    const page = toPageInRange(input.value);
    if (!page || page === state.page) return;
    state.page = page;
    loadLogs();
    return;
  }

  const page = Number(target.getAttribute("data-page") || 0);
  if (!Number.isFinite(page) || page < 1 || page === state.page) {
    return;
  }

  state.page = page;
  loadLogs();
});

async function init() {
  try {
    await resolveApiBase();
  } catch (error) {
    logTableWrap.innerHTML = `<p>${error.message}</p>`;
    return;
  }
  state.pageSize = Number(pageSizeFilter.value || 20);
  await loadLogs();
}

init();
