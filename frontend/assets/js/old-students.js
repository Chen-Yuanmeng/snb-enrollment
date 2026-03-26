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
    historyList.innerHTML = "<p>暂无老生记录</p>";
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

async function searchHistory() {
  historyList.textContent = "加载中...";
  try {
    const query = new URLSearchParams();
    const keyword = searchKeywordInput.value.trim();
    const grade = searchGradeInput.value.trim();
    if (keyword) {
      query.append("keyword", keyword);
    }
    if (grade) {
      query.append("grade", grade);
    }

    const result = await fetchJson(`${API_BASE}/students-history?${query.toString()}`);
    renderHistoryRows(result.data || []);
  } catch (error) {
    historyList.textContent = `查询失败: ${error.message}`;
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
}

async function loadSources() {
  const result = await fetchJson(`${API_BASE}/sources`);
  sourceSelect.innerHTML = [`<option value=''>请选择</option>`]
    .concat((result.data || []).map((item) => `<option value='${item.name}'>${item.name}</option>`))
    .join("");
}

searchBtn.addEventListener("click", searchHistory);
resetBtn.addEventListener("click", async () => {
  searchKeywordInput.value = "";
  searchGradeInput.value = "";
  await searchHistory();
});
createForm.addEventListener("submit", createHistory);

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources()]);
    await searchHistory();
  } catch (error) {
    historyList.textContent = `初始化失败: ${error.message}`;
  }
})();
