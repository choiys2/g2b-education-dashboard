#!/usr/bin/env python3
"""
나이스 개방포털 + 공공데이터포털(odcloud) -> live/neis_full_export.json

1) 17개 시도 x 초/중학교 학교 수, 공립비율 (나이스 학교기본정보 API)
2) AI교육 선도학교 지정 정보 전체 (odcloud API, 공공데이터포털 활용신청 승인 필요)
3) 선도학교에 나이스 학교기본정보(연락처/주소/홈페이지)와 학급수(학교 규모 대리지표)를 매칭

환경변수:
  NEIS_KEY      나이스 개방포털 일반 인증키
  ODCLOUD_KEY   공공데이터포털 일반 인증키(15091298 데이터셋 활용신청 승인된 계정의 키)
  (나라장터 서비스키와 같은 계정이면 보통 같은 값)
"""
import json, os, sys, time, urllib.request, urllib.parse

NEIS_KEY = os.environ.get("NEIS_KEY", "")
ODCLOUD_KEY = os.environ.get("ODCLOUD_KEY", NEIS_KEY)
NEIS_BASE = "https://open.neis.go.kr/hub"
LEADING_SCHOOL_URL = "https://api.odcloud.kr/api/15091298/v1/uddi:c6543d8e-b7f8-425b-b45f-f2297d871fa6"

REGIONS = [
    ("B10", "서울"), ("C10", "부산"), ("D10", "대구"), ("E10", "인천"), ("F10", "광주"),
    ("G10", "대전"), ("H10", "울산"), ("I10", "세종"), ("J10", "경기"), ("K10", "강원"),
    ("M10", "충북"), ("N10", "충남"), ("P10", "전북"), ("Q10", "전남"), ("R10", "경북"),
    ("S10", "경남"), ("T10", "제주"),
]
KIND_MAP = {"초": "초등학교", "중": "중학교", "고": "고등학교"}
STRENGTH = {"대구", "강원", "경북", "광주", "전북", "전남", "경기", "충남", "세종", "충북"}


def call_neis(op, params, retries=3):
    url = f"{NEIS_BASE}/{op}?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"[경고] NEIS 호출 실패 {op} {params}: {e}", file=sys.stderr)
                return None
            time.sleep(1)


def fetch_school_counts():
    rows = []
    for code, region in REGIONS:
        row = {"region": region, "office": f"{region} 교육청"}
        for grade, kind in KIND_MAP.items():
            if grade == "고":
                continue
            data = call_neis("schoolInfo", {"KEY": NEIS_KEY, "Type": "json", "pIndex": 1, "pSize": 1,
                                             "ATPT_OFCDC_SC_CODE": code, "SCHUL_KND_SC_NM": kind})
            cnt = data["schoolInfo"][0]["head"][0]["list_total_count"] if data and "schoolInfo" in data else 0
            pub = call_neis("schoolInfo", {"KEY": NEIS_KEY, "Type": "json", "pIndex": 1, "pSize": 1,
                                            "ATPT_OFCDC_SC_CODE": code, "SCHUL_KND_SC_NM": kind, "FOND_SC_NM": "공립"})
            pubcnt = pub["schoolInfo"][0]["head"][0]["list_total_count"] if pub and "schoolInfo" in pub else 0
            row["elem" if grade == "초" else "middle"] = cnt
            row["pub_elem" if grade == "초" else "pub_middle"] = pubcnt
            time.sleep(0.12)
        row["total"] = row.get("elem", 0) + row.get("middle", 0)
        row["public"] = row.get("pub_elem", 0) + row.get("pub_middle", 0)
        row["public_ratio"] = round(row["public"] / row["total"] * 100, 1) if row["total"] else 0
        row["strength"] = region in STRENGTH
        rows.append(row)
        print(f"  {region} 완료: 초{row.get('elem')} 중{row.get('middle')}", file=sys.stderr)
    return rows


def fetch_leading_schools():
    if not ODCLOUD_KEY:
        print("[경고] ODCLOUD_KEY 없음 - AI 선도학교 조회 건너뜀", file=sys.stderr)
        return []
    url = f"{LEADING_SCHOOL_URL}?" + urllib.parse.urlencode({"page": 1, "perPage": 1500, "serviceKey": ODCLOUD_KEY})
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", [])
    except Exception as e:
        print(f"[경고] AI 선도학교 조회 실패: {e}", file=sys.stderr)
        return []


def enrich_leading_schools(leading, days_budget_sec=480):
    """선도학교에 나이스 학교기본정보(연락처)와 학급수를 붙인다.
    시간이 오래 걸리므로(학교당 최대 2회 호출) days_budget_sec를 넘기면 남은 건은 스킵.
    """
    if not leading or not NEIS_KEY:
        return leading

    # 1) 지역 x 학교급 전체 목록을 한 번에 받아 학교명->상세정보 lookup 구성
    lookup = {}
    for code, region in REGIONS:
        for grade, kind in KIND_MAP.items():
            page = 1
            while True:
                data = call_neis("schoolInfo", {"KEY": NEIS_KEY, "Type": "json", "pIndex": page, "pSize": 1000,
                                                 "ATPT_OFCDC_SC_CODE": code, "SCHUL_KND_SC_NM": kind})
                if not data or "schoolInfo" not in data:
                    break
                rows_ = data["schoolInfo"][1]["row"]
                total = data["schoolInfo"][0]["head"][0]["list_total_count"]
                for r in rows_:
                    key = (region, grade, r.get("SCHUL_NM", ""))
                    lookup[key] = {
                        "code": r.get("SD_SCHUL_CODE"), "office_code": r.get("ATPT_OFCDC_SC_CODE"),
                        "tel": (r.get("ORG_TELNO") or "").strip(),
                        "addr": ((r.get("ORG_RDNMA") or "") + " " + (r.get("ORG_RDNDA") or "")).strip(),
                        "homepage": (r.get("HMPG_ADRES") or "").strip(),
                        "found_sc": r.get("FOND_SC_NM") or "",
                    }
                if page * 1000 >= total or not rows_:
                    break
                page += 1
            time.sleep(0.1)

    start = time.time()
    enriched = []
    for r in leading:
        row = dict(r)
        info = lookup.get((r.get("소속지역"), r.get("학교급"), r.get("학교명")))
        if info:
            row.update(info)
        if info and info.get("code") and time.time() - start < days_budget_sec:
            data = call_neis("classInfo", {"KEY": NEIS_KEY, "Type": "json", "pIndex": 1, "pSize": 1,
                                            "ATPT_OFCDC_SC_CODE": info["office_code"], "SD_SCHUL_CODE": info["code"],
                                            "AY": "2026"})
            row["class_count"] = data["classInfo"][0]["head"][0]["list_total_count"] if data and "classInfo" in data else None
            time.sleep(0.08)
        else:
            row["class_count"] = None
        enriched.append(row)
    return enriched


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "live/neis_full_export.json"
    print("[1/3] 시도별 학교 수 조회", file=sys.stderr)
    school_counts = fetch_school_counts()
    print("[2/3] AI 선도학교 명단 조회", file=sys.stderr)
    leading = fetch_leading_schools()
    print(f"  {len(leading)}건", file=sys.stderr)
    print("[3/3] 선도학교 연락처/학급수 매칭", file=sys.stderr)
    enriched = enrich_leading_schools(leading)

    result = {"school_counts": school_counts, "leading_schools": enriched}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
