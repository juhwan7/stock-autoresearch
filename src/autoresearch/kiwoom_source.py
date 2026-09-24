from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


class KiwoomAPIError(RuntimeError):
    pass


class KiwoomSource:
    """키움 REST API의 읽기 전용 시장 데이터 어댑터.

    주문 API는 의도적으로 구현하지 않는다.
    """

    base_url = "https://api.kiwoom.com"

    def __init__(self, app_key: str | None = None, secret_key: str | None = None):
        self.app_key = app_key or os.getenv("KIWOOM_APP_KEY")
        self.secret_key = secret_key or os.getenv("KIWOOM_SECRET_KEY")
        if not self.app_key or not self.secret_key:
            raise KiwoomAPIError("KIWOOM_APP_KEY / KIWOOM_SECRET_KEY가 필요합니다.")
        self._token: str | None = None

    def _request(
        self,
        path: str,
        body: dict[str, Any],
        *,
        api_id: str | None = None,
        token: bool = True,
        cont_yn: str | None = None,
        next_key: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if token:
            headers["authorization"] = "Bearer " + self.access_token()
        if api_id:
            headers["api-id"] = api_id
        if cont_yn:
            headers["cont-yn"] = cont_yn
        if next_key:
            headers["next-key"] = next_key

        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                response_headers = {k.lower(): v for k, v in response.headers.items()}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise KiwoomAPIError(str(exc)) from exc

        if payload.get("return_code") not in (None, 0):
            raise KiwoomAPIError(
                f"{api_id or path}: {payload.get('return_code')} {payload.get('return_msg')}"
            )
        return payload, response_headers

    def access_token(self) -> str:
        if self._token:
            return self._token
        payload, _ = self._request(
            "/oauth2/token",
            {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.secret_key,
            },
            token=False,
        )
        token = payload.get("token")
        if not token:
            raise KiwoomAPIError("접근토큰이 응답에 없습니다.")
        self._token = str(token)
        return self._token


    def market_index_summary(
        self,
        market_type: str,
        index_code: str,
    ) -> dict[str, Any]:
        """업종현재가(ka20001)의 종합지수 요약.

        KOSPI: market_type=0, index_code=001
        KOSDAQ: market_type=1, index_code=101

        상승/보합/하락 종목 수와 시장 거래대금을 함께 사용한다.
        """
        payload, _ = self._request(
            "/api/dostk/sect",
            {
                "mrkt_tp": market_type,
                "inds_cd": index_code,
            },
            api_id="ka20001",
        )
        keys = (
            "cur_prc",
            "pred_pre_sig",
            "pred_pre",
            "flu_rt",
            "trde_qty",
            "trde_prica",
            "trde_frmatn_stk_num",
            "trde_frmatn_rt",
            "open_pric",
            "high_pric",
            "low_pric",
            "upl",
            "rising",
            "stdns",
            "fall",
            "lst",
        )
        return {key: payload.get(key) for key in keys}

    def stock_list(
        self,
        market_type: str,
        *,
        max_pages: int = 10,
        request_delay: float = 0.2,
    ) -> list[dict[str, Any]]:
        """종목정보 리스트(ka10099).

        market_type: 0=코스피, 10=코스닥.
        상장일(regDay), 업종명(upName)을 신규주/업종 분석에 사용한다.
        """
        rows: list[dict[str, Any]] = []
        cont_yn = None
        next_key = None
        for page in range(max_pages):
            payload, headers = self._request(
                "/api/dostk/stkinfo",
                {"mrkt_tp": market_type},
                api_id="ka10099",
                cont_yn=cont_yn,
                next_key=next_key,
            )
            batch = payload.get("list", [])
            if isinstance(batch, list):
                rows.extend(x for x in batch if isinstance(x, dict))
            cont_yn = headers.get("cont-yn")
            next_key = headers.get("next-key")
            if cont_yn != "Y" or not next_key:
                break
            if page + 1 < max_pages:
                time.sleep(request_delay)
        return rows

    def trading_value_top(self, *, limit: int = 30) -> list[dict[str, Any]]:
        payload, _ = self._request(
            "/api/dostk/rkinfo",
            {
                "mrkt_tp": "000",
                "mang_stk_incls": "0",
                "stex_tp": "1",
            },
            api_id="ka10032",
        )
        rows = payload.get("trde_prica_upper", [])
        if not isinstance(rows, list):
            return []
        return [x for x in rows if isinstance(x, dict)][:limit]

    def daily_chart(
        self,
        ticker: str,
        *,
        base_date: str,
        max_pages: int = 1,
        request_delay: float = 0.2,
    ) -> list[dict[str, Any]]:
        """주식일봉차트조회(ka10081).

        수정주가를 적용하고 일자·OHLC·거래량·거래대금을 반환한다.
        """
        body = {
            "stk_cd": ticker,
            "base_dt": base_date,
            "upd_stkpc_tp": "1",
        }
        rows: list[dict[str, Any]] = []
        cont_yn = None
        next_key = None
        for page in range(max_pages):
            payload, headers = self._request(
                "/api/dostk/chart",
                body,
                api_id="ka10081",
                cont_yn=cont_yn,
                next_key=next_key,
            )
            batch = payload.get("stk_dt_pole_chart_qry", [])
            if isinstance(batch, list):
                rows.extend(x for x in batch if isinstance(x, dict))
            cont_yn = headers.get("cont-yn")
            next_key = headers.get("next-key")
            if cont_yn != "Y" or not next_key:
                break
            if page + 1 < max_pages:
                time.sleep(request_delay)
        return rows

    @staticmethod
    def normalize_daily_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            dt = str(row.get("dt") or "")
            close = str(row.get("cur_prc") or "").lstrip("+-")
            result.append(
                {
                    "date": dt,
                    "open": str(row.get("open_pric") or "").lstrip("+-"),
                    "high": str(row.get("high_pric") or "").lstrip("+-"),
                    "low": str(row.get("low_pric") or "").lstrip("+-"),
                    "close": close,
                    "volume": str(row.get("trde_qty") or "").lstrip("+-"),
                    "amount": str(row.get("trde_prica") or "").lstrip("+-"),
                    "turnover_rate": str(row.get("trde_tern_rt") or "").lstrip("+-"),
                }
            )
        result.sort(key=lambda x: str(x.get("date") or ""))
        return result

    def minute_chart(
        self,
        ticker: str,
        *,
        base_date: str | None = None,
        max_pages: int = 2,
        request_delay: float = 0.2,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "stk_cd": ticker,
            "tic_scope": "1",
            "upd_stkpc_tp": "1",
        }
        if base_date:
            body["base_dt"] = base_date

        rows: list[dict[str, Any]] = []
        cont_yn = None
        next_key = None
        for page in range(max_pages):
            payload, headers = self._request(
                "/api/dostk/chart",
                body,
                api_id="ka10080",
                cont_yn=cont_yn,
                next_key=next_key,
            )
            batch = payload.get("stk_min_pole_chart_qry", [])
            if isinstance(batch, list):
                rows.extend(x for x in batch if isinstance(x, dict))

            cont_yn = headers.get("cont-yn")
            next_key = headers.get("next-key")
            if cont_yn != "Y" or not next_key:
                break
            if page + 1 < max_pages:
                time.sleep(request_delay)

        return rows

    @staticmethod
    def normalize_minute_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            close = str(row.get("cur_prc") or "").lstrip("+-")
            volume = str(row.get("trde_qty") or "").lstrip("+-")
            # ka10080은 분봉 OHLC/거래량을 제공한다. 분 거래대금은 종가×거래량으로
            # 근사하고 amount_estimated 플래그를 남긴다.
            try:
                estimated_amount = float(close or 0) * float(volume or 0)
            except ValueError:
                estimated_amount = 0.0
            result.append(
                {
                    "time": row.get("cntr_tm"),
                    "open": str(row.get("open_pric") or "").lstrip("+-"),
                    "high": str(row.get("high_pric") or "").lstrip("+-"),
                    "low": str(row.get("low_pric") or "").lstrip("+-"),
                    "close": close,
                    "volume": volume,
                    "amount": estimated_amount,
                    "amount_estimated": True,
                }
            )
        return result
