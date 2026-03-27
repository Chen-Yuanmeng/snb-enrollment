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
const enrollmentPagination = document.querySelector("#enrollmentPagination");

const enrollmentState = {
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

function totalPages() {
  const pages = Math.ceil((enrollmentState.total || 0) / enrollmentState.pageSize);
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

function renderEnrollmentPagination() {
  if (!enrollmentPagination) return;

  if (!enrollmentState.total) {
    enrollmentPagination.innerHTML = "";
    return;
  }

  const current = enrollmentState.page;
  const pages = totalPages();
  const numbers = pageNumbers(current, pages);

  enrollmentPagination.innerHTML = `
    <div class='pagination-controls'>
      <button type='button' class='pagination-btn pagination-nav-btn' data-enrollment-page='${current - 1}' ${current <= 1 ? "disabled" : ""}>上一页</button>
      ${numbers
        .map(
          (p) =>
            `<button type='button' class='pagination-btn pagination-page-btn ${p === current ? "current" : ""}' data-enrollment-page='${p}' ${
              p === current ? "disabled" : ""
            }>${p}</button>`
        )
        .join("")}
      <button type='button' class='pagination-btn pagination-nav-btn' data-enrollment-page='${current + 1}' ${current >= pages ? "disabled" : ""}>下一页</button>
      <div class='pagination-jump'>
        <label for='enrollmentJumpInput' class='pagination-jump-label'>跳转</label>
        <input id='enrollmentJumpInput' class='pagination-jump-input' type='number' min='1' max='${pages}' value='${current}' />
        <button type='button' class='pagination-btn pagination-jump-btn' data-enrollment-jump='1'>跳转</button>
      </div>
      <span class='pagination-summary'>第 ${current}/${pages} 页，共 ${enrollmentState.total} 条</span>
    </div>
  `;
}

function parseEnrollmentJumpPage() {
  if (!enrollmentPagination) return null;
  const input = enrollmentPagination.querySelector("#enrollmentJumpInput");
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

async function loadEnrollments() {
  if (enrollmentState.isLoading) return;

  enrollmentState.isLoading = true;
  enrollmentList.textContent = "加载中...";
  try {
    const query = new URLSearchParams();
    query.append("page", String(enrollmentState.page));
    query.append("page_size", String(enrollmentState.pageSize));
    if (statusFilter.value) query.append("status", statusFilter.value);
    if (gradeFilter.value) query.append("grade", gradeFilter.value);

    const result = await fetchJson(`${API_BASE}/enrollments?${query.toString()}`);
    const rows = parseRows(result);
    enrollmentState.total = parseTotal(result, rows);
    if (enrollmentState.page > totalPages()) {
      enrollmentState.page = totalPages();
    }

    if (rows.length === 0) {
      enrollmentList.innerHTML = enrollmentState.page > 1 ? "<p>当前页暂无记录</p>" : "<p>暂无记录</p>";
      renderEnrollmentPagination();
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
    renderEnrollmentPagination();
  } catch (error) {
    enrollmentList.textContent = `加载失败: ${error.message}`;
    if (enrollmentPagination) {
      enrollmentPagination.innerHTML = "";
    }
  } finally {
    enrollmentState.isLoading = false;
  }
}

refreshBtn.addEventListener("click", loadEnrollments);
gradeFilter.addEventListener("change", async () => {
  enrollmentState.page = 1;
  await loadEnrollments();
});
statusFilter.addEventListener("change", async () => {
  enrollmentState.page = 1;
  await loadEnrollments();
});
enrollmentList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const button = target.closest("button[data-pay-id]");
  if (!button) return;
  const id = Number(button.getAttribute("data-pay-id"));
  if (!Number.isFinite(id)) return;
  await payEnrollment(id);
});
enrollmentPagination?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  const jumpButton = target.closest("button[data-enrollment-jump]");
  if (jumpButton) {
    const jumpPage = parseEnrollmentJumpPage();
    if (!jumpPage || jumpPage === enrollmentState.page) return;
    enrollmentState.page = jumpPage;
    await loadEnrollments();
    return;
  }

  const button = target.closest("button[data-enrollment-page]");
  if (!button) return;

  const nextPage = Number(button.getAttribute("data-enrollment-page"));
  if (!Number.isFinite(nextPage)) return;
  const pages = totalPages();
  const normalized = Math.max(1, Math.min(nextPage, pages));
  if (normalized === enrollmentState.page) return;
  enrollmentState.page = normalized;
  await loadEnrollments();
});
enrollmentPagination?.addEventListener("keydown", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (event.key !== "Enter") return;
  if (!(target instanceof HTMLInputElement) || target.id !== "enrollmentJumpInput") return;

  event.preventDefault();
  const jumpPage = parseEnrollmentJumpPage();
  if (!jumpPage || jumpPage === enrollmentState.page) return;
  enrollmentState.page = jumpPage;
  await loadEnrollments();
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources(), loadRules()]);
    await loadEnrollments();
  } catch (error) {
    enrollmentList.textContent = `初始化失败: ${error.message}`;
  }
})();
