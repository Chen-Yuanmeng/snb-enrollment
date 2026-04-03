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
    return "<p>暂无符合口径的报名统计数据</p>";
  }

  return `
    <table class="stats-table">
      <thead>
        <tr>
          <th>年级</th>
          <th>科目</th>
          <th>线下人数</th>
          <th>线上人数</th>
          <th>合计</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (item) => `
              <tr>
                <td>${item.grade || "-"}</td>
                <td>${item.subject || "-"}</td>
                <td>${Number(item.offline_count || 0)}</td>
                <td>${Number(item.online_count || 0)}</td>
                <td>${Number(item.total_count || 0)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderSummary(summary) {
  const totalRows = Number(summary?.total_rows || 0);
  const totalUnits = Number(summary?.total_enrollment_subject_units || 0);
  const totalOffline = Number(summary?.total_offline || 0);
  const totalOnline = Number(summary?.total_online || 0);
  return `统计行数: ${totalRows}，科目计数单元: ${totalUnits}，线下: ${totalOffline}，线上: ${totalOnline}`;
}

async function loadStats() {
  statsSummary.textContent = "加载中...";
  statsTableWrap.textContent = "加载中...";
  try {
    const result = await fetchJson(`${API_BASE}/enrollments/stats`);
    const rows = result.data?.rows || [];
    const summary = result.data?.summary || {};
    statsSummary.textContent = renderSummary(summary);
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
