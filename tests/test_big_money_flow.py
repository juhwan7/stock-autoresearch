from datetime import date

from autoresearch.big_money_flow import build_payload, parse_kofia_main


SAMPLE = """
<html><body>
<div>투자자예탁금</div><div>백만원 | 09/22</div><div>100,982,555 2,843,942 2.9%</div>
<div>신용융자</div><div>백만원 | 09/22</div><div>32,819,168 -236,317 -0.71%</div>
<div>CMA잔고</div><div>백만원 | 09/22</div><div>105,635,781 2,564,136 2.49%</div>
<div>주식형펀드 순자산</div><div>억원 | 09/22</div><div>3,921,769 14,692 0.38%</div>
<div>펀드 순자산</div><div>억원 | 09/22</div><div>15,608,006 -19,168 -0.12%</div>
</body></html>
"""


def test_parse_kofia_main_normalizes_units():
    metrics = parse_kofia_main(SAMPLE, today=date(2026, 9, 26))
    assert metrics["investor_deposit"]["reported_date"] == "2026-09-22"
    assert metrics["investor_deposit"]["value_krw_100m"] == 1009825.55
    assert metrics["credit_financing"]["change_krw_100m"] == -2363.17
    assert metrics["equity_fund_nav"]["value_krw_100m"] == 3921769.0
    assert metrics["total_fund_nav"]["value_krw_100m"] == 15608006.0


def test_build_payload_derives_ratios_and_history():
    metrics = parse_kofia_main(SAMPLE, today=date(2026, 9, 26))
    payload = build_payload(metrics, collected_at="2026-09-26T05:45:00+00:00")
    assert payload["derived"]["credit_to_deposit_pct"] == 32.5
    assert payload["derived"]["equity_fund_share_pct"] == 25.13
    assert len(payload["history"]) == 1
    assert payload["extensions"][0]["status"] == "adapter_pending"
