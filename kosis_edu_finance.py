#!/usr/bin/env python3
"""
KOSIS(국가통계포털) 지자체 기본통계 - 시도교육청 "교육비특별회계 세출결산"(지출액) 조회.

실측(2026-08-02)으로 확인된 사항:
  - KOSIS Open API는 objL1(분류)을 빈 문자열이 아니라 반드시 "ALL"로 명시해야 한다.
    빈 문자열은 "누락"으로 취급돼 err20이 난다.
  - 이 통계표는 시도마다 완전히 다른 세대의 테이블로 등록돼 있다. 서울은 최신
    표준 스키마(분류값1/분류값2 2단계, 최근 연도까지 갱신)지만, 나머지 지역은
    "e지방지표"의 옛 스키마(항목ID가 통짜 코드 하나)이고 대부분 2018~2023년
    어딘가에서 갱신이 멈춰 있다(충남은 2009년까지만 - 그마저도 있는 게 다행).
    그래서 지역별로 "최신 확보 가능 연도"가 다르며, 이 스크립트는 그 연도를
    그대로 노출한다(억지로 맞추지 않음 - 대시보드에 지역별 기준연도를 함께 표시).
  - "전남광주통합특별시교육청"은 나라장터 발주기관명에서는 하나로 합쳐 보이지만,
    KOSIS 지자체 기본통계 트리에서는 여전히 "광주광역시"(orgId=205)와
    "전라남도"(orgId=215)로 분리돼 있다. 대시보드의 REGIONS 목록도 광주/전남을
    별도 17개 지역으로 다루므로, 여기서도 합치지 않고 그대로 둘로 나눠 조회한다.
  - 강원은 이 표에 "지출액"(결산 실제 지출) 행 자체가 전부 공란(-)이라, 부득이
    "예산액①"(당초 예산, 결산 아님)으로 대체했다 - 다른 지역과 성격이 다르므로
    이 역시 대시보드에 명시한다.

사용법: python kosis_edu_finance.py <KOSIS_KEY> [출력경로]
"""
import json
import sys

TABLES = {
    "서울": ("201", "DT_201004_O140014_02"), "부산": ("202", "DT_202N_BSY141301"),
    "대구": ("203", "DT_N47001"), "인천": ("204", "DT_20402_N000006"),
    "광주": ("205", "DT_20503_N001017"),
    "대전": ("206", "DT_20603_N001017"), "울산": ("207", "DT_2071O20"),
    "세종": ("208", "DT_20802N_258"),
    "경기": ("210", "DT_21002_N012"), "강원": ("211", "DT_211002_N002"),
    "충북": ("212", "DT_Y31"), "충남": ("213", "DT_213N_CN15012"),
    "전북": ("214", "DT_214N_Z01689"), "전남": ("215", "DT_N040"),
    "경북": ("216", "DT_21603_N001017"),
    "경남": ("217", "DT_217003N_N013"), "제주": ("218", "DT_21802_N001017"),
}

# 강원은 "지출액" 행이 전부 공란이라 예산액①로 대체 - 그 사실을 데이터에도 남긴다.
MEASURE_OVERRIDE = {"강원": "예산①"}

UNIT_TO_WON = {"백만원": 1_000_000, "천원": 1_000, "원": 1}


def to_num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_region(api, name, org, tbl):
    from_measure = MEASURE_OVERRIDE.get(name, "지출액")
    attempts = [
        dict(itmId="ALL", objL1="ALL", objL2="ALL", prdSe="Y", startPrdDe="2015", endPrdDe="2026"),
        dict(itmId="ALL", objL1="ALL", prdSe="Y", startPrdDe="2015", endPrdDe="2026"),
        dict(itmId="ALL", objL1="ALL", prdSe="Y", startPrdDe="2005", endPrdDe="2020"),
    ]
    df = None
    for kw in attempts:
        try:
            d = api.get_data("통계자료", orgId=org, tblId=tbl, **kw)
        except Exception:
            d = None
        if d is not None and len(d) > 0:
            df = d
            break
    if df is None:
        return None

    name_col = "분류값명2" if "분류값명2" in df.columns else "항목명"
    cat_col = "분류값명1" if "분류값명1" in df.columns else "항목명"
    unit_col = "단위명" if "단위명" in df.columns else None

    measure_rows = df[df[name_col].astype(str) == from_measure]
    if len(measure_rows) == 0:
        measure_rows = df[df[name_col].astype(str).str.contains(from_measure, na=False)]
    if len(measure_rows) == 0:
        return None

    for year in sorted(measure_rows["수록시점"].astype(str).unique(), reverse=True):
        year_rows = measure_rows[measure_rows["수록시점"].astype(str) == year]
        total_rows = year_rows[year_rows[cat_col].astype(str).str.contains("합계|계$", na=False, regex=True)]
        if len(total_rows) == 0:
            total_rows = year_rows
        for _, row in total_rows.iterrows():
            val = to_num(row["수치값"])
            if val:
                unit = str(row[unit_col]) if unit_col else "원"
                won = round(val * UNIT_TO_WON.get(unit, 1))
                return {
                    "region": name, "org_id": org, "tbl_id": tbl, "reference_year": year,
                    "measure": from_measure, "amount_won": won,
                }
    return None


def main():
    if len(sys.argv) < 2:
        print("사용법: python kosis_edu_finance.py <KOSIS_KEY> [출력경로]", file=sys.stderr)
        sys.exit(1)
    kosis_key = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "live/kosis_edu_finance.json"

    from PublicDataReader import Kosis
    api = Kosis(kosis_key)

    results = []
    for name, (org, tbl) in TABLES.items():
        r = fetch_region(api, name, org, tbl)
        if r:
            results.append(r)
        else:
            print(f"  [경고] {name} 데이터 조회 실패", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "regions": results,
            "note": ("KOSIS 지자체 기본통계 기준. 지역마다 최신 갱신연도가 다릅니다"
                     "(2009~2024) - 절대금액을 지역 간 비교할 때는 이 점을 감안하세요. "
                     "강원은 지출액 데이터가 없어 예산액으로 대체했습니다."),
        }, f, ensure_ascii=False, indent=2)
    print(f"saved {out_path}: {len(results)}/{len(TABLES)}개 지역")


if __name__ == "__main__":
    main()
