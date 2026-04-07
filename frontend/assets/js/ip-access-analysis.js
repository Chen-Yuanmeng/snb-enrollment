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

const ipInput = document.querySelector("#ipInput");
const analyzeBtn = document.querySelector("#analyzeBtn");
const summaryWrap = document.querySelector("#summaryWrap");

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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toApiDateTime(date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

function renderPresetSummary({ quick, hourly }) {
  const location = quick?.location || null;
  const locationText = location?.location || "未知";
  const countryText = location?.country || "-";
  const localText = location?.local || "-";

  const quickWarning = quick?.truncated
    ? "<div class='ip-summary-note'>最近5分钟统计受日志读取上限影响，可能不是全量结果。</div>"
    : "";
  const hourlyWarning = hourly?.truncated
    ? "<div class='ip-summary-note'>最近24小时统计受日志读取上限影响，可能不是全量结果。</div>"
    : "";

  const rows = Array.isArray(hourly?.buckets)
    ? hourly.buckets
        .map(
          (item) => `
      <tr>
        <td>${escapeHtml(item.hour || "-")}</td>
        <td>${escapeHtml(item.count ?? 0)}</td>
      </tr>
    `
        )
        .join("")
    : "";

  summaryWrap.innerHTML = `
    <div class='ip-summary-grid'>
      <div><strong>IP</strong>：${escapeHtml(quick?.ip || hourly?.ip || "-")}</div>
      <div><strong>位置</strong>：${escapeHtml(locationText)}</div>
      <div><strong>区域</strong>：${escapeHtml(countryText)}</div>
      <div><strong>运营商/本地信息</strong>：${escapeHtml(localText)}</div>
      <div><strong>最近5分钟访问次数</strong>：${escapeHtml(quick?.count ?? 0)}</div>
      <div><strong>最近24小时总访问次数</strong>：${escapeHtml(hourly?.total ?? 0)}</div>
    </div>
    ${quickWarning}
    ${hourlyWarning}
    <div class='hourly-table-wrap'>
      <h3 class='hourly-table-title'>最近24小时（逐小时）</h3>
      <table class='stats-table log-table'>
        <thead>
          <tr>
            <th>小时</th>
            <th>访问次数</th>
          </tr>
        </thead>
        <tbody>
          ${rows || "<tr><td colspan='2'>暂无数据</td></tr>"}
        </tbody>
      </table>
    </div>
  `;
}

async function analyzeIp() {
  const ip = ipInput.value.trim();
  if (!ip) {
    summaryWrap.textContent = "请输入 IP 后再分析。";
    return;
  }

  summaryWrap.textContent = "统计中...";
  try {
    const now = new Date();
    const sinceDate = new Date(now.getTime() - 5 * 60 * 1000);

    const quickQuery = new URLSearchParams();
    quickQuery.append("ip", ip);
    quickQuery.append("since", toApiDateTime(sinceDate));
    quickQuery.append("until", toApiDateTime(now));

    const hourlyQuery = new URLSearchParams();
    hourlyQuery.append("ip", ip);
    hourlyQuery.append("last_hours", "24");

    const [quickResult, hourlyResult] = await Promise.all([
      fetchJson(`${API_BASE}/system-access-logs/ip-summary?${quickQuery.toString()}`),
      fetchJson(`${API_BASE}/system-access-logs/ip-hourly?${hourlyQuery.toString()}`),
    ]);

    renderPresetSummary({ quick: quickResult.data || {}, hourly: hourlyResult.data || {} });
  } catch (error) {
    summaryWrap.innerHTML = `<p>统计失败：${escapeHtml(error.message)}</p>`;
  }
}

analyzeBtn.addEventListener("click", () => {
  analyzeIp();
});

async function init() {
  try {
    await resolveApiBase();
  } catch (error) {
    summaryWrap.innerHTML = `<p>${error.message}</p>`;
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const ipFromUrl = (params.get("ip") || "").trim();
  if (ipFromUrl) {
    ipInput.value = ipFromUrl;
    analyzeIp();
  }
}

init();
