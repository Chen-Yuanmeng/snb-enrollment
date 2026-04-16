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

let GRADE_LIST = [];

const DISCOUNT_LABELS = {
  三人成团: "三人成团（每项减100）",
  老带新: "老带新",
  转发朋友圈: "转发朋友圈",
  老生续报: "老生续报",
  现金优惠: "现金优惠",
};

const LEGACY_DISCOUNT_NAME_MAP = {
  老带新28天: "老带新",
  老带新24天: "老带新",
  老带新21天: "老带新",
};

function canonicalizeDiscountName(name) {
  const trimmed = String(name || "").trim();
  if (!trimmed) return "";
  return LEGACY_DISCOUNT_NAME_MAP[trimmed] || trimmed;
}

const operatorSelect = document.querySelector("#operator");
const sourceSelect = document.querySelector("#source");
const gradeSelector = document.querySelector("#gradeSelector");
const gradeTitle = document.querySelector("#gradeTitle");
const quoteForm = document.querySelector("#quoteForm");
const quoteResult = document.querySelector("#quoteResult");
const classSubjectWrap = document.querySelector("#classSubjectWrap");
const classModeWrap = document.querySelector("#classModeWrap");
const mixModeWrap = document.querySelector("#mixModeWrap");
const discountWrap = document.querySelector("#discountWrap");
const discountNote = document.querySelector("#discountNote");
const excellentWrap = document.querySelector("#excellentWrap");
const historyWrap = document.querySelector("#historyWrap");
const historyKeyword = document.querySelector("#historyKeyword");
const historyStudentSelect = document.querySelector("#historyStudentSelect");
const searchHistoryBtn = document.querySelector("#searchHistory");
const studentNameInput = document.querySelector("#studentName");
const studentPhoneInput = document.querySelector("#studentPhone");
let isDirty = false;

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

let activeGradeId = "";
const autoDiscountCheckedNames = new Set();
const renewalDecisionCache = new Map();
const gradeRuleCache = new Map();
let autoDiscountRequestSeq = 0;
let autoRenewalHistoryStudentId = 0;
let autoRenewalIdentityKey = "";
let autoWuyiCaseInput = 0;
let autoWuyiIdentityKey = "";

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

function currentGrade() {
  return GRADE_LIST.find((x) => x.id === activeGradeId);
}

function shortGradeName(name) {
  if (!name) return "";
  if (name.length <= 8) return name;
  return `${name.slice(0, 6)}...`;
}

function formatDateTime(value) {
  if (!value) return "-";
  const raw = String(value).trim();
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}

function normalizeDiscountItem(item) {
  if (typeof item === "string") {
    const name = canonicalizeDiscountName(item);
    return name ? { name, mode: "manual" } : null;
  }
  if (!item || typeof item !== "object") {
    return null;
  }
  const name = canonicalizeDiscountName(item.name);
  if (!name) {
    return null;
  }
  const mode = item.mode === "auto" ? "auto" : "manual";
  return {
    name,
    mode,
    requiresHistoryStudent: Boolean(item.requires_history_student),
    exclusiveWith: Array.isArray(item.exclusive_with) ? item.exclusive_with : [],
  };
}

function normalizeDiscounts(discounts) {
  const list = Array.isArray(discounts) ? discounts : [];
  const normalized = list
    .map(normalizeDiscountItem)
    .filter(Boolean)
    .filter((item, idx, arr) => arr.findIndex((x) => x.name === item.name) === idx);
  const excellentNames = new Set(["优秀生第一档", "优秀生第二档", "优秀生第三档"]);
  const hasExcellent = normalized.some((item) => excellentNames.has(item.name));
  const nonExcellent = normalized.filter((item) => !excellentNames.has(item.name));
  return hasExcellent ? [...nonExcellent, { name: "优秀生", mode: "manual" }] : nonExcellent;
}

function getDiscountLabel(conf, name) {
  const labels = conf?.discountLabels || {};
  return labels[name] || DISCOUNT_LABELS[name] || name;
}

function hasDiscount(conf, name) {
  return (conf.discounts || []).some((item) => item.name === name);
}

function evaluateAutoDiscount(_conf, discountName) {
  return autoDiscountCheckedNames.has(discountName);
}

function getIdentityKey(grade, name, phone) {
  return `${grade}||${String(name || "").trim()}||${String(phone || "").trim()}`;
}

function getAutoDiscountInput(discountName) {
  return [...discountWrap.querySelectorAll("input[name='discount']")].find(
    (input) => input.getAttribute("data-discount-mode") === "auto" && input.value === discountName
  );
}

function setAutoDiscountInputsDisabled(disabled) {
  discountWrap.querySelectorAll("input[name='discount'][data-discount-mode='auto']").forEach((input) => {
    input.disabled = disabled;
    const row = input.closest(".choice-item");
    if (row) {
      row.classList.toggle("disabled", disabled);
    }
  });
}

function clearAutoDiscountSelectionState() {
  autoDiscountCheckedNames.clear();
  autoRenewalHistoryStudentId = 0;
  autoRenewalIdentityKey = "";
  autoWuyiCaseInput = 0;
  autoWuyiIdentityKey = "";
  discountWrap.querySelectorAll("input[name='discount'][data-discount-mode='auto']").forEach((input) => {
    input.checked = false;
    input.setAttribute("data-last-checked", "false");
  });
  refreshHistoryArea();
}

function setAutoDiscountChecked(discountName, checked) {
  if (checked) {
    autoDiscountCheckedNames.add(discountName);
  } else {
    autoDiscountCheckedNames.delete(discountName);
  }
  const input = getAutoDiscountInput(discountName);
  if (input) {
    input.checked = checked;
    input.setAttribute("data-last-checked", checked ? "true" : "false");
  }
}

function renderDiscountNotes(conf, extraMessage = "") {
  const tips = (conf?.notes || []).concat(conf?.autoNotes || []);
  if (extraMessage) {
    discountNote.innerHTML = `<div>${extraMessage}</div>`;
    return;
  }
  discountNote.innerHTML = tips.length ? `<div>${tips.join(" ")}</div>` : "";
}

function resetIdentityOnGradeSwitch() {
  autoDiscountRequestSeq += 1;
  if (studentNameInput) {
    studentNameInput.value = "";
  }
  if (studentPhoneInput) {
    studentPhoneInput.value = "";
  }
  historyKeyword.value = "";
  historyStudentSelect.innerHTML = "<option value=''>未选择</option>";
  renewalDecisionCache.clear();
  clearAutoDiscountSelectionState();
}

async function loadGradeRule(grade) {
  if (gradeRuleCache.has(grade)) {
    return gradeRuleCache.get(grade);
  }
  const result = await fetchJson(`${API_BASE}/rules/grade/${encodeURIComponent(grade)}`);
  const rule = result.data || {};
  gradeRuleCache.set(grade, rule);
  return rule;
}

function isPhoneExactMatch(left, right) {
  return String(left || "").trim() === String(right || "").trim();
}

function chooseRenewalHistoryStudentIdForAuto(rows, studentName, grade) {
  const optionsText = rows
    .map(
      (row, idx) =>
        `${idx + 1}. #${row.id} ${row.name} / ${row.grade || grade || "未知年级"} / 尾号:${row.phone_suffix || "-"}`
    )
    .join("\n");

  const answer = window.prompt(
    [`
请选择老生续报对应记录（自动优惠判定）：
学生：${studentName}
0. 无匹配（按新生处理，不勾选老生续报）
${optionsText}
请输入序号（0-${rows.length}）
`.trim()].join("\n")
  );

  if (answer === null) {
    return null;
  }

  const picked = Number(answer.trim());
  if (!Number.isInteger(picked) || picked < 0 || picked > rows.length) {
    alert("手动选择无效，本次不勾选老生续报，请重新失焦触发检查。");
    return null;
  }

  if (picked === 0) {
    return 0;
  }

  return Number(rows[picked - 1]?.id || 0);
}

async function evaluateEarlyBirdEligibility(conf) {
  if (!hasDiscount(conf, "早鸟")) {
    return false;
  }
  const rule = await loadGradeRule(conf.grade);
  const stageEnds = rule?.quote_validity?.params?.early_bird_stage_ends;
  if (!Array.isArray(stageEnds) || stageEnds.length === 0) {
    return false;
  }
  const now = new Date();
  return stageEnds.some((value) => {
    const end = new Date(value);
    return !Number.isNaN(end.getTime()) && now <= end;
  });
}

async function evaluateRenewalEligibility(conf, studentName, studentPhone) {
  if (!hasDiscount(conf, "老生续报")) {
    return { eligible: false, historyStudentId: 0 };
  }

  const identityKey = getIdentityKey(conf.grade, studentName, studentPhone);
  if (renewalDecisionCache.has(identityKey)) {
    const cached = Number(renewalDecisionCache.get(identityKey) || 0);
    return { eligible: cached > 0, historyStudentId: cached > 0 ? cached : 0 };
  }

  const query = new URLSearchParams({ name: studentName, grade: conf.grade });
  const result = await fetchJson(`${API_BASE}/students-history/search/renewal?${query.toString()}`);
  const rows = result.data || [];
  if (rows.length === 0) {
    renewalDecisionCache.set(identityKey, 0);
    return { eligible: false, historyStudentId: 0 };
  }

  const autoMatched = rows.filter((row) => isPhoneSuffixMatch(studentPhone, row.phone_suffix));
  if (autoMatched.length === 1) {
    const historyStudentId = Number(autoMatched[0]?.id || 0);
    const normalized = historyStudentId > 0 ? historyStudentId : 0;
    renewalDecisionCache.set(identityKey, normalized);
    return { eligible: normalized > 0, historyStudentId: normalized };
  }

  const pickedHistoryStudentId = chooseRenewalHistoryStudentIdForAuto(rows, studentName, conf.grade);
  if (pickedHistoryStudentId === null) {
    renewalDecisionCache.set(identityKey, 0);
    return { eligible: false, historyStudentId: 0 };
  }
  const normalized = pickedHistoryStudentId > 0 ? pickedHistoryStudentId : 0;
  renewalDecisionCache.set(identityKey, normalized);
  return { eligible: normalized > 0, historyStudentId: normalized };
}

async function evaluateWuyiEligibility(conf, studentName, studentPhone) {
  if (!hasDiscount(conf, "五一报名优惠")) {
    return { eligible: false, caseInput: 0 };
  }

  const rule = await loadGradeRule(conf.grade);
  const cases = rule?.discount_presets?.core_common?.find((item) => item?.name === "五一报名优惠")?.params?.cases || {};

  const studentResult = await fetchJson(`${API_BASE}/students/search?${new URLSearchParams({ keyword: studentPhone }).toString()}`);
  const studentRows = studentResult.data || [];
  const exactBoth = studentRows.find((item) => isPhoneExactMatch(item.phone, studentPhone) && item.name === studentName);
  const exactPhone = studentRows.find((item) => isPhoneExactMatch(item.phone, studentPhone));
  const targetStudent = exactBoth || exactPhone;
  if (!targetStudent?.id) {
    return { eligible: false, caseInput: 0 };
  }

  const statuses = ["confirmed", "pending_adjustment", "adjusted", "increased", "partial_refunded", "refunded"];
  const enrollmentLists = await Promise.all(
    statuses.map(async (status) => {
      const query = new URLSearchParams({
        student_id: String(targetStudent.id),
        grade: "五一中考",
        status,
        valid: "true",
      });
      const enrollmentResult = await fetchJson(`${API_BASE}/enrollments?${query.toString()}`);
      return enrollmentResult.data || [];
    })
  );

  const merged = enrollmentLists.flat();
  if (merged.length === 0) {
    return { eligible: false, caseInput: 0 };
  }
  merged.sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
  const latest = merged[0] || {};
  const classSubjects = Array.isArray(latest.class_subjects) ? latest.class_subjects : [];
  const subjectCount = classSubjects.length;
  const amount = Number(cases[String(subjectCount)] ?? 0);
  const eligible = Number.isFinite(amount) && amount > 0;
  return { eligible, caseInput: subjectCount };
}

async function refreshAutoDiscountsByIdentity() {
  const conf = currentGrade();
  if (!conf) {
    return;
  }

  const studentName = studentNameInput.value.trim();
  const studentPhone = studentPhoneInput.value.trim();
  const seq = ++autoDiscountRequestSeq;

  if (!studentName || !studentPhone) {
    clearAutoDiscountSelectionState();
    setAutoDiscountInputsDisabled(true);
    renderDiscountNotes(conf);
    return;
  }

  try {
    const [earlyBirdEligible, renewalResult, wuyiResult] = await Promise.all([
      evaluateEarlyBirdEligibility(conf),
      evaluateRenewalEligibility(conf, studentName, studentPhone),
      evaluateWuyiEligibility(conf, studentName, studentPhone),
    ]);

    if (seq !== autoDiscountRequestSeq) {
      return;
    }

    clearAutoDiscountSelectionState();
    if (earlyBirdEligible) {
      setAutoDiscountChecked("早鸟", true);
    }
    if (renewalResult.eligible) {
      setAutoDiscountChecked("老生续报", true);
      autoRenewalHistoryStudentId = renewalResult.historyStudentId;
      autoRenewalIdentityKey = getIdentityKey(conf.grade, studentName, studentPhone);
    }
    if (wuyiResult.eligible) {
      setAutoDiscountChecked("五一报名优惠", true);
      autoWuyiCaseInput = Number(wuyiResult.caseInput || 0);
      autoWuyiIdentityKey = getIdentityKey(conf.grade, studentName, studentPhone);
    }
    setAutoDiscountInputsDisabled(false);
    refreshHistoryArea();
    renderDiscountNotes(conf);
  } catch (error) {
    if (seq !== autoDiscountRequestSeq) {
      return;
    }
    clearAutoDiscountSelectionState();
    setAutoDiscountInputsDisabled(false);
    renderDiscountNotes(conf, `自动优惠检查失败：${error.message}`);
  }
}

async function loadRules() {
  const result = await fetchJson(`${API_BASE}/rules/meta`);
  const gradeOptions = result.data?.grade_options || [];
  GRADE_LIST = gradeOptions.map((item, idx) => {
    const grade = item.grade;
    const hints = item.ui_hints || {};
    return {
      id: `grade${idx + 1}`,
      grade,
      short: shortGradeName(grade),
      classModes: item.class_modes || [],
      classSubjectGroups: item.class_subject_groups || [],
      discounts: normalizeDiscounts(item.discounts || []),
      discountLabels: hints.discount_labels || {},
      notes: hints.notes || [],
      selectionMode: item.selection_mode || "multiple",
      maxSelect: item.max_select,
    };
  });

  if (GRADE_LIST.length === 0) {
    throw new Error("规则元数据为空");
  }
  activeGradeId = GRADE_LIST[0].id;
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

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const detail =
      typeof data.detail === "object" && data.detail?.message
        ? data.detail.message
        : data.detail;
    throw new Error(detail || data.message || "请求失败");
  }
  if (data.code && data.code !== 0) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function gridClassByLength(size) {
  if (size >= 3) return "grid-3";
  if (size === 2) return "grid-2";
  return "grid-1";
}

function renderChoiceRow(inputHtml, text) {
  return `<label class="choice-item">${inputHtml}<span>${text}</span></label>`;
}

function renderGradeTabs() {
  gradeSelector.innerHTML = GRADE_LIST.map(
    (item) =>
      `<button type="button" class="grade-tab ${item.id === activeGradeId ? "active" : ""}" data-grade-id="${item.id}">${item.grade}</button>`
  ).join("");

  gradeSelector.querySelectorAll(".grade-tab").forEach((button) => {
    button.addEventListener("click", () => {
      activeGradeId = button.getAttribute("data-grade-id");
      resetIdentityOnGradeSwitch();
      renderGradeTabs();
      renderActiveGradeForm();
    });
  });
}

function renderClassSubjectGroups(conf) {
  const isSingleSelect = conf.selectionMode === "single";
  classSubjectWrap.innerHTML = conf.classSubjectGroups
    .map((group, groupIdx) => {
      const choices = group
        .map((item) => {
          const subjectName = typeof item === "string" ? item : item?.name;
          if (!subjectName) {
            return "";
          }
          const inputType = isSingleSelect ? "radio" : "checkbox";
          const input = `<input type="${inputType}" name="classSubject" value="${subjectName}" />`;
          return renderChoiceRow(input, subjectName);
        })
        .join("");
      const separator = groupIdx < conf.classSubjectGroups.length - 1 ? "<div class='choice-group-separator'></div>" : "";
      return `<div class="choice-group-row"><div class="choice-grid ${gridClassByLength(group.length)}">${choices}</div></div>${separator}`;
    })
    .join("");
}

function renderActiveGradeForm() {
  const conf = currentGrade();

  gradeTitle.textContent = `报价录入 - ${conf.grade}`;

  renderClassSubjectGroups(conf);

  classModeWrap.classList.remove("grid-1", "grid-2", "grid-3");
  classModeWrap.classList.add(gridClassByLength(conf.classModes.length));
  classModeWrap.innerHTML = conf.classModes
    .map((mode, idx) => {
      const checked = idx === 0 ? "checked" : "";
      return renderChoiceRow(`<input type="radio" name="classMode" value="${mode}" ${checked} />`, mode);
    })
    .join("");

  discountWrap.classList.remove("grid-1", "grid-2", "grid-3");
  const standardDiscountCount = conf.discounts.filter((item) => item.name !== "优秀生" && item.name !== "考分优惠").length;
  const scoreDiscountCount = hasDiscount(conf, "考分优惠") ? 1 : 0;
  _length = standardDiscountCount + scoreDiscountCount;
  switch (_length) {
    case 3:
    case 5:
      discountWrap.classList.add("grid-3");
      break;
    case 2:
    case 4:
      discountWrap.classList.add("grid-2");
      break;
    case 1:
    default:
      discountWrap.classList.add("grid-1");
  }

  discountWrap.innerHTML = conf.discounts
    .filter((item) => item.name !== "优秀生" && item.name !== "考分优惠")
    .map((item) => {
      const text = getDiscountLabel(conf, item.name);
      const isAuto = item.mode === "auto";
      const checked = isAuto && evaluateAutoDiscount(conf, item.name) ? "checked" : "";
      const disabled = isAuto ? "disabled" : "";
      const row = renderChoiceRow(
        `<input type="checkbox" name="discount" value="${item.name}" data-discount-mode="${item.mode}" data-last-checked="${checked ? "true" : "false"}" ${disabled} ${checked} />`,
        text
      );
      return isAuto ? row.replace("choice-item", "choice-item disabled") : row;
    })
    .join("");

  if (hasDiscount(conf, "考分优惠")) {
    discountWrap.innerHTML += [
      renderChoiceRow("<input type='checkbox' name='discount' value='考分优惠' data-discount-mode='manual' data-last-checked='false' />", "考分优惠"),
      "<input id='scoreDiscountAmount' type='number' min='0' max='600' step='1' placeholder='考分优惠金额' />",
    ].join("");
  }

  if (hasDiscount(conf, "优秀生")) {
    excellentWrap.classList.remove("hidden");
    excellentWrap.innerHTML = [
      "<p class='hint'>优秀生（三档） <a href='#' class='hint-action-link' id='clearExcellentLink'>清除选择</a></p>",
      "<div class='choice-grid grid-3 excellent-options'>",
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第一档' />", "第一档 1000"),
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第二档' />", "第二档 800"),
      renderChoiceRow("<input type='radio' name='excellent' value='优秀生第三档' />", "第三档 600"),
      "</div>",
    ].join("");

    const clearExcellentLink = excellentWrap.querySelector("#clearExcellentLink");
    if (clearExcellentLink) {
      clearExcellentLink.addEventListener("click", (event) => {
        event.preventDefault();
        excellentWrap.querySelectorAll("input[name='excellent']").forEach((input) => {
          input.checked = false;
        });
      });
    }
  } else {
    excellentWrap.classList.add("hidden");
    excellentWrap.innerHTML = "";
  }

  renderDiscountNotes(conf);

  refreshHistoryArea();
  refreshMixedModeRows();

  classSubjectWrap.querySelectorAll("input[name='classSubject']").forEach((item) => {
    item.addEventListener("change", refreshMixedModeRows);
  });
  classModeWrap.querySelectorAll("input[name='classMode']").forEach((item) => {
    item.addEventListener("change", refreshMixedModeRows);
  });
  discountWrap.querySelectorAll("input[name='discount']").forEach((item) => {
    item.addEventListener("change", () => {
      const isAuto = item.getAttribute("data-discount-mode") === "auto";
      const previousChecked = item.getAttribute("data-last-checked") === "true";
      const currentChecked = item.checked;

      if (isAuto && previousChecked !== currentChecked) {
        const ok = window.confirm("确定要改动该自动选择项？");
        if (!ok) {
          item.checked = previousChecked;
          return;
        }
      }

      item.setAttribute("data-last-checked", item.checked ? "true" : "false");
      refreshHistoryArea();
    });
  });
}

function selectedClassMode() {
  return classModeWrap.querySelector("input[name='classMode']:checked")?.value || "线下";
}

function selectedClassSubjects() {
  return [...classSubjectWrap.querySelectorAll("input[name='classSubject']:checked")].map((x) => x.value);
}

function selectedDiscounts() {
  return [...discountWrap.querySelectorAll("input[name='discount']:checked")].map((x) => x.value);
}

function refreshHistoryArea() {
  const active = selectedDiscounts();
  const needHistory = active.includes("老带新");
  historyWrap.classList.toggle("hidden", !needHistory);
}

function refreshMixedModeRows() {
  const conf = currentGrade();
  const mode = selectedClassMode();
  const classSubjects = selectedClassSubjects();

  if (!conf.classModes.includes("混合") || mode !== "混合") {
    mixModeWrap.classList.add("hidden");
    mixModeWrap.innerHTML = "";
    return;
  }

  mixModeWrap.classList.remove("hidden");
  if (classSubjects.length === 0) {
    mixModeWrap.innerHTML = "<p class='hint'>请先选择至少一项班型与科目，再分配线上/线下。</p>";
    return;
  }

  mixModeWrap.innerHTML = classSubjects
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
  mixModeWrap.querySelectorAll("select[data-mix-item]").forEach((select) => {
    const item = select.getAttribute("data-mix-item");
    if (!classSubjects.includes(item)) {
      return;
    }
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

function isPhoneSuffixMatch(phone, phoneSuffix) {
  const left = String(phone || "").trim();
  const right = String(phoneSuffix || "").trim();
  if (!left || !right) {
    return false;
  }

  const shorter = left.length <= right.length ? left : right;
  const longer = left.length <= right.length ? right : left;
  return longer.endsWith(shorter);
}

function pickRenewalHistoryStudentIdManually(rows, studentName, grade) {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("未找到匹配老生，无法使用老生续报");
  }

  const optionsText = rows
    .map(
      (row, idx) =>
        `${idx + 1}. #${row.id} ${row.name} / ${row.grade || grade || "未知年级"} / 尾号:${row.phone_suffix || "-"}`
    )
    .join("\n");

  const answer = window.prompt(
    [`
请选择老生续报对应记录：
学生：${studentName}
0. 无匹配（该学生按新生处理）
${optionsText}
请输入序号（0-${rows.length}）
`.trim()].join("\n")
  );

  if (answer === null) {
    throw new Error("已取消老生续报手动选择");
  }

  const picked = Number(answer.trim());
  if (!Number.isInteger(picked) || picked < 0 || picked > rows.length) {
    throw new Error("手动选择无效，请重新报价并输入正确序号");
  }

  if (picked === 0) {
    throw new Error("已选择无匹配：该学生按新生处理，请取消老生续报后重新报价");
  }

  const historyStudentId = Number(rows[picked - 1]?.id || 0);
  if (historyStudentId <= 0) {
    throw new Error("手动选择结果无效");
  }
  return historyStudentId;
}

async function resolveRenewalHistoryStudentId(studentName, studentPhone, grade) {
  const query = new URLSearchParams({ name: studentName, grade });
  const result = await fetchJson(`${API_BASE}/students-history/search/renewal?${query.toString()}`);
  const rows = result.data || [];
  if (rows.length === 0) {
    throw new Error("未找到匹配老生，无法使用老生续报");
  }

  const autoMatched = rows.filter((row) => isPhoneSuffixMatch(studentPhone, row.phone_suffix));
  if (autoMatched.length === 1) {
    const historyStudentId = Number(autoMatched[0]?.id || 0);
    if (historyStudentId <= 0) {
      throw new Error("老生续报自动匹配结果无效");
    }
    return historyStudentId;
  }

  return pickRenewalHistoryStudentIdManually(rows, studentName, grade);
}

async function buildDiscountPayload(conf, studentName, studentPhone) {
  const picked = selectedDiscounts().map(canonicalizeDiscountName);
  const referralHistoryStudentId = Number(historyStudentSelect.value || 0);
  const identityKey = getIdentityKey(conf.grade, studentName, studentPhone);
  let renewalHistoryStudentId = 0;
  if (picked.includes("老生续报")) {
    if (autoRenewalIdentityKey === identityKey && autoRenewalHistoryStudentId > 0) {
      renewalHistoryStudentId = autoRenewalHistoryStudentId;
    } else {
      renewalHistoryStudentId = await resolveRenewalHistoryStudentId(studentName, studentPhone, conf.grade);
      if (renewalHistoryStudentId > 0) {
        autoRenewalIdentityKey = identityKey;
        autoRenewalHistoryStudentId = renewalHistoryStudentId;
      }
    }
  }
  const discountItems = [];

  if (picked.includes("老带新") && picked.includes("老生续报")) {
    throw new Error("老带新与老生续报不能同时选择");
  }

  const excellent = quoteForm.querySelector("input[name='excellent']:checked")?.value;
  if (picked.includes("考分优惠") && excellent) {
    throw new Error("考分优惠与优秀生优惠不能同时选择");
  }

  picked.forEach((name) => {
    const item = { name, amount: 0 };
    if (name === "老带新" && referralHistoryStudentId > 0) {
      item.history_student_id = referralHistoryStudentId;
    }
    if (name === "老生续报" && renewalHistoryStudentId > 0) {
      item.history_student_id = renewalHistoryStudentId;
    }
    if (name === "五一报名优惠") {
      item.amount = autoWuyiIdentityKey === identityKey ? Number(autoWuyiCaseInput || 0) : 0;
    }
    if (name === "考分优惠") {
      const manualInput = document.querySelector("#scoreDiscountAmount");
      const manualAmount = Number(manualInput?.value || 0);
      if (Number.isNaN(manualAmount) || manualAmount < 0 || manualAmount > 600) {
        throw new Error("考分优惠金额需在0到600之间");
      }
      item.amount = manualAmount;
    }
    discountItems.push(item);
  });

  if (picked.includes("老带新") && referralHistoryStudentId <= 0) {
    throw new Error("已选择老带新，请先搜索并选择老生");
  }

  if (hasDiscount(conf, "优秀生")) {
    if (excellent) {
      const item = { name: excellent, amount: 0 };
      discountItems.push(item);
    }
  }

  return discountItems;
}

async function buildPayload() {
  const conf = currentGrade();
  const name = document.querySelector("#studentName").value.trim();
  const phone = document.querySelector("#studentPhone").value.trim();

  if (!name || !phone) {
    throw new Error("姓名和手机号不能为空");
  }

  const classSubjects = selectedClassSubjects();
  const classMode = selectedClassMode();

  if (classSubjects.length === 0) {
    throw new Error("请至少选择一项班型与科目");
  }
  if (conf.selectionMode === "single" && classSubjects.length !== 1) {
    throw new Error(`${conf.grade}班型与科目仅支持单选`);
  }
  if (typeof conf.maxSelect === "number" && conf.maxSelect > 0 && classSubjects.length > conf.maxSelect) {
    throw new Error(`当前年级最多可选${conf.maxSelect}项`);
  }

  return {
    operator_name: operatorSelect.value,
    source: sourceSelect.value,
    student_info: { name, phone },
    grade: conf.grade,
    class_subjects: classSubjects,
    class_mode: classMode,
    discounts: await buildDiscountPayload(conf, name, phone),
    mode_details: buildModeDetails(classSubjects, classMode),
  };
}

function renderQuoteText(payload, quoteData) {
  if (quoteData?.quote_text) {
    return quoteData.quote_text;
  }

  const lines = [
    `${payload.student_info.name} / ${payload.student_info.phone}`,
    `${payload.grade}`,
    `班型与科目: ${payload.class_subjects.join("、")}`,
    `上课方式: ${payload.class_mode}`,
    `来源: ${payload.source}`,
    `原价: ${quoteData.base_price}`,
    `优惠: ${quoteData.discount_total}`,
    `报价: ${quoteData.final_price}`,
    `算式: ${quoteData.pricing_formula}`,
    `有效期: ${formatDateTime(quoteData.quote_valid_until)}`,
  ];

  if (quoteData.non_price_benefits && quoteData.non_price_benefits.length > 0) {
    lines.push("提示:");
    quoteData.non_price_benefits.forEach((item) => lines.push(`- ${item}`));
  }
  return lines.join("\n");
}

async function copyText(text) {
  if (!navigator.clipboard) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    // ignore clipboard errors
  }
}

async function searchHistory() {
  if (!mustOperatorAndSource()) return;

  const keyword = historyKeyword.value.trim();
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
    if (rows.length === 0) {
      alert("未找到匹配老带新老生");
    }
  } catch (error) {
    alert(`老带新老生搜索失败: ${error.message}`);
  }
}

quoteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!mustOperatorAndSource()) return;

  try {
    const payload = await buildPayload();

    const quoteResultData = await fetchJson(`${API_BASE}/quotes/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const text = renderQuoteText(payload, quoteResultData.data);
    await copyText(text);

    try {
      const saveResult = await fetchJson(`${API_BASE}/enrollments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      quoteResult.textContent = `${text}\n\n已自动生成报名记录，报名ID: ${saveResult.data.enrollment_id}`;
    } catch (saveError) {
      quoteResult.textContent = `${text}\n\n报价已复制，但自动保存失败: ${saveError.message}`;
    }
    clearDirty();
  } catch (error) {
    quoteResult.textContent = `报价失败: ${error.message}`;
  }
});

quoteForm.addEventListener("input", markDirty);
quoteForm.addEventListener("change", markDirty);
window.addEventListener("beforeunload", (event) => {
  if (!isDirty) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});

searchHistoryBtn.addEventListener("click", searchHistory);
studentNameInput.addEventListener("blur", refreshAutoDiscountsByIdentity);
studentPhoneInput.addEventListener("blur", refreshAutoDiscountsByIdentity);

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
    renderGradeTabs();
    renderActiveGradeForm();
    refreshHistoryArea();
  } catch (error) {
    quoteResult.textContent = `页面初始化失败: ${error.message}`;
  }
})();
