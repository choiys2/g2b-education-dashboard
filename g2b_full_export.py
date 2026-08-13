#!/usr/bin/env python3
"""
live/full_live.json (fetch_g2b_listings.build_full_digest 출력) -> live/g2b_full_export.json

build_dashboard.render_v2()가 화면에 그리는 것과 동일한 집계(월별추이/지역별/기관랭킹/
키워드빈도/사업유형/경쟁사랭킹/인사이트/상세리스트)를 analytics.py 함수로 그대로 재사용해
JSON으로 뽑는다. HTML을 스크레이핑해서 데이터를 역추출하는 대신, 원 소스에서 바로 만든다.

이 출력이 neis 통합 대시보드의 G2B_FULL 상수로 그대로 들어간다(combine_dashboard.py 참고).
"""
import sys, json
from datetime import date

import analytics as an


def build_g2b_full(full):
    action, ana = full["action"], full["analytics"]
    bid_a, spec_a, win_a = ana["입찰공고"], ana["사전규격"], ana["낙찰정보"]
    bid_act, spec_act = action["입찰공고"], action["사전규격"]

    win_a = an.enrich_win_region(win_a, bid_a)
    today = date.today()

    trend = an.monthly_trend(spec_a, bid_a, win_a)
    region = an.region_stats(bid_a)
    org = an.org_ranking(bid_a, top_n=20)
    keyword = an.keyword_frequency(bid_a + spec_a)
    biz = an.biz_type_breakdown(bid_a + spec_a)
    competitor = an.competitor_ranking(win_a, top_n=30)
    recommend = sorted(bid_act + spec_act, key=lambda x: x["점수"], reverse=True)[:5]
    insights = an.generate_insights(bid_a, spec_act, win_a, recommend, today)

    # 상세검색용 통합 리스트(구분/공고명/기관/지역/예산/날짜/점수) - 원본 _detail_rows와 동일한 스키마
    detail = []
    for it in bid_a:
        detail.append({"구분": "입찰공고", "공고명": it.get("공고명", ""), "기관": it.get("발주기관", ""),
                        "지역": it.get("지역", "전국"), "예산": it.get("예산", 0), "날짜": it.get("공고일", ""),
                        "점수": it.get("점수", 0), "url": it.get("url", ""), "자격": it.get("자격")})
    for it in spec_a:
        detail.append({"구분": "사전규격", "공고명": it.get("공고명", ""), "기관": it.get("발주기관", ""),
                        "지역": it.get("지역", "전국"), "예산": it.get("예산", 0), "날짜": it.get("공고일", ""),
                        "점수": it.get("점수", 0), "url": it.get("url", "")})
    for it in win_a:
        detail.append({"구분": "낙찰정보", "공고명": it.get("공고명", ""), "기관": it.get("발주기관", ""),
                        "지역": it.get("지역", "전국"), "예산": it.get("낙찰금액", 0), "날짜": it.get("개찰일", ""),
                        "점수": None, "url": it.get("url", ""), "낙찰업체": it.get("낙찰업체", "")})

    def fmt_won(n):
        n = n or 0
        return f"{n/100000000:.1f}억" if n >= 100000000 else (f"{round(n/10000):,}만" if n >= 10000 else f"{n:,}")

    org_disp = [{"기관": o["기관"], "건수": o["건수"], "총예산": fmt_won(o["총예산"]), "평균사업비": fmt_won(o["평균사업비"])} for o in org]
    comp_disp = []
    for i, c in enumerate(competitor, 1):
        comp_disp.append({
            "순위": i, "낙찰업체": c["낙찰업체"], "낙찰건수": c["낙찰건수"],
            "총낙찰금액": fmt_won(c["총낙찰금액"]),
            "평균낙찰률": f'{c["평균낙찰률"]}%' if c["평균낙찰률"] is not None else "-%",
            "최근수주일": c["최근수주일"], "주요수주기관": c["주요수주기관"], "주요지역": c["주요지역"],
        })
    detail_disp = [{**d, "예산표시": fmt_won(d["예산"])} for d in detail]

    return {
        "trend": trend, "region": region, "biz": biz, "insights": insights,
        "org": org_disp, "keyword": keyword, "competitor": comp_disp, "detail": detail_disp,
        "generated_at": full.get("generated_at"),
    }


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "live/full_live.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "live/g2b_full_export.json"
    with open(in_path, encoding="utf-8") as f:
        full = json.load(f)
    result = build_g2b_full(full)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"saved {out_path}: detail {len(result['detail'])}건, org {len(result['org'])}, competitor {len(result['competitor'])}")


if __name__ == "__main__":
    main()
