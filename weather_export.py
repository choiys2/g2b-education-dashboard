#!/usr/bin/env python3
"""
기상청 단기예보(공공데이터포털 VilageFcstInfoService_2.0) - 주요 도시 오늘·내일 날씨(출장·행사 참고용).

인증키는 공공데이터포털 계정 공용 키(G2B_SERVICE_KEY)를 그대로 쓴다.
매일 02시 발표분(base_time=0200)을 받으면 그날과 다음 날의 최저·최고기온(TMN/TMX)이 모두 들어 있다.
  python weather_export.py [out_json]
"""
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = timezone(timedelta(hours=9))
# 기상청 격자(nx, ny) - 시도청 소재지 기준
CITIES = [("서울", 60, 127), ("인천", 55, 124), ("수원", 60, 121), ("춘천", 73, 134), ("청주", 69, 106),
          ("세종", 66, 103), ("대전", 67, 100), ("전주", 63, 89), ("광주", 58, 74), ("대구", 89, 90),
          ("부산", 98, 76), ("울산", 102, 84), ("창원", 90, 77), ("안동", 91, 106), ("홍성", 55, 106), ("제주", 52, 38)]
SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY = {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기", "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림"}
ICON = {"맑음": "☀️", "구름많음": "⛅", "흐림": "☁️", "비": "🌧", "비/눈": "🌨", "눈": "❄️", "소나기": "🌦"}


def fetch(key, nx, ny, base_date):
    q = {"serviceKey": key, "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
         "base_date": base_date, "base_time": "0200", "nx": nx, "ny": ny}
    with urlopen(f"{URL}?{urlencode(q)}", timeout=20) as r:
        d = json.loads(r.read().decode("utf-8"))
    hdr = d["response"]["header"]
    if hdr.get("resultCode") != "00":
        raise RuntimeError(hdr.get("resultMsg"))
    return d["response"]["body"]["items"]["item"]


def summarize(items, day):
    by = defaultdict(dict)
    for it in items:
        if it["fcstDate"] == day:
            by[it["category"]][it["fcstTime"]] = it["fcstValue"]
    if not by:
        return None
    day_hours = [h for h in by.get("SKY", {}) if "0900" <= h <= "1800"]
    sky = Counter(SKY.get(by["SKY"][h], "") for h in day_hours).most_common(1)
    rain = [PTY[v] for h, v in by.get("PTY", {}).items() if v != "0" and "0600" <= h <= "2100" and v in PTY]
    cond = Counter(rain).most_common(1)[0][0] if rain else (sky[0][0] if sky else "")
    pop = max([int(v) for v in by.get("POP", {}).values()] or [0])
    tmn = next(iter(by.get("TMN", {}).values()), None)
    tmx = next(iter(by.get("TMX", {}).values()), None)
    return {"cond": cond, "icon": ICON.get(cond, ""), "pop": pop,
            "tmin": round(float(tmn)) if tmn else None, "tmax": round(float(tmx)) if tmx else None}


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/weather.json")
    key = os.environ.get("G2B_SERVICE_KEY") or os.environ.get("DATA_GO_KR_KEY")
    if not key:
        print("[경고] 공공데이터포털 키 없음 - 날씨 건너뜀", file=sys.stderr)
        return
    now = datetime.now(KST)
    base = now if now.hour >= 3 else now - timedelta(days=1)  # 02시 발표분은 02:10 이후 제공
    bd = base.strftime("%Y%m%d")
    today, tomorrow = now.strftime("%Y%m%d"), (now + timedelta(days=1)).strftime("%Y%m%d")
    d2 = (now + timedelta(days=2)).strftime("%Y%m%d")  # 모레 - 집합연수 운영 지원(ops_insights.py)용
    cities, errors = [], []
    for name, nx, ny in CITIES:
        try:
            items = fetch(key, nx, ny, bd)
            cities.append({"city": name, "today": summarize(items, today), "tomorrow": summarize(items, tomorrow),
                           "d2": summarize(items, d2)})
        except Exception as e:
            errors.append(f"{name}: {str(e)[:120]}")
        time.sleep(0.1)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated": now.strftime("%Y-%m-%d %H:%M"), "base": f"{bd[4:6]}/{bd[6:]} 02시 발표",
                               "dates": [today, tomorrow, d2], "cities": cities, "errors": errors}, ensure_ascii=False), encoding="utf-8")
    print(f"weather: {len(cities)}개 도시, 오류 {len(errors)}건 {errors[:2]}")


if __name__ == "__main__":
    main()
