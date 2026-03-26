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
const gradeFilter = document.querySelector("#gradeFilter");
const statusFilter = document.querySelector("#statusFilter");
const refreshBtn = document.querySelector("#refreshBtn");
const enrollmentList = document.querySelector("#enrollmentList");

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

function statusText(status) {
  if (status === "quoted") return "已报价";
  if (status === "paid") return "已缴费";
  if (status === "refund_requested") return "退费申请中";
  if (status === "refunded") return "已退费";
  return status;
}

function statusClass(status) {
  if (status === "quoted") return "status-quoted";
  if (status === "paid") return "status-paid";
  return "";
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}

function formatMoney(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return `¥${num.toFixed(2)}`;
}

function renderQuoteInfo(item) {
  const discountInfo = item.discount_info && typeof item.discount_info === "object" ? item.discount_info : {};
  const discountTotal = Number(item.discount_total);
  const finalPrice = Number(item.final_price);
  const hasDiscountTotal = Number.isFinite(discountTotal);
  const hasFinalPrice = Number.isFinite(finalPrice);
  const basePrice = Number.isFinite(Number(item.base_price))
    ? Number(item.base_price)
    : hasFinalPrice && hasDiscountTotal
      ? finalPrice + discountTotal
      : hasFinalPrice
        ? finalPrice
        : NaN;

  const discountLines = Object.entries(discountInfo)
    .filter(([, amount]) => Number(amount) > 0)
    .map(([name, amount]) => `${name} -${formatMoney(amount)}`);

  const summary = `原价 ${formatMoney(basePrice)}，优惠 ${formatMoney(hasDiscountTotal ? discountTotal : 0)}，实收 ${formatMoney(finalPrice)}`;
  if (discountLines.length === 0) {
    return summary;
  }
  return `${summary}；明细：${discountLines.join("；")}`;
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

async function loadRules() {
  const result = await fetchJson(`${API_BASE}/rules/meta`);
  const grades = result.data?.grades || [];
  gradeFilter.innerHTML = [`<option value=''>全部年级</option>`]
    .concat(grades.map((grade) => `<option value='${grade}'>${grade}</option>`))
    .join("");
}

async function payEnrollment(id) {
  if (!mustOperator()) return;

  try {
    await fetchJson(`${API_BASE}/enrollments/${id}/pay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator_name: operatorSelect.value,
        source: sourceSelect.value,
        note: "前端报价管理页面确认缴费",
      }),
    });
    await loadEnrollments();
  } catch (error) {
    alert(`确认缴费失败: ${error.message}`);
  }
}

async function loadEnrollments() {
  enrollmentList.textContent = "加载中...";
  try {
    const query = new URLSearchParams();
    if (statusFilter.value) query.append("status", statusFilter.value);
    if (gradeFilter.value) query.append("grade", gradeFilter.value);

    const result = await fetchJson(`${API_BASE}/enrollments?${query.toString()}`);
    const rows = result.data || [];

    if (rows.length === 0) {
      enrollmentList.innerHTML = "<p>暂无记录</p>";
      return;
    }

    enrollmentList.innerHTML = rows
      .map((item) => {
        const canPay = item.status === "quoted";
        const subjects = Array.isArray(item.class_subjects) ? item.class_subjects.join("、") : "-";
        return `
          <div class='list-row'>
            <div>
              <strong>#${item.id}</strong><br />
              学生姓名: ${item.student_name || "-"}<br />
              年级: ${item.grade || "-"}<br />
              所报科目: ${subjects}<br />
              报名时间: ${formatDateTime(item.created_at)}<br />
              报价信息: ${renderQuoteInfo(item)}<br />
              来源: ${item.source || "-"}
              <span class='status-pill ${statusClass(item.status)}'>${statusText(item.status)}</span>
            </div>
            ${
              canPay
                ? `<div class='actions'><button type='button' data-pay-id='${item.id}'>确认缴费</button></div>`
                : ""
            }
          </div>
        `;
      })
      .join("");

    enrollmentList.querySelectorAll("button[data-pay-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = Number(button.getAttribute("data-pay-id"));
        payEnrollment(id);
      });
    });
  } catch (error) {
    enrollmentList.textContent = `加载失败: ${error.message}`;
  }
}

refreshBtn.addEventListener("click", loadEnrollments);
gradeFilter.addEventListener("change", loadEnrollments);
statusFilter.addEventListener("change", loadEnrollments);

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources(), loadRules()]);
    await loadEnrollments();
  } catch (error) {
    enrollmentList.textContent = `初始化失败: ${error.message}`;
  }
})();
