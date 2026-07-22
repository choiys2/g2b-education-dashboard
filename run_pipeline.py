#!/usr/bin/env python3
"""
나라장터 실데이터 전략 대시보드 파이프라인 한 번에 실행:
  1) fetch_g2b_listings.build_full_digest  (data.go.kr OpenAPI: 입찰공고+사전규격+낙찰정보,
     교육청·연수원 발주 건만, 올해 1/1~오늘 범위로 1회 조회 후 진행중인 것만 골라 action 셋 구성)
  2) build_dashboard.render_v2             (KPI+추이/지역/사업유형 차트+기관/경쟁사 랭킹+
     키워드 클라우드+규칙기반 인사이트+검색/정렬/CSV 상세테이블)

사용법:
  python run_pipeline.py                  (기본: 올해 1월 1일 ~ 오늘)
  python run_pipeline.py --days 90        (최근 90일만, 조회 시간 단축)
  python run_pipeline.py --out-dir ./live
"""
import argparse, json, os
from datetime import date

from fetch_g2b_listings import load_config, build_full_digest, SEARCH_KEYWORDS
from build_dashboard import render_v2


def main():
    ap = argparse.ArgumentParser(description="나라장터 실데이터(교육청·연수원 발주) -> 전략 대시보드 한 번에 실행")
    ap.add_argument("--days", type=int, default=None, help="분석 조회 기간(일). 기본값은 올해 1월 1일부터 오늘까지")
    ap.add_argument("--out-dir", default="live", help="결과 파일을 저장할 디렉터리")
    ap.add_argument("--config", default="g2b_config.json")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    cfg = load_config(args.config)
    today = date.today()
    ytd_days = (today - date(today.year, 1, 1)).days + 1
    days = args.days or min(ytd_days, 365)
    org_kw = cfg.get("org_filter_keywords", ["교육청", "연수원"])

    print(f"[1/2] 나라장터 실데이터 수집 (분석범위 {days}일, 키워드 {len(SEARCH_KEYWORDS)}개, 대상기관: {'/'.join(org_kw)})")
    full = build_full_digest(cfg, analytics_days=days)

    full_path = os.path.join(args.out_dir, "full_live.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)
    a = full["analytics"]
    print(f"  -> {full_path}")
    print(f"     analytics: 입찰공고 {len(a['입찰공고'])} / 사전규격 {len(a['사전규격'])} / 낙찰정보 {len(a['낙찰정보'])}")
    print(f"     action(진행중): 입찰공고 {len(full['action']['입찰공고'])} / 사전규격 {len(full['action']['사전규격'])}")

    print("[2/2] 전략 대시보드 생성")
    dashboard_path = os.path.join(args.out_dir, "dashboard_live.html")
    render_v2(full, dashboard_path)
    print(f"완료: {dashboard_path} 를 브라우저로 열어 확인하세요 (KPI/추이/랭킹/키워드/경쟁사/상세검색).")


if __name__ == "__main__":
    main()
