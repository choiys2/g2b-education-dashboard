#!/usr/bin/env python3
"""
경쟁사(티처빌/아이스크림/비바샘/한교원) 나라장터 낙찰 매트릭스를 실제 API로
재현한다. 원본은 경쟁사_연수_대시보드/work/g2b_snapshot.json — 2026-07-15
기준 엑셀 피벗테이블 1회성 export였다.

ScsbidInfoService(낙찰정보서비스)는 낙찰업체명으로 서버측 필터링을 지원하지
않는다(공고명만 필터 가능) - 그래서 교육청/연수원 낙찰정보를 폭넓게 긁은 뒤
낙찰업체명에 경쟁사명이 포함된 건만 클라이언트에서 골라낸다.

원본 엑셀 export가 정확히 몇 년치를 담았는지 알 수 없어 그대로 재현할 수는
없다. 대신 누적 방식을 쓴다: history/competitor_wins.jsonl(git 추적, live/처럼
매일 지워지지 않음)에 새로 발견되는 낙찰 건을 계속 추가해나간다. 매일 도는
파이프라인은 최근 N일치만 조회하고(--days, 기본 60일 - 낙찰 데이터가 뒤늦게
등록되는 경우를 감안해 겹치게 조회), 대시보드에는 지금까지 누적된 전체
이력을 집계해서 보여준다. 이번에 처음 도입할 때만 --days를 크게 줘서
과거분을 한 번 채워 넣는다(백필).

테마 분류는 대시보드 원본에서 쓴 37개 테마 태그를 그대로 키워드 삼아
과정명에 포함되는지로 판정한다(포함 안 되면 "기타") - 사람이 직접 태깅한
원본과 완전히 같은 정확도는 아니지만, 규칙 기반이라 결정적이고 검증 가능하다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_g2b_listings import call_api, date_chunks, guess_region, load_config, to_date

TARGET_COMPETITORS = ["티처빌", "아이스크림", "비바샘", "한교원"]

# 나라장터 낙찰업체명(bidwinnrNm)은 소비자 브랜드명이 아니라 사업자등록증상
# 법인명으로 등록돼 있어, 브랜드명 그대로는 거의 안 걸린다(실측: "티처빌"
# 문자열로는 0건 - 실제로는 "테크빌교육(주)"으로 등록). 사용자 확인(2026-08-04)
# 및 이 대시보드가 이미 수집해둔 경쟁사 랭킹 데이터로 확인한 별칭 매핑.
COMPETITOR_ALIASES = {
    "티처빌": ["테크빌교육"],
    "아이스크림": ["아이스크림미디어"],
    "비바샘": ["비상교육"],
    "한교원": ["한국교원연수원"],
}

# 원본 SEARCH_KEYWORDS(score_listings.py)는 AI/디지털 위주라 이 4개사가 실제로
# 수주하는 일반 교원연수(기초학력·인성교육·예술교육 등 37개 테마)를 거의 못 잡았다
# (실측: 730일 검색해도 10건). 여기서는 "교원연수 낙찰" 자체를 넓게 잡는 게
# 목적이라 더 일반적인 용어로 바꾼다.
COMPETITOR_KEYWORDS = [
    "교원연수", "원격연수", "직무연수", "위탁교육", "역량강화", "원격직무연수",
    "교원 역량", "교사 연수", "연수 위탁", "온라인 연수",
]

THEMES = [
    "AI", "IB", "경제", "교권", "교권보호", "교육과정", "기초학력", "늘봄", "다문화",
    "도서관", "독서", "마을교육", "미래교육", "민간위탁", "방과후", "사회정서", "상담",
    "수업", "수학", "안전", "영재", "예술교육", "외국어", "유아교육", "유치원", "인권",
    "인성교육", "직업계고", "진로", "통합교육", "특수통합", "평가", "학교예술", "학부모",
    "학습코칭", "한국사", "한국어", "환경교육",
]

HISTORY_PATH = Path(__file__).parent / "history" / "competitor_wins.jsonl"


def classify_theme(title):
    for t in THEMES:
        if t in title:
            return t
    return "기타"


def match_competitor(bidwinnr_name):
    for c in TARGET_COMPETITORS:
        if c in bidwinnr_name:
            return c
        for alias in COMPETITOR_ALIASES.get(c, []):
            if alias in bidwinnr_name:
                return c
    return None


def fetch_competitor_wins(cfg, days_back, keywords=COMPETITOR_KEYWORDS):
    svc = cfg["services"]["scsbid"]
    chunk_days = cfg.get("date_range_chunk_days", 28)
    interval = cfg.get("request_interval_sec", 0.15)
    import time

    rows = []
    for kw in keywords:
        for begin, end in date_chunks(days_back, chunk_days):
            params = {
                "serviceKey": cfg["service_key"], "pageNo": 1, "numOfRows": 200,
                "inqryDiv": 1, "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
                "inqryEndDt": end.strftime("%Y%m%d%H%M"), "type": "json",
                svc["keyword_param"]: kw,
            }
            try:
                items, _ = call_api(svc["base_url"], svc["operation"], params)
            except Exception as e:
                print(f"  [경고] 조회 실패 (kw={kw}, {begin.date()}~{end.date()}): {e}", file=sys.stderr)
                continue
            for it in items:
                dminstt = it.get("dminsttNm", "")
                winner = it.get("bidwinnrNm", "")
                comp = match_competitor(winner)
                if not comp:
                    continue
                # 발주기관 필터(교육청/연수원)는 여기서 쓰지 않는다 - 낙찰업체명이
                # 이미 4개 경쟁사 중 하나와 정확히 일치해야 통과하는 강한 필터라
                # 발주기관까지 좁히면 "OO교육지원청"처럼 "교육청" 부분문자열이
                # 아닌 정상 기관명이 오탈락한다(실측으로 확인된 문제).
                bid_key = f'{it.get("bidNtceNo","")}-{it.get("bidNtceOrd","")}'
                rows.append({
                    "_key": bid_key,
                    "region": guess_region(dminstt),
                    "org": dminstt,
                    "org_type": "교육청" if "교육청" in dminstt and "지원청" not in dminstt else
                                ("교육지원청" if "지원청" in dminstt else "연수원"),
                    "competitor": comp,
                    "course": it.get("bidNtceNm", ""),
                    "theme": classify_theme(it.get("bidNtceNm", "")),
                    "metric": it.get("prtcptCnum"),
                    "date": to_date(it.get("rlOpengDt")),
                })
            time.sleep(interval)
    return rows


def load_history():
    if not HISTORY_PATH.exists():
        return {}
    out = {}
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            out[r["_key"]] = r
        except json.JSONDecodeError:
            continue
    return out


def save_history(records_by_key):
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records_by_key.values()]
    HISTORY_PATH.write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def build_aggregates(all_records, snapshot_date):
    from collections import defaultdict

    competitor_totals = defaultdict(lambda: {"deal_count": 0, "metric_sum": 0})
    for r in all_records:
        c = competitor_totals[r["competitor"]]
        c["deal_count"] += 1
        if r.get("metric"):
            try:
                c["metric_sum"] += int(r["metric"])
            except (TypeError, ValueError):
                pass
    all_competitors = sorted(competitor_totals.keys(), key=lambda c: -competitor_totals[c]["deal_count"])

    region_matrix = defaultdict(lambda: defaultdict(int))
    for r in all_records:
        region_matrix[r["region"]][r["competitor"]] += 1
    regions_sorted = sorted(region_matrix.keys(), key=lambda rg: -sum(region_matrix[rg].values()))
    region_matrix_out = [
        {"region": rg, "counts": dict(region_matrix[rg]), "total": sum(region_matrix[rg].values())}
        for rg in regions_sorted
    ]

    theme_matrix = defaultdict(lambda: defaultdict(int))
    for r in all_records:
        theme_matrix[r["theme"]][r["competitor"]] += 1
    themes_sorted = sorted(theme_matrix.keys(), key=lambda th: -sum(theme_matrix[th].values()))
    theme_matrix_out = [
        {"theme": th, "counts": dict(theme_matrix[th]), "total": sum(theme_matrix[th].values())}
        for th in themes_sorted
    ]

    records_out = [
        {"region": r["region"], "org": r["org"], "org_type": r["org_type"],
         "competitor": r["competitor"], "course": r["course"], "metric": r.get("metric")}
        for r in sorted(all_records, key=lambda r: r.get("date") or "", reverse=True)
    ]

    return {
        "snapshot_date": snapshot_date,
        "data_source": "나라장터 낙찰정보 실시간 API (누적)",
        "competitor_totals": {c: competitor_totals[c] for c in all_competitors},
        "core_competitors": TARGET_COMPETITORS,
        "all_competitors": all_competitors,
        "region_matrix": region_matrix_out,
        "theme_matrix": theme_matrix_out,
        "records": records_out,
        "totals": {
            "deal_count": len(all_records),
            "region_count": len(regions_sorted),
            "theme_count": len(themes_sorted),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="이번 실행에서 조회할 최근 일수(기본 60, 백필 시 크게)")
    ap.add_argument("--out", default="live/competitor_g2b_export.json")
    args = ap.parse_args()

    from datetime import date

    cfg = load_config()
    new_rows = fetch_competitor_wins(cfg, days_back=args.days)

    history = load_history()
    added = 0
    for r in new_rows:
        if r["_key"] not in history:
            added += 1
        history[r["_key"]] = r
    save_history(history)

    agg = build_aggregates(list(history.values()), snapshot_date=date.today().isoformat())
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {args.out}: 신규 {added}건 / 누적 {len(history)}건, "
          f"경쟁사 {len(agg['all_competitors'])}, 지역 {agg['totals']['region_count']}, "
          f"테마 {agg['totals']['theme_count']}")


if __name__ == "__main__":
    main()
