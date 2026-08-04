"""
매크로 3대 지표(미 10년물 국채금리 / 원달러 환율 / WTI 유가)를
FRED 공식 REST API에서 가져와 macro.json으로 저장하는 스크립트.

* fredgraph.csv(차트용 export)는 CDN에 캐싱되어 며칠씩 오래된 값이
  섞여 나오는 문제가 있어, 캐시를 거치지 않는 공식 API를 사용합니다.
* API 키는 환경변수 FRED_API_KEY로 전달합니다 (GitHub Actions Secret).
  무료 발급: https://fredaccount.stlouisfed.org/apikeys

GitHub Actions에서 매일 자동 실행되며, 결과 파일(macro.json)을
raw.githubusercontent.com URL로 티스토리 위젯에서 읽어옵니다.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED 시리즈 ID
# DGS10      : 미국 10년물 국채수익률 (%, 일별)
# DEXKOUS    : 원/달러 환율 (KRW per USD, 일별)
# DCOILWTICO : WTI 현물유가 (달러/배럴, 일별)
SERIES = {
    "us10y": {"series": "DGS10", "name": "미국 10년물 국채금리", "kind": "yield"},
    "usdkrw": {"series": "DEXKOUS", "name": "원/달러 환율", "kind": "price_krw"},
    "wti": {"series": "DCOILWTICO", "name": "WTI 국제유가", "kind": "price_usd"},
}


def fetch_last_two_values(series: str, api_key: str, retries: int = 3, delay: int = 5):
    """FRED 공식 API에서 결측치(".")를 건너뛰고 최근 유효값 2개를
    (날짜, 값) 튜플로 반환. 끝까지 실패하면 None, None."""
    params = {
        "series_id": series,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10,
    }
    for attempt in range(retries):
        try:
            resp = requests.get(FRED_API_URL, params=params, timeout=15)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            valid = [
                (o["date"], float(o["value"]))
                for o in obs
                if o.get("value") not in (None, "", ".")
            ]
            if len(valid) >= 2:
                # sort_order=desc이므로 valid[0]이 최신, valid[1]이 그 직전
                return valid[0], valid[1]
        except Exception as e:
            print(f"[warn] {series} fetch attempt {attempt + 1} failed: {e}", file=sys.stderr)
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


def build_indicator(key: str, meta: dict, api_key: str) -> dict:
    last, prev = fetch_last_two_values(meta["series"], api_key)

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
        "as_of": last_date,
        "stale": False,
    }


def main():
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("[error] 환경변수 FRED_API_KEY가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    indicators = [build_indicator(k, v, api_key) for k, v in SERIES.items()]

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
