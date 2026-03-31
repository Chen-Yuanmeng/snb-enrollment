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
const refreshBtn = document.querySelector("#refreshBtn");
const statsSummary = document.querySelector("#statsSummary");
const statsTableWrap = document.querySelector("#statsTableWrap");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
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

function renderStatsRows(rows) {
  if (!rows || rows.length === 0) {
    return "<p>暂无已确认住宿数据</p>";
  }

  return `
    <table class="stats-table">
      <thead>
        <tr>
          <th>酒店</th>
          <th>房型</th>
          <th>性别</th>
          <th>人数</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (item) => `
              <tr>
                <td>${item.hotel || "-"}</td>
                <td>${item.room_type_display || item.room_type || "-"}</td>
                <td>${item.gender || "-"}</td>
                <td>${Number(item.student_count || 0)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function loadStats() {
  statsSummary.textContent = "加载中...";
  statsTableWrap.textContent = "加载中...";
  try {
    const result = await fetchJson(`${API_BASE}/accommodations/stats`);
    const rows = result.data?.rows || [];
    const totalConfirmed = Number(result.data?.total_confirmed || 0);
    statsSummary.textContent = `已确认住宿总人数: ${totalConfirmed}`;
    statsTableWrap.innerHTML = renderStatsRows(rows);
  } catch (error) {
    statsSummary.textContent = "加载失败";
    statsTableWrap.textContent = `统计加载失败: ${error.message}`;
  }
}

refreshBtn.addEventListener("click", loadStats);
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources()]);
    await loadStats();
  } catch (error) {
    statsSummary.textContent = "页面初始化失败";
    statsTableWrap.textContent = error.message;
  }
})();
