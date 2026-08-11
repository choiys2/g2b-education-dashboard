#!/usr/bin/env python3
"""
경쟁사(티처빌/아이스크림/비바샘/한교원)의 공시 재무정보를 금융위원회 오픈API로 조회한다.

- GetCorpBasicInfoService_V2(getCorpOutline_V2)로 회사명 -> 법인등록번호(crno)를 1회
  수동 조회해 아래 COMPETITOR_CRNO에 고정해뒀다(매일 이름 매칭에 의존하면 동명이인/과거
  상호변경 이력 때문에 흔들릴 수 있어, 이미 확인된 crno를 그대로 쓰는 게 더 안정적이다).
- GetFinaStatInfoService_V2(getSummFinaStat_V2)로 crno 기준 최근 결산연도 요약재무제표를
  조회한다. 비상장/외부감사 비대상 법인은 애초에 공시 의무가 없어 데이터가 안 나올 수 있다
  (실측: 한국교원연수원 - 정상 응답이지만 항목 없음. 오류가 아니라 데이터 자체가 없는 것).
- 별도재무제표(개별 법인 실적)를 비교 기준으로 우선 사용한다 - 연결재무제표는 자회사 실적이
  섞여 있어 회사 간 단순 비교에는 별도 쪽이 더 적합하다. 연결이 있으면 참고용으로 같이 싣는다.
"""
import argparse
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_g2b_listings import load_config

BASE = "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2/getSummFinaStat_V2"

# 2026-08-06 GetCorpBasicInfoService_V2(getCorpOutline_V2)로 회사명 조회해 확인한 값.
COMPETITOR_CRNO = {
    "티처빌": "1101112163907",
    "아이스크림": "1101112453184",
    "비바샘": "1101112427098",
    "한교원": "9991168170154",
}


def call(params, timeout=15):
    url = BASE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "00":
        raise RuntimeError(f"API 오류[{header.get('resultCode')}]: {header.get('resultMsg')}")
    items = data.get("response", {}).get("body", {}).get("items", "")
    if not items or not items.get("item"):
        return []
    return items["item"]


def fetch_company(service_key, crno, years):
    """최근 연도부터 순서대로 조회해, 데이터가 있는 가장 최근 연도를 반환한다."""
    for year in years:
        params = {
            "serviceKey": service_key, "crno": crno, "bizYear": str(year),
            "numOfRows": 10, "pageNo": 1, "resultType": "json",
        }
        try:
            rows = call(params)
        except Exception as e:
            print(f"  [경고] crno={crno} bizYear={year} 조회 실패: {e}", file=sys.stderr)
            continue
        if rows:
            standalone = [r for r in rows if r.get("fnclDcdNm") == "별도요약재무제표"]
            consolidated = [r for r in rows if r.get("fnclDcdNm") == "연결요약재무제표"]
            return {
                "bizYear": year,
                "standalone": standalone[0] if standalone else None,
                "consolidated": consolidated[0] if consolidated else None,
            }
    return None


def fetch_company_history(service_key, crno, years):
    """연도별로 개별 조회해(중간에 데이터 없는 해가 있어도 건너뛰지 않고) 시계열을 모은다."""
    history = []
    for year in years:
        params = {
            "serviceKey": service_key, "crno": crno, "bizYear": str(year),
            "numOfRows": 10, "pageNo": 1, "resultType": "json",
        }
        try:
            rows = call(params)
        except Exception as e:
            print(f"  [경고] crno={crno} bizYear={year} 조회 실패: {e}", file=sys.stderr)
            continue
        if not rows:
            continue
        standalone = [r for r in rows if r.get("fnclDcdNm") == "별도요약재무제표"]
        consolidated = [r for r in rows if r.get("fnclDcdNm") == "연결요약재무제표"]
        raw = standalone[0] if standalone else (consolidated[0] if consolidated else None)
        if raw is None:
            continue
        history.append({"biz_year": year, "consolidated": not standalone, **simplify(raw)})
    history.sort(key=lambda h: h["biz_year"])
    return history


def to_number(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def next_disclosure_estimate(biz_year, today=None):
    """사업보고서 법정 제출기한(결산일로부터 90일 이내, 12월 결산 가정)을 근거로
    '다음 결산연도(biz_year+1) 공시가 언제쯤 올라올지' 대략적인 시점만 안내한다.
    biz_year는 이미 확보한 가장 최근 결산연도이므로, 그 다음 연도(biz_year+1)분
    사업보고서의 법정기한은 (biz_year+2)년 3월 31일이다 - 회사별 실제 공시일이
    아니라 법정기한 기반 추정이라 오차가 있을 수 있다."""
    from datetime import date
    today = today or date.today()
    next_year = biz_year + 1
    expected = date(next_year + 1, 3, 31)
    status = "대기중" if today <= expected else "법정기한 경과(공시 지연 또는 곧 반영 예정)"
    return {"expected_year": next_year, "expected_by": expected.isoformat(), "status": status}


def simplify(raw):
    if raw is None:
        return None
    return {
        "sales": to_number(raw.get("enpSaleAmt")),
        "operating_profit": to_number(raw.get("enpBzopPft")),
        "net_profit": to_number(raw.get("enpCrtmNpf")),
        "total_assets": to_number(raw.get("enpTastAmt")),
        "total_debt": to_number(raw.get("enpTdbtAmt")),
        "total_capital": to_number(raw.get("enpTcptAmt")),
        "debt_ratio": raw.get("fnclDebtRto"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="live/competitor_finance_export.json")
    args = ap.parse_args()

    cfg = load_config()
    service_key = cfg["service_key"]

    from datetime import date
    this_year = date.today().year
    years = [this_year - 1, this_year - 2, this_year - 3]  # 최근 결산 반영 지연 감안, 3개년 중 최신 탐색
    history_years = list(range(this_year - 1, this_year - 6, -1))  # 최근 5개년 시계열

    companies = {}
    for brand, crno in COMPETITOR_CRNO.items():
        result = fetch_company(service_key, crno, years)
        history = fetch_company_history(service_key, crno, history_years)
        if result is None:
            companies[brand] = {"crno": crno, "available": False, "history": history}
            print(f"  {brand}: 데이터 없음(비상장/외감 비대상 추정)")
            continue
        companies[brand] = {
            "crno": crno,
            "available": True,
            "biz_year": result["bizYear"],
            "standalone": simplify(result["standalone"]),
            "consolidated": simplify(result["consolidated"]),
            "history": history,
            "next_disclosure": next_disclosure_estimate(result["bizYear"]),
        }
        s = companies[brand]["standalone"]
        if s:
            print(f"  {brand}: {result['bizYear']}년 매출 {s['sales']:,} 영업이익 {s['operating_profit']:,} 순이익 {s['net_profit']:,} (히스토리 {len(history)}개년)")

    out = {
        "data_source": "금융위원회 공시 재무정보 오픈API(GetFinaStatInfoService_V2)",
        "note": "외부감사대상(상장 또는 일정 규모 이상 비상장) 법인만 조회됩니다. 연 1회 결산 공시 기준이라 최신 분기 실적은 반영되지 않습니다.",
        "companies": companies,
    }
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
