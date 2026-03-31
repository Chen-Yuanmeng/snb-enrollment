let API_BASE = `${window.location.origin}/api/v1`;

const DISCOUNT_LABELS = {
  三人成团: "三人成团（每项减100）",
  老带新: "老带新",
  转发朋友圈: "转发朋友圈",
  老生续报: "老生续报",
  现金优惠: "现金优惠",
};

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
const refundForm = document.querySelector("#refundForm");
const searchKeywordInput = document.querySelector("#searchKeyword");
const searchEnrollmentBtn = document.querySelector("#searchEnrollment");
const searchResultSelect = document.querySelector("#searchResultSelect");
const originalIdInput = document.querySelector("#originalId");
const studentNameInput = document.querySelector("#studentName");
const studentPhoneInput = document.querySelector("#studentPhone");
const newGradeSelect = document.querySelector("#newGrade");
const newClassModeSelect = document.querySelector("#newClassMode");
const newClassSubjectWrap = document.querySelector("#newClassSubjectWrap");
const newMixModeWrap = document.querySelector("#newMixModeWrap");
const newDiscountWrap = document.querySelector("#newDiscountWrap");
const excellentWrap = document.querySelector("#excellentWrap");
const historyWrap = document.querySelector("#historyWrap");
const historyKeywordInput = document.querySelector("#historyKeyword");
const historyStudentSelect = document.querySelector("#historyStudentSelect");
const searchHistoryBtn = document.querySelector("#searchHistory");
const discountNote = document.querySelector("#discountNote");
const submitRefundBtn = document.querySelector("#submitRefund");
const refundResult = document.querySelector("#refundResult");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

let gradeRules = [];
let currentSearchRows = [];
let autofilledReferralHistoryStudentId = 0;
let isDirty = false;

function markDirty() {
  isDirty = true;
}

function clearDirty() {
  isDirty = false;
}

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

async function copyText(text) {
  if (!navigator.clipboard) {
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    return false;
  }
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

function normalizeDiscountItem(item) {
  if (typeof item === "string") {
    const name = item.trim();
    return name ? { name, mode: "manual" } : null;
  }
  if (!item || typeof item !== "object") {
    return null;
  }
  const name = String(item.name || "").trim();
  if (!name) {
    return null;
  }
  return {
    name,
    mode: item.mode === "auto" ? "auto" : "manual",
    requiresHistoryStudent: Boolean(item.requires_history_student),
    exclusiveWith: Array.isArray(item.exclusive_with) ? item.exclusive_with : [],
  };
}

function normalizeDiscounts(discounts) {
  const list = Array.isArray(discounts) ? discounts : [];
  const normalized = list.map(normalizeDiscountItem).filter(Boolean);
  const hasExcellent = normalized.some((item) => item.name.startsWith("优秀生"));
  const nonExcellent = normalized.filter((item) => !item.name.startsWith("优秀生"));
  return hasExcellent ? [...nonExcellent, { name: "优秀生", mode: "manual" }] : nonExcellent;
}

function getDiscountLabel(rule, name) {
  const labels = rule?.discountLabels || {};
  return labels[name] || DISCOUNT_LABELS[name] || name;
}

function hasDiscount(rule, name) {
  return (rule?.discounts || []).some((item) => item.name === name);
}

function selectedDiscounts() {
  return [...newDiscountWrap.querySelectorAll("input[name='refundDiscount']:checked")].map((item) => item.value);
}

function buildDiscountItems() {
  const picked = selectedDiscounts();
  const discountItems = [];

  if (picked.includes("老带新") && picked.includes("老生续报")) {
    throw new Error("老带新与老生续报不能同时选择");
  }

  picked.forEach((name) => {
    const item = { name, amount: 0 };
    if (name === "老带新") {
      const historyStudentId = Number(historyStudentSelect.value || 0);
      if (historyStudentId <= 0) {
        throw new Error("已选择老带新，请先搜索并选择老生");
      }
      item.history_student_id = historyStudentId;
    }
    discountItems.push(item);
  });

  const excellent = document.querySelector("input[name='excellent']:checked")?.value;
  if (excellent) {
    const item = { name: excellent, amount: 0 };
    if (excellent === "优秀生第四档") {
      const manualInput = document.querySelector("#excellentManualAmount");
      const manualAmount = Number(manualInput?.value || 0);
      if (Number.isNaN(manualAmount) || manualAmount < 0 || manualAmount > 600) {
        throw new Error("优秀生第四档金额需在0到600之间");
      }
      item.amount = manualAmount;
    }
    discountItems.push(item);
  }

  return discountItems;
}

function applyDiscountsByNames(names) {
  const wanted = new Set((names || []).filter((name) => !String(name).startsWith("优秀生")));
  newDiscountWrap.querySelectorAll("input[name='refundDiscount']").forEach((item) => {
    item.checked = wanted.has(item.value);
  });
}

function renderDiscountNotes(rule) {
  const notes = rule?.notes || [];
  discountNote.textContent = notes.length ? notes.join(" ") : "";
}

function refreshHistoryArea() {
  const needHistory = selectedDiscounts().includes("老带新");
  historyWrap.classList.toggle("hidden", !needHistory);
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

function renderDiscounts(rule) {
  const discounts = (rule.discounts || []).filter((item) => item?.name && item.name !== "优秀生");
  if (discounts.length === 0) {
    newDiscountWrap.innerHTML = "<p class='hint'>当前年级暂无可选优惠活动</p>";
  } else {
    newDiscountWrap.classList.remove("grid-1", "grid-2", "grid-3");
    newDiscountWrap.classList.add(gridClassByLength(discounts.length));
    newDiscountWrap.innerHTML = discounts
      .map((item) => {
        const isAuto = item.mode === "auto";
        const disabled = isAuto ? "disabled" : "";
        const row = renderChoiceRow(
          `<input type='checkbox' name='refundDiscount' value='${item.name}' data-discount-mode='${item.mode}' ${disabled} />`,
          getDiscountLabel(rule, item.name)
        );
        return isAuto ? row.replace("choice-item", "choice-item disabled") : row;
      })
      .join("");
  }

  if (hasDiscount(rule, "优秀生")) {
    excellentWrap.classList.remove("hidden");
    excellentWrap.innerHTML = [
      "<p class='hint'>优秀生（四档）</p>",
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第一档' />", "第一档 1000"),
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第二档' />", "第二档 800"),
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第三档' />", "第三档 600"),
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第四档' />", "第四档（手动填写）"),
      "<input id='excellentManualAmount' type='number' min='0' max='600' step='1' placeholder='手动优惠金额（不超过600）' />",
    ].join("");
  } else {
    excellentWrap.classList.add("hidden");
    excellentWrap.innerHTML = "";
  }

  newDiscountWrap.querySelectorAll("input[name='refundDiscount']").forEach((item) => {
    item.addEventListener("change", refreshHistoryArea);
  });
  renderDiscountNotes(rule);
  refreshHistoryArea();
}

function renderGradeRule() {
  const rule = currentRule();
  if (!rule) return;
  renderClassModes(rule);
  renderClassSubjectGroups(rule);
  renderDiscounts(rule);
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
  const snapshotDiscounts = Array.isArray(row?.pricing_snapshot?.discounts) ? row.pricing_snapshot.discounts : [];
  const discountInfo = row.discount_info || {};
  const discountNames = snapshotDiscounts.length
    ? snapshotDiscounts.map((item) => item?.name).filter(Boolean)
    : Object.keys(discountInfo || {});

  originalIdInput.value = String(row.id || "");

  studentNameInput.value = row.student_name || "";
  studentPhoneInput.value = row.student_phone || "";

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
  applyDiscountsByNames(discountNames);
  const excellentPicked = snapshotDiscounts.find((item) => String(item?.name || "").startsWith("优秀生"));
  if (excellentPicked) {
    const excellentInput = document.querySelector(
      `input[name='excellent'][value='${excellentPicked.name}']`
    );
    if (excellentInput) {
      excellentInput.checked = true;
    }
    if (excellentPicked.name === "优秀生第四档") {
      const manualInput = document.querySelector("#excellentManualAmount");
      if (manualInput) {
        manualInput.value = String(Number(excellentPicked.amount || 0));
      }
    }
  }

  const referralDiscount = snapshotDiscounts.find((item) => item?.name === "老带新");
  autofilledReferralHistoryStudentId = Number(referralDiscount?.history_student_id || 0);
  if (autofilledReferralHistoryStudentId > 0) {
    historyStudentSelect.innerHTML = [
      `<option value='${autofilledReferralHistoryStudentId}'>已关联老生ID: ${autofilledReferralHistoryStudentId}</option>`,
    ].join("");
    historyStudentSelect.value = String(autofilledReferralHistoryStudentId);
  } else {
    historyStudentSelect.innerHTML = "<option value=''>未选择</option>";
  }
  refreshMixedModeRows();
  refreshHistoryArea();
}

async function searchHistory() {
  if (!mustOperator()) return;

  const keyword = historyKeywordInput.value.trim();
  if (!keyword) {
    alert("请输入老生姓名关键词");
    return;
  }

  try {
    const query = new URLSearchParams({ name: keyword });
    const result = await fetchJson(`${API_BASE}/students-history/search/referral?${query.toString()}`);
    const rows = result.data || [];
    historyStudentSelect.innerHTML = `<option value=''>未选择</option>${rows
      .map((item) => `<option value='${item.id}'>${item.name} / ${item.grade || "未知"} / 尾号:${item.phone_suffix || "-"}</option>`)
      .join("")}`;

    if (autofilledReferralHistoryStudentId > 0) {
      const exists = rows.some((item) => Number(item.id) === autofilledReferralHistoryStudentId);
      if (exists) {
        historyStudentSelect.value = String(autofilledReferralHistoryStudentId);
      }
    }
    if (rows.length === 0) {
      alert("未找到匹配老带新老生");
    }
  } catch (error) {
    alert(`老带新老生搜索失败: ${error.message}`);
  }
}

function buildPayload() {
  const originalId = Number(originalIdInput.value || 0);
  const name = studentNameInput.value.trim();
  const phone = studentPhoneInput.value.trim();
  const grade = newGradeSelect.value;
  const classMode = newClassModeSelect.value;
  const rule = currentRule();
  const classSubjects = selectedClassSubjects();
  const discounts = buildDiscountItems();

  if (!originalId) {
    throw new Error("原报名ID不能为空");
  }
  if (!name || !phone) {
    throw new Error("学生姓名和手机号不能为空");
  }
  if (classSubjects.length === 0) {
    throw new Error("请至少选择一个班型与科目");
  }
  if (rule && (rule.selection_mode || "multiple") === "single" && classSubjects.length !== 1) {
    throw new Error(`${grade}班型与科目仅支持单选`);
  }
  if (rule && typeof rule.max_select === "number" && rule.max_select > 0 && classSubjects.length > rule.max_select) {
    throw new Error(`${grade}班型与科目最多可选${rule.max_select}项`);
  }
  if (classMode === "混合" && classSubjects.length === 0) {
    throw new Error("混合模式下请先勾选班型与科目");
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
    review_note: null,
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

function renderAdjustmentSummary(data) {
  const branchMap = {
    increase: "金额增加（需补交）",
    decrease: "金额减少（可退费）",
    equal: "金额不变",
  };
  const branchText = branchMap[data.branch_type] || data.branch_type || "-";
  return [
    `分支类型: ${branchText}`,
    `原金额: ${data.old_price}`,
    `新金额: ${data.new_price}`,
    `差额: ${data.delta_amount}`,
    `需补交: ${data.payable_amount || 0}`,
    `应退费: ${data.refundable_amount || 0}`,
    `原报名ID: ${data.related_ids?.original_enrollment_id || "-"}`,
    `新报名ID: ${data.related_ids?.recalculated_enrollment_id || "-"}`,
    `退费单ID: ${data.related_ids?.refund_id || "-"}`,
    "",
    "通知文案:",
    data.notice_text || "-",
  ].join("\n");
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

async function submitRefund() {
  if (!mustOperator()) return;

  try {
    const payload = buildPayload();
    const result = await fetchJson(`${API_BASE}/refunds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const content = renderAdjustmentSummary(result.data || {});
    refundResult.textContent = content;
    const copied = await copyText((result.data && result.data.notice_text) || content);
    if (!copied) {
      refundResult.textContent = `${content}\n\n提示: 当前浏览器不支持自动复制，请手动复制通知文案。`;
    }
    clearDirty();
  } catch (error) {
    refundResult.textContent = `提交失败: ${error.message}`;
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
  const gradeOptions = result.data?.grade_options || [];
  gradeRules = gradeOptions.map((item) => {
    const hints = item.ui_hints || {};
    return {
      grade: item.grade,
      class_modes: item.class_modes || [],
      class_subject_groups: item.class_subject_groups || [],
      selection_mode: item.selection_mode || "multiple",
      max_select: item.max_select,
      discounts: normalizeDiscounts(item.discounts || []),
      discountLabels: hints.discount_labels || {},
      notes: hints.notes || [],
    };
  });
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
refundForm.addEventListener("input", markDirty);
refundForm.addEventListener("change", markDirty);
window.addEventListener("beforeunload", (event) => {
  if (!isDirty) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});
searchEnrollmentBtn.addEventListener("click", searchPaidEnrollments);
newGradeSelect.addEventListener("change", renderGradeRule);
newClassModeSelect.addEventListener("change", refreshMixedModeRows);
searchHistoryBtn.addEventListener("click", searchHistory);
submitRefundBtn.addEventListener("click", submitRefund);
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources(), loadRules()]);
  } catch (error) {
    refundResult.textContent = `初始化失败: ${error.message}`;
  }
})();
