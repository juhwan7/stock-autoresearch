const $ = (id) => document.getElementById(id);

const MARKET_STATE = { nasdaq: "1D", kospi: "1D" };
const MARKET_DATA = {};

function esc(value = "") {
  return String(value).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}

function pct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
}

function rsPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%p";
}

function compactNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

function tone(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "neutral";
  return n > 0 ? "up" : "down";
}

function marketStatus(block) {
  const status = String(block?.status || "unavailable").toLowerCase();
  const labels = {
    ok: "최신 데이터",
    partial: "일부 종목 계산",
    stale: "이전 데이터 · 갱신 실패",
    unavailable: "데이터 없음",
  };
  return {status, label: labels[status] || status};
}

function periodBlock(root, period) {
  if (period === "1D") return root || {};
  return (root?.periods || {})[period] || {};
}

function tableRows(rows, benchmark) {
  if (!rows || !rows.length) {
    return '<tr><td colspan="7" class="neutral">표시할 데이터가 없습니다.</td></tr>';
  }
  return rows.map((row) => `<tr>
    <td><strong>${esc(row.ticker || "-")}</strong></td>
    <td title="${esc(row.name || "")}">${esc(row.name || "-")}</td>
    <td class="${tone(row.change_pct)}">${esc(pct(row.change_pct))}</td>
    <td class="${tone(benchmark.change_pct)}">${esc(pct(benchmark.change_pct))}</td>
    <td class="rs ${tone(row.relative_strength_pct)}">${esc(rsPct(row.relative_strength_pct))}</td>
    <td>${esc(compactNumber(row.market_cap))}</td>
    <td>${esc(compactNumber(row.volume))}</td>
  </tr>`).join("");
}

function consistencyRows(rows) {
  if (!rows || !rows.length) return '<p class="muted">해당 종목 없음</p>';
  return rows.slice(0, 12).map((row) => `
    <div class="consistency-row">
      <div>
        <strong>${esc(row.name || row.ticker || "-")}</strong>
        <span>${esc(row.ticker || "")}</span>
      </div>
      <div class="rs-triplet">
        <b class="${tone(row.rs_1d)}">1D ${esc(rsPct(row.rs_1d))}</b>
        <b class="${tone(row.rs_5d)}">5D ${esc(rsPct(row.rs_5d))}</b>
        <b class="${tone(row.rs_20d)}">20D ${esc(rsPct(row.rs_20d))}</b>
      </div>
    </div>
  `).join("");
}

function renderConsistency(root) {
  const block = root?.consistency || {};
  if (!block || block.status === "unavailable") {
    return `<div class="consistency-empty">5D·20D 일봉이 충분히 확보되면 지속 강도 분류가 표시됩니다.</div>`;
  }
  const counts = block.counts || {};
  const coverage = Number(block.coverage_ratio);
  const coverageText = Number.isFinite(coverage) ? (coverage * 100).toFixed(1) + "%" : "-";
  return `
    <div class="consistency-head">
      <div>
        <strong>기간을 바꿔도 강한가?</strong>
        <p>1D·5D·20D를 함께 비교합니다. 계산 가능 종목 ${Number(block.coverage_count || 0).toLocaleString("ko-KR")}개 · 커버리지 ${esc(coverageText)}</p>
      </div>
      <span class="status ${esc(String(block.status || "partial").toLowerCase())}">${block.status === "ok" ? "기간 비교 정상" : "일부 종목 비교"}</span>
    </div>
    <div class="consistency-grid">
      <article class="consistency-card">
        <div class="consistency-title"><strong>계속 강함</strong><span>${Number(counts.persistent_strong || 0).toLocaleString("ko-KR")}개</span></div>
        <p>1D·5D·20D 모두 지수보다 강한 종목</p>
        ${consistencyRows(block.persistent_strong)}
      </article>
      <article class="consistency-card">
        <div class="consistency-title"><strong>최근 강세 전환</strong><span>${Number(counts.turning_strong || 0).toLocaleString("ko-KR")}개</span></div>
        <p>1D는 강하지만 5D 또는 20D는 아직 약한 종목</p>
        ${consistencyRows(block.turning_strong)}
      </article>
      <article class="consistency-card">
        <div class="consistency-title"><strong>계속 약함</strong><span>${Number(counts.persistent_weak || 0).toLocaleString("ko-KR")}개</span></div>
        <p>1D·5D·20D 모두 지수보다 약한 종목</p>
        ${consistencyRows(block.persistent_weak)}
      </article>
      <article class="consistency-card">
        <div class="consistency-title"><strong>최근 약세 전환</strong><span>${Number(counts.turning_weak || 0).toLocaleString("ko-KR")}개</span></div>
        <p>1D는 약하지만 5D 또는 20D는 아직 강한 종목</p>
        ${consistencyRows(block.turning_weak)}
      </article>
    </div>
  `;
}

function periodButtons(targetId, root) {
  return ["1D", "5D", "20D"].map((period) => {
    const block = periodBlock(root, period);
    const available = period === "1D" ? true : Boolean(block && Object.keys(block).length);
    const active = MARKET_STATE[targetId] === period;
    return `<button class="period-button ${active ? "active" : ""}" ${available ? "" : "disabled"}
      onclick="selectPeriod('${targetId}','${period}')">${period === "1D" ? "1일" : period === "5D" ? "5일" : "20일"}</button>`;
  }).join("");
}

function renderMarket(targetId, root, title, kicker) {
  const target = $(targetId);
  if (!target) return;
  root = root || {};
  const period = MARKET_STATE[targetId] || "1D";
  const block = periodBlock(root, period);
  const benchmark = block.benchmark || {};
  const state = marketStatus(block);
  const count = Number(block.universe_count || 0);
  const above = Number(block.above_benchmark_count || 0);
  const below = Number(block.below_benchmark_count || 0);
  const ratio = Number(block.above_benchmark_ratio);
  const ratioText = Number.isFinite(ratio) ? (ratio * 100).toFixed(1) + "%" : "-";
  const coverage = Number(block.history_coverage_ratio);
  const coverageText = Number.isFinite(coverage) ? (coverage * 100).toFixed(1) + "%" : null;
  const distribution = block.distribution || [];
  const maxCount = Math.max(1, ...distribution.map(x => Number(x.count || 0)));
  const error = block.stale_reason || block.reason || "";
  const periodLabel = period === "1D" ? "당일" : period === "5D" ? "최근 5거래일" : "최근 20거래일";

  target.innerHTML = `
    <article class="market" id="${targetId}-panel">
      <div class="market-head">
        <div>
          <p class="eyebrow">${esc(kicker)}</p>
          <h2>${esc(title)}</h2>
          <p>${esc(block.universe_label || root.universe_label || "유니버스 미확인")} · ${esc(periodLabel)} · 기준 ${esc(benchmark.session || "세션 미확인")}</p>
        </div>
        <span class="status ${esc(state.status)}">${esc(state.label)}</span>
      </div>

      <div class="period-tabs" aria-label="상대강도 기간">
        ${periodButtons(targetId, root)}
      </div>

      <div class="summary">
        <div class="card"><span>기준지수 수익률</span><strong class="${tone(benchmark.change_pct)}">${esc(pct(benchmark.change_pct))}</strong></div>
        <div class="card"><span>지수보다 강한 종목</span><strong class="up">${above.toLocaleString("ko-KR")}개</strong></div>
        <div class="card"><span>지수보다 약한 종목</span><strong class="down">${below.toLocaleString("ko-KR")}개</strong></div>
        <div class="card"><span>지수 상회 비율</span><strong>${esc(ratioText)}</strong></div>
        <div class="card"><span>중앙 상대강도</span><strong class="${tone(block.median_relative_strength_pct)}">${esc(rsPct(block.median_relative_strength_pct))}</strong></div>
      </div>

      ${coverageText ? `<div class="coverage-note">기간 일봉 확보율 <strong>${esc(coverageText)}</strong> · 현재 유니버스 ${Number(block.requested_universe_count || count).toLocaleString("ko-KR")}개 중 ${count.toLocaleString("ko-KR")}개 계산</div>` : ""}

      <div class="dist">
        ${distribution.map(x => {
          const width = Math.max(6, Math.round(Number(x.count || 0) / maxCount * 100));
          return `<div class="dist-item" title="분포 비중 ${width}%"><strong>${Number(x.count || 0).toLocaleString("ko-KR")}개</strong><span>${esc(x.label || "")}</span></div>`;
        }).join("") || '<div class="dist-item"><strong>-</strong><span>분포 데이터 없음</span></div>'}
      </div>

      <div class="tables">
        <div class="table-card">
          <div class="table-title"><strong>지수보다 강한 종목 TOP 50</strong><span>${esc(periodLabel)} 상대강도 높은 순</span></div>
          <div class="table-wrap"><table>
            <thead><tr><th>티커</th><th>종목명</th><th>종목수익률</th><th>지수수익률</th><th>상대강도</th><th>시총</th><th>거래량</th></tr></thead>
            <tbody>${tableRows(block.strongest || [], benchmark)}</tbody>
          </table></div>
        </div>
        <div class="table-card">
          <div class="table-title"><strong>지수보다 약한 종목 TOP 50</strong><span>${esc(periodLabel)} 상대강도 낮은 순</span></div>
          <div class="table-wrap"><table>
            <thead><tr><th>티커</th><th>종목명</th><th>종목수익률</th><th>지수수익률</th><th>상대강도</th><th>시총</th><th>거래량</th></tr></thead>
            <tbody>${tableRows(block.weakest || [], benchmark)}</tbody>
          </table></div>
        </div>
      </div>

      <section class="consistency">
        ${renderConsistency(root)}
      </section>

      <div class="source">
        <strong>데이터 상태:</strong> ${count.toLocaleString("ko-KR")}개 종목 계산. ${error ? "주의: " + esc(error) + " · " : ""}
        상대강도는 같은 기간의 종목 수익률에서 기준지수 수익률을 뺀 값이며 향후 수익률 예측값이 아닙니다.
        ${(block.sources || []).length ? "<br><strong>출처:</strong> " + (block.sources || []).map(esc).join(" · ") : ""}
      </div>
    </article>`;
}

function selectPeriod(targetId, period) {
  if (!MARKET_DATA[targetId]) return;
  MARKET_STATE[targetId] = period;
  if (targetId === "nasdaq") {
    renderMarket("nasdaq", MARKET_DATA.nasdaq, "NASDAQ Composite 대비 강·약 종목", "NASDAQ RELATIVE STRENGTH");
  } else {
    renderMarket("kospi", MARKET_DATA.kospi, "KOSPI 대비 강·약 종목", "KOSPI RELATIVE STRENGTH");
  }
}
window.selectPeriod = selectPeriod;

async function load() {
  const response = await fetch("data/상대강도.json", {cache: "no-store"});
  if (!response.ok) throw new Error("상대강도 데이터를 불러오지 못했습니다.");
  const data = await response.json();
  MARKET_DATA.nasdaq = data.nasdaq || {};
  MARKET_DATA.kospi = data.kospi || {};
  renderMarket("nasdaq", MARKET_DATA.nasdaq, "NASDAQ Composite 대비 강·약 종목", "NASDAQ RELATIVE STRENGTH");
  renderMarket("kospi", MARKET_DATA.kospi, "KOSPI 대비 강·약 종목", "KOSPI RELATIVE STRENGTH");
  $("updated").textContent = data.generated_at
    ? "갱신 " + new Date(data.generated_at).toLocaleString("ko-KR")
    : "갱신 시각 미확인";
}

load().catch((error) => {
  document.body.insertAdjacentHTML(
    "beforeend",
    `<div style="position:fixed;left:12px;right:12px;bottom:12px;padding:14px;background:#9b263a;color:white;border-radius:10px">${esc(error.message)}</div>`
  );
});
