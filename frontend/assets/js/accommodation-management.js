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
      if (!response.ok) continue;
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

const operatorSelect = document.querySelector("#operator");
const sourceSelect = document.querySelector("#source");
const keywordFilter = document.querySelector("#keywordFilter");
const statusFilter = document.querySelector("#statusFilter");
const hotelFilter = document.querySelector("#hotelFilter");
const refreshBtn = document.querySelector("#refreshBtn");
const accommodationList = document.querySelector("#accommodationList");
const accommodationPagination = document.querySelector("#accommodationPagination");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

const state = {
  page: 1,
  pageSize: 20,
  total: 0,
  isLoading: false,
};

function readStoredValue(key) {
  try {
    return window.localStorage.getItem(key) || "";
  } catch (_) {
    return "";
  }
}

function writeStoredValue(key, value) {
  try {
    window.localStorage.setItem(key, value || "");
  } catch (_) {
    // ignore storage errors
  }
}

function restoreSelectValue(select, key) {
  const value = readStoredValue(key);
  if (!value) return;
  const optionExists = [...select.options].some((item) => item.value === value);
  if (optionExists) {
    select.value = value;
  }
}

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

function mustOperatorAndSource() {
  if (!operatorSelect.value) {
    alert("请先选择操作员");
    return false;
  }
  if (!sourceSelect.value) {
    alert("请先选择来源");
    return false;
  }
  return true;
}

function statusText(status) {
  if (status === "generated") return "已生成";
  if (status === "confirmed") return "已确认";
  if (status === "cancelled") return "已取消";
  if (status === "partial_refunded") return "已部分退费";
  return status || "-";
}

function statusClass(status) {
  if (status === "generated") return "status-quoted";
  if (status === "confirmed") return "status-paid";
  return "";
}

function formatDateTime(value) {
  if (!value) return "-";
  const raw = String(value).trim();
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}

function formatMoney(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return `¥${num.toFixed(2)}`;
}

function totalPages() {
  const pages = Math.ceil((state.total || 0) / state.pageSize);
  return Math.max(pages, 1);
}

function pageNumbers(current, total) {
  const start = Math.max(1, current - 2);
  const end = Math.min(total, current + 2);
  const pages = [];
  for (let p = start; p <= end; p += 1) {
    pages.push(p);
  }
  return pages;
}

function renderPagination() {
  if (!accommodationPagination) return;
  if (!state.total) {
    accommodationPagination.innerHTML = "";
    return;
  }

  const current = state.page;
  const pages = totalPages();
  const numbers = pageNumbers(current, pages);
  accommodationPagination.innerHTML = `
    <div class='pagination-controls'>
      <button type='button' class='pagination-btn pagination-nav-btn' data-page='${current - 1}' ${current <= 1 ? "disabled" : ""}>上一页</button>
      ${numbers
        .map(
          (p) =>
            `<button type='button' class='pagination-btn pagination-page-btn ${p === current ? "current" : ""}' data-page='${p}' ${
              p === current ? "disabled" : ""
            }>${p}</button>`
        )
        .join("")}
      <button type='button' class='pagination-btn pagination-nav-btn' data-page='${current + 1}' ${current >= pages ? "disabled" : ""}>下一页</button>
      <span class='pagination-summary'>第 ${current}/${pages} 页，共 ${state.total} 条</span>
    </div>
  `;
}

function parseRows(result) {
  if (Array.isArray(result.data)) return result.data;
  if (result.data && Array.isArray(result.data.items)) return result.data.items;
  return [];
}

function parseTotal(result, rows) {
  if (Number.isFinite(Number(result.total))) return Number(result.total);
  if (result.data && Number.isFinite(Number(result.data.total))) return Number(result.data.total);
  return rows.length;
}

async function loadAccommodationRule() {
  const result = await fetchJson(`${API_BASE}/rules/accommodation`);
  const hotels = Array.isArray(result.data?.hotels) ? result.data.hotels : [];
  hotelFilter.innerHTML = [`<option value=''>全部酒店</option>`]
    .concat(hotels.map((item) => `<option value='${item}'>${item}</option>`))
    .join("");
}

async function loadOperators() {
  const result = await fetchJson(`${API_BASE}/operators`);
  operatorSelect.innerHTML = [`<option value=''>请选择</option>`]
    .concat((result.data || []).map((item) => `<option value='${item.name}'>${item.name}</option>`))
    .join("");
  restoreSelectValue(operatorSelect, STORAGE_KEYS.operator);
}

async function loadSources() {
  const result = await fetchJson(`${API_BASE}/sources`);
  sourceSelect.innerHTML = [`<option value=''>请选择</option>`]
    .concat((result.data || []).map((item) => `<option value='${item.name}'>${item.name}</option>`))
    .join("");
  restoreSelectValue(sourceSelect, STORAGE_KEYS.source);
}

async function updateStatus(id, status) {
  if (!mustOperatorAndSource()) return;

  const actionText = status === "confirmed" ? "确认交费" : "取消";
  const ok = window.confirm(`确认将住宿单 #${id} 标记为${actionText}吗？`);
  if (!ok) return;

  try {
    await fetchJson(`${API_BASE}/accommodations/${id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator_name: operatorSelect.value,
        source: sourceSelect.value,
        status,
      }),
    });
    await loadAccommodations();
  } catch (error) {
    alert(`状态更新失败: ${error.message}`);
  }
}

async function loadAccommodations() {
  if (state.isLoading) return;

  state.isLoading = true;
  accommodationList.textContent = "加载中...";

  try {
    const query = new URLSearchParams();
    query.append("page", String(state.page));
    query.append("page_size", String(state.pageSize));
    if (statusFilter.value) query.append("status", statusFilter.value);
    if (hotelFilter.value) query.append("hotel", hotelFilter.value);
    const keyword = keywordFilter.value.trim();
    if (keyword) query.append("keyword", keyword);

    const result = await fetchJson(`${API_BASE}/accommodations?${query.toString()}`);
    const rows = parseRows(result);
    state.total = parseTotal(result, rows);
    if (state.page > totalPages()) {
      state.page = totalPages();
    }

    if (rows.length === 0) {
      accommodationList.innerHTML = state.page > 1 ? "<p>当前页暂无记录</p>" : "<p>暂无记录</p>";
      renderPagination();
      return;
    }

    accommodationList.innerHTML = rows
      .map((item) => {
        const canConfirm = item.status === "generated";
        const canCancel = item.status === "generated" || item.status === "confirmed";

        return `
          <div class='list-row'>
            <div>
              <div class='enrollment-title-line'>
                <strong>#${item.id} ${item.student_name || "-"}</strong>
                <span class='grade-pill'>关联课程单 #${item.related_enrollment_id}</span>
                <span class='amount-pill'>住宿金额 ${formatMoney(item.total_price)}</span>
                <span class='status-pill ${statusClass(item.status)}'>${statusText(item.status)}</span>
              </div>
              <div class='enrollment-meta'>酒店/房型: ${item.hotel || "-"} / ${item.room_type_display || item.room_type || "-"}</div>
              <div class='enrollment-meta'>时长/性别: ${item.duration_label || item.duration_days + "天"} / ${item.gender || "-"}</div>
              <div class='enrollment-meta'>每晚价格: ${formatMoney(item.nightly_price)}；来源: ${item.source || "-"}</div>
              <div class='enrollment-meta'>备注: ${item.note || "-"}</div>
              <div class='enrollment-meta'>创建时间: ${formatDateTime(item.created_at)}</div>
            </div>
            <div class='actions'>
              ${canConfirm ? `<button type='button' data-status-id='${item.id}' data-next-status='confirmed'>确认交费</button>` : ""}
              ${canCancel ? `<button type='button' data-status-id='${item.id}' data-next-status='cancelled' class='secondary'>取消</button>` : ""}
            </div>
          </div>
        `;
      })
      .join("");
    renderPagination();
  } catch (error) {
    accommodationList.textContent = `加载失败: ${error.message}`;
    if (accommodationPagination) accommodationPagination.innerHTML = "";
  } finally {
    state.isLoading = false;
  }
}

refreshBtn.addEventListener("click", async () => {
  state.page = 1;
  await loadAccommodations();
});
keywordFilter.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  state.page = 1;
  await loadAccommodations();
});
statusFilter.addEventListener("change", async () => {
  state.page = 1;
  await loadAccommodations();
});
hotelFilter.addEventListener("change", async () => {
  state.page = 1;
  await loadAccommodations();
});
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});
accommodationList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const button = target.closest("button[data-status-id]");
  if (!button) return;
  const id = Number(button.getAttribute("data-status-id"));
  const nextStatus = button.getAttribute("data-next-status");
  if (!Number.isFinite(id) || !nextStatus) return;
  await updateStatus(id, nextStatus);
});
accommodationPagination?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const button = target.closest("button[data-page]");
  if (!button) return;

  const nextPage = Number(button.getAttribute("data-page"));
  if (!Number.isFinite(nextPage)) return;
  const pages = totalPages();
  const normalized = Math.max(1, Math.min(nextPage, pages));
  if (normalized === state.page) return;
  state.page = normalized;
  await loadAccommodations();
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources(), loadAccommodationRule()]);
    await loadAccommodations();
  } catch (error) {
    accommodationList.textContent = `页面初始化失败: ${error.message}`;
  }
})();
