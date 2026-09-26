const $ = (id) => document.getElementById(id);

function esc(value = "") {
  return String(value).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}
function setHTML(id, markup) { const el = $(id); if (el) el.innerHTML = markup; }
function setText(id, value) { const el = $(id); if (el) el.textContent = value; }
function num(value, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString("ko-KR", {maximumFractionDigits:digits}) : "-";
}
function signedPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
}
function flowEok(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return (n > 0 ? "+" : "") + n.toLocaleString("ko-KR") + "억";
}
function tone(value) {
  const n = Number(value);
  return Number.isFinite(n) ? (n > 0 ? "up" : n < 0 ? "down" : "flat") : "flat";
}
function flowTone(value) {
  const n = Number(value);
  return Number.isFinite(n) ? (n > 0 ? "flow-buy" : n < 0 ? "flow-sell" : "flow-flat") : "flow-flat";
}
function relativeTime(value) {
  if (!value) return "미확인";
  const t = new Date(value);
  if (Number.isNaN(t.getTime())) return String(value);
  const minutes = Math.max(0, (Date.now() - t.getTime()) / 60000);
  if (minutes < 1) return "방금";
  if (minutes < 60) return Math.round(minutes) + "분 전";
  if (minutes < 1440) return (minutes / 60).toFixed(minutes < 600 ? 1 : 0) + "시간 전";
  return (minutes / 1440).toFixed(1) + "일 전";
}

function kstDateParts(value) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone:"Asia/Seoul", year:"numeric", month:"2-digit", day:"2-digit"
  }).formatToParts(new Date(value));
  const get = (type) => Number((parts.find((part) => part.type === type) || {}).value);
  return {year:get("year"), month:get("month"), day:get("day")};
}
function durationLabel(totalMinutes, suffix) {
  const minutes = Math.max(0, Math.round(Number(totalMinutes) || 0));
  if (minutes < 60) return Math.max(1, minutes) + "분 " + suffix;
  const hours = Math.floor(minutes / 60);
  const remainMinutes = minutes % 60;
  if (hours < 24) return hours + "시간" + (remainMinutes ? " " + remainMinutes + "분" : "") + " " + suffix;
  const days = Math.floor(hours / 24);
  const remainHours = hours % 24;
  if (days >= 30) {
    const months = Math.floor(days / 30);
    const remainDays = days % 30;
    return months + "개월" + (remainDays ? " " + remainDays + "일" : "") + " " + suffix;
  }
  return days + "일" + (remainHours ? " " + remainHours + "시간" : "") + " " + suffix;
}
function eventTiming(event, nowMs = Date.now()) {
  const x = event && typeof event === "object" ? event : {};
  const timeUnknown = x.time_unknown === true || String(x.time_status || "").toLowerCase() === "unknown" || (!x.datetime_kst && Boolean(x.date_kst));
  const dateOnly = String(x.date_kst || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);

  if (timeUnknown && dateOnly) {
    const targetSerial = Date.UTC(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
    const now = kstDateParts(nowMs);
    const nowSerial = Date.UTC(now.year, now.month - 1, now.day);
    const days = Math.round((targetSerial - nowSerial) / 86400000);
    const dateForLabel = new Date(Date.UTC(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]), 12));
    const dateLabel = new Intl.DateTimeFormat("ko-KR", {
      timeZone:"Asia/Seoul", month:"long", day:"numeric", weekday:"short"
    }).format(dateForLabel) + " · 시간 미확정";
    return {
      valid:true, exact:false, dateLabel,
      countdown:days > 0 ? "D-" + days + " · 시간 미확정" : days === 0 ? "D-DAY · 시간 미확정" : "종료 · 시간 미확정",
      urgency:days < 0 ? "past" : days === 0 ? "today" : days <= 3 ? "soon" : days <= 7 ? "near" : "normal",
      remainingHours:null
    };
  }

  const raw = x.datetime_kst || (!timeUnknown ? x.resolved_datetime_kst : "");
  const target = raw ? new Date(raw) : null;
  if (!target || Number.isNaN(target.getTime())) {
    return {valid:false, exact:false, dateLabel:"일정 시각 확인 중", countdown:"일정 시각 확인 중", urgency:"unknown", remainingHours:null};
  }

  const diffMinutes = Math.round((target.getTime() - nowMs) / 60000);
  const absMinutes = Math.abs(diffMinutes);
  const dateLabel = new Intl.DateTimeFormat("ko-KR", {
    timeZone:"Asia/Seoul", month:"long", day:"numeric", weekday:"short"
  }).format(target) + " · " + new Intl.DateTimeFormat("ko-KR", {
    timeZone:"Asia/Seoul", hour:"numeric", minute:"2-digit", hour12:true
  }).format(target);

  if (diffMinutes < 0) {
    return {valid:true, exact:true, dateLabel, countdown:"종료 · " + durationLabel(absMinutes, "전"), urgency:"past", remainingHours:diffMinutes / 60};
  }

  const hours = diffMinutes / 60;
  const dDay = hours < 24 ? "D-DAY" : "D-" + Math.max(1, Math.floor(hours / 24));
  const urgency = hours < 1 ? "imminent" : hours < 24 ? "today" : hours < 72 ? "soon" : hours < 168 ? "near" : "normal";
  return {valid:true, exact:true, dateLabel, countdown:dDay + " · " + durationLabel(diffMinutes, "남음"), urgency, remainingHours:hours};
}
function eventCard(event) {
  const x = event && typeof event === "object" ? event : {};
  const timing = eventTiming(x);
  const level = x.risk_level || (Number(x.severity) >= 5 ? "HIGH" : Number(x.severity) >= 4 ? "WATCH" : "");
  return '<div class="event-row" data-urgency="' + esc(timing.urgency) + '">' +
    '<div class="event-main"><strong>' + esc(x.title || "주요 일정") + '</strong><div class="event-date">' + esc(timing.dateLabel) + '</div>' +
    '<div class="event-countdown">' + esc(timing.countdown) + '</div></div>' +
    (level ? '<span class="event-level">' + esc(level) + '</span>' : '') +
    '</div>';
}
function initPersistentDetails() {
  document.querySelectorAll("details[data-persist]").forEach((node) => {
    const id = String(node.dataset.persist || "").trim();
    if (!id) return;
    const key = "stock-autoresearch:details:" + location.pathname + ":" + id;
    const toggle = node.querySelector(":scope > summary .disclosure-toggle");
    const syncLabel = () => {
      if (toggle) toggle.textContent = node.open ? "접기" : "상세 보기";
    };
    try {
      const saved = localStorage.getItem(key);
      if (saved === "open") node.open = true;
      if (saved === "closed") node.open = false;
    } catch (_) {}
    syncLabel();
    node.addEventListener("toggle", () => {
      syncLabel();
      try {
        localStorage.setItem(key, node.open ? "open" : "closed");
      } catch (_) {}
    });
  });
}
function issueTemporalLabel(issue) {
  const status = String(issue.status || "WATCHING").toUpperCase();
  const statusWord = {NEW:"등장",WATCHING:"관찰",ACTIVE:"지속",ESCALATING:"강화",EASING:"완화",RESOLVED:"해소"}[status] || status;
  const startRaw = issue.event_time || issue.first_detected || "";
  const start = new Date(startRaw);
  const statusAt = new Date(issue.status_changed_at || issue.last_updated || startRaw);
  const now = Date.now();
  if (Number.isNaN(start.getTime())) return statusWord + " 시각 미확인";
  const hours = Math.max(0, (now - start.getTime()) / 3600000);
  const statusHours = Number.isNaN(statusAt.getTime()) ? null : Math.max(0, (now - statusAt.getTime()) / 3600000);
  if (hours < 24) {
    if (status === "ACTIVE" || status === "WATCHING") return (hours < 1 ? Math.max(1, Math.round(hours * 60)) + "분" : Math.round(hours) + "시간") + "째 " + statusWord + " 중";
    if (statusHours !== null && statusHours < 24) return relativeTime(issue.status_changed_at || issue.last_updated || startRaw) + " " + statusWord;
    return relativeTime(startRaw) + " 시작";
  }
  const date = new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric"}).format(start);
  const days = Math.max(1, Math.floor(hours / 24) + 1);
  if (status === "RESOLVED") return date + " 시작 · " + relativeTime(issue.status_changed_at || issue.last_updated || startRaw) + " 해소";
  return date + " 시작 · " + days + "일째 " + (status === "ACTIVE" ? "지속" : "추적");
}
function issueLatestUpdateLabel(issue) {
  const latest = issue.last_updated || issue.first_detected || issue.event_time;
  if (!latest) return "업데이트 시각 미확인";
  return "추가 소식 · " + relativeTime(latest);
}
function compoundPct(rows, key) {
  if (!rows.length) return null;
  let acc = 1;
  let used = 0;
  rows.forEach((row) => {
    const v = Number((row[key] || {}).change_pct);
    if (Number.isFinite(v)) { acc *= 1 + v / 100; used += 1; }
  });
  return used ? (acc - 1) * 100 : null;
}
function sumFlow(rows, key) {
  return rows.reduce((s, row) => {
    const n = Number(((row.flows_krw_100m || {})[key]));
    return s + (Number.isFinite(n) ? n : 0);
  }, 0);
}
function empty(message, detail = "") {
  return '<div class="empty-state"><strong>' + esc(message) + '</strong>' +
    (detail ? '<div class="source-line">' + esc(detail) + '</div>' : '') + '</div>';
}
function indexCell(block) {
  if (!block || block.close == null) return "-";
  return '<strong>' + esc(num(block.close)) + '</strong><small class="' + tone(block.change_pct) + '">' + esc(signedPct(block.change_pct)) + '</small>';
}
function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  return [value];
}
function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function readableItem(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(readableItem).filter(Boolean).join(" · ");
  const item = asObject(value);
  const head = item.title || item.name || item.term || item.issue_id || item.check || item.action || item.claim || item.text || "";
  const detail = item.reason || item.why || item.summary || item.evidence || item.note || "";
  if (head && detail && String(head) !== String(detail)) return String(head) + " — " + String(detail);
  if (head || detail) return String(head || detail);
  try { return JSON.stringify(item); } catch (_) { return String(item); }
}
function shortText(value, limit = 280) {
  const text = readableItem(value).replace(/\s+/g, " ").trim();
  return text.length > limit ? text.slice(0, limit).trimEnd() + "…" : text;
}
function researchDateValue(item) {
  const x = asObject(item);
  const explicit = x.published_at || x.report_datetime || x.generated_at || x.created_at || x.updated_at || x.sort_at || x.report_date || x.date || "";
  if (explicit) {
    const parsed = new Date(explicit).getTime();
    if (Number.isFinite(parsed)) return parsed;
  }
  const source = [x.title, x.file, x.name].filter(Boolean).join(" ");
  const day = source.match(/20\d{2}-\d{2}-\d{2}/);
  if (!day) return 0;
  const tail = source.slice((day.index || 0) + day[0].length);
  const matches = [...tail.matchAll(/(?:^|\D)([01]\d|2[0-3]):?([0-5]\d)(?!\d)/g)];
  const time = matches.length ? matches[matches.length - 1][1] + ":" + matches[matches.length - 1][2] : "00:00";
  const parsed = new Date(day[0] + "T" + time + ":00+09:00").getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}
function researchDateLabel(item) {
  const x = asObject(item);
  const raw = x.published_at || x.report_datetime || x.generated_at || x.created_at || x.updated_at || x.sort_at || x.report_date || x.date || "";
  if (raw) return String(raw).replace("T", " ").replace(/\+09:00$|Z$/, "").slice(0, 16);
  const source = [x.title, x.file].filter(Boolean).join(" ");
  const day = source.match(/20\d{2}-\d{2}-\d{2}/);
  return day ? day[0] : "작성 시각 미확인";
}
function researchValueMarkup(value) {
  const values = asArray(value).map(readableItem).filter(Boolean);
  if (!values.length) return "";
  if (values.length === 1) return '<p>' + esc(values[0]) + '</p>';
  return '<ul>' + values.map((item) => '<li>' + esc(item) + '</li>').join("") + '</ul>';
}
function researchSection(title, value) {
  const body = researchValueMarkup(value);
  return body ? '<section class="research-section"><h3>' + esc(title) + '</h3>' + body + '</section>' : "";
}
function researchTags(values) {
  const items = asArray(values).map(readableItem).filter(Boolean);
  return items.length ? '<div class="research-tags">' + items.map((item) => '<span>' + esc(item) + '</span>').join("") + '</div>' : "";
}
function sessionCard(row, market) {
  if (market === "kr") {
    return '<div class="session-card"><div class="date"><span>' + esc(row.date || "-") + '</span><span>' + esc(row.status || "") + '</span></div>' +
      '<strong>KOSPI ' + esc(num((row.kospi || {}).close)) + ' <span class="' + tone((row.kospi || {}).change_pct) + '">' + esc(signedPct((row.kospi || {}).change_pct)) + '</span></strong>' +
      '<div class="line"><span>KOSDAQ</span><b class="' + tone((row.kosdaq || {}).change_pct) + '">' + esc(signedPct((row.kosdaq || {}).change_pct)) + '</b></div>' +
      '<div class="line"><span>외국인</span><b class="' + flowTone((row.flows_krw_100m || {}).foreign) + '">' + esc(flowEok((row.flows_krw_100m || {}).foreign)) + '</b></div>' +
      '<div class="line"><span>기관</span><b class="' + flowTone((row.flows_krw_100m || {}).institution) + '">' + esc(flowEok((row.flows_krw_100m || {}).institution)) + '</b></div></div>';
  }
  return '<div class="session-card"><div class="date"><span>' + esc(row.date || "-") + '</span><span>' + esc(row.status || "") + '</span></div>' +
    '<strong>S&P 500 ' + esc(num((row.sp500 || {}).close)) + ' <span class="' + tone((row.sp500 || {}).change_pct) + '">' + esc(signedPct((row.sp500 || {}).change_pct)) + '</span></strong>' +
    '<div class="line"><span>Nasdaq</span><b class="' + tone((row.nasdaq || {}).change_pct) + '">' + esc(signedPct((row.nasdaq || {}).change_pct)) + '</b></div>' +
    '<div class="line"><span>Dow</span><b class="' + tone((row.dow || {}).change_pct) + '">' + esc(signedPct((row.dow || {}).change_pct)) + '</b></div></div>';
}
function renderMetrics(data, krRows, usRows) {
  const el = $("metrics");
  if (!el) return;
  const kr = krRows[0] || {};
  const us = usRows[0] || {};
  const health = data.health || {};
  const cards = [
    ["한국 최근 거래일", kr.date || "-", kr.kospi ? "KOSPI " + signedPct(kr.kospi.change_pct) : "종가 데이터 대기"],
    ["외국인 3일 누적", flowEok(sumFlow(krRows, "foreign")), "최근 실제 거래일 기준"],
    ["미국 최근 거래일", us.date || "-", us.nasdaq ? "Nasdaq " + signedPct(us.nasdaq.change_pct) : "종가 데이터 대기"],
    ["데이터 상태", health.status || "UNKNOWN", (health.issue_count || 0) + "개 점검 항목"]
  ];
  el.innerHTML = cards.map(([label, value, small]) =>
    '<div class="metric"><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong><small>' + esc(small) + '</small></div>'
  ).join("");
}
function renderBrief(data) {
  const supervisor = data.supervisor_latest || {};
  const narrative = supervisor.market_narrative != null && supervisor.market_narrative !== ""
    ? supervisor.market_narrative
    : supervisor.summary;
  const rows = asArray(narrative).slice(0, 4);
  setHTML("market-narrative", rows.length
    ? rows.map((x) => '<p class="brief-paragraph">' + esc(typeof x === "string" ? x : (x.text || x.summary || "")) + '</p>').join("")
    : empty("AI 시장 해설을 기다리는 중입니다."));
  const focus = asArray(supervisor.market_focus).slice(0, 5);
  setHTML("market-focus", focus.length
    ? focus.map((x, i) => '<div class="mini-row"><strong>' + (i + 1) + '. ' + esc(typeof x === "string" ? x : (x.title || x.name || "확인 항목")) + '</strong><span>' + esc(typeof x === "string" ? "" : (x.reason || x.why || "")) + '</span></div>').join("")
    : empty("현재 우선 확인 항목이 없습니다."));
  const invalid = asArray(supervisor.invalidation_checks || supervisor.next_checks).slice(0, 4);
  setHTML("market-invalidation", invalid.length
    ? invalid.map((x) => '<div class="mini-row"><span>' + esc(typeof x === "string" ? x : (x.check || x.title || x.reason || "")) + '</span></div>').join("")
    : empty("다음 관측에서 재검증합니다."));
  setText("market-brief-status", supervisor.processed_at ? "최근 AI · " + relativeTime(supervisor.processed_at) : ":00/:30 AI");
}
function renderQuickSessions(krRows, usRows) {
  setHTML("quick-korea-sessions", krRows.length ? krRows.map((r) => sessionCard(r, "kr")).join("") : empty("한국 거래일 데이터 없음"));
  setHTML("quick-us-sessions", usRows.length ? usRows.map((r) => sessionCard(r, "us")).join("") : empty("미국 거래일 데이터 없음"));
  const krCum = compoundPct(krRows, "kospi"), kdCum = compoundPct(krRows, "kosdaq");
  setHTML("quick-korea-summary", krRows.length ? [
    ["KOSPI 3일", signedPct(krCum)],
    ["KOSDAQ 3일", signedPct(kdCum)],
    ["외국인", flowEok(sumFlow(krRows, "foreign"))],
    ["기관", flowEok(sumFlow(krRows, "institution"))],
  ].map(([a,b]) => '<div class="summary-item"><span>' + esc(a) + '</span><strong>' + esc(b) + '</strong></div>').join("") : "");
  const spCum = compoundPct(usRows, "sp500"), nqCum = compoundPct(usRows, "nasdaq"), dwCum = compoundPct(usRows, "dow");
  setHTML("quick-us-summary", usRows.length ? [
    ["S&P 500 3일", signedPct(spCum)],
    ["Nasdaq 3일", signedPct(nqCum)],
    ["Dow 3일", signedPct(dwCum)],
    ["최근일", usRows[0] ? usRows[0].date : "-"],
  ].map(([a,b]) => '<div class="summary-item"><span>' + esc(a) + '</span><strong>' + esc(b) + '</strong></div>').join("") : "");
}
function renderSessionTables(session, krRows, usRows) {
  setText("three-session-updated", session.updated_at ? "갱신 · " + relativeTime(session.updated_at) : "데이터 없음");
  setHTML("korea-session-history", krRows.length ? '<div class="table-scroll"><table><thead><tr><th>날짜</th><th>KOSPI</th><th>KOSDAQ</th><th>외국인</th><th>기관</th><th>개인</th></tr></thead><tbody>' +
    krRows.map((row) => '<tr><td><strong>' + esc(row.date || "-") + '</strong><small>' + esc(row.note || "") + '</small></td><td>' + indexCell(row.kospi) + '</td><td>' + indexCell(row.kosdaq) + '</td><td class="' + flowTone((row.flows_krw_100m || {}).foreign) + '">' + esc(flowEok((row.flows_krw_100m || {}).foreign)) + '</td><td class="' + flowTone((row.flows_krw_100m || {}).institution) + '">' + esc(flowEok((row.flows_krw_100m || {}).institution)) + '</td><td class="' + flowTone((row.flows_krw_100m || {}).individual) + '">' + esc(flowEok((row.flows_krw_100m || {}).individual)) + '</td></tr>').join("") +
    '</tbody></table></div>' : empty("한국 최근 거래일 데이터가 없습니다."));
  setHTML("us-session-history", usRows.length ? '<div class="table-scroll"><table><thead><tr><th>날짜</th><th>S&P 500</th><th>Nasdaq</th><th>Dow</th><th>메모</th></tr></thead><tbody>' +
    usRows.map((row) => '<tr><td><strong>' + esc(row.date || "-") + '</strong></td><td>' + indexCell(row.sp500) + '</td><td>' + indexCell(row.nasdaq) + '</td><td>' + indexCell(row.dow) + '</td><td><small>' + esc(row.note || "") + '</small></td></tr>').join("") +
    '</tbody></table></div>' : empty("미국 최근 거래일 데이터가 없습니다."));
  const notes = (session.holiday_notes || []).map((x) => (x.market === "KR" ? "한국" : x.market) + " " + (x.from || "") + "~" + (x.to || "") + " " + (x.reason || "휴장"));
  setHTML("session-holiday-note", notes.length ? '<div class="notice warn">' + esc(notes.join(" · ")) + ' · 휴장 중 실시간 빈 값을 표시하지 않고 최근 실제 거래일을 유지합니다.</div>' : "");
}
function renderFlow(krRows) {
  const latest = krRows[0] || null;
  const cards = $("investor-flow-cards");
  if (cards) {
    if (!latest) cards.innerHTML = empty("수급 데이터가 없습니다.");
    else {
      const lf = latest.flows_krw_100m || {};
      const items = [
        ["외국인 최근일", lf.foreign, latest.date],
        ["기관 최근일", lf.institution, latest.date],
        ["외국인 3일 누적", sumFlow(krRows, "foreign"), "최근 3거래일"],
        ["기관 3일 누적", sumFlow(krRows, "institution"), "최근 3거래일"],
      ];
      cards.innerHTML = items.map(([label,value,sub]) => '<div class="flow-card"><span>' + esc(label) + '</span><strong class="' + flowTone(value) + '">' + esc(flowEok(value)) + '</strong><small>' + esc(sub) + '</small></div>').join("");
    }
  }
  setText("investor-flow-status", latest ? latest.date + " 종가 기준" : "데이터 없음");
  setHTML("investor-flow-history", krRows.length ? krRows.map((row) => {
    const f = row.flows_krw_100m || {};
    return '<div class="flow-history-row"><strong>' + esc(row.date || "-") + '</strong><span class="' + flowTone(f.foreign) + '">외국인 ' + esc(flowEok(f.foreign)) + '</span><span class="' + flowTone(f.institution) + '">기관 ' + esc(flowEok(f.institution)) + '</span><span class="' + flowTone(f.individual) + '">개인 ' + esc(flowEok(f.individual)) + '</span></div>';
  }).join("") : empty("수급 이력 없음"));
  if ($("investor-flow-reading")) {
    if (!latest) setHTML("investor-flow-reading", empty("수급 해석 대기"));
    else {
      const f3 = sumFlow(krRows, "foreign"), i3 = sumFlow(krRows, "institution");
      let headline = "외국인과 기관의 3일 방향이 엇갈립니다.";
      if (f3 > 0 && i3 > 0) headline = "외국인과 기관이 최근 3거래일 모두 합산 기준 순매수입니다.";
      if (f3 < 0 && i3 < 0) headline = "외국인과 기관이 최근 3거래일 합산 기준 모두 순매도입니다.";
      const detail = "외국인 " + flowEok(f3) + ", 기관 " + flowEok(i3) + "입니다. 하루 숫자보다 3거래일 누적과 지수 방향을 함께 보도록 구성했습니다.";
      setHTML("investor-flow-reading", '<div class="flow-reading"><strong>' + esc(headline) + '</strong><p>' + esc(detail) + '</p><div class="source-line">원자료에 저장된 종가 수급값을 그대로 합산합니다. 휴장일은 새 값으로 간주하지 않습니다.</div></div>');
    }
  }
}
function issueImpactGroup(value) {
  const text = String(value || "MIXED").toUpperCase();
  if (text.startsWith("POSITIVE")) return "POSITIVE";
  if (text.startsWith("NEGATIVE")) return "NEGATIVE";
  return "MIXED";
}
function issueImpactLabel(value) {
  const group = issueImpactGroup(value);
  return group === "POSITIVE" ? "호재 가능" : group === "NEGATIVE" ? "악재 가능" : "혼합/양면";
}
function issuePricingLabel(value) {
  const key = String(value || "").toUpperCase();
  const labels = {
    "NOT_PRICED":"미반영 가능",
    "EARLY":"초기 반영",
    "PARTLY_PRICED":"일부 반영",
    "ACTIVE_MARKET_DRIVER":"현재 가격결정",
    "FULLY_PRICED":"상당부분 반영",
    "LOW_CURRENT_PRICING":"현재 반영 낮음",
    "WATCH":"관찰",
    "UNCERTAIN":"반영 불확실"
  };
  return labels[key] || (key ? key.replaceAll("_"," ") : "반영 판단 대기");
}
function renderIssues(data) {
  const target = $("market-issue-list");
  if (!target) return;
  const digest = asObject(data.news_issue_digest);
  const digestIssues = asArray(digest.issues);
  const fallback = asObject(data.market_issues);
  const rows = (digestIssues.length ? digestIssues : asArray(fallback.issues)).slice();
  const researchMode = target.dataset.mode === "research";
  const rank = {ESCALATING:0,NEW:1,ACTIVE:2,WATCHING:3,EASING:4,RESOLVED:5};
  const sev = {CRITICAL:0,HIGH:1,MEDIUM:2,LOW:3};

  if (researchMode) {
    rows.sort((a,b) => researchDateValue({
      updated_at:b.last_updated || b.latest_update || b.event_time || b.first_detected
    }) - researchDateValue({
      updated_at:a.last_updated || a.latest_update || a.event_time || a.first_detected
    }));
  } else {
    rows.sort((a,b)=>
      (rank[String(a.status||"WATCHING").toUpperCase()]??9)-(rank[String(b.status||"WATCHING").toUpperCase()]??9) ||
      (sev[String(a.severity||"LOW").toUpperCase()]??9)-(sev[String(b.severity||"LOW").toUpperCase()]??9) ||
      String(b.last_updated||b.last_seen||"").localeCompare(String(a.last_updated||a.last_seen||""))
    );
  }

  const limit = target.dataset.limit ? Number(target.dataset.limit) : rows.length;
  const selected = rows.slice(0, Number.isFinite(limit) ? limit : rows.length);
  if (!selected.length) {
    target.innerHTML = empty("누적된 시장 이슈가 아직 없습니다.");
    return;
  }

  if (researchMode) {
    target.innerHTML = selected.map((x) => {
      const status = String(x.status || "WATCHING").toUpperCase();
      const label = {NEW:"신규",WATCHING:"관찰",ACTIVE:"지속",ESCALATING:"강화",EASING:"완화",RESOLVED:"해소"}[status] || status;
      const impact = issueImpactGroup(x.impact);
      const sources = asArray(x.sources).map((source) => {
        const s = asObject(source);
        return s.url ? '<a class="button" href="' + esc(s.url) + '" target="_blank" rel="noreferrer">' + esc(s.publisher || "원문") + '</a>' : "";
      }).filter(Boolean).join("");
      return '<details class="research-detail" data-level="' + esc(status) + '">' +
        '<summary><div class="research-summary-main"><div class="research-title-line"><span class="issue-status">' + esc(label) + '</span><span class="issue-impact ' + impact.toLowerCase() + '">' + esc(issueImpactLabel(x.impact)) + '</span><strong>' + esc(x.title || x.issue_id || "시장 이슈") + '</strong></div>' +
        '<div class="research-meta"><span>' + esc(x.scope === "KOREA" ? "국내" : "글로벌") + '</span><span>' + esc(x.category || "기타") + '</span><span>' + esc(researchDateLabel({updated_at:x.last_updated || x.event_time || x.first_detected})) + '</span></div>' +
        '<p>' + esc(shortText(x.summary || x.reason || x.latest_update || "", 260)) + '</p></div><span class="research-toggle">상세 보기</span></summary>' +
        '<div class="research-expanded"><div class="research-section-grid">' +
        researchSection("전체 요약", x.summary || x.latest_update) +
        researchSection("왜 중요한가", x.why_market_matters) +
        researchSection("현재 상황", x.latest_update || x.reason) +
        researchSection("시장 영향·전달 경로", asArray(x.transmission_path)) +
        researchSection("관련 업종·자산", asArray(x.affected_assets)) +
        researchSection("확인된 사실·근거", x.confirmed_facts || x.evidence) +
        researchSection("반론·불확실성", x.unconfirmed || x.unknowns) +
        researchSection("앞으로 확인할 것", x.next_check) +
        '</div>' + (sources ? '<div class="research-actions">' + sources + '</div>' : '<div class="notice">상세 출처 링크를 추가 확인 중입니다.</div>') + '</div></details>';
    }).join("");
    return;
  }

  target.innerHTML = selected.map((x) => {
    const status = String(x.status || "WATCHING").toUpperCase();
    const label = {NEW:"신규",WATCHING:"관찰",ACTIVE:"지속",ESCALATING:"강화",EASING:"완화",RESOLVED:"해소"}[status] || status;
    const impact = issueImpactGroup(x.impact);
    return '<div class="mini-row issue-mini" data-level="' + esc(status) + '">' +
      '<div class="issue-mini-head"><strong>[' + esc(label) + '] ' + esc(x.title || x.issue_id || "이슈") + '</strong>' +
      '<span class="issue-impact ' + impact.toLowerCase() + '">' + esc(issueImpactLabel(x.impact)) + '</span></div>' +
      '<span>' + esc(x.reason || x.summary || "") + '</span>' +
      '<div class="issue-mini-meta"><small>' + esc(x.scope==="KOREA"?"국내":"글로벌") + ' · ' + esc(x.category||"기타") + ' · ' + esc(issuePricingLabel(x.pricing_status)) + '</small>' +
      '<small>사건 ' + esc(x.event_time || "미확인") + ' · 최근 ' + esc((x.last_updated || x.last_seen) ? relativeTime(x.last_updated || x.last_seen) : "미확인") + '</small></div></div>';
  }).join("");
}
function issueHotScore(issue) {
  const statusScore = {ESCALATING:24,NEW:20,ACTIVE:14,WATCHING:8,EASING:3,RESOLVED:0}[String(issue.status||"WATCHING").toUpperCase()] || 0;
  const severityScore = {CRITICAL:18,HIGH:12,MEDIUM:6,LOW:2}[String(issue.severity||"LOW").toUpperCase()] || 0;
  const velocity = Math.max(0, Number(issue.article_velocity || 0));
  const publishers = Math.max(0, Number(issue.publisher_count || issue.source_count || 0));
  const articles = Math.max(0, Number(issue.article_count || 0));
  const official = (issue.confirmed_facts||[]).length ? 5 : 0;
  const reaction = [issue.market_reaction,issue.foreign_flow_reaction,issue.institution_flow_reaction,issue.turnover_reaction].filter(Boolean).length * 3;
  const recencyRaw = issue.last_updated || issue.event_time || issue.first_detected;
  const recencyHours = recencyRaw ? Math.max(0,(Date.now()-new Date(recencyRaw).getTime())/3600000) : 999;
  const recency = recencyHours <= 1 ? 18 : recencyHours <= 6 ? 12 : recencyHours <= 24 ? 6 : 0;
  return statusScore + severityScore + velocity*4 + publishers*2 + Math.min(articles,20) + official + reaction + recency;
}
function renderHotIssues(data) {
  const root=$("hot-issue-list");
  if(!root) return;
  const rows=((data.news_issue_digest||{}).issues||[])
    .filter((x)=>String(x.status||"").toUpperCase()!=="RESOLVED")
    .map((x)=>({...x,_hotScore:issueHotScore(x)}))
    .sort((a,b)=>b._hotScore-a._hotScore || String(b.last_updated||"").localeCompare(String(a.last_updated||"")))
    .slice(0,10);
  root.innerHTML=rows.length?rows.map((x,i)=>{
    const status=String(x.status||"WATCHING").toUpperCase();
    const publishers=Number(x.publisher_count||x.source_count||0);
    const articles=Number(x.article_count||0);
    const velocity=Number(x.article_velocity||0);
    return '<a class="hot-issue-card" href="#issue-'+esc(x.issue_id||i)+'" data-level="'+esc(status)+'">'+
      '<div class="hot-rank">'+(i+1)+'</div><div><div class="hot-head"><strong>🔥 '+esc(x.title||"이슈")+'</strong><span>'+esc(issueTemporalLabel(x))+'</span></div>'+
      '<p>'+esc(x.latest_update||x.summary||"")+'</p>'+
      '<small>관련 기사 '+esc(articles||"-")+'건 · 매체 '+esc(publishers||"-")+'개 · 최근 증가 +'+esc(Math.max(0,velocity))+' · '+esc(status)+'</small>'+
      '</div></a>';
  }).join(""):empty("급부상 이슈 점수를 계산할 데이터가 아직 부족합니다.");
}
function renderIssueTracker(data) {
  const root = $("issue-full-list");
  if (!root) return;
  const store = data.news_issue_digest || {};
  const rows = (store.issues || []).slice();
  const statusLabel = {NEW:"등장",WATCHING:"관찰",ACTIVE:"지속",ESCALATING:"강화",EASING:"완화",RESOLVED:"해소"};
  const statuses = ["ALL","NEW","ESCALATING","ACTIVE","WATCHING","EASING","RESOLVED"];
  const scopes = ["ALL","GLOBAL","KOREA"];
  const impacts = ["ALL","POSITIVE","NEGATIVE","MIXED"];

  setText("issue-updated", store.updated_at ? "갱신 · " + relativeTime(store.updated_at) : "데이터 없음");
  setText("issue-total-count", rows.length + "개");
  const scan = store.scan_summary || {};
  const discovery = data.discovery || {};
  const liveArticleCount = Number(discovery.item_count);
  const liveGroupCount = Number(discovery.query_group_count);
  setHTML("issue-scan-summary",
    '<strong>:00/:30 전체 뉴스 이슈화</strong><div class="source-line">' +
    esc(scan.note || "최신 뉴스 후보를 넓게 수집한 뒤 중복 기사·단순 재탕·시장 연관성이 낮은 항목을 제거하고 사건 단위로 묶습니다.") +
    (Number.isFinite(liveArticleCount) ? " · 현재 센서 후보 " + esc(liveArticleCount) + "건" : (scan.actual_articles ? " · 직전 후보 " + esc(scan.actual_articles) + "건" : "")) +
    (Number.isFinite(liveGroupCount) ? " · 검색축 " + esc(liveGroupCount) + "개" : "") +
    " · 최대 수집 " + esc(scan.target_articles || discovery.news_scan_target || 500) + "건 · 이슈 최대 " + esc(store.max_issues || 100) + "개 · 해소 이슈 최소 " + esc(store.retention_days || 7) + "일 보존</div>"
  );

  const counts = {};
  rows.forEach((x) => { const s=String(x.status||"WATCHING").toUpperCase(); counts[s]=(counts[s]||0)+1; });
  setHTML("issue-tracker-counts", ["NEW","ESCALATING","ACTIVE","WATCHING","EASING","RESOLVED"].map((s) =>
    '<div class="issue-count-card" data-level="' + s + '"><span>' + esc(statusLabel[s]) + '</span><strong>' + esc(counts[s] || 0) + '</strong></div>'
  ).join(""));
  setHTML("issue-status-filters", statuses.map((s,i) =>
    '<button type="button" class="issue-filter' + (i===0?" active":"") + '" data-status="' + s + '">' + esc(s==="ALL"?"전체":statusLabel[s]) + '</button>'
  ).join(""));
  setHTML("issue-scope-filters", scopes.map((s,i) =>
    '<button type="button" class="issue-filter' + (i===0?" active":"") + '" data-scope="' + s + '">' + esc(s==="ALL"?"전체":s==="KOREA"?"국내":"글로벌") + '</button>'
  ).join(""));
  setHTML("issue-impact-filters", impacts.map((s,i) =>
    '<button type="button" class="issue-filter' + (i===0?" active":"") + '" data-impact="' + s + '">' + esc(s==="ALL"?"전체":s==="POSITIVE"?"호재":s==="NEGATIVE"?"악재":"혼합") + '</button>'
  ).join(""));

  let activeStatus="ALL";
  let activeScope="ALL";
  let activeImpact="ALL";
  let activeAge="7";
  let activeSort="priority";
  let query="";
  const issueTime = (x, key) => {
    const raw = x[key] || "";
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? 0 : d.getTime();
  };
  const render = () => {
    const nowMs = Date.now();
    const filtered = rows.filter((x) => {
      const s=String(x.status||"WATCHING").toUpperCase();
      const scope=String(x.scope||"GLOBAL").toUpperCase();
      const impact=issueImpactGroup(x.impact);
      if (activeStatus!=="ALL" && s!==activeStatus) return false;
      if (activeScope!=="ALL" && scope!==activeScope) return false;
      if (activeImpact!=="ALL" && impact!==activeImpact) return false;
      if (activeAge!=="ALL") {
        const days=Number(activeAge);
        const eventMs=issueTime(x,"event_time") || issueTime(x,"last_updated") || issueTime(x,"first_detected");
        if (eventMs && nowMs-eventMs > days*86400000) return false;
      }
      if (!query) return true;
      const hay=[x.title,x.summary,x.category,x.scope,x.why_market_matters,x.pricing_status,(x.affected_assets||[]).join(" "),(x.transmission_path||[]).join(" ")].join(" ").toLowerCase();
      return hay.includes(query);
    });
    const statusRank={ESCALATING:0,NEW:1,ACTIVE:2,WATCHING:3,EASING:4,RESOLVED:5};
    const severityRank={CRITICAL:0,HIGH:1,MEDIUM:2,LOW:3};
    filtered.sort((a,b)=>{
      if(activeSort==="updated") return Math.max(issueTime(b,"last_updated"),issueTime(b,"event_time"),issueTime(b,"first_detected"))-Math.max(issueTime(a,"last_updated"),issueTime(a,"event_time"),issueTime(a,"first_detected"));
      if(activeSort==="event") return issueTime(b,"event_time")-issueTime(a,"event_time");
      if(activeSort==="detected") return issueTime(b,"first_detected")-issueTime(a,"first_detected");
      const pricingScore={ACTIVE_MARKET_DRIVER:24,NOT_PRICED:18,EARLY:15,PARTLY_PRICED:11,LOW_CURRENT_PRICING:8,WATCH:6,UNCERTAIN:5,FULLY_PRICED:2};
      const priorityScore=(x)=>{
        const status=String(x.status||"WATCHING").toUpperCase();
        const severity=String(x.severity||"LOW").toUpperCase();
        const pricing=String(x.pricing_status||"UNCERTAIN").toUpperCase();
        const statusPoints={ESCALATING:30,ACTIVE:24,NEW:20,WATCHING:12,EASING:6,RESOLVED:0}[status]||0;
        const severityPoints={CRITICAL:26,HIGH:18,MEDIUM:10,LOW:3}[severity]||0;
        const velocity=Math.min(20,Math.max(0,Number(x.article_velocity||0)));
        const sourceBreadth=Math.min(12,Math.max(0,Number(x.independent_story_count_estimate||x.source_count||(x.sources||[]).length||0)));
        const assetBreadth=Math.min(8,asArray(x.affected_assets).length*2);
        const triggerReady=x.next_check?5:0;
        return statusPoints+severityPoints+(pricingScore[pricing]||0)+velocity+sourceBreadth+assetBreadth+triggerReady;
      };
      const priorityDiff=priorityScore(b)-priorityScore(a);
      if(priorityDiff) return priorityDiff;
      return (issueTime(b,"last_updated")||0)-(issueTime(a,"last_updated")||0);
    });
    setText("issue-total-count", filtered.length + "개 / 전체 " + rows.length + "개");
    root.innerHTML = filtered.length ? filtered.map((x) => {
      const status=String(x.status||"WATCHING").toUpperCase();
      const impact=issueImpactGroup(x.impact);
      const sources=(x.sources||[]).map((s) =>
        '<a class="issue-source" href="' + esc(s.url||"#") + '" target="_blank" rel="noreferrer"><strong>' + esc(s.publisher||"출처") + '</strong><span>' + esc(s.title||s.url||"") + '</span></a>'
      ).join("");
      const history=(x.history||[]).slice().reverse().map((h) =>
        '<div class="issue-history-row"><time>' + esc(h.at||h.event_time||"") + '</time><strong>' + esc((h.from?statusLabel[String(h.from).toUpperCase()]+" → ":"") + (statusLabel[String(h.to||status).toUpperCase()]||h.to||status)) + '</strong><span>' + esc(h.note||"") + '</span></div>'
      ).join("");
      const facts=(x.confirmed_facts||x.evidence||[]);
      const unknowns=(x.unconfirmed||x.unknowns||[]);
      return '<details id="issue-' + esc(x.issue_id||"unknown") + '" class="issue-detail" data-level="' + esc(status) + '" data-impact="' + esc(impact) + '">' +
        '<summary><div class="issue-summary-main"><div class="issue-title-line">' +
          '<span class="issue-status">' + esc(statusLabel[status]||status) + '</span>' +
          '<span class="issue-impact ' + impact.toLowerCase() + '">' + esc(issueImpactLabel(x.impact)) + '</span>' +
          '<strong>' + esc(x.title||x.issue_id||"이슈") + '</strong></div><p>' + esc(x.summary||x.reason||"") + '</p></div>' +
        '<div class="issue-summary-meta"><span>' + esc(x.scope==="KOREA"?"국내":"글로벌") + '</span><span>' + esc(x.category||"") + '</span><b>' + esc(x.severity||"") + '</b>' +
        '<span>' + esc(issuePricingLabel(x.pricing_status)) + '</span><span>출처 ' + esc(x.source_count ?? (x.sources||[]).length) + '개</span>' +
        '<small><b>' + esc(issueTemporalLabel(x)) + '</b><br>' + esc(issueLatestUpdateLabel(x)) + ' · 최초 감지 ' + esc(x.first_detected?relativeTime(x.first_detected):"미확인") + '</small></div></summary>' +
        '<div class="issue-expanded">' +
          '<div class="issue-explain-grid">' +
            '<section><h3>어떤 이슈인가</h3><p>' + esc(x.summary||"") + '</p></section>' +
            '<section><h3>왜 시장에 중요한가</h3><p>' + esc(x.why_market_matters||"시장 영향 경로를 추가 확인 중입니다.") + '</p></section>' +
            '<section><h3>시장 반영 판단</h3><p><strong>' + esc(issuePricingLabel(x.pricing_status)) + '</strong>' + (x.pricing_reason ? " · " + esc(x.pricing_reason) : "") + '</p></section>' +
            '<section><h3>다음 확인</h3><p>' + esc(x.next_check||"다음 :00/:30 사이클에서 추가 확인합니다.") + '</p></section>' +
          '</div>' +
          '<div class="issue-detail-grid">' +
            '<section><h3>전달 경로</h3><div class="issue-tags">' + (x.transmission_path||[]).map((v)=>'<span>'+esc(v)+'</span>').join("") + '</div></section>' +
            '<section><h3>영향 자산·섹터</h3><div class="issue-tags">' + (x.affected_assets||[]).map((v)=>'<span>'+esc(v)+'</span>').join("") + '</div></section>' +
            '<section><h3>확인된 사실·근거</h3>' + (facts.length?'<ul>'+facts.map((v)=>'<li>'+esc(typeof v==="string"?v:(v.text||v.claim||JSON.stringify(v)))+'</li>').join("")+'</ul>':'<p class="muted">구조화된 사실 목록을 추가 확인 중입니다.</p>') + '</section>' +
            '<section><h3>미확인·반증 조건</h3>' + (unknowns.length?'<ul>'+unknowns.map((v)=>'<li>'+esc(typeof v==="string"?v:(v.text||JSON.stringify(v)))+'</li>').join("")+'</ul>':'<p class="muted">현재 별도 미확인 항목 없음</p>') + '</section>' +
          '</div>' +
          '<section class="issue-history"><h3>상태 변경 기록</h3>' + (history||'<div class="issue-history-row"><time>'+esc(x.first_detected||x.event_time||"")+'</time><strong>'+esc(statusLabel[status]||status)+'</strong><span>현재 저장된 첫 상태</span></div>') + '</section>' +
          '<section class="issue-sources"><h3>출처</h3>' + (sources||'<p class="muted">출처 링크 추가 확인 중</p>') + '</section>' +
        '</div></details>';
    }).join("") : empty("조건에 맞는 이슈가 없습니다.");
  };
  render();

  const search=$("issue-search");
  if (search) search.addEventListener("input",()=>{query=search.value.trim().toLowerCase();render();});
  const statusFilters=$("issue-status-filters");
  if (statusFilters) statusFilters.addEventListener("click",(event)=>{
    const button=event.target.closest("[data-status]"); if(!button) return;
    activeStatus=button.dataset.status||"ALL";
    statusFilters.querySelectorAll(".issue-filter").forEach((x)=>x.classList.toggle("active",x===button));
    render();
  });
  const scopeFilters=$("issue-scope-filters");
  if (scopeFilters) scopeFilters.addEventListener("click",(event)=>{
    const button=event.target.closest("[data-scope]"); if(!button) return;
    activeScope=button.dataset.scope||"ALL";
    scopeFilters.querySelectorAll(".issue-filter").forEach((x)=>x.classList.toggle("active",x===button));
    render();
  });
  const impactFilters=$("issue-impact-filters");
  if (impactFilters) impactFilters.addEventListener("click",(event)=>{
    const button=event.target.closest("[data-impact]"); if(!button) return;
    activeImpact=button.dataset.impact||"ALL";
    impactFilters.querySelectorAll(".issue-filter").forEach((x)=>x.classList.toggle("active",x===button));
    render();
  });
  const ageFilter=$("issue-age-filter");
  if(ageFilter) ageFilter.addEventListener("change",()=>{activeAge=ageFilter.value||"7";render();});
  const sortFilter=$("issue-sort");
  if(sortFilter) sortFilter.addEventListener("change",()=>{activeSort=sortFilter.value||"priority";render();});
}

function renderResearch(data) {
  const supervisor = asObject(data.supervisor_latest);
  setText("supervisor-status", supervisor.status || "NO DATA");

  const discovery = asObject(data.discovery);
  const trends = asArray(supervisor.dynamic_trends).length ? asArray(supervisor.dynamic_trends) : asArray(discovery.trending_terms);
  setHTML("dynamic-trends", trends.length ? trends.slice(0,10).map((x) =>
    '<div class="mini-row"><strong>' + esc(typeof x === "string" ? x : (x.title || x.name || x.term || "트렌드")) + '</strong><span>' +
    esc(typeof x === "string" ? "" : (x.reason || x.evidence || (x.count != null ? "언급 " + x.count + "건" : ""))) + '</span></div>'
  ).join("") : empty("동적 트렌드를 수집 중입니다."));

  const filings = asArray(discovery.new_dart_filings).slice().sort((a,b)=>researchDateValue(b)-researchDateValue(a)).slice(0,8);
  setHTML("new-filings", filings.length ? filings.map((x) =>
    '<a class="mini-row" href="' + esc(x.url || "#") + '" target="_blank" rel="noreferrer"><strong>' + esc(x.corp_name || x.company || "") + '</strong><span>' +
    esc(x.report_nm || x.title || "") + '</span><small>' + esc(researchDateLabel(x)) + '</small></a>'
  ).join("") : empty("새 공시 없음 또는 DART 연결 대기"));

  const supervisorSummary = asArray(supervisor.summary);
  const supervisorFocus = asArray(supervisor.market_focus);
  const supervisorRisks = asArray(supervisor.overnight_risks);
  const supervisorInvalidation = asArray(supervisor.invalidation_checks);
  const supervisorChecks = asArray(supervisor.next_checks);
  const supervisorActions = asArray(supervisor.actions);
  const supervisorSource = supervisor.research_report_path
    ? "https://github.com/juhwan7/stock-autoresearch/blob/main/" + encodeURI(supervisor.research_report_path)
    : "https://github.com/juhwan7/stock-autoresearch/blob/main/data/supervisor/latest-report.json";
  const supervisorTitle = supervisor.title || (supervisor.supervisor ? "Supervisor " + supervisor.supervisor + " 최신 시장 리서치" : "최신 AI 심층 리서치");
  const supervisorPreview = supervisorSummary.length ? supervisorSummary.slice(0,3).map(readableItem).join(" ") : readableItem(supervisor.market_narrative);
  setHTML("supervisor-research", Object.keys(supervisor).length ? '<details class="research-detail">' +
    '<summary><div class="research-summary-main"><div class="research-title-line"><strong>' + esc(supervisorTitle) + '</strong></div>' +
    '<div class="research-meta"><span>' + esc(researchDateLabel({generated_at:supervisor.processed_at})) + '</span><span>' + esc(supervisor.status || "") + '</span>' +
    (supervisorFocus.length ? '<span>관련 이슈 ' + esc(supervisorFocus.length) + '개</span>' : '') + '</div><p>' + esc(shortText(supervisorPreview, 360)) + '</p>' +
    researchTags(supervisorFocus.slice(0,4).map((x)=>asObject(x).issue_id || asObject(x).title || "")) +
    '</div><span class="research-toggle">상세 보기</span></summary><div class="research-expanded"><div class="research-section-grid">' +
    researchSection("전체 요약", supervisorSummary) +
    researchSection("왜 중요한가", supervisor.market_narrative) +
    researchSection("현재 상황·핵심 이슈", supervisorFocus) +
    researchSection("시장 영향·리스크", supervisorRisks) +
    researchSection("반론·해석을 바꿀 조건", supervisorInvalidation) +
    researchSection("앞으로 확인할 것", supervisorChecks) +
    researchSection("이번 리서치의 확인·조치", supervisorActions) +
    '</div><div class="research-actions"><a class="button primary" href="' + esc(supervisorSource) + '" target="_blank" rel="noreferrer">원본 리서치·데이터 보기</a></div></div></details>' :
    empty("심층 리서치 결과가 없습니다."));

  const popular = asObject(data.popular_reports);
  const items = asArray(popular.items).slice().sort((a,b) => {
    const time = researchDateValue(b) - researchDateValue(a);
    return time || Number(b.views || 0) - Number(a.views || 0);
  }).slice(0,30);
  setText("popular-reports-updated", popular.updated_at ? "갱신 · " + relativeTime(popular.updated_at) : "데이터 없음");
  setHTML("popular-report-list", items.length ? items.map((x,i) => {
    const analysis = asObject(x.analysis);
    const views = Number(x.views);
    const targetPrice = x.target_price || analysis.target_price || "";
    const previousTargetPrice = x.previous_target_price || analysis.previous_target_price || "";
    const detailAvailable = Boolean(analysis.core || analysis.evidence || analysis.market_link || analysis.countercheck || targetPrice || previousTargetPrice);
    const sourceUrl = x.report_url || analysis.source_url || "";
    return '<details class="research-detail broker-research">' +
      '<summary><div class="research-summary-main"><div class="research-title-line"><span class="research-rank">' + (i+1) + '</span><strong>' + esc(x.title || "증권 리포트") + '</strong></div>' +
      '<div class="research-meta"><span>' + esc(researchDateLabel(x)) + '</span><span>' + esc(x.broker || "증권사 미확인") + '</span><span>' + esc(x.company || x.industry || "기업·산업 미확인") + '</span>' +
      (Number.isFinite(views) ? '<span>조회 ' + esc(views.toLocaleString("ko-KR")) + '회</span>' : '') + '</div>' +
      '<p>' + esc(shortText(x.summary || analysis.core || "", 300)) + '</p>' +
      researchTags([x.theme, x.ticker].filter(Boolean)) + '</div><span class="research-toggle">상세 보기</span></summary>' +
      '<div class="research-expanded"><div class="research-section-grid">' +
      researchSection("리포트 핵심 요약", analysis.core || x.summary) +
      researchSection("주요 주장·근거", analysis.evidence) +
      researchSection("실적·산업 전망 / 시장 연결", analysis.market_link) +
      (targetPrice ? researchSection("목표주가", targetPrice) : "") +
      (previousTargetPrice ? researchSection("이전 목표주가", previousTargetPrice) : "") +
      researchSection("투자 포인트", analysis.market_link) +
      researchSection("주요 리스크·반론", analysis.countercheck) +
      researchSection("언급 기업·산업", [x.company, x.theme].filter(Boolean)) +
      researchSection("데이터 출처·발행일", [x.broker, x.report_date].filter(Boolean)) +
      '</div>' +
      (!detailAvailable ? '<div class="notice warn">상세 데이터 미수집 · 현재 확보된 제목·요약·발행정보만 표시합니다.</div>' : '') +
      (sourceUrl ? '<div class="research-actions"><a class="button primary" href="' + esc(sourceUrl) + '" target="_blank" rel="noreferrer">원본 리포트 열기</a></div>' : '<div class="notice">원본 리포트 링크 미수집</div>') +
      '</div></details>';
  }).join("") : empty("인기 리포트 목록을 불러오는 중입니다."));

  const reports = asArray(data.reports).slice().sort((a,b)=>researchDateValue(b)-researchDateValue(a)).slice(0,15);
  setHTML("recent-reports", reports.length ? reports.map((x) => {
    const title = x.title || x.name || x.report_title || x.path || "프로젝트 리포트";
    const tags = [...asArray(x.industries), ...asArray(x.stocks)].filter(Boolean).slice(0,8);
    const content = typeof x.content === "string" ? x.content : "";
    const preview = x.preview || "";
    return '<details class="research-detail project-research"><summary><div class="research-summary-main"><div class="research-title-line"><strong>' + esc(title) + '</strong></div>' +
      '<div class="research-meta"><span>' + esc(researchDateLabel(x)) + '</span><span>프로젝트 리서치</span></div>' +
      '<p>' + esc(shortText(preview, 340)) + '</p>' + researchTags(tags) + '</div><span class="research-toggle">상세 보기</span></summary>' +
      '<div class="research-expanded">' +
      (content ? '<section class="research-section"><h3>저장된 Markdown 원문</h3><pre class="research-markdown">' + esc(content) + '</pre></section>' :
        '<div class="notice warn">상세 데이터 미수집 · 이 항목은 현재 요약만 저장되어 있습니다.</div>' + researchSection("저장된 요약", preview)) +
      (x.github_url ? '<div class="research-actions"><a class="button primary" href="' + esc(x.github_url) + '" target="_blank" rel="noreferrer">GitHub 원문 열기</a></div>' : '') +
      '</div></details>';
  }).join("") : empty("저장된 최근 리포트가 없습니다."));

  const sources = Object.entries(asObject(discovery.source_status));
  setHTML("discovery-sources", sources.length ? sources.map(([name,v]) => {
    const state = asObject(v);
    return '<div class="mini-row"><strong>' + esc(name) + '</strong><span>' + esc(state.status || "unknown") +
      (state.count != null ? " · " + esc(state.count) + "건" : "") + '</span></div>';
  }).join("") : empty("소스 상태 데이터 없음"));
}

function renderHomeResearch(data) {
  const root = $("home-research-list");
  if (!root) return;
  const supervisor = asObject(data.supervisor_latest);
  const reports = asArray(data.reports);
  const rows = [];
  if (Object.keys(supervisor).length) {
    rows.push({
      title: supervisor.supervisor ? "Supervisor " + supervisor.supervisor + " 최신 심층 리서치" : "최신 AI 심층 리서치",
      preview: shortText(asArray(supervisor.summary).length ? supervisor.summary : supervisor.market_narrative, 240),
      meta: supervisor.processed_at ? researchDateLabel({generated_at:supervisor.processed_at}) : "시각 미확인",
      href: "리서치.html"
    });
  }
  reports.slice(0,2).forEach((x) => rows.push({
    title: x.title || "프로젝트 리서치",
    preview: shortText(x.preview || x.content || "", 220),
    meta: researchDateLabel(x),
    href: "리서치.html"
  }));
  root.innerHTML = rows.length ? rows.slice(0,3).map((x) =>
    '<a class="mini-row home-research-row" href="' + esc(x.href) + '"><strong>' + esc(x.title) + '</strong><span>' + esc(x.preview) + '</span><small>' + esc(x.meta) + '</small></a>'
  ).join("") : empty("연결된 최신 리서치를 준비 중입니다.");
}

function renderAIDialogue(data) {
  const root = $("ai-dialogue");
  if (!root) return;
  const rows = asArray(data.supervisor_timeline).slice(0,40);
  if (!rows.length) {
    root.innerHTML = empty("저장된 A/B Supervisor 결과가 아직 없습니다.");
    setText("ai-dialogue-status", "데이터 없음");
    return;
  }
  const latest = rows[0] || {};
  const latestTime = latest.processed_at ? new Date(latest.processed_at).getTime() : NaN;
  const stale = Number.isFinite(latestTime) && Date.now() - latestTime > 90 * 60 * 1000;
  setText("ai-dialogue-status", (stale ? "STALE · " : "최근 ") + (latest.processed_at ? relativeTime(latest.processed_at) : "시각 미확인"));

  root.innerHTML = rows.map((x) => {
    const speaker = String(x.supervisor || "SYSTEM").toUpperCase();
    const speakerClass = speaker === "A" ? "speaker-a" : speaker === "B" ? "speaker-b" : "speaker-recovery";
    const label = speaker === "A" ? "A · 탐색/개발" : speaker === "B" ? "B · 반증/검증" : "Recovery · 연속성";
    const summary = asArray(x.summary).map(readableItem).filter(Boolean);
    const received = asArray(x.feedback_received).map(readableItem).filter(Boolean);
    const resolved = asArray(x.feedback_resolved).map(readableItem).filter(Boolean);
    const disagreed = [...asArray(x.feedback_disagreed), ...asArray(x.supervisor_disagreements)].map(readableItem).filter(Boolean);
    const deferred = asArray(x.feedback_deferred).map(readableItem).filter(Boolean);
    const outgoing = asArray(x.feedback_to_other_supervisor).map(readableItem).filter(Boolean);
    const actions = asArray(x.actions).map(readableItem).filter(Boolean);
    const changes = asArray(x.changed_paths).map(readableItem).filter(Boolean);
    const next = asArray(x.next_checks).map(readableItem).filter(Boolean);
    const signals = asArray(x.project_improvement_signals).map(readableItem).filter(Boolean);
    const completenessRaw = x.observation_completeness_ratio;
    const completeness = completenessRaw == null || completenessRaw === "" ? NaN : Number(completenessRaw);
    const completenessText = Number.isFinite(completeness) ? Math.round(completeness * 100) + "% 관측" : "";
    const body = summary.length ? summary.slice(0,4).join(" ") : shortText(x.market_narrative || "", 520);
    return '<article class="ai-turn ' + speakerClass + '">' +
      '<div class="ai-turn-marker">' + esc(speaker === "RECOVERY" ? "R" : speaker) + '</div>' +
      '<details class="ai-message">' +
        '<summary><div class="ai-message-head"><div><span class="ai-speaker">' + esc(label) + '</span><time>' + esc(researchDateLabel({generated_at:x.processed_at})) + '</time></div>' +
        '<div class="ai-message-badges"><span>' + esc(x.status || "") + '</span>' + (completenessText ? '<span>' + esc(completenessText) + '</span>' : '') + '</div></div>' +
        '<p>' + esc(shortText(body, 520)) + '</p><span class="research-toggle">대화·근거 펼치기</span></summary>' +
        '<div class="ai-message-detail">' +
          researchSection("현재 판단", summary.length ? summary : x.market_narrative) +
          researchSection("받은 의견", received) +
          researchSection("반영·해결", resolved) +
          researchSection("반론·의견 충돌", disagreed) +
          researchSection("보류한 판단", deferred) +
          researchSection("이번 실행의 조치", actions) +
          researchSection("프로젝트 개선 신호", signals) +
          researchSection("다음 Supervisor에게 전달", outgoing) +
          researchSection("다음 확인", next) +
          researchSection("변경 파일", changes) +
          (x.source_url ? '<div class="research-actions"><a class="button primary" href="' + esc(x.source_url) + '" target="_blank" rel="noreferrer">저장된 원본 JSON 보기</a></div>' : '') +
        '</div>' +
      '</details>' +
    '</article>';
  }).join("");
}

function renderRisk(data) {
  const risk = data.risk || {};
  const evaln = risk.evaluation || {};
  const supervisor = data.supervisor_latest || {};
  const macro = data.macro_matrix || {};
  const known = Number(macro.known_count || 0), total = Number(macro.total_count || 0);
  const rows = [];
  (risk.macro_signals || []).forEach((x)=>rows.push({level:x.risk_level||"WATCH",title:x.field||"매크로 변화",why:"임계값을 넘은 매크로 변화를 확인합니다.",value:x.value}));
  asArray(risk.upcoming_events).slice(0,5).forEach((x)=>{
    const timing = eventTiming(x);
    const fallbackHours = Number(x.hours_to_event);
    const remainingHours = Number.isFinite(timing.remainingHours) ? timing.remainingHours : (Number.isFinite(fallbackHours) ? fallbackHours : null);
    if (remainingHours !== null && remainingHours >= 0 && remainingHours <= 72) {
      rows.push({level:x.risk_level||"WATCH",title:x.title||"주요 일정",why:"향후 72시간 안 예정된 이벤트입니다.",value:timing.countdown});
    }
  });
  (supervisor.market_focus || []).slice(0,3).forEach((x,i)=>rows.push({level:i===0?"WATCH":"LOW",title:x.title||x.name||"AI 확인 항목",why:x.reason||x.why||"",value:""}));
  if (total && !known) rows.push({level:"UNKNOWN",title:"실시간 매크로 값 미수집",why:"빈 값을 LOW로 해석하지 않습니다. 실시간 값이 복구될 때까지 최근 종가와 AI 검증 메모를 함께 봅니다.",value:known+"/"+total});
  const score={VETO:5,HIGH:4,WATCH:3,UNKNOWN:2,LOW:1};
  rows.sort((a,b)=>(score[b.level]||0)-(score[a.level]||0));
  setHTML("overnight-risk-list", rows.length ? '<div class="risk-list">' + rows.slice(0,8).map((x,i) => '<div class="risk-card" data-level="' + esc(x.level) + '"><div class="risk-rank">' + (i+1) + '</div><div><strong>' + esc(x.title) + ' · ' + esc(x.level) + '</strong><p>' + esc(x.why) + '</p><small>' + esc(x.value || "") + '</small></div></div>').join("") + '</div>' : empty("확인 가능한 오버나잇 리스크 입력이 없습니다."));
  const level = evaln.risk_level || risk.risk_level || "UNKNOWN";
  setText("risk-level", level);
  if ($("risk-level")) $("risk-level").dataset.level = level;
  setHTML("risk-summary", '<div class="regime"><strong>' + esc(evaln.summary || "리스크 입력을 확인 중입니다.") + '</strong><p>' + esc(((evaln.single_biggest_risk || {}).title) || "확정된 단일 대형 리스크 없음") + '</p><small>' + esc(((evaln.single_biggest_risk || {}).why) || "") + '</small></div>');
  const upcomingEvents = asArray(risk.upcoming_events);
  const riskEventsNode = $("risk-events");
  const riskEventsLimit = Math.max(1, Number((riskEventsNode && riskEventsNode.dataset.limit) || 8));
  setHTML("risk-events", upcomingEvents.length ? '<div class="event-list">' + upcomingEvents.slice(0,riskEventsLimit).map(eventCard).join("") + '</div>' : empty("예정 이벤트 없음"));
  setHTML("next-checks", (supervisor.next_checks || []).length ? (supervisor.next_checks || []).slice(0,8).map((x)=>'<div class="mini-row"><span>' + esc(typeof x === "string" ? x : (x.title || x.check || "")) + '</span></div>').join("") : empty("다음 확인 항목 없음"));
}
function renderMacro(data) {
  const macro = data.macro_matrix || {};
  setText("macro-regime", macro.macro_regime || macro.risk_level || "UNKNOWN");
  setText("macro-coverage", (macro.known_count || 0) + "/" + (macro.total_count || 0) + " 확인");
  setHTML("macro-paths", (macro.transmission_paths || []).length ? (macro.transmission_paths || []).slice(0,6).map((x)=>'<div class="mini-row"><span>' + esc(x) + '</span></div>').join("") : empty("전달 경로를 평가할 실시간 입력이 부족합니다."));
  setHTML("macro-conflicts", (macro.conflicting_signals || []).length ? (macro.conflicting_signals || []).slice(0,6).map((x)=>'<div class="mini-row"><span>' + esc(x) + '</span></div>').join("") : empty("현재 기록된 충돌 신호 없음"));
  const knownItems = (macro.items || []).filter((x)=>x.value !== null && x.value !== "");
  if (!knownItems.length) {
    setHTML("macro-groups", empty("실시간 매크로 값이 비어 있습니다.","휴장·주말에 빈 값으로 시장을 해석하지 않도록 숨겼습니다. 위의 최근 미국 3거래일과 다음 일정, AI 검증 메모를 우선 사용합니다."));
    return;
  }
  const groups={};
  knownItems.forEach((x)=>(groups[x.group] ||= []).push(x));
  const val=(x)=>{
    const n=Number(x.value); if(!Number.isFinite(n)) return x.value;
    if(x.kind==="yield") return n.toFixed(3)+"%";
    if(x.kind==="bp") return (n>=0?"+":"")+n.toFixed(1)+"bp";
    return (n>=0?"+":"")+n.toFixed(2)+"%";
  };
  setHTML("macro-groups", Object.entries(groups).map(([g,items])=>'<div><p class="subhead">' + esc(g) + '</p><div class="macro-cards">' + items.map((x)=>'<div class="macro-card"><strong>' + esc(x.label) + '</strong><b>' + esc(val(x)) + '</b><small>' + esc(x.risk_level || "LOW") + '</small></div>').join("") + '</div></div>').join(""));
}
function renderDomesticLive(data, krRows) {
  const market=data.market||{}, runtime=data.market_runtime||{}, q=market.quantitative||{}, source=market.source||{}, interp=market.interpretation||{};
  const status=q.status==="historical_fallback" ? "historical_fallback" : (runtime.source_status||source.status||q.status||"no_live_data");
  const labels={ok:"장중 실데이터",historical_fallback:"휴장 · 최근 3거래일 분석",outside_regular_session:"장 종료 · 최근 거래일 분석",needs_credentials:"API 설정 필요",no_rows:"실시간 시세 없음",toss_snapshot_unavailable:"Toss Collector 대기",outside_domestic_monitor_window:"국내 감시시간 종료",no_live_data:"최근 3거래일 모드"};
  setText("market-status", labels[status] || status);
  if (q.status === "ok") {
    const ov=source.market_overview||{}, kp=ov.KOSPI||{}, kd=ov.KOSDAQ||{};
    setHTML("market-summary", '<div class="live-layout"><div class="regime"><strong>' + esc(interp.regime_name||"정량 장세 분석") + '</strong><p>' + esc(interp.one_line||"거래대금과 시장폭을 분석 중입니다.") + '</p></div><div class="live-cards"><div class="live-card"><span>KOSPI</span><strong class="' + tone(kp.change_pct) + '">' + esc(signedPct(kp.change_pct)) + '</strong></div><div class="live-card"><span>KOSDAQ</span><strong class="' + tone(kd.change_pct) + '">' + esc(signedPct(kd.change_pct)) + '</strong></div><div class="live-card"><span>분석 종목</span><strong>' + esc(q.stock_count||0) + '개</strong></div><div class="live-card"><span>Top10 집중</span><strong>' + esc((((source.turnover_rank_top10_share??(q.turnover||{}).top10_share)||0)*100).toFixed(1)) + '%</strong></div></div></div>');
    setHTML("burst-leaders",(q.burst_leaders||[]).length?(q.burst_leaders||[]).slice(0,8).map((x)=>'<div class="mini-row"><strong>' + esc(x.name||x.ticker) + '</strong><span>' + esc(x.burst_count||0) + '회 · 1분 최대 ' + esc(num(Number(x.max_minute_amount||0)/100000000,1)) + '억</span></div>').join(""):empty("현재 Burst 조건 종목 없음"));
    setHTML("coflow-groups",(q.coflow_groups||[]).length?(q.coflow_groups||[]).slice(0,8).map((x)=>'<div class="mini-row"><strong>' + esc(x.group||"그룹") + '</strong><span>' + esc(x.synchronized_burst_members||0) + '종목 동조</span></div>').join(""):empty("확인된 동조 수급 없음"));
    const pm=source.postmarket||{};
    setHTML("nxt-after",(pm.stocks||[]).length?'<div class="nxt-list">' + (pm.stocks||[]).slice(0,8).map((x)=>'<div class="nxt-card"><strong>' + esc(x.name||x.ticker) + '</strong><span>KRX 대비 ' + esc(signedPct(x.krx_close_premium_pct)) + '</span><span>애프터 ' + esc(signedPct(x.return_pct)) + '</span></div>').join("") + '</div>':empty("현재 NXT 체결 데이터 없음"));
  } else {
    const latest=krRows[0]||{};
    setHTML("market-summary", '<div class="notice warn"><strong>실시간 장중 데이터 대신 최근 실제 거래일을 사용 중입니다.</strong><div class="source-line">' + esc(source.reason||q.reason||"휴장·장외 또는 실시간 공급자 데이터가 없어 과거 1분값을 임의 생성하지 않습니다.") + '</div></div>' + (latest.date?'<div class="summary-strip" style="margin-top:12px"><div class="summary-item"><span>기준일</span><strong>' + esc(latest.date) + '</strong></div><div class="summary-item"><span>KOSPI</span><strong class="' + tone((latest.kospi||{}).change_pct) + '">' + esc(signedPct((latest.kospi||{}).change_pct)) + '</strong></div><div class="summary-item"><span>KOSDAQ</span><strong class="' + tone((latest.kosdaq||{}).change_pct) + '">' + esc(signedPct((latest.kosdaq||{}).change_pct)) + '</strong></div><div class="summary-item"><span>기관</span><strong class="' + flowTone((latest.flows_krw_100m||{}).institution) + '">' + esc(flowEok((latest.flows_krw_100m||{}).institution)) + '</strong></div></div>':""));
    setHTML("burst-leaders",empty("과거 1분 거래대금 백필 없음","정확한 과거 분봉 거래대금 원자료가 저장되지 않은 날은 숫자를 만들지 않습니다."));
    setHTML("coflow-groups",empty("과거 동조 수급 백필 없음","다음 실거래 세션부터 누적 관측합니다."));
    setHTML("nxt-after",empty("NXT 실시간 데이터 없음","휴장·장외에는 마지막 거래일 종가만 유지합니다."));
  }
  const st=market.strategy_stats||{}, close=st.close_bet||{}, swing=st.pullback||{};
  const closeN=((close.summary||{}).sample_size||0), swingN=((swing.summary||{}).sample_size||0);
  setHTML("strategy-stats", '<div class="mini-list"><div class="mini-row"><strong>종가베팅 표본</strong><span>n=' + esc(closeN) + ' · ' + esc(close.reliability||"축적 중") + '</span></div><div class="mini-row"><strong>눌림스윙 표본</strong><span>n=' + esc(swingN) + ' · ' + esc(swing.reliability||"축적 중") + '</span></div></div>');
}
function renderOperations(data) {
  const ops=data.operations||{};
  setText("operations-status",ops.status||"UNKNOWN");
  const cards=Array.isArray(ops.cards)?ops.cards:[];
  const actions=Array.isArray(ops.user_actions)?ops.user_actions:[];
  const sup=ops.supervisors||{};
  const a=(sup.A||{}).processed_at,b=(sup.B||{}).processed_at;
  setHTML("operations-summary",
    '<strong>자가복구 상태 · '+esc(ops.status||"UNKNOWN")+'</strong>'+
    '<div class="source-line">A '+esc(a?relativeTime(a):"미확인")+' · B '+esc(b?relativeTime(b):"미확인")+
    ' · 뉴스 후보 '+esc((ops.news||{}).candidate_count??"-")+'건 · 이슈 '+esc((ops.news||{}).issue_count??"-")+'개'+
    (actions.length?' · 사용자 확인 '+esc(actions.length)+'건':' · 사용자 확인 필요 없음')+'</div>'
  );
  const columns=["발견","조사 중","수정 중","검증 대기","사용자 확인 필요","완료"];
  setHTML("operations-kanban",columns.map((name)=>{
    const rows=cards.filter((x)=>String(x.state||"")===name);
    return '<section class="ops-column"><h3>'+esc(name)+' <span>'+rows.length+'</span></h3><div class="ops-cards">'+
      (rows.length?rows.map((x)=>'<div class="ops-card"><strong>'+esc(x.title||"상태")+'</strong><p>'+esc(x.impact||"")+'</p><small>담당 '+esc(x.owner||"자동화")+(x.verify_after?' · 다음 '+esc(x.verify_after):'')+'</small></div>').join(""):'<div class="ops-empty">없음</div>')+
      '</div></section>';
  }).join(""));
}
function renderSystem(data) {
  const provider=data.toss_provider||{}, runtime=data.market_runtime||{};
  const mode=provider.available?"TOSS LIVE":(runtime.provider==="kiwoom"?"KIWOOM FALLBACK":"WAITING");
  const cards=[
    ["현재 경로",mode],["Toss Snapshot",provider.available?relativeTime(provider.captured_at):"없음"],
    ["최근 체결",provider.last_message_at?relativeTime(provider.last_message_at):"미확인"],["구독",(provider.subscription_count??0)+"개"],
    ["구독 거절",(provider.rejected_count??0)+"건"],["정규장 종목",(provider.regular_ticker_count??0)+"개"],
    ["NXT 종목",(provider.postmarket_ticker_count??0)+"개"],["1분 거래대금",provider.minute_amount_method==="exact_trade_sum"?"실체결 합산":"근사/미확인"]
  ];
  setHTML("provider-status",cards.map(([a,b])=>'<div class="provider-card"><span>' + esc(a) + '</span><strong>' + esc(b) + '</strong></div>').join(""));
  const health=data.health||{}, hs=health.status||"UNKNOWN";
  setText("health-status",hs); if($("health-status")) $("health-status").dataset.level=hs;
  setHTML("health-issues",(health.issues||[]).length?(health.issues||[]).map((x)=>'<div class="health-item" data-level="' + esc(x.severity||"") + '"><div><strong>' + esc(x.component||"") + ' · ' + esc(x.code||"") + '</strong><p>' + esc(x.message||"") + '</p></div><div class="health-recovery">' + esc(x.recovery||"") + '</div></div>').join("") : '<div class="notice">현재 확인된 운영 이상 없음</div>');
  const reg=data.regression||{}, snap=reg.snapshot||{}, base=reg.baseline_summary||{};
  setText("regression-status",reg.status||"COLLECTING");
  setHTML("regression-summary",[
    ["현재 종합 품질",(snap.overall_quality??"-")+"점"],["7일 평균",(base.overall_7d??"-")+"점"],["활성 AI 변경",reg.active_change_count??0],["격리",reg.quarantine_count??0]
  ].map(([a,b])=>'<div class="regression-number"><span>' + esc(a) + '</span><strong>' + esc(b) + '</strong></div>').join(""));
  setHTML("regression-evals",(reg.evaluations||[]).length?(reg.evaluations||[]).slice(0,8).map((x)=>'<div class="mini-row"><strong>' + esc(x.change_id||x.status||"평가") + '</strong><span>' + esc(x.status||"") + (x.drop_7d!=null?" · 7일 "+Number(x.drop_7d).toFixed(1)+"p":"") + '</span></div>').join("") : empty("회귀 평가 표본을 수집 중입니다."));
  setHTML("recent-changes",(data.recent_changes||[]).length?(data.recent_changes||[]).slice(0,15).map((x)=>'<div class="tick"><span class="dot"></span><div><strong>' + esc(x.title||x.change_id||"AI 변경") + '</strong><p>' + esc((x.paths||[]).join(", ")) + '</p><div class="meta">' + esc(x.applied_at||"") + ' · ' + esc(x.status||"") + '</div></div></div>').join("") : empty("최근 변경 manifest 없음"));
  setHTML("ticks",(data.ticks||[]).length?(data.ticks||[]).slice(0,15).map((x)=>'<div class="tick"><span class="dot"></span><div><strong>' + esc(x.title||"판단") + '</strong><p>' + esc(x.observation||"") + '</p><div class="meta">' + esc(x.time||"") + ' · ' + esc(x.outcome||"") + '</div></div></div>').join("") : empty("AI 진화 Tick 기록 없음"));
  if ($("decisions")) $("decisions").textContent=data.decision_memory||"기록 없음";
  if ($("help")) $("help").textContent=data.help_needed||"현재 요청 없음";
  if ($("changelog")) $("changelog").textContent=data.changelog||"기록 없음";
}
async function load() {
  const response = await fetch("data/상태.json", {cache:"no-store"});
  if (!response.ok) throw new Error("대시보드 데이터를 불러오지 못했습니다.");
  const data = await response.json();
  const session = data.market_recent_sessions || {};
  const krRows = (session.korea || []).slice(0,3);
  const usRows = (session.us || []).slice(0,3);

  renderMetrics(data, krRows, usRows);
  renderBrief(data);
  renderQuickSessions(krRows, usRows);
  renderSessionTables(session, krRows, usRows);
  renderFlow(krRows);
  renderIssues(data);
  renderHotIssues(data);
  renderIssueTracker(data);
  renderResearch(data);
  renderHomeResearch(data);
  renderAIDialogue(data);
  renderRisk(data);
  renderMacro(data);
  renderDomesticLive(data, krRows);
  renderOperations(data);
  renderSystem(data);

  const holiday = (session.holiday_notes || []).find((x)=>x.market==="KR");
  setHTML("global-data-note", holiday
    ? '<div class="notice warn">한국은 ' + esc(holiday.from) + '~' + esc(holiday.to) + ' ' + esc(holiday.reason||"휴장") + '입니다. 국내 실시간 영역은 최근 실제 거래일을 표시하고, 미국장은 각 시장의 실제 최근 3거래일을 별도로 사용합니다.</div>'
    : '<div class="notice">각 시장은 서로 다른 실제 최근 거래일 기준으로 표시합니다.</div>');

  setText("updated","갱신 " + (data.generated_at ? new Date(data.generated_at).toLocaleString("ko-KR") : "미확인"));
}
initPersistentDetails();
load().catch((error)=>{
  document.body.insertAdjacentHTML("beforeend",'<div style="position:fixed;z-index:99;left:12px;right:12px;bottom:12px;padding:14px;background:#7f1d1d;color:white;border-radius:10px;font:12px/1.5 system-ui">대시보드 오류: ' + esc(error.message) + '</div>');
});
