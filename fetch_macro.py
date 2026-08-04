"""
매크로 3대 지표(미 10년물 국채금리 / 원달러 환율 / WTI 유가)를
FRED(세인트루이스 연방준비은행 공식 통계)에서 가져와 macro.json으로 저장하는 스크립트.

야후 파이낸스 대신 FRED를 쓰는 이유:
- 10년물 금리(^TNX)는 야후에서 가끔 배율(x10) 없이 값이 내려와 오작동하는 경우가 있음
- WTI 선물(CL=F)은 월물 롤오버 시점에 실제 가격변동과 무관하게 몇 % 급변하는 문제가 있음
FRED는 두 문제 모두 없는 공식 일별 통계치를 제공함 (단, 발표가 하루 정도 지연될 수 있음).

GitHub Actions에서 매일 자동 실행되며, 결과 파일(macro.json)을
raw.githubusercontent.com URL로 티스토리 위젯에서 읽어옵니다.
"""

import csv
import io
import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

# FRED 시리즈 ID
# DGS10      : 미국 10년물 국채수익률 (%, 일별)
# DEXKOUS    : 원/달러 환율 (KRW per USD, 일별)
# DCOILWTICO : WTI 현물유가 (달러/배럴, 일별)
SERIES = {
    "us10y": {"series": "DGS10", "name": "미국 10년물 국채금리", "kind": "yield"},
    "usdkrw": {"series": "DEXKOUS", "name": "원/달러 환율", "kind": "price_krw"},
    "wti": {"series": "DCOILWTICO", "name": "WTI 국제유가", "kind": "price_usd"},
}


def fetch_last_two_values(series: str, retries: int = 3, delay: int = 5):
    """FRED CSV에서 결측치(".")를 건너뛰고 최근 유효값 2개를 (날짜, 값) 튜플로 반환.
    끝까지 실패하면 None, None."""
    url = FRED_CSV_URL.format(series=series)
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            reader = csv.reader(io.StringIO(resp.text))
            rows = list(reader)
            valid = [
                (r[0], float(r[1]))
                for r in rows[1:]
                if len(r) == 2 and r[1] not in ("", ".")
            ]
            if len(valid) >= 2:
                return valid[-1], valid[-2]
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(delay)
    return None, None


def load_previous_indicator(key: str):
    """직전 실행에서 저장된 macro.json에서 해당 지표의 값을 가져옴."""
    if not os.path.exists("macro.json"):
        return None
    try:
        with open("macro.json", "r", encoding="utf-8") as f:
            old = json.load(f)
        for ind in old.get("indicators", []):
            if ind.get("key") == key:
                return ind
    except Exception:
        return None
    return None


def build_indicator(key: str, meta: dict) -> dict:
    last, prev = fetch_last_two_values(meta["series"])

    if last is None:
        old = load_previous_indicator(key)
        if old is not None:
            carried = dict(old)
            carried["stale"] = True
            return carried
        return {
            "key": key,
            "name": meta["name"],
            "value": "N/A",
            "change": "N/A",
            "direction": "flat",
            "stale": True,
        }

    last_date, last_val = last
    _, prev_val = prev
    diff = last_val - prev_val

    if meta["kind"] == "yield":
        diff_bp = round(diff * 100)
        direction = "up" if diff_bp > 0 else ("down" if diff_bp < 0 else "flat")
        value_str = f"{last_val:.2f}%"
        change_str = f"{'+' if diff_bp >= 0 else ''}{diff_bp}bp"
    else:
        pct = (diff / prev_val) * 100 if prev_val else 0
        direction = "up" if diff > 0 else ("down" if diff < 0 else "flat")
        if meta["kind"] == "price_krw":
            value_str = f"{last_val:,.1f}원"
        else:
            value_str = f"${last_val:,.2f}"
        change_str = f"{'+' if diff >= 0 else ''}{diff:,.2f} ({pct:+.2f}%)"

    return {
        "key": key,
        "name": meta["name"],
        "value": value_str,
        "change": change_str,
        "direction": direction,
        "as_of": last_date,   # 실제 데이터 기준일 (FRED 발표 기준)
        "stale": False,
    }


def main():
    indicators = [build_indicator(k, v) for k, v in SERIES.items()]

    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST)

    data = {
        "updated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "updated_at_kst": now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "indicators": indicators,
    }

    with open("macro.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
