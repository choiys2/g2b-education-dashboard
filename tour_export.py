#!/usr/bin/env python3
"""
한국관광공사 국문 관광정보(공공데이터포털 B551011/KorService2) - 17개 시도 숙박·연수시설 위치(집합연수 장소 섭외용).

- 숙박: areaBasedList2 contentTypeId=32 (시도별 상위 30곳, 대표이미지 있는 곳 우선)
- 연수·회의 시설: searchKeyword2 키워드(연수원·교육원·컨벤션·리조트 세미나) 시도별
- 키: TOUR_API_KEY(있으면) → 공공데이터포털 계정 공용 키 G2B_SERVICE_KEY
- 결과는 자주 바뀌지 않으므로 history/tour_venues.json 에 보관(git 추적)하고, 수집이 실패하면 이전 결과를 그대로 쓴다.
  python tour_export.py [out_json]
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

BASE = "https://apis.data.go.kr/B551011/KorService2"
KST = timezone(timedelta(hours=9))
HERE = Path(__file__).parent
CACHE = HERE / "history" / "tour_venues.json"
# (시도, 관광공사 areaCode, 법정동 시도코드 lDongRegnCd)
SIDO = [("서울", 1, 11), ("부산", 6, 26), ("대구", 4, 27), ("인천", 2, 28), ("광주", 5, 29), ("대전", 3, 30),
        ("울산", 7, 31), ("세종", 8, 36), ("경기", 31, 41), ("강원", 32, 51), ("충북", 33, 43), ("충남", 34, 44),
        ("전북", 37, 52), ("전남", 38, 46), ("경북", 35, 47), ("경남", 36, 48), ("제주", 39, 50)]
KEYWORDS = ["연수원", "교육원", "컨벤션", "수련원"]
SKIP_TITLE = ("모텔", "펜션", "게스트하우스", "민박", "캠핑", "글램핑", "카라반", "하우스")


def call(key, op, **q):
    q = {"serviceKey": key, "MobileOS": "ETC", "MobileApp": "g2bEduDashboard", "_type": "json", "pageNo": 1, **q}
    with urlopen(f"{BASE}/{op}?{urlencode(q)}", timeout=25) as r:
        raw = r.read().decode("utf-8")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(raw[:160].replace("\n", " "))
    hdr = d.get("response", {}).get("header", {})
    if hdr.get("resultCode") not in ("0000", "00"):
        raise RuntimeError(f"{hdr.get('resultCode')} {hdr.get('resultMsg')}")
    items = (d["response"].get("body", {}).get("items") or {})
    items = items.get("item", []) if isinstance(items, dict) else []
    return items if isinstance(items, list) else [items]


def slim(it, kind):
    return {"n": it.get("title", ""), "k": kind, "addr": " ".join(x for x in (it.get("addr1"), it.get("addr2")) if x).strip(),
            "tel": it.get("tel", ""), "x": it.get("mapx"), "y": it.get("mapy"), "img": it.get("firstimage2") or it.get("firstimage") or "",
            "id": it.get("contentid")}


def area_q(code, ldong, use_ldong):
    return {"lDongRegnCd": ldong} if use_ldong else {"areaCode": code}


def collect(key):
    out, errors, use_ldong = {}, [], False
    for name, code, ldong in SIDO:
        rows, seen = [], set()
        try:
            hotels = call(key, "areaBasedList2", numOfRows=40, arrange="Q", contentTypeId=32, **area_q(code, ldong, use_ldong))
            if not hotels and not use_ldong:  # 지역코드 체계가 법정동 코드로만 동작하는 경우 대비
                use_ldong = True
                hotels = call(key, "areaBasedList2", numOfRows=40, arrange="Q", contentTypeId=32, **area_q(code, ldong, True))
        except Exception as e:
            errors.append(f"{name} 숙박: {str(e)[:120]}")
            hotels = []
        for it in hotels:
            if it.get("contentid") in seen or any(w in it.get("title", "") for w in SKIP_TITLE):
                continue
            seen.add(it.get("contentid"))
            rows.append(slim(it, "숙박"))
            if len([r for r in rows if r["k"] == "숙박"]) >= 30:
                break
        time.sleep(0.15)
        for kw in KEYWORDS:
            try:
                found = call(key, "searchKeyword2", numOfRows=30, arrange="Q", keyword=kw, **area_q(code, ldong, use_ldong))
            except Exception as e:
                errors.append(f"{name} {kw}: {str(e)[:120]}")
                found = []
            for it in found:
                if it.get("contentid") in seen:
                    continue
                seen.add(it.get("contentid"))
                rows.append(slim(it, "연수·회의"))
            time.sleep(0.15)
        out[name] = rows
    return out, errors


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/tour_venues.json")
    key = os.environ.get("TOUR_API_KEY") or os.environ.get("G2B_SERVICE_KEY")
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    prev = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else None
    data = None
    if key:
        regions, errors = collect(key)
        n = sum(len(v) for v in regions.values())
        print(f"tour: {n}곳 ({len(regions)}개 시도), 오류 {len(errors)}건 {errors[:3]}")
        (HERE / "history" / "tour_status.json").write_text(json.dumps(
            {"at": now, "places": n, "by_region": {k: len(v) for k, v in regions.items()}, "errors": errors[:10]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        if n:
            data = {"generated": now, "source": "한국관광공사 국문 관광정보 서비스(공공데이터포털)", "regions": regions,
                    "errors": errors[:20]}
            CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        elif prev:
            prev["errors"] = errors[:20]
    else:
        print("[경고] 공공데이터포털 키 없음 - 관광정보 건너뜀", file=sys.stderr)
    data = data or prev or {"generated": now, "regions": {}, "errors": ["아직 수집 전"]}
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
