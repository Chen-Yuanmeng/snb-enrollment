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
const keywordInput = document.querySelector("#keyword");
const taskTypeSelect = document.querySelector("#taskType");
const taskStatusSelect = document.querySelector("#taskStatus");
const refreshBtn = document.querySelector("#refreshBtn");
const taskSummary = document.querySelector("#taskSummary");
const taskList = document.querySelector("#taskList");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

let rawTasks = [];

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

function mustOperator() {
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

function taskTypeText(type) {
  if (type === "increase") return "待补交确认";
  if (type === "decrease") return "待退费确认";
  if (type === "equal") return "金额不变调整";
  return type || "-";
}

function taskStatusText(status) {
  if (status === "pending") return "未调整";
  if (status === "adjusted") return "已调整";
  return status || "-";
}

function isPendingStatus(status) {
  return status === "pending";
}

function filteredTasks() {
  const pickedType = taskTypeSelect.value;
  const pickedStatus = taskStatusSelect.value;

  return rawTasks.filter((item) => {
    if (pickedType && item.task_type !== pickedType) {
      return false;
    }
    if (!pickedStatus) {
      return true;
    }
    if (pickedStatus === "pending") {
      return isPendingStatus(item.status);
    }
    if (pickedStatus === "confirmed") {
      return !isPendingStatus(item.status);
    }
    return true;
  });
}

function renderTaskSummary(rows) {
  const pendingCount = rows.filter((item) => isPendingStatus(item.status)).length;
  const confirmedCount = rows.length - pendingCount;
  const increaseCount = rows.filter((item) => item.task_type === "increase").length;
  const decreaseCount = rows.filter((item) => item.task_type === "decrease").length;
  const equalCount = rows.filter((item) => item.task_type === "equal").length;
  taskSummary.textContent = `共 ${rows.length} 条，未调整 ${pendingCount} 条，已调整 ${confirmedCount} 条；补交 ${increaseCount} 条，退费 ${decreaseCount} 条，金额不变 ${equalCount} 条`;
}

function renderTasks() {
  const rows = filteredTasks();
  renderTaskSummary(rows);

  if (rows.length === 0) {
    taskList.innerHTML = "<p>当前筛选条件下暂无记录</p>";
    return;
  }

  taskList.innerHTML = rows
    .map((item) => {
      const subjects = Array.isArray(item.class_subjects) ? item.class_subjects.join("、") : "-";
      const pending = isPendingStatus(item.status);
      const actionHtml = !pending
        ? "<span class='enrollment-meta'>已调整，无需操作</span>"
        : item.task_type === "decrease"
          ? `<button type='button' data-action='confirm-refund' data-refund-id='${item.refund_id}'>确认已退费</button>`
          : `<button type='button' data-action='confirm-payment' data-enrollment-id='${item.enrollment_id}'>确认调整</button>`;

      return `
        <div class='list-row'>
          <div>
            <div class='enrollment-title-line'>
              <strong>${item.student_name || "-"}</strong>
              <span class='grade-pill'>${item.grade || "-"}</span>
              <span class='source-pill'>${taskTypeText(item.task_type)}</span>
              <span class='source-pill'>${taskStatusText(item.status)}</span>
            </div>
            <div class='enrollment-meta'>原报名ID: ${item.original_enrollment_id || "-"}；补交报名ID: ${item.enrollment_id || "-"}；退费单ID: ${item.refund_id || "-"}</div>
            <div class='enrollment-meta'>科目: ${subjects}</div>
            <div class='enrollment-meta'>需补交: ${formatMoney(item.payable_amount)}；应退费: ${formatMoney(item.refundable_amount)}</div>
            <div class='enrollment-meta'>创建时间: ${formatDateTime(item.created_at)}</div>
          </div>
          <div class='actions'>
            ${actionHtml}
          </div>
        </div>
      `;
    })
    .join("");
}

async function loadTasks() {
  taskSummary.textContent = "加载中...";
  taskList.textContent = "加载中...";
  try {
    const query = new URLSearchParams();
    const keyword = keywordInput.value.trim();
    if (keyword) {
      query.append("keyword", keyword);
    }
    const result = await fetchJson(`${API_BASE}/refunds/adjustments/pending?${query.toString()}`);
    rawTasks = result.data || [];
    renderTasks();
  } catch (error) {
    taskSummary.textContent = "加载失败";
    taskList.textContent = `加载失败: ${error.message}`;
  }
}

async function confirmPayment(enrollmentId) {
  if (!mustOperator()) return;

  const note = window.prompt("可填写确认备注（可留空）", "") || null;
  try {
    await fetchJson(`${API_BASE}/refunds/adjustments/${enrollmentId}/confirm-payment`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator_name: operatorSelect.value,
        source: sourceSelect.value,
        note,
      }),
    });
    await loadTasks();
  } catch (error) {
    alert(`确认补交失败: ${error.message}`);
  }
}

async function confirmRefund(refundId) {
  if (!mustOperator()) return;

  const note = window.prompt("可填写退费备注（可留空）", "") || null;
  try {
    await fetchJson(`${API_BASE}/refunds/${refundId}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator_name: operatorSelect.value,
        source: sourceSelect.value,
        note,
      }),
    });
    await loadTasks();
  } catch (error) {
    alert(`确认退费失败: ${error.message}`);
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

refreshBtn.addEventListener("click", loadTasks);
taskTypeSelect.addEventListener("change", renderTasks);
taskStatusSelect.addEventListener("change", renderTasks);
keywordInput.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  await loadTasks();
});
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});
taskList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  const confirmPaymentBtn = target.closest("button[data-action='confirm-payment']");
  if (confirmPaymentBtn) {
    const enrollmentId = Number(confirmPaymentBtn.getAttribute("data-enrollment-id") || 0);
    if (enrollmentId > 0) {
      await confirmPayment(enrollmentId);
    }
    return;
  }

  const confirmRefundBtn = target.closest("button[data-action='confirm-refund']");
  if (!confirmRefundBtn) return;
  const refundId = Number(confirmRefundBtn.getAttribute("data-refund-id") || 0);
  if (refundId > 0) {
    await confirmRefund(refundId);
  }
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources()]);
    await loadTasks();
  } catch (error) {
    taskSummary.textContent = "初始化失败";
    taskList.textContent = `初始化失败: ${error.message}`;
  }
})();
