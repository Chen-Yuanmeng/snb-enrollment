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
const accommodationForm = document.querySelector("#accommodationForm");
const relatedKeywordInput = document.querySelector("#relatedKeyword");
const searchRelatedEnrollmentBtn = document.querySelector("#searchRelatedEnrollment");
const relatedEnrollmentSelect = document.querySelector("#relatedEnrollmentId");
const hotelWrap = document.querySelector("#hotelWrap");
const roomTypeWrap = document.querySelector("#roomTypeWrap");
const durationWrap = document.querySelector("#durationWrap");
const genderWrap = document.querySelector("#genderWrap");
const otherRoomWrap = document.querySelector("#otherRoomWrap");
const otherRoomTypeNameInput = document.querySelector("#otherRoomTypeName");
const manualNightlyPriceInput = document.querySelector("#manualNightlyPrice");
const noteInput = document.querySelector("#noteInput");
const accommodationResult = document.querySelector("#accommodationResult");

const STORAGE_KEYS = {
  operator: "snb.selectedOperator",
  source: "snb.selectedSource",
};

let accommodationRule = null;

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

async function copyText(text) {
  if (!navigator.clipboard) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    return false;
  }
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

function fillNoteTemplate() {
  noteInput.value = `与  同住`;
  // move cursor to the middle for easy editing
  noteInput.focus();
  noteInput.setSelectionRange(2, 2);
}

function renderChoiceRow(inputHtml, text) {
  return `<label class="choice-item">${inputHtml}<span>${text}</span></label>`;
}

function selectedValueFromWrap(wrap, name) {
  return wrap?.querySelector(`input[name='${name}']:checked`)?.value || "";
}

function selectedHotel() {
  return selectedValueFromWrap(hotelWrap, "hotel");
}

function selectedRoomType() {
  return selectedValueFromWrap(roomTypeWrap, "roomType");
}

function selectedDurationDays() {
  return Number(selectedValueFromWrap(durationWrap, "durationDays"));
}

function selectedGender() {
  return selectedValueFromWrap(genderWrap, "gender");
}

function isOtherRoomType() {
  return selectedRoomType() === "其他房型";
}

function refreshOtherRoomFields() {
  const shouldShow = isOtherRoomType();
  otherRoomWrap.classList.toggle("hidden", !shouldShow);
}

function renderAccommodationRule(rule) {
  const hotels = Array.isArray(rule?.hotels) ? rule.hotels : [];
  hotelWrap.innerHTML = hotels
    .map((item, idx) =>
      renderChoiceRow(
        `<input type='radio' name='hotel' value='${item}' ${idx === 0 ? "checked" : ""} />`,
        item
      )
    )
    .join("");

  const roomTypes = Array.isArray(rule?.room_types) ? rule.room_types : [];
  roomTypeWrap.innerHTML = roomTypes
    .map((item, idx) =>
      renderChoiceRow(
        `<input type='radio' name='roomType' value='${item.name}' ${idx === 0 ? "checked" : ""} />`,
        item.name
      )
    )
    .join("");

  const durations = Array.isArray(rule?.durations) ? rule.durations : [];
  const hasDefault = durations.some((item) => Boolean(item.is_default));
  durationWrap.innerHTML = durations
    .map((item, idx) =>
      renderChoiceRow(
        `<input type='radio' name='durationDays' value='${item.days}' ${
          item.is_default || (!hasDefault && idx === 0) ? "checked" : ""
        } />`,
        item.label
      )
    )
    .join("");

  const genders = Array.isArray(rule?.genders) ? rule.genders : [];
  genderWrap.innerHTML = genders
    .map((item, idx) =>
      renderChoiceRow(
        `<input type='radio' name='gender' value='${item}' ${idx === 0 ? "checked" : ""} />`,
        item
      )
    )
    .join("");
  refreshOtherRoomFields();
}

async function loadAccommodationRule() {
  const result = await fetchJson(`${API_BASE}/rules/accommodation`);
  accommodationRule = result.data || {};
  renderAccommodationRule(accommodationRule);
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

function statusText(status) {
  if (status === "quoted") return "已报价";
  if (status === "paid") return "已缴费";
  if (status === "refund_requested") return "退费申请中";
  if (status === "refunded") return "已退费";
  return status || "-";
}

async function searchRelatedEnrollments() {
  if (!mustOperatorAndSource()) return;
  const keyword = relatedKeywordInput.value.trim();
  const query = new URLSearchParams();
  query.append("limit", "100");
  if (keyword) query.append("keyword", keyword);

  try {
    const result = await fetchJson(`${API_BASE}/accommodations/related-enrollments/search?${query.toString()}`);
    const rows = result.data || [];
    relatedEnrollmentSelect.innerHTML = [`<option value=''>请选择课程报价单</option>`]
      .concat(
        rows.map(
          (item) =>
            `<option value='${item.enrollment_id}'>#${item.enrollment_id} ${item.student_name} / ${item.grade || "-"} / ${statusText(item.status)} / 课程金额: ¥${Number(item.final_price || 0).toFixed(2)}</option>`
        )
      )
      .join("");
    if (rows.length === 0) {
      alert("未找到可关联报价单");
    }
  } catch (error) {
    alert(`搜索关联报价单失败: ${error.message}`);
  }
}

function buildPayload() {
  const relatedEnrollmentId = Number(relatedEnrollmentSelect.value || 0);
  if (relatedEnrollmentId <= 0) {
    throw new Error("请先搜索并选择关联报价单");
  }

  const payload = {
    operator_name: operatorSelect.value,
    source: sourceSelect.value,
    related_enrollment_id: relatedEnrollmentId,
    hotel: selectedHotel(),
    room_type: selectedRoomType(),
    duration_days: selectedDurationDays(),
    gender: selectedGender(),
    note: noteInput.value.trim() || null,
  };

  if (!payload.hotel || !payload.room_type || !payload.duration_days || !payload.gender) {
    throw new Error("请完整选择酒店、房型、时长和性别");
  }

  if (isOtherRoomType()) {
    const name = otherRoomTypeNameInput.value.trim();
    const nightlyPrice = Number(manualNightlyPriceInput.value);
    if (!name) {
      throw new Error("其他房型必须填写房型名称");
    }
    if (!Number.isFinite(nightlyPrice) || nightlyPrice <= 0) {
      throw new Error("其他房型每晚价格必须大于0");
    }
    payload.other_room_type_name = name;
    payload.nightly_price = nightlyPrice;
  }

  return payload;
}

accommodationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!mustOperatorAndSource()) return;

  try {
    const payload = buildPayload();
    const result = await fetchJson(`${API_BASE}/accommodations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = result.data?.quote_text || "";
    await copyText(text);
    accommodationResult.textContent = `${text}\n\n住宿报价单ID: ${result.data?.accommodation_id || "-"}（已复制）`;
  } catch (error) {
    accommodationResult.textContent = `生成失败: ${error.message}`;
  }
});

searchRelatedEnrollmentBtn.addEventListener("click", searchRelatedEnrollments);
relatedKeywordInput.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  await searchRelatedEnrollments();
});
roomTypeWrap.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement) || target.name !== "roomType") return;
  refreshOtherRoomFields();
});
operatorSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.operator, operatorSelect.value);
});
sourceSelect.addEventListener("change", () => {
  writeStoredValue(STORAGE_KEYS.source, sourceSelect.value);
});

(async function boot() {
  try {
    await resolveApiBase();
    await Promise.all([loadOperators(), loadSources(), loadAccommodationRule()]);
  } catch (error) {
    accommodationResult.textContent = `页面初始化失败: ${error.message}`;
  }
})();
