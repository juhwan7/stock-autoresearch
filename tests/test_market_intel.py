from datetime import datetime, timedelta, timezone

from autoresearch.kiwoom_source import KiwoomSource
from autoresearch.market_intel import in_krx_intraday


KST = timezone(timedelta(hours=9))


def test_market_collection_window():
    assert in_krx_intraday(datetime(2026, 9, 25, 10, 0, tzinfo=KST))
    assert not in_krx_intraday(datetime(2026, 9, 25, 8, 59, tzinfo=KST))
    assert not in_krx_intraday(datetime(2026, 9, 26, 10, 0, tzinfo=KST))


def test_kiwoom_minute_normalization_marks_estimated_amount():
    rows = KiwoomSource.normalize_minute_rows(
        [
            {
                "cntr_tm": "20260925143000",
                "cur_prc": "+10000",
                "open_pric": "+9900",
                "high_pric": "+10100",
                "low_pric": "+9800",
                "trde_qty": "100",
            }
        ]
    )
    assert rows[0]["amount"] == 1_000_000
    assert rows[0]["amount_estimated"] is True
