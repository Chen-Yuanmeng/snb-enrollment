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
const searchEnrollmentBtn = document.querySelector("#searchEnrollment");
const searchResultSelect = document.querySelector("#searchResultSelect");
const oldStudentNameInput = document.querySelector("#oldStudentName");
const oldStudentPhoneInput = document.querySelector("#oldStudentPhone");
const oldGradeInput = document.querySelector("#oldGrade");
const oldClassSubjectsInput = document.querySelector("#oldClassSubjects");
const oldDiscountsInput = document.querySelector("#oldDiscounts");
const originalIdInput = document.querySelector("#originalId");
const studentNameInput = document.querySelector("#studentName");
const studentPhoneInput = document.querySelector("#studentPhone");
const newGradeSelect = document.querySelector("#newGrade");
const newClassModeSelect = document.querySelector("#newClassMode");
const newClassSubjectWrap = document.querySelector("#newClassSubjectWrap");
const newMixModeWrap = document.querySelector("#newMixModeWrap");
const newClassSubjectsInput = document.querySelector("#newClassSubjects");
const newDiscountsInput = document.querySelector("#newDiscounts");
const reviewNoteInput = document.querySelector("#reviewNote");
const previewRefundBtn = document.querySelector("#previewRefund");
const submitRefundBtn = document.querySelector("#submitRefund");
const refundResult = document.querySelector("#refundResult");

let gradeRules = [];
let currentSearchRows = [];

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

function parseClassSubjects(raw) {
  return raw
    .split(/\n|,|，|;/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function parseDiscounts(raw) {
  const lines = raw
    .split(/\n|;/)
    .map((line) => line.trim())
    .filter(Boolean);

  return lines.map((line) => {
    const parts = line.split(/,|，|:|：/).map((item) => item.trim());
    const name = parts[0] || "";
    const amountRaw = parts[1] || "0";
    const amount = Number(amountRaw);
    return {
      name,
      amount: Number.isFinite(amount) ? amount : 0,
    };
  }).filter((item) => item.name);
}

function discountInfoToLines(discountInfo) {
  if (!discountInfo || typeof discountInfo !== "object") {
    return "";
  }
  return Object.entries(discountInfo)
    .map(([name, amount]) => `${name},${Number(amount) || 0}`)
    .join("\n");
}

function discountInfoToReadableText(discountInfo) {
  if (!discountInfo || typeof discountInfo !== "object") {
    return "-";
  }
  const rows = Object.entries(discountInfo);
  if (rows.length === 0) {
    return "-";
  }
  return rows.map(([name, amount]) => `${name}: ${Number(amount) || 0}`).join("\n");
}

function currentRule() {
  return gradeRules.find((item) => item.grade === newGradeSelect.value) || null;
}

function gridClassByLength(size) {
  if (size >= 3) return "grid-3";
  if (size === 2) return "grid-2";
  return "grid-1";
}

function renderChoiceRow(inputHtml, text) {
  return `<label class="choice-item">${inputHtml}<span>${text}</span></label>`;
}

function selectedClassSubjects() {
  return [...newClassSubjectWrap.querySelectorAll("input[name='refundClassSubject']:checked")].map(
    (item) => item.value
  );
}

function selectedClassMode() {
  return newClassModeSelect.value || "线下";
}

function refreshMixedModeRows() {
  const rule = currentRule();
  const mode = selectedClassMode();
  const classSubjects = selectedClassSubjects();

  if (!rule || !rule.class_modes?.includes("混合") || mode !== "混合") {
    newMixModeWrap.classList.add("hidden");
    newMixModeWrap.innerHTML = "";
    return;
  }

  newMixModeWrap.classList.remove("hidden");
  if (classSubjects.length === 0) {
    newMixModeWrap.innerHTML = "<p class='hint'>请先选择至少一项班型与科目，再分配线上/线下。</p>";
    return;
  }

  newMixModeWrap.innerHTML = classSubjects
    .map(
      (item) =>
        `<div class='mix-row'><span>${item}</span><select data-mix-item='${item}'><option value='线下'>线下</option><option value='线上'>线上</option></select></div>`
    )
    .join("");
}

function buildModeDetails(classSubjects, classMode) {
  if (classMode !== "混合") {
    return null;
  }
  const offline = [];
  const online = [];
  newMixModeWrap.querySelectorAll("select[data-mix-item]").forEach((select) => {
    const item = select.getAttribute("data-mix-item");
    if (!classSubjects.includes(item)) return;
    if (select.value === "线上") {
      online.push(item);
    } else {
      offline.push(item);
    }
  });
  return {
    offline_subjects: offline,
    online_subjects: online,
  };
}

function renderClassSubjectGroups(rule) {
  const isSingleSelect = (rule.selection_mode || "multiple") === "single";
  newClassSubjectWrap.innerHTML = (rule.class_subject_groups || [])
    .map((group, groupIdx) => {
      const choices = group
        .map((item) => {
          const subjectName = typeof item === "string" ? item : item?.name;
          if (!subjectName) {
            return "";
          }
          const inputType = isSingleSelect ? "radio" : "checkbox";
          const input = `<input type="${inputType}" name="refundClassSubject" value="${subjectName}" />`;
          return renderChoiceRow(input, subjectName);
        })
        .join("");
      const separator =
        groupIdx < (rule.class_subject_groups || []).length - 1
          ? "<div class='choice-group-separator'></div>"
          : "";
      return `<div class="choice-group-row"><div class="choice-grid ${gridClassByLength(group.length)}">${choices}</div></div>${separator}`;
    })
    .join("");

  newClassSubjectWrap.querySelectorAll("input[name='refundClassSubject']").forEach((item) => {
    item.addEventListener("change", refreshMixedModeRows);
  });
}

function renderClassModes(rule) {
  const modes = rule.class_modes || [];
  newClassModeSelect.innerHTML = modes.map((mode) => `<option value='${mode}'>${mode}</option>`).join("");
}

function renderGradeRule() {
  const rule = currentRule();
  if (!rule) return;
  renderClassModes(rule);
  renderClassSubjectGroups(rule);
  refreshMixedModeRows();
}

function applyClassSubjectsByValues(classSubjects) {
  const rule = currentRule();
  const wanted = new Set(classSubjects || []);
  const subjectInputs = [...newClassSubjectWrap.querySelectorAll("input[name='refundClassSubject']")];
  if (!rule || subjectInputs.length === 0) {
    return;
  }

  const isSingle = (rule.selection_mode || "multiple") === "single";
  let pickedSingle = false;

  subjectInputs.forEach((item) => {
    if (isSingle) {
      if (!pickedSingle && wanted.has(item.value)) {
        item.checked = true;
        pickedSingle = true;
      } else {
        item.checked = false;
      }
    } else {
      item.checked = wanted.has(item.value);
    }
  });
}

function applyEnrollmentToForm(row) {
  if (!row) {
    return;
  }

  const classSubjects = Array.isArray(row.class_subjects) ? row.class_subjects : [];
  const discountInfo = row.discount_info || {};

  originalIdInput.value = String(row.id || "");

  oldStudentNameInput.value = row.student_name || "";
  oldStudentPhoneInput.value = row.student_phone || "";
  oldGradeInput.value = row.grade || "";
  oldClassSubjectsInput.value = classSubjects.join("、");
  oldDiscountsInput.value = discountInfoToReadableText(discountInfo);

  studentNameInput.value = row.student_name || "";
  studentPhoneInput.value = row.student_phone || "";
  newClassSubjectsInput.value = classSubjects.join("\n");
  newDiscountsInput.value = discountInfoToLines(discountInfo);

  if (row.grade) {
    newGradeSelect.value = row.grade;
  }
  renderGradeRule();

  if (row.class_mode) {
    const modeExists = [...newClassModeSelect.options].some((option) => option.value === row.class_mode);
    if (modeExists) {
      newClassModeSelect.value = row.class_mode;
    }
  }
  applyClassSubjectsByValues(classSubjects);
  refreshMixedModeRows();
}

function buildPayload() {
  const originalId = Number(originalIdInput.value || 0);
  const name = studentNameInput.value.trim();
  const phone = studentPhoneInput.value.trim();
  const grade = newGradeSelect.value;
  const classMode = newClassModeSelect.value;
  const rule = currentRule();
  const selected = selectedClassSubjects();
  const fallbackTyped = parseClassSubjects(newClassSubjectsInput.value);
  const classSubjects = selected.length > 0 ? selected : fallbackTyped;
  const discounts = parseDiscounts(newDiscountsInput.value);

  if (!originalId) {
    throw new Error("原报名ID不能为空");
  }
  if (!name || !phone) {
    throw new Error("学生姓名和手机号不能为空");
  }
  if (classSubjects.length === 0) {
    throw new Error("请填写至少一个新班型与科目");
  }
  if (rule && (rule.selection_mode || "multiple") === "single" && classSubjects.length !== 1) {
    throw new Error(`${grade}班型与科目仅支持单选`);
  }
  if (rule && typeof rule.max_select === "number" && rule.max_select > 0 && classSubjects.length > rule.max_select) {
    throw new Error(`${grade}班型与科目最多可选${rule.max_select}项`);
  }
  if (classMode === "混合" && selected.length === 0) {
    throw new Error("混合模式请通过上方规则项勾选科目，手填不支持混合拆分");
  }

  const modeDetails = buildModeDetails(classSubjects, classMode);

  return {
    operator_name: operatorSelect.value,
    source: sourceSelect.value,
    original_enrollment_id: originalId,
    new_enrollment_payload: {
      operator_name: operatorSelect.value,
      source: sourceSelect.value,
      student_info: {
        name,
        phone,
      },
      grade,
      class_subjects: classSubjects,
      class_mode: classMode,
      discounts,
      mode_details: modeDetails,
    },
    review_note: reviewNoteInput.value.trim() || null,
  };
}

function renderSearchResults(rows) {
  searchResultSelect.innerHTML = [`<option value=''>请选择</option>`]
    .concat(
      rows.map(
        (item) =>
          `<option value='${item.id}'>#${item.id} ${item.student_name || ""} ${item.grade} ${
            (item.class_subjects || []).join("、")
          }</option>`
      )
    )
    .join("");
}

async function searchPaidEnrollments() {
  const keyword = searchKeywordInput.value.trim();
  if (!keyword) {
    alert("请输入学生姓名或报名ID");
    return;
  }

  try {
    const result = await fetchJson(
      `${API_BASE}/enrollments?status=paid&keyword=${encodeURIComponent(keyword)}`
    );
    currentSearchRows = result.data || [];
    renderSearchResults(currentSearchRows);

    if (currentSearchRows.length === 0) {
      refundResult.textContent = "未搜索到已缴费报名记录";
      return;
    }

    if (currentSearchRows.length === 1) {
      searchResultSelect.value = String(currentSearchRows[0].id);
      applyEnrollmentToForm(currentSearchRows[0]);
    }
    refundResult.textContent = `已搜索到 ${currentSearchRows.length} 条报名记录，请选择并调整新信息后提交`;
  } catch (error) {
    refundResult.textContent = `搜索失败: ${error.message}`;
  }
}

async function previewRefund() {
  if (!mustOperator()) return;

  try {
    const payload = buildPayload();
    const result = await fetchJson(`${API_BASE}/refunds/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = result.data;
    refundResult.textContent = [
      `原金额: ${data.old_price}`,
      `新金额: ${data.new_price}`,
      `退费金额: ${data.refund_amount}`,
      `自动拒绝: ${data.auto_rejected ? "是" : "否"}`,
      `说明: ${data.reject_reason || "-"}`,
    ].join("\n");
  } catch (error) {
    refundResult.textContent = `预览失败: ${error.message}`;
  }
}

async function submitRefund() {
  if (!mustOperator()) return;

  try {
    const payload = buildPayload();
    const result = await fetchJson(`${API_BASE}/refunds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    refundResult.textContent = `提交成功: 退费ID ${result.data.refund_id}，金额 ${result.data.refund_amount}`;
    await loadPaidEnrollments();
  } catch (error) {
    refundResult.textContent = `提交失败: ${error.message}`;
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

async function loadRules() {
  const result = await fetchJson(`${API_BASE}/rules/meta`);
  gradeRules = result.data?.grade_options || [];
  const grades = gradeRules.map((item) => item.grade);
  newGradeSelect.innerHTML = grades.map((item) => `<option value='${item}'>${item}</option>`).join("");
  renderGradeRule();
}

searchResultSelect.addEventListener("change", () => {
  const id = Number(searchResultSelect.value || 0);
  if (!id) {
    return;
  }
  const row = currentSearchRows.find((item) => item.id === id);
  applyEnrollmentToForm(row);
});
searchEnrollmentBtn.addEventListener("click", searchPaidEnrollments);
newGradeSelect.addEventListener("change", renderGradeRule);
newClassModeSelect.addEventListener("change", refreshMixedModeRows);
previewRefundBtn.addEventListener("click", previewRefund);
submitRefundBtn.addEventListener("click", submitRefund);

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources(), loadRules()]);
  } catch (error) {
    refundResult.textContent = `初始化失败: ${error.message}`;
  }
})();
