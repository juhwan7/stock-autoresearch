const $ = (id) => document.getElementById(id);

function krwEok(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return "-";
  return (n / 100000000).toFixed(n >= 1000000000 ? 1 : 2) + "억";
}

function medianField(block, field) {
  return (((block || {}).summary || {}).fields || {})[field]?.median;
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

  const market = data.market || {};
  const q = market.quantitative || {};
  const interp = market.interpretation || {};
  const source = market.source || {};
  $("market-status").textContent = source.status || q.status || "데이터 없음";

  if (q.status === "ok") {
    const breadth = q.breadth || {};
    const turnover = q.turnover || {};
    $("market-summary").innerHTML =
      `<div class="regime"><strong>${esc(interp.regime_name || "정량 장세 분석")}</strong><p>${esc(interp.one_line || "분봉 거래대금과 시장 폭을 분석 중입니다.")}</p></div>` +
      `<div class="market-numbers">
        <span>분석 종목 <b>${esc(q.stock_count || 0)}</b></span>
        <span>상승 <b>${esc(breadth.advancers || 0)}</b></span>
        <span>하락 <b>${esc(breadth.decliners || 0)}</b></span>
        <span>Top10 집중 <b>${((turnover.top10_share || 0) * 100).toFixed(1)}%</b></span>
      </div>`;

    $("burst-leaders").innerHTML = (q.burst_leaders || []).slice(0, 6).map((x) =>
      `<div class="mini-row"><strong>${esc(x.name || x.ticker)}</strong><span>${esc(x.burst_count)}회 · 1분 최대 ${esc(krwEok(x.max_minute_amount))} · ${esc(x.max_burst_ratio)}배</span></div>`
    ).join("") || "<p class='muted'>조건 충족 종목 없음</p>";

    $("coflow-groups").innerHTML = (q.coflow_groups || []).slice(0, 5).map((x) =>
      `<div class="mini-row"><strong>${esc(x.group)}</strong><span>${esc(x.positive_burst_members)}종목 동조</span></div>`
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
    $("strategy-stats").innerHTML =
      `<div class="mini-row"><strong>종가베팅</strong><span>${esc(closeBlock.reliability || "표본 축적")} · n=${closeN}</span></div>` +
      `<div class="mini-row"><strong>다음날 중앙</strong><span>MFE ${closeMfe ?? "-"}% / MAE ${closeMae ?? "-"}%</span></div>` +
      `<div class="mini-row"><strong>눌림스윙</strong><span>${esc(swingBlock.reliability || "표본 축적")} · n=${swingN}</span></div>` +
      `<div class="mini-row"><strong>5일 중앙</strong><span>MFE ${swingMfe ?? "-"}% / MAE ${swingMae ?? "-"}%</span></div>`;

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
    $("coflow-groups").innerHTML = "<p class='muted'>데이터 필요</p>";
    $("strategy-stats").innerHTML = "<p class='muted'>표본 축적 전</p>";
  }

  $("reports").innerHTML = (data.reports || []).length
    ? data.reports.map((r) =>
      `<a class="report" href="${esc(r.github_url)}" target="_blank" rel="noreferrer">
        <span>${esc(r.title)}</span><small>GitHub ↗</small>
      </a>`
    ).join("")
    : `<div class="report"><span>아직 생성된 실전 보고서가 없습니다.</span></div>`;

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
