"""
매크로 3대 지표(미 10년물 국채금리 / 원달러 환율 / WTI 유가)를 가져와
macro.json 파일로 저장하는 스크립트.

GitHub Actions에서 매일 자동 실행되며, 결과 파일(macro.json)을
raw.githubusercontent.com URL로 티스토리 위젯에서 읽어옵니다.
"""

import json
from datetime import datetime, timezone, timedelta

import yfinance as yf

KST = timezone(timedelta(hours=9))

# 야후 파이낸스 티커
# ^TNX : 미국 10년물 국채금리 (표시값의 1/10이 실제 % 수익률, 예: 42.85 -> 4.285%)
# KRW=X : 원/달러 환율 (USD 1달러당 원화)
# CL=F  : WTI 원유 선물 (배럴당 달러)
TICKERS = {
    "us10y": {"symbol": "^TNX", "name": "미국 10년물 국채금리", "kind": "yield"},
    "usdkrw": {"symbol": "KRW=X", "name": "원/달러 환율", "kind": "price"},
    "wti": {"symbol": "CL=F", "name": "WTI 국제유가", "kind": "price"},
}


def fetch_last_two_closes(symbol: str):
    """최근 종가와 그 직전 종가를 반환. 데이터가 부족하면 None, None."""
    hist = yf.Ticker(symbol).history(period="10d")
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None, None
    return float(closes.iloc[-1]), float(closes.iloc[-2])


def build_indicator(key: str, meta: dict) -> dict:
    last, prev = fetch_last_two_closes(meta["symbol"])

    if last is None:
        return {
            "key": key,
            "name": meta["name"],
            "value": "N/A",
            "change": "N/A",
            "direction": "flat",
        }

    if meta["kind"] == "yield":
        # ^TNX는 실제 수익률의 10배로 표시됨
        yield_now = last / 10
        yield_prev = prev / 10
        diff_bp = round((yield_now - yield_prev) * 100)  # basis point
        direction = "up" if diff_bp > 0 else ("down" if diff_bp < 0 else "flat")
        return {
            "key": key,
            "name": meta["name"],
            "value": f"{yield_now:.2f}%",
            "change": f"{'+' if diff_bp >= 0 else ''}{diff_bp}bp",
            "direction": direction,
        }
    else:
        diff = last - prev
        pct = (diff / prev) * 100 if prev else 0
        direction = "up" if diff > 0 else ("down" if diff < 0 else "flat")
        # 원/달러는 소수점 1자리, 유가는 소수점 2자리
        if key == "usdkrw":
            value_str = f"{last:,.1f}원"
            change_str = f"{'+' if diff >= 0 else ''}{diff:,.1f} ({pct:+.2f}%)"
        else:
            value_str = f"${last:,.2f}"
            change_str = f"{'+' if diff >= 0 else ''}{diff:,.2f} ({pct:+.2f}%)"
        return {
            "key": key,
            "name": meta["name"],
            "value": value_str,
            "change": change_str,
            "direction": direction,
        }


def main():
    indicators = [build_indicator(k, v) for k, v in TICKERS.items()]

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
