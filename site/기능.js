const $ = (id) => document.getElementById(id);

function krwEok(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return "-";
  return (n / 100000000).toFixed(n >= 1000000000 ? 1 : 2) + "억";
}

function medianField(block, field) {
  return (((block || {}).summary || {}).fields || {})[field]?.median;
}

function ratePct(value) {
  return value == null ? "-" : (Number(value) * 100).toFixed(1) + "%";
}

function ageText(value) {
  if (!value) return "미확인";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return "미확인";
  const minutes = Math.max(0, (Date.now() - stamp.getTime()) / 60000);
  if (minutes < 1) return "1분 이내";
  if (minutes < 60) return Math.round(minutes) + "분 전";
  return (minutes / 60).toFixed(1) + "시간 전";
}

function signedPct(value) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
}

function flowEok(value) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return (n > 0 ? "+" : "") + n.toLocaleString("ko-KR") + "억";
}

function esc(value = "") {
  return String(value).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}

async function load() {
  const response = await fetch("data/상태.json", { cache: "no-store" });
  if (!response.ok) throw new Error("status.json을 불러오지 못했습니다.");
  const data = await response.json();

  const metrics = [
    ["Heartbeat", data.heartbeat || "6분"],
    ["최근 보고서", (data.reports || []).length + "개"],
    ["최근 진화 Tick", (data.ticks || []).length + "개"],
    ["상태", "자동 진화 중"],
  ];
  $("metrics").innerHTML = metrics.map(([label, value]) =>
    `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
  ).join("");

  const issueStore = data.market_issues || {};
  const issueRows = (issueStore.issues || []).slice().sort((a, b) => {
    const rank = {ESCALATING: 0, NEW: 1, ACTIVE: 2, WATCHING: 3, EASING: 4, RESOLVED: 5};
    return (rank[a.status] ?? 9) - (rank[b.status] ?? 9);
  });
  const issueList = $("market-issue-list");
  if (issueList) issueList.innerHTML = issueRows.length
    ? issueRows.map((x) => {
        const status = String(x.status || "WATCHING").toUpperCase();
        const label = {NEW:"신규", WATCHING:"관찰", ACTIVE:"지속", ESCALATING:"강화", EASING:"완화", RESOLVED:"해소"}[status] || status;
        const first = x.first_detected ? ageText(x.first_detected) : "미확인";
        const last = x.last_seen ? ageText(x.last_seen) : "미확인";
        const resolved = x.resolved_at ? " · " + ageText(x.resolved_at) + " 해소" : "";
        const history = (x.history || []).slice(-3).reverse().map(h =>
          `<small>${esc(h.at ? ageText(h.at) : "")} · ${esc(h.from || "최초")} → ${esc(h.to || "")} ${esc(h.note || "")}</small>`
        ).join("");
        return `<div class="mini-row" data-level="${esc(status)}"><strong>[${esc(label)}] ${esc(x.title || x.issue_id)}</strong><span>처음 감지 ${esc(first)} · 최근 확인 ${esc(last)}${esc(resolved)}</span><span>${esc(x.reason || "")}</span>${history}</div>`;
      }).join("")
    : "<p class='muted'>다음 :00/:30 AI부터 이슈의 등장·강화·완화·해소 시점을 누적합니다.</p>";

  const sessionHistory = data.market_recent_sessions || {};
  const sessionUpdated = $("three-session-updated");
  if (sessionUpdated) sessionUpdated.textContent = sessionHistory.updated_at ? "갱신 · " + ageText(sessionHistory.updated_at) : "데이터 없음";

  function indexCell(block) {
    if (!block || block.close == null) return "<span class='muted'>-</span>";
    const pct = Number(block.change_pct);
    const cls = Number.isFinite(pct) ? (pct > 0 ? "session-up" : pct < 0 ? "session-down" : "session-flat") : "";
    return `<strong>${Number(block.close).toLocaleString("ko-KR")}</strong><small class="${cls}">${esc(signedPct(block.change_pct))}</small>`;
  }

  const koreaRows = (sessionHistory.korea || []).slice(0, 3);
  const koreaBox = $("korea-session-history");
  if (koreaBox) koreaBox.innerHTML = koreaRows.length ? `
    <div class="session-table-wrap"><table class="session-table">
      <thead><tr><th>날짜</th><th>KOSPI</th><th>KOSDAQ</th><th>외국인</th><th>기관</th></tr></thead>
      <tbody>${koreaRows.map(row => `<tr>
        <td><strong>${esc(row.date || "-")}</strong><small>${esc(row.note || "")}</small></td>
        <td>${indexCell(row.kospi)}</td>
        <td>${indexCell(row.kosdaq)}</td>
        <td><strong>${esc(flowEok((row.flows_krw_100m || {}).foreign))}</strong></td>
        <td><strong>${esc(flowEok((row.flows_krw_100m || {}).institution))}</strong></td>
      </tr>`).join("")}</tbody>
    </table></div>`
    : "<p class='muted'>한국 최근 거래일 데이터가 아직 없습니다.</p>";

  const latestKorea = koreaRows[0] || null;
  const latestFlows = (latestKorea || {}).flows_krw_100m || {};
  const foreign3 = koreaRows.reduce((sum, row) => sum + Number((row.flows_krw_100m || {}).foreign || 0), 0);
  const institution3 = koreaRows.reduce((sum, row) => sum + Number((row.flows_krw_100m || {}).institution || 0), 0);

  function flowTone(value) {
    const n = Number(value);
    return Number.isFinite(n) ? (n > 0 ? "flow-buy" : n < 0 ? "flow-sell" : "flow-flat") : "flow-flat";
  }

  function flowLabel(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "미확인";
    if (n > 0) return "순매수";
    if (n < 0) return "순매도";
    return "중립";
  }

  const flowStatus = $("investor-flow-status");
  if (flowStatus) {
    flowStatus.textContent = latestKorea
      ? `${latestKorea.date} 종가 기준`
      : "수급 데이터 없음";
  }

  const flowCards = $("investor-flow-cards");
  if (flowCards) {
    flowCards.innerHTML = latestKorea ? [
      ["외국인", latestFlows.foreign, "최근 거래일"],
      ["기관", latestFlows.institution, "최근 거래일"],
      ["외국인 3일 누적", foreign3, "최근 3거래일"],
      ["기관 3일 누적", institution3, "최근 3거래일"],
    ].map(([label, value, period]) =>
      `<div class="investor-flow-card ${flowTone(value)}">
        <span>${esc(label)}</span>
        <strong>${esc(flowEok(value))}</strong>
        <small>${esc(flowLabel(value))} · ${esc(period)}</small>
      </div>`
    ).join("") : "<p class='muted'>확인된 외국인·기관 수급 데이터가 없습니다.</p>";
  }

  const flowHistory = $("investor-flow-history");
  if (flowHistory) {
    flowHistory.innerHTML = koreaRows.length ? koreaRows.map((row) => {
      const flows = row.flows_krw_100m || {};
      return `<div class="investor-flow-row">
        <strong>${esc(row.date || "-")}</strong>
        <span class="${flowTone(flows.foreign)}">외국인 ${esc(flowEok(flows.foreign))}</span>
        <span class="${flowTone(flows.institution)}">기관 ${esc(flowEok(flows.institution))}</span>
      </div>`;
    }).join("") : "<p class='muted'>최근 거래일 수급 이력이 없습니다.</p>";
  }

  const flowReading = $("investor-flow-reading");
  if (flowReading) {
    if (!latestKorea) {
      flowReading.innerHTML = "<p class='muted'>수급 데이터를 기다리는 중입니다.</p>";
    } else {
      const f = Number(latestFlows.foreign || 0);
      const i = Number(latestFlows.institution || 0);
      let headline = "외국인·기관 수급이 엇갈립니다.";
      if (f > 0 && i > 0) headline = "외국인·기관이 함께 순매수했습니다.";
      if (f < 0 && i < 0) headline = "외국인·기관이 함께 순매도했습니다.";
      const detail = f * i < 0
        ? "한쪽 매수를 다른 주체 매도가 상쇄하는 구조라 지수 상승만으로 수급 확산을 단정하기 어렵습니다."
        : (f > 0 && i > 0
          ? "두 주체의 동반 매수가 이어지는지 거래대금·시장폭과 함께 확인합니다."
          : "동반 매도가 이어지면 지수보다 개별 종목 체감이 더 약할 수 있어 다음 거래일 지속 여부를 확인합니다.");
      flowReading.innerHTML =
        `<strong>${esc(headline)}</strong><p>${esc(detail)}</p><small>출처: ${esc(latestKorea.source || "미확인")} · 휴장일에는 마지막 거래일 종가 수급을 표시합니다.</small>`;
    }
  }

  const usRows = (sessionHistory.us || []).slice(0, 3);
  const usBox = $("us-session-history");
  if (usBox) usBox.innerHTML = usRows.length ? `
    <div class="session-table-wrap"><table class="session-table">
      <thead><tr><th>날짜</th><th>S&P 500</th><th>Nasdaq</th><th>Dow</th></tr></thead>
      <tbody>${usRows.map(row => `<tr>
        <td><strong>${esc(row.date || "-")}</strong><small>${esc(row.note || "")}</small></td>
        <td>${indexCell(row.sp500)}</td>
        <td>${indexCell(row.nasdaq)}</td>
        <td>${indexCell(row.dow)}</td>
      </tr>`).join("")}</tbody>
    </table></div>`
    : "<p class='muted'>미국 최근 거래일 데이터가 아직 없습니다.</p>";

  const holidayRows = sessionHistory.holiday_notes || [];
  const holidayNote = $("session-holiday-note");
  if (holidayNote) holidayNote.textContent = holidayRows.length
    ? holidayRows.map(x => `${x.market === "KR" ? "한국" : x.market}: ${x.from}~${x.to} ${x.reason || "휴장"}`).join(" · ")
    : "휴장 정보 없음";

  const popularReports = data.popular_reports || {};
  const popularUpdated = $("popular-reports-updated");
  const snapshotAt = popularReports.updated_at || ((popularReports.ranking_source || {}).snapshot_at);
  if (popularUpdated) popularUpdated.textContent = snapshotAt ? "기준 · " + relativeTime(snapshotAt) : "데이터 없음";

  const popularItems = (popularReports.items || []).slice().sort((a, b) =>
    String(b.report_date || "").localeCompare(String(a.report_date || "")) ||
    Number(b.views || 0) - Number(a.views || 0) ||
    String(a.title || "").localeCompare(String(b.title || ""))
  ).slice(0, 30);
  const popularList = $("popular-report-list");
  if (popularList) popularList.innerHTML = popularItems.length
    ? popularItems.map((x) => {
        const views = Number(x.views);
        const viewsText = Number.isFinite(views) ? views.toLocaleString("ko-KR") + "회" : "조회수 미확인";
        const url = x.report_url || ((popularReports.ranking_source || {}).url) || "#";
        const analysis = x.analysis || {};
        const status = String(analysis.status || "");
        const ready = status === "ready_source_read";
        const summaryOnly = status === "summary_only_needs_source_read";
        const analysisHtml = ready
          ? `<div class="report-analysis">
              <div class="report-analysis-status ready">원문 확인 완료 · AI 분석</div>
              <div><b>핵심 주장</b><p>${esc(analysis.core || x.summary || "")}</p></div>
              <div><b>근거·재료</b><p>${esc(analysis.evidence || "")}</p></div>
              <div><b>시장과 연결</b><p>${esc(analysis.market_link || "")}</p></div>
              <div><b>반론·확인할 점</b><p>${esc(analysis.countercheck || "")}</p></div>
            </div>`
          : summaryOnly
            ? `<div class="report-analysis summary-only">
                <div class="report-analysis-status partial">1차 요약 · 원문 직접 확인 대기</div>
                <div><b>현재 확인된 요약</b><p>${esc(analysis.core || x.summary || "")}</p></div>
                <div><b>다음 작업</b><p>원문/PDF를 직접 읽은 뒤 근거·시장 연결·반론을 보강합니다.</p></div>
              </div>`
            : `<div class="report-analysis-pending"><strong>AI 분석 대기</strong><span>원문/PDF를 실제로 읽고 확인한 뒤 핵심 주장·근거·시장 연결·반론을 정리합니다. 제목만 보고 분석하지 않습니다.</span></div>`;
        return `<article class="popular-report-card">
          <div class="popular-rank">${esc(x.display_order || (popularItems.indexOf(x) + 1))}</div>
          <div class="popular-report-main">
            <div class="popular-report-meta"><span>${esc(x.company || "")}</span><span>${esc(x.broker || "")}</span><span>${esc(x.report_date || "")}</span></div>
            <strong>${esc(x.title || "")}</strong>
            ${analysisHtml}
            <div class="popular-report-foot"><span>${esc(x.theme || "")}</span><b>${esc(viewsText)}</b></div>
            <div class="popular-report-actions">
              <a href="${esc(url)}" target="_blank" rel="noreferrer">원문/PDF 보기 ↗</a>
            </div>
          </div>
        </article>`;
      }).join("")
    : "<p class='muted'>인기 리포트 데이터를 수집 중입니다.</p>";

  const themeRows = (popularReports.theme_summary || []).slice(0, 6);
  const themeBox = $("popular-theme-summary");
  if (themeBox) themeBox.innerHTML = themeRows.length
    ? themeRows.map((x) => `<div class="mini-row"><strong>${esc(x.theme || "")} · ${esc(x.count || 0)}건</strong><span>${esc(x.note || "")}</span></div>`).join("")
    : "<p class='muted'>주제별 관심도를 계산 중입니다.</p>";

  const popularSource = $("popular-research-source");
  if (popularSource && (popularReports.ranking_source || {}).url) {
    popularSource.href = popularReports.ranking_source.url;
  }

  const supervisor = data.supervisor_latest || {};
  const discovery = data.discovery || {};
  const supervisorStatus = $("supervisor-status");
  if (supervisorStatus) {
    supervisorStatus.textContent = supervisor.status || "NO DATA";
    supervisorStatus.dataset.level = supervisor.status || "unknown";
  }

  const narrativeRows = (supervisor.market_narrative || supervisor.market_context || supervisor.summary || []).slice(0, 5);
  const narrative = $("market-narrative");
  if (narrative) narrative.innerHTML = narrativeRows.length
    ? narrativeRows.map((x, i) => `<p class="brief-paragraph${i === 0 ? " lead-brief" : ""}">${esc(typeof x === "string" ? x : (x.text || x.summary || ""))}</p>`).join("")
    : "<p class='muted'>최근 3거래일 시장 흐름을 연결해 설명할 AI 해설을 기다리는 중입니다.</p>";

  const focusRows = (supervisor.market_focus || supervisor.dynamic_trends || []).slice(0, 4);
  const focus = $("market-focus");
  if (focus) focus.innerHTML = focusRows.length
    ? focusRows.map((x, i) => {
        const title = typeof x === "string" ? x : (x.title || x.name || x.term || "핵심 이슈");
        const reason = typeof x === "string" ? "" : (x.reason || x.why || x.evidence || "");
        return `<div class="mini-row"><strong>${i + 1}. ${esc(title)}</strong><span>${esc(reason)}</span></div>`;
      }).join("")
    : "<p class='muted'>핵심 이슈를 선별 중입니다.</p>";

  const invalidRows = (supervisor.invalidation_checks || supervisor.next_checks || []).slice(0, 4);
  const invalid = $("market-invalidation");
  if (invalid) invalid.innerHTML = invalidRows.length
    ? invalidRows.map(x => `<div class="mini-row"><span>${esc(typeof x === "string" ? x : (x.check || x.title || x.reason || ""))}</span></div>`).join("")
    : "<p class='muted'>다음 6분 데이터와 뉴스로 계속 재검증합니다.</p>";

  const briefStatus = $("market-brief-status");
  if (briefStatus) briefStatus.textContent = supervisor.processed_at ? `최근 AI · ${relativeTime(supervisor.processed_at)}` : ":00/:30 AI 해석";

  const summaryRows = (supervisor.summary || []).slice(0, 6);
  if ($("supervisor-summary")) {
    $("supervisor-summary").innerHTML = summaryRows.length
      ? summaryRows.map((x) => `<div class="mini-row"><span>${esc(x)}</span></div>`).join("")
      : "<p class='muted'>아직 심층 리서치 결과가 없습니다.</p>";
  }

  const reportPath = supervisor.research_report_path || "";
  const reportLink = $("supervisor-report-link");
  if (reportLink) {
    if (reportPath) {
      reportLink.href = "https://github.com/juhwan7/stock-autoresearch/blob/main/" + encodeURI(reportPath);
      reportLink.style.display = "inline-flex";
    } else {
      reportLink.style.display = "none";
    }
  }

  const dynamic = (supervisor.dynamic_trends || discovery.trending_terms || []).slice(0, 8);
  if ($("dynamic-trends")) {
    $("dynamic-trends").innerHTML = dynamic.length
      ? dynamic.map((x) => {
          const name = x.name || x.term || x.topic || "트렌드";
          const reason = x.reason || x.evidence || (x.count != null ? `언급 ${x.count}건` : "");
          return `<div class="mini-row"><strong>${esc(name)}</strong><span>${esc(reason)}</span></div>`;
        }).join("")
      : "<p class='muted'>동적 트렌드 수집 중</p>";
  }

  const filings = (discovery.new_dart_filings || []).slice(0, 8);
  if ($("new-filings")) {
    $("new-filings").innerHTML = filings.length
      ? filings.map((x) => `<a class="mini-row doc-link" href="${esc(x.url || "#")}" target="_blank" rel="noreferrer"><strong>${esc(x.corp_name || "")}</strong><span>${esc(x.report_nm || "")}</span></a>`).join("")
      : "<p class='muted'>새 공시 없음 또는 DART API 대기</p>";
  }

  const sourceRows = Object.entries(discovery.source_status || {}).slice(0, 10);
  if ($("discovery-sources")) {
    $("discovery-sources").innerHTML = sourceRows.length
      ? sourceRows.map(([name, value]) => `<div class="mini-row"><strong>${esc(name)}</strong><span>${esc((value || {}).status || "unknown")}</span></div>`).join("")
      : "<p class='muted'>6분 센서 첫 실행 대기</p>";
  }

  const recentObs = ((data.supervisor_recent || {}).observations || []).slice(-6);
  const macroMatrixForRisk = data.macro_matrix || {};
  const macroKnown = Number(macroMatrixForRisk.known_count || 0);
  const macroTotal = Number(macroMatrixForRisk.total_count || 0);
  const macroMissing = macroTotal > 0 && macroKnown === 0;
  const levelScore = {VETO: 5, HIGH: 4, WATCH: 3, LOW: 1, UNKNOWN: 2};

  const overnightRows = [];
  const riskPreview = data.risk || {};
  (riskPreview.macro_signals || []).forEach((x) => overnightRows.push({
    level: x.risk_level || "WATCH",
    title: x.field || "매크로 변화",
    value: x.value == null ? "" : String(x.value),
    why: "금리·환율·원자재 변화가 다음 한국장 밸류에이션과 외국인 수급에 전달될 수 있습니다."
  }));
  (riskPreview.upcoming_events || []).slice(0, 4).forEach((x) => {
    if (Number(x.hours_to_event || 9999) <= 36) overnightRows.push({
      level: x.risk_level || "WATCH",
      title: x.title || "주요 일정",
      value: x.hours_to_event == null ? "" : Number(x.hours_to_event).toFixed(1) + "시간 후",
      why: "보유 중 발표될 수 있는 이벤트라 갭 변동 위험을 별도로 봅니다."
    });
  });
  if (macroMissing) overnightRows.push({
    level: "UNKNOWN",
    title: "실시간 매크로 데이터 공백",
    value: macroKnown + "/" + macroTotal,
    why: "값이 없으므로 LOW로 해석하지 않습니다. 유가·금리·환율 확인 전에는 오버나잇 판단 신뢰도를 낮춥니다."
  });
  const aiSummary = ((data.supervisor_latest || {}).summary || []);
  aiSummary.slice(0, 3).forEach((x, idx) => overnightRows.push({
    level: idx === 0 ? "WATCH" : "LOW",
    title: idx === 0 ? "AI 최우선 관찰" : "AI 추가 관찰",
    value: "",
    why: String(x)
  }));
  overnightRows.sort((a,b) => (levelScore[b.level] || 0) - (levelScore[a.level] || 0));
  const riskList = $("overnight-risk-list");
  if (riskList) riskList.innerHTML = overnightRows.slice(0, 6).map((x, i) =>
    `<div class="overnight-risk-card" data-level="${esc(x.level)}">
      <div class="risk-rank">${i + 1}</div>
      <div><div class="risk-title-line"><strong>${esc(x.title)}</strong><span>${esc(x.level)}</span></div>
      <p>${esc(x.why)}</p><small>${esc(x.value)}</small></div>
    </div>`
  ).join("") || "<p class='muted'>확인 가능한 리스크 입력을 수집 중입니다.</p>";
  const coverage = $("overnight-coverage");
  if (coverage) coverage.textContent = macroMissing ? "데이터 공백 · 판단 보류" : `매크로 ${macroKnown}/${macroTotal}`;

  const flow = $("six-minute-flow");
  if (flow) flow.innerHTML = recentObs.map((obs) => {
    const t = String(obs.observed_at || "").slice(11,16);
    const leaders = (((obs.public_batch_market || {}).interval_leaders) || []).slice(0,3);
    const names = leaders.map(x => x.name || x.stock_name || x.ticker || x.code).filter(Boolean);
    return `<div class="flow-point"><time>${esc(t || "-")}</time><div><strong>${esc(names.join(" · ") || "유효 자금흐름 없음")}</strong><small>${esc((obs.signals || []).slice(0,2).join(" · "))}</small></div></div>`;
  }).join("") || "<p class='muted'>6분 관측이 쌓이면 최근 30분 자금 이동을 시간순으로 표시합니다.</p>";

  const interpretation = $("overnight-interpretation");
  if (interpretation) interpretation.innerHTML = aiSummary.length
    ? aiSummary.slice(0,4).map(x => `<p>${esc(x)}</p>`).join("")
    : "<p class='muted'>:00/:30 Supervisor 해석을 기다리는 중입니다.</p>";

  const risk = data.risk || {};
  const riskEval = risk.evaluation || {};
  const riskLevel = riskEval.risk_level || risk.risk_level || "LOW";
  const riskBadge = $("risk-level");
  riskBadge.textContent = riskLevel;
  riskBadge.dataset.level = riskLevel;

  const biggest = riskEval.single_biggest_risk || {};
  $("risk-summary").innerHTML =
    `<div class="risk-level-large">${esc(riskLevel)}</div>` +
    `<strong>${esc(riskEval.summary || "리스크 상태를 계산 중입니다.")}</strong>` +
    `<p>${esc(biggest.title || "확인된 단일 대형 리스크 없음")}</p>` +
    `<small>${esc(biggest.why || "")}</small>`;

  $("risk-events").innerHTML = (risk.upcoming_events || []).slice(0, 5).map((x) =>
    `<div class="mini-row risk-row"><strong>${esc(x.title)}</strong><span>${esc(x.hours_to_event)}h · ${esc(x.risk_level)}</span></div>`
  ).join("") || "<p class='muted'>가까운 주요 일정 없음</p>";

  $("risk-macro").innerHTML = (risk.macro_signals || []).slice(0, 6).map((x) =>
    `<div class="mini-row risk-row"><strong>${esc(x.field)}</strong><span>${esc(x.value)} · ${esc(x.risk_level)}</span></div>`
  ).join("") || "<p class='muted'>현재 임계값 초과 경고 없음</p>";

  $("docs-links").innerHTML = (data.docs_links || []).map((x) =>
    `<a class="mini-row doc-link" href="${esc(x.url)}" target="_blank" rel="noreferrer"><strong>${esc(x.title)}</strong><span>읽기 ↗</span></a>`
  ).join("");

  const market = data.market || {};
  const runtime = data.market_runtime || {};
  const q = market.quantitative || {};
  const interp = market.interpretation || {};
  const source = market.source || {};
  const runtimeStatus = runtime.source_status || source.status || q.status || "데이터 없음";
  const statusLabels = {
    ok: "장중 분석",
    outside_regular_session: "장 종료 · 마지막 유효 장세",
    needs_credentials: "키움 API 설정 필요",
    no_rows: "시세 데이터 없음",
    toss_snapshot_unavailable: "토스 Collector 대기",
    outside_domestic_monitor_window: "국내시장 감시시간 종료"
  };
  $("market-status").textContent = statusLabels[runtimeStatus] || runtimeStatus;

  if (q.status === "ok") {
    const breadth = q.breadth || {};
    const turnover = q.turnover || {};
    const overview = source.market_overview || {};
    const kospi = overview.KOSPI || {};
    const kosdaq = overview.KOSDAQ || {};
    $("market-summary").innerHTML =
      `<div class="regime"><strong>${esc(interp.regime_name || "정량 장세 분석")}</strong><p>${esc(interp.one_line || "분봉 거래대금과 전체시장 폭을 분석 중입니다.")}</p><small>${source.minute_amount_method === "close_x_volume_estimate" ? "1분 거래대금은 종가×거래량 근사" : ""}</small></div>` +
      `<div class="market-numbers">
        <span>KOSPI <b>${kospi.change_pct ?? "-"}%</b><small>상승 ${kospi.rising ?? "-"} / 하락 ${kospi.falling ?? "-"}</small></span>
        <span>KOSDAQ <b>${kosdaq.change_pct ?? "-"}%</b><small>상승 ${kosdaq.rising ?? "-"} / 하락 ${kosdaq.falling ?? "-"}</small></span>
        <span>상세 분석 <b>${esc(q.stock_count || 0)}종목</b><small>거래대금 중심 Universe</small></span>
        <span>Top10 집중 <b>${(((source.turnover_rank_top10_share ?? turnover.top10_share) || 0) * 100).toFixed(1)}%</b><small>거래대금 순위 기준</small></span>
      </div>`;

    const postmarket = source.postmarket || {};
    $("nxt-after").innerHTML = (postmarket.stocks || []).length
      ? (postmarket.stocks || []).slice(0, 8).map((x) => {
          const premium = x.krx_close_premium_pct == null
            ? "-"
            : (Number(x.krx_close_premium_pct) >= 0 ? "+" : "") + Number(x.krx_close_premium_pct).toFixed(2) + "%";
          return `<div class="nxt-card">
            <strong>${esc(x.name || x.ticker)}</strong>
            <span>KRX 대비 ${esc(premium)}</span>
            <span>애프터 ${esc(x.return_pct)}%</span>
            <span>${esc(krwEok(x.amount))}</span>
          </div>`;
        }).join("")
      : `<p class="muted">${source.provider === "toss" ? "현재 애프터마켓 체결 없음" : "토스 Collector 연결 후 20시까지 표시됩니다."}</p>`;

    $("burst-leaders").innerHTML = (q.burst_leaders || []).slice(0, 6).map((x) =>
      `<div class="mini-row"><strong>${esc(x.name || x.ticker)}</strong><span>${esc(x.burst_count)}회 · 1분 최대 ${esc(krwEok(x.max_minute_amount))} · ${esc(x.max_burst_ratio)}배</span></div>`
    ).join("") || "<p class='muted'>조건 충족 종목 없음</p>";

    const recent = q.recent_listings || {};
    const recentEvents = recent.threshold_event_counts || {};
    const recentStocks = recent.threshold_stock_counts || {};
    const recentHeader = recent.count
      ? `<div class="mini-row"><strong>10억↑ 분봉</strong><span>${esc(recentEvents["1000000000"] || 0)}회 · ${esc(recentStocks["1000000000"] || 0)}종목</span></div>` +
        `<div class="mini-row"><strong>20억↑ 분봉</strong><span>${esc(recentEvents["2000000000"] || 0)}회 · ${esc(recentStocks["2000000000"] || 0)}종목</span></div>`
      : "";
    $("new-listings").innerHTML = recentHeader + (
      (recent.stocks || []).slice(0, 5).map((x) =>
        `<div class="mini-row"><strong>${esc(x.name || x.ticker)}</strong><span>${esc(x.burst_count)}회 · 1분 최대 ${esc(krwEok(x.max_minute_amount))}</span></div>`
      ).join("") || `<p class="muted">현재 상세 Universe에서 신규주 흐름 없음</p>`
    );

    $("coflow-groups").innerHTML = (q.coflow_groups || []).slice(0, 5).map((x) =>
      `<div class="mini-row"><strong>${esc(x.group)}</strong><span>${esc(x.synchronized_burst_members || 0)}종목 · ${esc(x.synchronized_center || "-")} 동조</span></div>`
    ).join("") || "<p class='muted'>확인된 동조 그룹 없음</p>";

    const st = market.strategy_stats || {};
    const closeBlock = st.close_bet || {};
    const swingBlock = st.pullback || {};
    const closeN = ((closeBlock.summary || {}).sample_size || 0);
    const swingN = ((swingBlock.summary || {}).sample_size || 0);
    const closeMfe = medianField(closeBlock, "next_mfe_pct");
    const closeMae = medianField(closeBlock, "next_mae_pct");
    const swingMfe = medianField(swingBlock, "forward_5d_mfe_pct");
    const swingMae = medianField(swingBlock, "forward_5d_mae_pct");
    const closeRates = closeBlock.rates || {};
    const swingRates = swingBlock.rates || {};
    const rebound5 = (((swingBlock.rebound_drawdown || {}).mfe_ge_5 || {}).summary || {});
    const rebound5Drawdown = (((rebound5.fields || {}).drawdown_pct || {}).median);
    $("strategy-stats").innerHTML =
      `<div class="mini-row"><strong>종가베팅</strong><span>${esc(closeBlock.reliability || "표본 축적")} · n=${closeN}</span></div>` +
      `<div class="mini-row"><strong>다음날 중앙</strong><span>MFE ${closeMfe ?? "-"}% / MAE ${closeMae ?? "-"}%</span></div>` +
      `<div class="mini-row"><strong>+5% / -5%</strong><span>${ratePct(closeRates.mfe_ge_5)} / ${ratePct(closeRates.mae_le_minus5)}</span></div>` +
      `<div class="mini-row"><strong>눌림스윙</strong><span>${esc(swingBlock.reliability || "표본 축적")} · n=${swingN}</span></div>` +
      `<div class="mini-row"><strong>5일 중앙</strong><span>MFE ${swingMfe ?? "-"}% / MAE ${swingMae ?? "-"}%</span></div>` +
      `<div class="mini-row"><strong>+5% 반등 / -5% 역행</strong><span>${ratePct(swingRates.mfe_ge_5)} / ${ratePct(swingRates.mae_le_minus5)}</span></div>` +
      `<div class="mini-row"><strong>+5% 반등 표본 중앙 눌림</strong><span>${rebound5Drawdown ?? "-"}%</span></div>`;

    const thin = (q.rise_without_burst || []).slice(0, 4);
    if (thin.length) {
      $("burst-leaders").insertAdjacentHTML(
        "beforeend",
        `<div class="thin-title">거래대금 미확인 상승</div>` +
        thin.map((x) =>
          `<div class="mini-row warning-row"><strong>${esc(x.name || x.ticker)}</strong><span>+${esc(x.return_pct)}% · burst 0</span></div>`
        ).join("")
      );
    }
  } else {
    const reason = source.reason || q.reason || "국내시장 실데이터가 아직 연결되지 않았습니다.";
    $("market-summary").innerHTML = `<div class="regime"><strong>분석 대기</strong><p>${esc(reason)}</p></div>`;
    $("nxt-after").innerHTML = "<p class='muted'>토스 Collector 데이터 필요</p>";
    $("burst-leaders").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("new-listings").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("coflow-groups").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("strategy-stats").innerHTML = "<p class='muted'>표본 축적 전</p>";
  }

  const macro = data.macro_matrix || {};
  $("macro-regime").textContent = macro.macro_regime || macro.risk_level || "UNKNOWN";
  $("macro-regime").dataset.level = macro.risk_level || "LOW";
  $("macro-coverage").textContent = `${macro.known_count || 0}/${macro.total_count || 0} 확인`;

  $("macro-paths").innerHTML = (macro.transmission_paths || []).length
    ? (macro.transmission_paths || []).slice(0, 5).map((x) =>
      `<div class="mini-row macro-note"><span>${esc(x)}</span></div>`
    ).join("")
    : "<p class='muted'>AI가 전달 경로를 평가할 데이터가 아직 부족합니다.</p>";

  $("macro-conflicts").innerHTML = (macro.conflicting_signals || []).length
    ? (macro.conflicting_signals || []).slice(0, 5).map((x) =>
      `<div class="mini-row macro-note"><span>${esc(x)}</span></div>`
    ).join("")
    : "<p class='muted'>현재 기록된 충돌 신호 없음</p>";

  function macroValue(item) {
    if (item.value == null || item.value === "") return "미확인";
    const n = Number(item.value);
    if (!Number.isFinite(n)) return esc(item.value);
    if (item.kind === "yield") return n.toFixed(3) + "%";
    if (item.kind === "bp") return (n >= 0 ? "+" : "") + n.toFixed(1) + "bp";
    return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
  }

  const macroGroups = {};
  (macro.items || []).forEach((item) => {
    (macroGroups[item.group] ||= []).push(item);
  });
  $("macro-groups").innerHTML = Object.entries(macroGroups).map(([group, items]) =>
    `<div class="macro-group">
      <div class="subhead">${esc(group)}</div>
      <div class="macro-cards">
        ${items.map((x) => `<div class="macro-card" data-risk="${esc(x.risk_level || "LOW")}">
          <strong>${esc(x.label)}</strong>
          <b>${macroValue(x)}</b>
          <small>${esc(x.risk_level || "LOW")}</small>
        </div>`).join("")}
      </div>
    </div>`
  ).join("");

  const provider = data.toss_provider || {};
  const providerRuntime = data.market_runtime || {};
  const providerMode = provider.available
    ? "TOSS LIVE"
    : (providerRuntime.provider === "kiwoom" ? "KIWOOM FALLBACK" : "WAITING");
  const providerCards = [
    ["현재 경로", providerMode],
    ["Toss Snapshot", provider.available ? ageText(provider.captured_at) : "없음"],
    ["최근 체결", provider.last_message_at ? ageText(provider.last_message_at) : "미확인"],
    ["구독", (provider.subscription_count ?? 0) + "개"],
    ["구독 거절", (provider.rejected_count ?? 0) + "건"],
    ["정규장 종목", (provider.regular_ticker_count ?? 0) + "개"],
    ["NXT 종목", (provider.postmarket_ticker_count ?? 0) + "개"],
    ["1분 거래대금", provider.minute_amount_method === "exact_trade_sum" ? "실체결 합산" : "근사/미확인"],
  ];
  $("provider-status").innerHTML = providerCards.map(([label, value]) =>
    `<div class="provider-card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
  ).join("");

  const health = data.health || {};
  const healthStatus = health.status || "UNKNOWN";
  const healthBadge = $("health-status");
  healthBadge.textContent = healthStatus;
  healthBadge.dataset.level = healthStatus;
  $("health-issues").innerHTML = (health.issues || []).length
    ? health.issues.map((x) =>
      `<div class="health-item" data-level="${esc(x.severity)}">
        <div><strong>${esc(x.component)} · ${esc(x.code)}</strong><p>${esc(x.message)}</p></div>
        <div class="health-recovery">${esc(x.recovery)}</div>
      </div>`
    ).join("")
    : `<div class="health-ok">현재 확인된 운영 이상 없음</div>`;


  });
  renderQualityChart();
  renderReports();

  const regression = data.regression || {};
  const regressionStatus = regression.status || "COLLECTING";
  const regressionBadge = $("regression-status");
  regressionBadge.textContent = regressionStatus;
  regressionBadge.dataset.level = regressionStatus;
  const snap = regression.snapshot || {};
  const baseline = regression.baseline_summary || {};
  $("regression-summary").innerHTML =
    `<div class="regression-number"><strong>${snap.overall_quality ?? "-"}점</strong><span>현재 종합 품질</span></div>` +
    `<div class="regression-number"><strong>${baseline.overall_7d ?? "-"}점</strong><span>7일 평균 · n=${baseline.samples_7d ?? 0}</span></div>` +
    `<div class="regression-number"><strong>${baseline.overall_30d ?? "-"}점</strong><span>30일 평균 · n=${baseline.samples_30d ?? 0}</span></div>` +
    `<div class="regression-number"><strong>${regression.active_change_count ?? 0}</strong><span>활성 AI 변경</span></div>` +
    `<div class="regression-number"><strong>${regression.quarantine_count ?? 0}</strong><span>격리</span></div>` +
    `<div class="regression-number"><strong>${regression.rolled_back_count ?? 0}</strong><span>기능 롤백</span></div>`;

  $("regression-evals").innerHTML = (regression.evaluations || []).slice(0, 6).map((x) =>
    `<div class="mini-row"><strong>${esc(x.change_id || x.status)}</strong><span>${esc(x.status)}${x.drop_7d != null ? " · 7일 " + Number(x.drop_7d).toFixed(1) + "p" : ""}</span></div>`
  ).join("") || "<p class='muted'>평가할 AI 변경 표본을 수집 중입니다.</p>";

  $("recent-changes").innerHTML = (data.recent_changes || []).length
    ? (data.recent_changes || []).slice(0, 12).map((x) =>
      `<div class="tick" data-outcome="${esc(x.status)}">
        <span class="dot"></span>
        <div>
          <strong>${esc(x.title || x.change_id || "AI 변경")}</strong>
          <p>${esc((x.paths || []).join(", "))}</p>
          <div class="meta">${esc(x.applied_at || "")} · ${esc(x.status || "active")} · ${esc(x.risk || "")}</div>
        </div>
      </div>`
    ).join("")
    : "<p class='muted'>앞으로 자동 적용되는 변경부터 manifest가 기록됩니다.</p>";

  const board = data.idea_board || {};
  const boardOrder = ["채택", "실험중", "후보", "재검토", "보류", "폐기"];
  $("ideas-kanban").innerHTML = boardOrder.map((status) => {
    const items = board[status] || [];
    return `<div class="kanban-column">
      <div class="kanban-head"><strong>${esc(status)}</strong><span>${items.length}</span></div>
      <div class="kanban-list">${items.slice(0, 12).map((x) =>
        `<div class="kanban-card"><strong>${esc(x.title)}</strong><p>${esc(x.summary || "")}</p></div>`
      ).join("") || "<p class='muted'>없음</p>"}</div>
    </div>`;
  }).join("");

  $("ticks").innerHTML = (data.ticks || []).length
    ? data.ticks.map((t) =>
      `<div class="tick" data-outcome="${esc(t.outcome)}">
        <span class="dot"></span>
        <div>
          <strong>${esc(t.title || "판단")}</strong>
          <p>${esc(t.observation || "")}</p>
          <div class="meta">${esc(t.time || "")} · ${esc(t.category || "")} · ${esc(t.outcome || "")}</div>
        </div>
      </div>`
    ).join("")
    : `<p>첫 10분 Tick을 기다리고 있습니다.</p>`;

  $("decisions").textContent = data.decision_memory || "기록 없음";
  $("ideas").textContent = data.ideas || "기록 없음";
  $("help").textContent = data.help_needed || "현재 요청 없음";
  $("changelog").textContent = data.changelog || "기록 없음";
  $("updated").textContent = "갱신 " + new Date(data.generated_at).toLocaleString("ko-KR");
}

load().catch((error) => {
  document.body.insertAdjacentHTML("beforeend",
    `<div style="position:fixed;left:12px;right:12px;bottom:12px;padding:14px;background:#521f2b;color:white;border-radius:10px">${esc(error.message)}</div>`);
});
