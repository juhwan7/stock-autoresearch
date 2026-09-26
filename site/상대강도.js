const $ = (id) => document.getElementById(id);

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

function marketStatus(block) {
  const status = String(block.status || "unavailable").toLowerCase();
  const label = status === "ok" ? "최신 데이터" : status === "stale" ? "이전 데이터 · 갱신 실패" : "데이터 없음";
  return {status, label};
}

function renderMarket(targetId, block, title, kicker) {
  const target = $(targetId);
  if (!target) return;
  block = block || {};
  const benchmark = block.benchmark || {};
  const state = marketStatus(block);
  const count = Number(block.universe_count || 0);
  const above = Number(block.above_benchmark_count || 0);
  const below = Number(block.below_benchmark_count || 0);
  const ratio = Number(block.above_benchmark_ratio);
  const ratioText = Number.isFinite(ratio) ? (ratio * 100).toFixed(1) + "%" : "-";
  const distribution = block.distribution || [];
  const maxCount = Math.max(1, ...distribution.map(x => Number(x.count || 0)));
  const error = block.stale_reason || block.reason || "";

  target.innerHTML = `
    <article class="market" id="${targetId}-panel">
      <div class="market-head">
        <div>
          <p class="eyebrow">${esc(kicker)}</p>
          <h2>${esc(title)}</h2>
          <p>${esc(block.universe_label || "유니버스 미확인")} · 기준 ${esc(benchmark.session || "세션 미확인")}</p>
        </div>
        <span class="status ${esc(state.status)}">${esc(state.label)}</span>
      </div>

      <div class="summary">
        <div class="card"><span>기준지수 등락률</span><strong class="${tone(benchmark.change_pct)}">${esc(pct(benchmark.change_pct))}</strong></div>
        <div class="card"><span>지수보다 강한 종목</span><strong class="up">${above.toLocaleString("ko-KR")}개</strong></div>
        <div class="card"><span>지수보다 약한 종목</span><strong class="down">${below.toLocaleString("ko-KR")}개</strong></div>
        <div class="card"><span>지수 상회 비율</span><strong>${esc(ratioText)}</strong></div>
        <div class="card"><span>중앙 상대강도</span><strong class="${tone(block.median_relative_strength_pct)}">${esc(rsPct(block.median_relative_strength_pct))}</strong></div>
      </div>

      <div class="dist">
        ${distribution.map(x => {
          const width = Math.max(6, Math.round(Number(x.count || 0) / maxCount * 100));
          return `<div class="dist-item" title="분포 비중 ${width}%"><strong>${Number(x.count || 0).toLocaleString("ko-KR")}개</strong><span>${esc(x.label || "")}</span></div>`;
        }).join("") || '<div class="dist-item"><strong>-</strong><span>분포 데이터 없음</span></div>'}
      </div>

      <div class="tables">
        <div class="table-card">
          <div class="table-title"><strong>지수보다 강한 종목 TOP 50</strong><span>상대강도 높은 순</span></div>
          <div class="table-wrap"><table>
            <thead><tr><th>티커</th><th>종목명</th><th>종목</th><th>지수</th><th>상대강도</th><th>시총</th><th>거래량</th></tr></thead>
            <tbody>${tableRows(block.strongest || [], benchmark)}</tbody>
          </table></div>
        </div>
        <div class="table-card">
          <div class="table-title"><strong>지수보다 약한 종목 TOP 50</strong><span>상대강도 낮은 순</span></div>
          <div class="table-wrap"><table>
            <thead><tr><th>티커</th><th>종목명</th><th>종목</th><th>지수</th><th>상대강도</th><th>시총</th><th>거래량</th></tr></thead>
            <tbody>${tableRows(block.weakest || [], benchmark)}</tbody>
          </table></div>
        </div>
      </div>

      <div class="source">
        <strong>데이터 상태:</strong> ${count.toLocaleString("ko-KR")}개 종목 계산. ${error ? "주의: " + esc(error) + " · " : ""}
        상대강도는 같은 세션의 상대수익률이며 향후 수익률 예측값이 아닙니다.
        ${(block.sources || []).length ? "<br><strong>출처:</strong> " + (block.sources || []).map(esc).join(" · ") : ""}
      </div>
    </article>`;
}

async function load() {
  const response = await fetch("data/상대강도.json", {cache: "no-store"});
  if (!response.ok) throw new Error("상대강도 데이터를 불러오지 못했습니다.");
  const data = await response.json();
  renderMarket("nasdaq", data.nasdaq, "NASDAQ Composite 대비 강·약 종목", "NASDAQ RELATIVE STRENGTH");
  renderMarket("kospi", data.kospi, "KOSPI 대비 강·약 종목", "KOSPI RELATIVE STRENGTH");
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