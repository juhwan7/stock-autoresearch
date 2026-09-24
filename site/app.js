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

function esc(value = "") {
  return String(value).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}

async function load() {
  const response = await fetch("data/status.json", { cache: "no-store" });
  if (!response.ok) throw new Error("status.json을 불러오지 못했습니다.");
  const data = await response.json();

  const metrics = [
    ["Heartbeat", data.heartbeat || "10분"],
    ["최근 보고서", (data.reports || []).length + "개"],
    ["최근 진화 Tick", (data.ticks || []).length + "개"],
    ["상태", "자동 진화 중"],
  ];
  $("metrics").innerHTML = metrics.map(([label, value]) =>
    `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`
  ).join("");

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
    no_rows: "시세 데이터 없음"
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
    $("burst-leaders").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("new-listings").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("coflow-groups").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("strategy-stats").innerHTML = "<p class='muted'>표본 축적 전</p>";
  }

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

  const allReports = data.reports || [];
  const stockSelect = $("report-stock");
  const industrySelect = $("report-industry");
  const searchInput = $("report-search");
  const dateInput = $("report-date");

  const stocks = [...new Set(allReports.flatMap((r) => r.stocks || []))].sort();
  const industries = [...new Set(allReports.flatMap((r) => r.industries || []))].sort();
  stockSelect.insertAdjacentHTML(
    "beforeend",
    stocks.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("")
  );
  industrySelect.insertAdjacentHTML(
    "beforeend",
    industries.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("")
  );

  function reportDay(value) {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 10);
    return parsed.toISOString().slice(0, 10);
  }

  function renderQualityChart() {
    const rows = (data.quality_history || []).filter((x) => x.quality != null);
    $("quality-chart").innerHTML = rows.length
      ? rows.map((x) => {
          const score = Math.max(0, Math.min(100, Number(x.quality || 0)));
          return `<div class="quality-bar-wrap" title="${esc(reportDay(x.generated_at))} · ${score.toFixed(1)}점">
            <div class="quality-bar" style="height:${score}%"></div>
          </div>`;
        }).join("")
      : `<p class="muted">아직 품질점수 이력이 충분하지 않습니다.</p>`;
  }

  function renderReports() {
    const query = (searchInput.value || "").trim().toLowerCase();
    const day = dateInput.value || "";
    const stock = stockSelect.value || "";
    const industry = industrySelect.value || "";

    const filtered = allReports.filter((r) => {
      const haystack = [
        r.title,
        r.preview,
        ...(r.stocks || []),
        ...(r.industries || []),
      ].join(" ").toLowerCase();
      return (!query || haystack.includes(query))
        && (!day || reportDay(r.generated_at) === day)
        && (!stock || (r.stocks || []).includes(stock))
        && (!industry || (r.industries || []).includes(industry));
    });

    $("report-count").textContent = filtered.length + "개";
    $("reports").innerHTML = filtered.length
      ? filtered.map((r) => {
          const meta = [
            reportDay(r.generated_at),
            r.quality != null ? `품질 ${Number(r.quality).toFixed(1)}` : "",
            (r.stocks || []).slice(0, 2).join(" · "),
            (r.industries || []).slice(0, 2).join(" · "),
          ].filter(Boolean).join(" · ");
          return `<a class="report report-card" href="${esc(r.github_url)}" target="_blank" rel="noreferrer">
            <span><strong>${esc(r.title)}</strong><small>${esc(meta)}</small></span>
            <b>읽기 ↗</b>
          </a>`;
        }).join("")
      : `<div class="report"><span>조건에 맞는 리서치가 없습니다.</span></div>`;
  }

  [searchInput, dateInput, stockSelect, industrySelect].forEach((element) => {
    element.addEventListener("input", renderReports);
    element.addEventListener("change", renderReports);
  });
  $("report-clear").addEventListener("click", () => {
    searchInput.value = "";
    dateInput.value = "";
    stockSelect.value = "";
    industrySelect.value = "";
    renderReports();
  });
  renderQualityChart();
  renderReports();

  const regression = data.regression || {};
  const regressionStatus = regression.status || "COLLECTING";
  const regressionBadge = $("regression-status");
  regressionBadge.textContent = regressionStatus;
  regressionBadge.dataset.level = regressionStatus;
  const snap = regression.snapshot || {};
  $("regression-summary").innerHTML =
    `<div class="regression-number"><strong>${snap.overall_quality ?? "-"}점</strong><span>현재 종합 품질</span></div>` +
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
  const boardOrder = ["채택", "실험중", "재검토", "보류", "폐기"];
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
