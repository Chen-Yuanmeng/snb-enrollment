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

const operatorSelect = document.querySelector("#operator");
const sourceSelect = document.querySelector("#source");
const searchKeywordInput = document.querySelector("#searchKeyword");
const searchGradeInput = document.querySelector("#searchGrade");
const searchBtn = document.querySelector("#searchBtn");
const resetBtn = document.querySelector("#resetBtn");
const createForm = document.querySelector("#createForm");
const newNameInput = document.querySelector("#newName");
const newGradeInput = document.querySelector("#newGrade");
const newPhoneSuffixInput = document.querySelector("#newPhoneSuffix");
const newNoteInput = document.querySelector("#newNote");
const historyList = document.querySelector("#historyList");
const historyPagination = document.querySelector("#historyPagination");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

const historyState = {
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
  if (!value) {
    return;
  }
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

function renderHistoryRows(rows) {
  if (!rows || rows.length === 0) {
    historyList.innerHTML = historyState.page > 1 ? "<p>当前页暂无老生记录</p>" : "<p>暂无老生记录</p>";
    return;
  }

  historyList.innerHTML = rows
    .map((item) => {
      const createdAt = item.created_at ? new Date(item.created_at).toLocaleString() : "-";
      return `
        <div class='list-row'>
          <div class='history-main'>
            <strong>#${item.id}</strong> ${item.name}
            <span class='status-pill status-quoted'>${item.grade || "未填写年级"}</span><br />
            手机尾号: ${item.phone_suffix || "-"}<br />
            备注: ${item.note || "-"}<br />
            创建时间: ${createdAt}
          </div>
        </div>
      `;
    })
    .join("");
}

function totalPages() {
  const pages = Math.ceil((historyState.total || 0) / historyState.pageSize);
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

function renderHistoryPagination() {
  if (!historyPagination) return;

  if (!historyState.total) {
    historyPagination.innerHTML = "";
    return;
  }

  const current = historyState.page;
  const pages = totalPages();
  const numbers = pageNumbers(current, pages);

  historyPagination.innerHTML = `
    <div class='pagination-controls'>
      <button type='button' class='pagination-btn pagination-nav-btn' data-history-page='${current - 1}' ${current <= 1 ? "disabled" : ""}>上一页</button>
      ${numbers
        .map(
          (p) =>
            `<button type='button' class='pagination-btn pagination-page-btn ${p === current ? "current" : ""}' data-history-page='${p}' ${
              p === current ? "disabled" : ""
            }>${p}</button>`
        )
        .join("")}
      <button type='button' class='pagination-btn pagination-nav-btn' data-history-page='${current + 1}' ${current >= pages ? "disabled" : ""}>下一页</button>
      <div class='pagination-jump'>
        <label for='historyJumpInput' class='pagination-jump-label'>跳转</label>
        <input id='historyJumpInput' class='pagination-jump-input' type='number' min='1' max='${pages}' value='${current}' />
        <button type='button' class='pagination-btn pagination-jump-btn' data-history-jump='1'>跳转</button>
      </div>
      <span class='pagination-summary'>第 ${current}/${pages} 页，共 ${historyState.total} 条</span>
    </div>
  `;
}

function parseHistoryJumpPage() {
  if (!historyPagination) return null;
  const input = historyPagination.querySelector("#historyJumpInput");
  if (!(input instanceof HTMLInputElement)) return null;
  const value = Number(input.value);
  if (!Number.isFinite(value)) return null;
  const pages = totalPages();
  return Math.max(1, Math.min(Math.trunc(value), pages));
}

function parseRows(result) {
  if (Array.isArray(result.data)) {
    return result.data;
  }
  if (result.data && Array.isArray(result.data.items)) {
    return result.data.items;
  }
  return [];
}

function parseTotal(result, rows) {
  if (Number.isFinite(Number(result.total))) {
    return Number(result.total);
  }
  if (result.data && Number.isFinite(Number(result.data.total))) {
    return Number(result.data.total);
  }
  return rows.length;
}

async function searchHistory() {
  if (historyState.isLoading) return;

  historyState.isLoading = true;
  historyList.textContent = "加载中...";
  try {
    const query = new URLSearchParams();
    const keyword = searchKeywordInput.value.trim();
    const grade = searchGradeInput.value.trim();
    query.append("page", String(historyState.page));
    query.append("page_size", String(historyState.pageSize));
    if (keyword) {
      query.append("keyword", keyword);
    }
    if (grade) {
      query.append("grade", grade);
    }

    const result = await fetchJson(`${API_BASE}/students-history?${query.toString()}`);
    const rows = parseRows(result);
    historyState.total = parseTotal(result, rows);
    if (historyState.page > totalPages()) {
      historyState.page = totalPages();
    }
    renderHistoryRows(rows);
    renderHistoryPagination();
  } catch (error) {
    historyList.textContent = `查询失败: ${error.message}`;
    if (historyPagination) {
      historyPagination.innerHTML = "";
    }
  } finally {
    historyState.isLoading = false;
  }
}

async function createHistory(event) {
  event.preventDefault();
  if (!mustOperatorAndSource()) return;

  const name = newNameInput.value.trim();
  const grade = newGradeInput.value.trim();
  const phoneSuffix = newPhoneSuffixInput.value.trim();
  const note = newNoteInput.value.trim();

  if (!name) {
    alert("老生姓名不能为空");
    return;
  }

  try {
    await fetchJson(`${API_BASE}/students-history`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator_name: operatorSelect.value,
        source: sourceSelect.value,
        name,
        grade: grade || null,
        phone_suffix: phoneSuffix || null,
        note: note || null,
      }),
    });

    newNameInput.value = "";
    newGradeInput.value = "";
    newPhoneSuffixInput.value = "";
    newNoteInput.value = "";

    historyState.page = 1;
    await searchHistory();
    alert("老生新增成功");
  } catch (error) {
    alert(`老生新增失败: ${error.message}`);
  }
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

searchBtn.addEventListener("click", async () => {
  historyState.page = 1;
  await searchHistory();
});
resetBtn.addEventListener("click", async () => {
  searchKeywordInput.value = "";
  searchGradeInput.value = "";
  historyState.page = 1;
  await searchHistory();
});
createForm.addEventListener("submit", createHistory);
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});
historyPagination?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  const jumpButton = target.closest("button[data-history-jump]");
  if (jumpButton) {
    const jumpPage = parseHistoryJumpPage();
    if (!jumpPage || jumpPage === historyState.page) return;
    historyState.page = jumpPage;
    await searchHistory();
    return;
  }

  const button = target.closest("button[data-history-page]");
  if (!button) return;

  const nextPage = Number(button.getAttribute("data-history-page"));
  if (!Number.isFinite(nextPage)) return;
  const pages = totalPages();
  const normalized = Math.max(1, Math.min(nextPage, pages));
  if (normalized === historyState.page) return;
  historyState.page = normalized;
  await searchHistory();
});
historyPagination?.addEventListener("keydown", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (event.key !== "Enter") return;
  if (!(target instanceof HTMLInputElement) || target.id !== "historyJumpInput") return;

  event.preventDefault();
  const jumpPage = parseHistoryJumpPage();
  if (!jumpPage || jumpPage === historyState.page) return;
  historyState.page = jumpPage;
  await searchHistory();
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources()]);
    await searchHistory();
  } catch (error) {
    historyList.textContent = `初始化失败: ${error.message}`;
  }
})();
