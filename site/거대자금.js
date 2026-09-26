const $=(id)=>document.getElementById(id);
const esc=(v)=>String(v??"").replace(/[&<>"']/g,(m)=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
const jo=(v)=>{const n=Number(v||0)/10000;return (Math.abs(n)>=100?n.toFixed(1):n.toFixed(2))+"조원"};
const signedJo=(v)=>{const n=Number(v||0)/10000;return (n>0?"+":"")+(Math.abs(n)>=100?n.toFixed(1):n.toFixed(2))+"조"};
const pct=(v)=>{const n=Number(v||0);return (n>0?"+":"")+n.toFixed(2)+"%"};
const tone=(v)=>Number(v)>0?"flow-buy":Number(v)<0?"flow-sell":"flow-flat";
const empty=(t)=>'<div class="notice">'+esc(t)+'</div>';
const flowEok=(v)=>{const n=Number(v||0);return (n>0?"+":"")+Math.round(n).toLocaleString("ko-KR")+"억원"};
const sumFlow=(rows,key)=>rows.reduce((s,r)=>s+Number(((r.flows_krw_100m||{})[key])||0),0);

function metricCard(item){
  return '<article class="money-card"><span>'+esc(item.label)+'</span><strong>'+esc(jo(item.value_krw_100m))+'</strong><div class="delta '+(item.change_krw_100m>0?"up":item.change_krw_100m<0?"down":"")+'">'+esc(signedJo(item.change_krw_100m))+' · '+esc(pct(item.change_pct))+'</div><small>'+esc(item.reported_date)+' · 원자료 '+esc(item.reported_unit)+'</small></article>';
}
function metricRow(item){
  return '<div class="money-row"><div><strong>'+esc(item.label)+'</strong><small>'+esc(item.description||"")+'</small></div><span>'+esc(jo(item.value_krw_100m))+'</span><span class="'+tone(item.change_krw_100m)+'">'+esc(signedJo(item.change_krw_100m))+'</span><span class="'+tone(item.change_pct)+'">'+esc(pct(item.change_pct))+'</span></div>';
}

function renderMoney(money,state){
  const m=money.metrics||{};
  const hero=["investor_deposit","credit_financing","cma_balance","equity_fund_nav","total_fund_nav"].filter((k)=>m[k]).map((k)=>metricCard(m[k])).join("");
  $("money-summary").innerHTML=hero||empty("거대자금 통계가 없습니다.");
  const latestDates=Object.values(m).map((x)=>x.reported_date).filter(Boolean).sort().reverse();
  $("money-date").textContent=latestDates.length?"최신 기준일 "+latestDates[0]:"기준일 미확인";
  $("liquidity-table").innerHTML=["investor_deposit","cma_balance","credit_financing"].filter((k)=>m[k]).map((k)=>metricRow(m[k])).join("")||empty("대기자금 데이터 없음");
  $("fund-table").innerHTML=["equity_fund_nav","total_fund_nav"].filter((k)=>m[k]).map((k)=>metricRow(m[k])).join("")||empty("펀드 데이터 없음");

  const d=money.derived||{};
  $("money-ratios").innerHTML='<div class="ratio-card"><span>예탁금 대비 신용융자</span><strong>'+esc(Number(d.credit_to_deposit_pct||0).toFixed(2))+'%</strong><p>신용잔고가 예탁금 규모에 비해 얼마나 큰지 보는 보조비율입니다. 상승 자체가 곧 과열을 뜻하지는 않습니다.</p></div><div class="ratio-card"><span>전체 펀드 중 주식형 순자산 비중</span><strong>'+esc(Number(d.equity_fund_share_pct||0).toFixed(2))+'%</strong><p>펀드 전체 순자산에서 주식형이 차지하는 비중입니다. 가격 변동과 실제 순유입을 분리해서 해석해야 합니다.</p></div>';

  const rows=((state.market_recent_sessions||{}).korea||[]).slice(0,3);
  const actors=[["외국인","foreign"],["기관","institution"],["개인","individual"]];
  $("actor-summary").innerHTML=actors.map(([label,key])=>'<div class="flow-card"><span>'+label+' 3일 누적</span><strong class="'+tone(sumFlow(rows,key))+'">'+esc(flowEok(sumFlow(rows,key)))+'</strong><small>최근 실제 3거래일</small></div>').join("");
  $("actor-history").innerHTML=rows.length?'<div class="table-scroll"><table><thead><tr><th>날짜</th><th>외국인</th><th>기관</th><th>개인</th></tr></thead><tbody>'+rows.map((r)=>{const f=r.flows_krw_100m||{};return '<tr><td><strong>'+esc(r.date||"-")+'</strong></td><td class="'+tone(f.foreign)+'">'+esc(flowEok(f.foreign))+'</td><td class="'+tone(f.institution)+'">'+esc(flowEok(f.institution))+'</td><td class="'+tone(f.individual)+'">'+esc(flowEok(f.individual))+'</td></tr>'}).join("")+'</tbody></table></div>':empty("최근 수급 데이터가 없습니다.");

  const history=(money.history||[]).slice().reverse().slice(0,20);
  $("money-history").innerHTML=history.length?'<div class="table-scroll history-table"><table><thead><tr><th>관측</th><th>예탁금</th><th>신용융자</th><th>CMA</th><th>주식형펀드</th></tr></thead><tbody>'+history.map((h)=>{const x=h.metrics||{};return '<tr><td><strong>'+esc((h.observed_at||"").slice(0,10))+'</strong></td><td>'+esc(x.investor_deposit?jo(x.investor_deposit.value_krw_100m):"-")+'</td><td>'+esc(x.credit_financing?jo(x.credit_financing.value_krw_100m):"-")+'</td><td>'+esc(x.cma_balance?jo(x.cma_balance.value_krw_100m):"-")+'</td><td>'+esc(x.equity_fund_nav?jo(x.equity_fund_nav.value_krw_100m):"-")+'</td></tr>'}).join("")+'</tbody></table></div>':empty("관측 이력이 아직 없습니다.");

  $("money-extensions").innerHTML=(money.extensions||[]).map((x)=>'<div class="extension"><strong>'+esc(x.label)+'</strong><span>자동수집 미연결</span><p>'+esc(x.official_path||"")+'</p><p>'+esc(x.reason||"")+'</p></div>').join("")||empty("추가 연결 항목 없음");

  const dep=m.investor_deposit||{}, credit=m.credit_financing||{}, fund=m.equity_fund_nav||{};
  const foreign=sumFlow(rows,"foreign"), institution=sumFlow(rows,"institution");
  const interpretations=[];
  if(dep.change_krw_100m>0&&credit.change_krw_100m<=0) interpretations.push(["대기자금↑ · 신용↓","현금성 여력은 늘지만 레버리지 확대는 동반되지 않은 조합입니다. 실제 주식 유입 여부는 수급·거래대금으로 확인해야 합니다."]);
  else if(dep.change_krw_100m>0&&credit.change_krw_100m>0) interpretations.push(["예탁금↑ · 신용↑","시장 참여 여력과 레버리지 사용이 동시에 늘어난 조합입니다. 위험선호 확대 가능성이 있지만 단일 일간 변화로 과열을 단정하지 않습니다."]);
  else interpretations.push(["예탁금·신용 혼조","대기자금과 레버리지가 같은 방향이 아닙니다. 며칠 연속성과 예탁금 대비 신용 비율의 방향을 같이 봅니다."]);
  interpretations.push([fund.change_krw_100m>0?"주식형펀드 순자산↑":"주식형펀드 순자산↓","순자산 변화에는 실제 설정·환매뿐 아니라 보유주식 가격 변동이 섞입니다. 자금유출입 통계가 연결되면 이를 별도로 분리합니다."]);
  interpretations.push([(foreign>0&&institution>0)?"외국인·기관 3일 동반 순매수":(foreign<0&&institution<0)?"외국인·기관 3일 동반 순매도":"외국인·기관 방향 엇갈림","최근 실제 거래일 합산 수급입니다. 잔고 통계의 방향이 실제 현물 매수주체와 일치하는지 교차 확인합니다."]);
  $("money-reading").innerHTML=interpretations.map(([a,b])=>'<div class="mini-row"><strong>'+esc(a)+'</strong><span>'+esc(b)+'</span></div>').join("");

  const source=money.source||{};
  $("money-source").innerHTML='<div class="notice"><strong>'+esc(source.name||"출처 미확인")+'</strong><br>'+esc(source.note||"")+'<br>자동 수집 상태: '+esc(source.status||"-")+' · 지표별 기준일은 카드에 표시합니다.</div>';
  $("money-note").innerHTML='<div class="notice warn">주의: 예탁금·CMA·펀드 순자산은 서로 정의가 달라 단순 합산하지 않습니다. 주식형펀드 순자산 증감도 곧바로 순유입액으로 해석하지 않습니다.</div>';
  $("updated").textContent="거대자금 통계 갱신 "+(money.updated_at?new Date(money.updated_at).toLocaleString("ko-KR"):"미확인");
}
async function load(){
  const mr=await fetch("data/거대자금.json",{cache:"no-store"});
  const sr=await fetch("data/상태.json",{cache:"no-store"});
  if(!mr.ok||!sr.ok) throw new Error("거대자금 또는 시장 수급 데이터를 불러오지 못했습니다.");
  renderMoney(await mr.json(),await sr.json());
}
load().catch((error)=>document.body.insertAdjacentHTML("beforeend",'<div style="position:fixed;z-index:99;left:12px;right:12px;bottom:12px;padding:14px;background:#7f1d1d;color:#fff;border-radius:10px;font:12px/1.5 system-ui">거대자금 페이지 오류: '+esc(error.message)+'</div>'));
