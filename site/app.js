const $ = (id) => document.getElementById(id);

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
