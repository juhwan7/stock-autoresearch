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
  const rows = (supervisor.market_narrative || supervisor.summary || []).slice(0, 4);
  setHTML("market-narrative", rows.length
    ? rows.map((x) => '<p class="brief-paragraph">' + esc(typeof x === "string" ? x : (x.text || x.summary || "")) + '</p>').join("")
    : empty("AI 시장 해설을 기다리는 중입니다."));
  const focus = (supervisor.market_focus || []).slice(0, 5);
  setHTML("market-focus", focus.length
    ? focus.map((x, i) => '<div class="mini-row"><strong>' + (i + 1) + '. ' + esc(typeof x === "string" ? x : (x.title || x.name || "확인 항목")) + '</strong><span>' + esc(typeof x === "string" ? "" : (x.reason || x.why || "")) + '</span></div>').join("")
    : empty("현재 우선 확인 항목이 없습니다."));
  const invalid = (supervisor.invalidation_checks || supervisor.next_checks || []).slice(0, 4);
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
  const digest = data.news_issue_digest || {};
  const store = (digest.issues || []).length ? digest : (data.market_issues || {});
  const rank = {ESCALATING:0,NEW:1,ACTIVE:2,WATCHING:3,EASING:4,RESOLVED:5};
  const sev = {CRITICAL:0,HIGH:1,MEDIUM:2,LOW:3};
  const rows = (store.issues || []).slice().sort((a,b)=>
    (rank[String(a.status||"WATCHING").toUpperCase()]??9)-(rank[String(b.status||"WATCHING").toUpperCase()]??9) ||
    (sev[String(a.severity||"LOW").toUpperCase()]??9)-(sev[String(b.severity||"LOW").toUpperCase()]??9) ||
    String(b.last_updated||b.last_seen||"").localeCompare(String(a.last_updated||a.last_seen||""))
  );
  const limit = $("market-issue-list")?.dataset.limit ? Number($("market-issue-list").dataset.limit) : rows.length;
  setHTML("market-issue-list", rows.length ? rows.slice(0,limit).map((x) => {
    const status = String(x.status || "WATCHING").toUpperCase();
    const label = {NEW:"신규",WATCHING:"관찰",ACTIVE:"지속",ESCALATING:"강화",EASING:"완화",RESOLVED:"해소"}[status] || status;
    const impact = issueImpactGroup(x.impact);
    return '<div class="mini-row issue-mini" data-level="' + esc(status) + '">' +
      '<div class="issue-mini-head"><strong>[' + esc(label) + '] ' + esc(x.title || x.issue_id || "이슈") + '</strong>' +
      '<span class="issue-impact ' + impact.toLowerCase() + '">' + esc(issueImpactLabel(x.impact)) + '</span></div>' +
      '<span>' + esc(x.reason || x.summary || "") + '</span>' +
      '<div class="issue-mini-meta"><small>' + esc(x.scope==="KOREA"?"국내":"글로벌") + ' · ' + esc(x.category||"기타") + ' · ' + esc(issuePricingLabel(x.pricing_status)) + '</small>' +
      '<small>사건 ' + esc(x.event_time || "미확인") + ' · 첫 감지 ' + esc(x.first_detected ? relativeTime(x.first_detected) : "미확인") + ' · 최근 ' + esc((x.last_updated || x.last_seen) ? relativeTime(x.last_updated || x.last_seen) : "미확인") + '</small></div>' +
      '</div>';
  }).join("") : empty("누적된 시장 이슈가 아직 없습니다."));
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
      if(activeSort==="updated") return (issueTime(b,"last_updated")||issueTime(b,"first_detected"))-(issueTime(a,"last_updated")||issueTime(a,"first_detected"));
      if(activeSort==="event") return issueTime(b,"event_time")-issueTime(a,"event_time");
      if(activeSort==="detected") return issueTime(b,"first_detected")-issueTime(a,"first_detected");
      const sr=(statusRank[String(a.status||"WATCHING").toUpperCase()]??9)-(statusRank[String(b.status||"WATCHING").toUpperCase()]??9);
      if(sr) return sr;
      const sev=(severityRank[String(a.severity||"LOW").toUpperCase()]??9)-(severityRank[String(b.severity||"LOW").toUpperCase()]??9);
      if(sev) return sev;
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
      return '<details class="issue-detail" data-level="' + esc(status) + '" data-impact="' + esc(impact) + '">' +
        '<summary><div class="issue-summary-main"><div class="issue-title-line">' +
          '<span class="issue-status">' + esc(statusLabel[status]||status) + '</span>' +
          '<span class="issue-impact ' + impact.toLowerCase() + '">' + esc(issueImpactLabel(x.impact)) + '</span>' +
          '<strong>' + esc(x.title||x.issue_id||"이슈") + '</strong></div><p>' + esc(x.summary||x.reason||"") + '</p></div>' +
        '<div class="issue-summary-meta"><span>' + esc(x.scope==="KOREA"?"국내":"글로벌") + '</span><span>' + esc(x.category||"") + '</span><b>' + esc(x.severity||"") + '</b>' +
        '<span>' + esc(issuePricingLabel(x.pricing_status)) + '</span><span>출처 ' + esc(x.source_count ?? (x.sources||[]).length) + '개</span>' +
        '<small>사건 ' + esc(x.event_time||"미확인") + '<br>첫 감지 ' + esc(x.first_detected?relativeTime(x.first_detected):"미확인") + ' · 최근 ' + esc(x.last_updated?relativeTime(x.last_updated):"미확인") + '</small></div></summary>' +
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
  const supervisor = data.supervisor_latest || {};
  setText("supervisor-status", supervisor.status || "NO DATA");
  const summary = (supervisor.summary || []).slice(0, 7);
  setHTML("supervisor-summary", summary.length ? summary.map((x) => '<div class="mini-row"><span>' + esc(x) + '</span></div>').join("") : empty("심층 리서치 결과가 없습니다."));
  const reportLink = $("supervisor-report-link");
  if (reportLink) {
    if (supervisor.research_report_path) {
      reportLink.href = "https://github.com/juhwan7/stock-autoresearch/blob/main/" + encodeURI(supervisor.research_report_path);
      reportLink.style.display = "inline-flex";
    } else reportLink.style.display = "none";
  }
  const discovery = data.discovery || {};
  const trends = (supervisor.dynamic_trends || discovery.trending_terms || []).slice(0, 10);
  setHTML("dynamic-trends", trends.length ? trends.map((x) => '<div class="mini-row"><strong>' + esc(typeof x === "string" ? x : (x.title || x.name || x.term || "트렌드")) + '</strong><span>' + esc(typeof x === "string" ? "" : (x.reason || x.evidence || (x.count != null ? "언급 " + x.count + "건" : ""))) + '</span></div>').join("") : empty("동적 트렌드를 수집 중입니다."));
  const filings = (discovery.new_dart_filings || []).slice(0,8);
  setHTML("new-filings", filings.length ? filings.map((x) => '<a class="mini-row" href="' + esc(x.url || "#") + '" target="_blank" rel="noreferrer"><strong>' + esc(x.corp_name || "") + '</strong><span>' + esc(x.report_nm || "") + '</span></a>').join("") : empty("새 공시 없음 또는 DART 연결 대기"));
  const popular = data.popular_reports || {};
  const items = (popular.items || []).slice().sort((a,b) => String(b.report_date||"").localeCompare(String(a.report_date||"")) || Number(b.views||0)-Number(a.views||0)).slice(0,30);
  setText("popular-reports-updated", popular.updated_at ? "갱신 · " + relativeTime(popular.updated_at) : "데이터 없음");
  setHTML("popular-report-list", items.length ? '<div class="report-grid">' + items.map((x,i) =>
    '<a class="report-card" href="' + esc(x.report_url || "#") + '" target="_blank" rel="noreferrer"><div class="report-rank">' + esc(x.display_order || i+1) + '</div><div><div class="report-meta"><span>' + esc(x.company || "") + '</span><span>' + esc(x.broker || "") + '</span><span>' + esc(x.report_date || "") + '</span></div><strong>' + esc(x.title || "") + '</strong><p>' + esc(x.summary || "") + '</p><div class="report-foot"><span>' + esc(x.theme || "") + '</span><b>' + esc(Number.isFinite(Number(x.views)) ? Number(x.views).toLocaleString("ko-KR") + "회" : "") + '</b></div></div></a>'
  ).join("") + '</div>' : empty("인기 리포트 목록을 불러오는 중입니다."));
  const reports = (data.reports || []).slice(0,10);
  setHTML("recent-reports", reports.length ? reports.map((x) => {
    const title = x.title || x.name || x.report_title || x.path || "리포트";
    const meta = x.generated_at || x.created_at || x.date || "";
    return '<div class="mini-row"><strong>' + esc(title) + '</strong><span>' + esc(meta) + '</span></div>';
  }).join("") : empty("저장된 최근 리포트가 없습니다."));
  const sources = Object.entries(discovery.source_status || {});
  setHTML("discovery-sources", sources.length ? sources.map(([name,v]) => '<div class="mini-row"><strong>' + esc(name) + '</strong><span>' + esc((v||{}).status || "unknown") + ((v||{}).count != null ? " · " + esc((v||{}).count) + "건" : "") + '</span></div>').join("") : empty("소스 상태 데이터 없음"));
}
function renderRisk(data) {
  const risk = data.risk || {};
  const evaln = risk.evaluation || {};
  const supervisor = data.supervisor_latest || {};
  const macro = data.macro_matrix || {};
  const known = Number(macro.known_count || 0), total = Number(macro.total_count || 0);
  const rows = [];
  (risk.macro_signals || []).forEach((x)=>rows.push({level:x.risk_level||"WATCH",title:x.field||"매크로 변화",why:"임계값을 넘은 매크로 변화를 확인합니다.",value:x.value}));
  (risk.upcoming_events || []).slice(0,5).forEach((x)=>{
    if (Number(x.hours_to_event || 9999) <= 72) rows.push({level:x.risk_level||"WATCH",title:x.title||"주요 일정",why:"향후 72시간 안 예정된 이벤트입니다.",value:Number.isFinite(Number(x.hours_to_event))?Number(x.hours_to_event).toFixed(1)+"시간 후":""});
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
  setHTML("risk-events", (risk.upcoming_events || []).length ? '<div class="event-list">' + (risk.upcoming_events || []).slice(0,8).map((x) => '<div class="event-row"><strong>' + esc(x.title || "") + '</strong><span>' + esc(x.risk_level || "") + '</span><small>' + esc(x.datetime_kst || x.date_kst || "") + (x.hours_to_event != null ? " · " + Number(x.hours_to_event).toFixed(1) + "시간 후" : "") + '</small></div>').join("") + '</div>' : empty("예정 이벤트 없음"));
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
  renderIssueTracker(data);
  renderResearch(data);
  renderRisk(data);
  renderMacro(data);
  renderDomesticLive(data, krRows);
  renderSystem(data);

  const holiday = (session.holiday_notes || []).find((x)=>x.market==="KR");
  setHTML("global-data-note", holiday
    ? '<div class="notice warn">한국은 ' + esc(holiday.from) + '~' + esc(holiday.to) + ' ' + esc(holiday.reason||"휴장") + '입니다. 국내 실시간 영역은 최근 실제 거래일을 표시하고, 미국장은 각 시장의 실제 최근 3거래일을 별도로 사용합니다.</div>'
    : '<div class="notice">각 시장은 서로 다른 실제 최근 거래일 기준으로 표시합니다.</div>');

  setText("updated","갱신 " + (data.generated_at ? new Date(data.generated_at).toLocaleString("ko-KR") : "미확인"));
}
load().catch((error)=>{
  document.body.insertAdjacentHTML("beforeend",'<div style="position:fixed;z-index:99;left:12px;right:12px;bottom:12px;padding:14px;background:#7f1d1d;color:white;border-radius:10px;font:12px/1.5 system-ui">대시보드 오류: ' + esc(error.message) + '</div>');
});
