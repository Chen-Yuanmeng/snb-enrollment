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
const studentNameFilter = document.querySelector("#studentNameFilter");
const gradeFilter = document.querySelector("#gradeFilter");
const statusFilter = document.querySelector("#statusFilter");
const refreshBtn = document.querySelector("#refreshBtn");
const enrollmentList = document.querySelector("#enrollmentList");
const enrollmentPagination = document.querySelector("#enrollmentPagination");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

const PAID_AT_INPUT_PATTERN = /^\d{2}\.\d{2}\s\d{4}$/;

const enrollmentState = {
  page: 1,
  pageSize: 20,
  total: 0,
  isLoading: false,
};

const modalState = {
  mode: null,
  enrollmentId: null,
  isSubmitting: false,
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

function statusText(status) {
  if (status === "unconfirmed") return "未确认";
  if (status === "confirmed") return "已确认";
  if (status === "cancelled") return "已取消";
  if (status === "pending_adjustment") return "待调整";
  if (status === "adjusted") return "已调整";
  if (status === "increased") return "已增报";
  if (status === "partial_refunded") return "已部分退费";
  if (status === "refunded") return "已退费";
  return status;
}

function statusClass(status) {
  if (status === "unconfirmed" || status === "pending_adjustment") return "status-quoted";
  if (status === "confirmed" || status === "adjusted" || status === "increased") return "status-paid";
  if (status === "cancelled") return "status-cancelled";
  if (status === "partial_refunded") return "status-paid";
  if (status === "refunded") return "status-refunded";
  return "";
}

function parseDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function formatDateTime(value) {
  const date = parseDate(value);
  if (!date) return "-";
  return date.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}

function formatPaidAt(value) {
  const date = parseDate(value);
  if (!date) return "-";
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map((item) => [item.type, item.value]));
  return `${parts.month}.${parts.day} ${parts.hour}:${parts.minute}`;
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

function createActionModal() {
  const modal = document.createElement("div");
  modal.className = "app-modal-backdrop hidden";
  modal.innerHTML = `
    <div class="app-modal-card" role="dialog" aria-modal="true" aria-labelledby="enrollmentActionModalTitle">
      <div class="app-modal-header">
        <h3 id="enrollmentActionModalTitle">报名操作</h3>
        <button type="button" class="secondary app-modal-close" data-role="dismiss">关闭</button>
      </div>
      <div class="app-modal-body">
        <p class="app-modal-text" data-role="description"></p>
        <label class="app-modal-field" data-role="paid-at-wrap">
          交费时间
          <input
            type="text"
            data-role="paid-at-input"
            placeholder="例如 04.29 1530"
            inputmode="numeric"
            autocomplete="off"
          />
        </label>
        <p class="app-modal-error hidden" data-role="error"></p>
      </div>
      <div class="actions app-modal-actions">
        <button type="button" class="secondary" data-role="cancel">取消</button>
        <button type="button" data-role="confirm">确认</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  return {
    root: modal,
    title: modal.querySelector("#enrollmentActionModalTitle"),
    description: modal.querySelector("[data-role='description']"),
    paidAtWrap: modal.querySelector("[data-role='paid-at-wrap']"),
    paidAtInput: modal.querySelector("[data-role='paid-at-input']"),
    error: modal.querySelector("[data-role='error']"),
    confirmBtn: modal.querySelector("[data-role='confirm']"),
    cancelBtn: modal.querySelector("[data-role='cancel']"),
    dismissBtn: modal.querySelector("[data-role='dismiss']"),
  };
}

const actionModal = createActionModal();

function showModalError(message) {
  if (!actionModal.error) return;
  if (!message) {
    actionModal.error.textContent = "";
    actionModal.error.classList.add("hidden");
    return;
  }
  actionModal.error.textContent = message;
  actionModal.error.classList.remove("hidden");
}

function setModalSubmitting(isSubmitting) {
  modalState.isSubmitting = isSubmitting;
  if (actionModal.confirmBtn instanceof HTMLButtonElement) {
    actionModal.confirmBtn.disabled = isSubmitting;
  }
  if (actionModal.cancelBtn instanceof HTMLButtonElement) {
    actionModal.cancelBtn.disabled = isSubmitting;
  }
  if (actionModal.dismissBtn instanceof HTMLButtonElement) {
    actionModal.dismissBtn.disabled = isSubmitting;
  }
  if (actionModal.paidAtInput instanceof HTMLInputElement) {
    actionModal.paidAtInput.disabled = isSubmitting || modalState.mode !== "pay";
  }
}

function closeActionModal(force = false) {
  if (modalState.isSubmitting && !force) return;
  modalState.mode = null;
  modalState.enrollmentId = null;
  modalState.isSubmitting = false;
  actionModal.root.classList.add("hidden");
  showModalError("");
  if (actionModal.paidAtInput instanceof HTMLInputElement) {
    actionModal.paidAtInput.disabled = false;
    actionModal.paidAtInput.value = "";
  }
  if (actionModal.confirmBtn instanceof HTMLButtonElement) {
    actionModal.confirmBtn.disabled = false;
  }
  if (actionModal.cancelBtn instanceof HTMLButtonElement) {
    actionModal.cancelBtn.disabled = false;
  }
  if (actionModal.dismissBtn instanceof HTMLButtonElement) {
    actionModal.dismissBtn.disabled = false;
  }
}

function openPayModal(enrollmentId, studentName) {
  if (!mustOperator()) return;
  modalState.mode = "pay";
  modalState.enrollmentId = enrollmentId;
  actionModal.title.textContent = "确认报名";
  actionModal.description.textContent = `请为报名 #${enrollmentId}${studentName ? `（${studentName}）` : ""}填写交费时间。`;
  actionModal.paidAtWrap.classList.remove("hidden");
  actionModal.confirmBtn.textContent = "确认报名";
  showModalError("");
  setModalSubmitting(false);
  actionModal.root.classList.remove("hidden");
  if (actionModal.paidAtInput instanceof HTMLInputElement) {
    actionModal.paidAtInput.focus();
  }
}

function openCancelModal(enrollmentId, studentName) {
  if (!mustOperator()) return;
  modalState.mode = "cancel";
  modalState.enrollmentId = enrollmentId;
  actionModal.title.textContent = "取消报名";
  actionModal.description.textContent = `确认取消报名 #${enrollmentId}${studentName ? `（${studentName}）` : ""} 吗？取消后状态将变为“已取消”。`;
  actionModal.paidAtWrap.classList.add("hidden");
  actionModal.confirmBtn.textContent = "确认取消";
  showModalError("");
  setModalSubmitting(false);
  actionModal.root.classList.remove("hidden");
}

function validatePaidAtInput(value) {
  const trimmed = String(value || "").trim();
  if (!PAID_AT_INPUT_PATTERN.test(trimmed)) {
    return "请输入 mm.dd hhmm 格式，例如 04.29 1530";
  }
  return "";
}

async function confirmPayEnrollment(id, paidAt) {
  await fetchJson(`${API_BASE}/enrollments/${id}/pay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operator_name: operatorSelect.value,
      source: sourceSelect.value,
      paid_at: paidAt,
      note: "前端报名管理页面确认报名",
    }),
  });
}

async function confirmCancelEnrollment(id) {
  await fetchJson(`${API_BASE}/enrollments/${id}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operator_name: operatorSelect.value,
      source: sourceSelect.value,
      note: "前端报名管理页面取消报名",
    }),
  });
}

async function submitActionModal() {
  if (!mustOperator()) return;
  const id = Number(modalState.enrollmentId || 0);
  if (!id) return;

  try {
    setModalSubmitting(true);
    showModalError("");

    if (modalState.mode === "pay") {
      const paidAt = actionModal.paidAtInput instanceof HTMLInputElement ? actionModal.paidAtInput.value.trim() : "";
      const validationMessage = validatePaidAtInput(paidAt);
      if (validationMessage) {
        showModalError(validationMessage);
        setModalSubmitting(false);
        return;
      }
      await confirmPayEnrollment(id, paidAt);
    } else if (modalState.mode === "cancel") {
      await confirmCancelEnrollment(id);
    } else {
      setModalSubmitting(false);
      return;
    }

    closeActionModal(true);
    await loadEnrollments();
  } catch (error) {
    showModalError(error.message || "操作失败");
    setModalSubmitting(false);
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

async function loadRules() {
  const result = await fetchJson(`${API_BASE}/rules/meta`);
  const grades = result.data?.grades || [];
  gradeFilter.innerHTML = [`<option value=''>全部年级</option>`]
    .concat(grades.map((grade) => `<option value='${grade}'>${grade}</option>`))
    .join("");
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
    query.append("latest_only", "true");
    if (statusFilter.value) query.append("status", statusFilter.value);
    if (gradeFilter.value) query.append("grade", gradeFilter.value);
    const studentName = studentNameFilter?.value.trim() || "";
    if (studentName) query.append("keyword", studentName);

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
        const isAdjustmentGenerated = Number(item.previous_enrollment_id || 0) > 0;
        const canOperate = item.status === "unconfirmed" && !isAdjustmentGenerated;
        const subjects = Array.isArray(item.class_subjects) ? item.class_subjects.join("、") : "-";
        const payable = formatMoney(item.final_price);
        const adjustmentTag = item.adjustment_tag ? `<span class='source-pill'>${item.adjustment_tag}</span>` : "";
        return `
          <div class='list-row'>
            <div>
              <div class='enrollment-title-line'>
                <strong>#${item.id} ${item.student_name || "-"}</strong>
                <span class='grade-pill'>${item.grade || "-"}</span>
                <span class='status-pill ${statusClass(item.status)}'>${statusText(item.status)}</span>
                ${adjustmentTag}
                <span class='amount-pill'>应缴 ${payable}</span>
                <span class='source-pill'>${item.source || "-"}</span>
              </div>
              <div class='enrollment-meta'>科目: ${subjects}</div>
              <div class='enrollment-meta'>报价时间: ${formatDateTime(item.created_at)}</div>
              <div class='enrollment-meta'>交费时间: ${formatPaidAt(item.paid_at)}</div>
              <div class='enrollment-meta'>报价信息: ${renderQuoteInfo(item)}</div>
            </div>
            ${
              canOperate
                ? `<div class='actions inline-actions'>
                    <button type='button' data-pay-id='${item.id}' data-student-name='${item.student_name || ""}'>确认报名</button>
                    <button type='button' class='secondary' data-cancel-id='${item.id}' data-student-name='${item.student_name || ""}'>取消报名</button>
                  </div>`
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
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});
studentNameFilter?.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  enrollmentState.page = 1;
  await loadEnrollments();
});
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

  const payButton = target.closest("button[data-pay-id]");
  if (payButton) {
    const id = Number(payButton.getAttribute("data-pay-id") || 0);
    if (!Number.isFinite(id) || id <= 0) return;
    openPayModal(id, payButton.getAttribute("data-student-name") || "");
    return;
  }

  const cancelButton = target.closest("button[data-cancel-id]");
  if (!cancelButton) return;
  const id = Number(cancelButton.getAttribute("data-cancel-id") || 0);
  if (!Number.isFinite(id) || id <= 0) return;
  openCancelModal(id, cancelButton.getAttribute("data-student-name") || "");
});

actionModal.confirmBtn?.addEventListener("click", submitActionModal);
actionModal.cancelBtn?.addEventListener("click", closeActionModal);
actionModal.dismissBtn?.addEventListener("click", closeActionModal);
actionModal.root.addEventListener("click", (event) => {
  if (event.target === actionModal.root) {
    closeActionModal();
  }
});
actionModal.paidAtInput?.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  await submitActionModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !actionModal.root.classList.contains("hidden")) {
    closeActionModal();
  }
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
