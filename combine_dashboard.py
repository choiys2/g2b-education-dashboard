#!/usr/bin/env python3
"""
live/full_live.json + live/g2b_full_export.json + live/neis_full_export.json
+ live/own_pipeline_export.json  ->  dashboard_template.html 채워서 live/neis_dashboard_full.html

통합 대시보드(시장분석/AI에듀테크/학교단위발주/AI선도학교/나라장터종합/영업파이프라인)를
매일 최신 데이터로 재생성한다. 이 스크립트가 combine 단계의 전부다:
  1) NEIS 학교수 x G2B 지역별 실적 -> DATA/TOTALS (시장분석 탭)
  2) full_live.json에서 AI 키워드 필터+중복제거+사업유형 분류 -> AI_ROWS (AI·에듀테크 탭)
  3) neis_full_export의 leading_schools -> LEADING_ROWS/LEADING_BY_REGION/LEADING_ENRICHED
  4) g2b_full_export.json 그대로 -> G2B_FULL (나라장터종합 탭)
  5) own_pipeline_export.json 가공 -> PIPE (영업파이프라인 탭, 지역기회점수 포함)
"""
import json, re, sys
from collections import defaultdict

import analytics as an
import beta_features as bf

STRENGTH = {"대구", "강원", "경북", "광주", "전북", "전남", "경기", "충남", "세종", "충북"}
REGIONS = ["서울","부산","대구","인천","광주","대전","울산","세종","경기","강원",
           "충북","충남","전북","전남","경북","경남","제주"]

AI_KEYWORDS = ["AI", "인공지능", "AIDT", "디지털교과서", "에듀테크", "메타버스", "VR", "코딩교육",
               "스마트교육", "디지털 튜터", "AI튜터", "생성형", "챗봇", "빅데이터", "디지털 전환",
               "온라인 플랫폼", "이러닝", "e러닝"]
EXCLUDE_ALWAYS = ["급식", "수련활동", "교육여행", "기숙사", "현장체험학습", "통학버스"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- 1) DATA/TOTALS (시장분석) ----------
def build_data_totals(neis_export, full_live):
    school_counts = {r["region"]: r for r in neis_export["school_counts"]}

    # 지역별 나라장터 활동(g2b_notice=입찰공고, g2b_award=낙찰) - 원본 REGION_MAP 기반 guess_region 재사용
    sys.path.insert(0, ".")
    from fetch_g2b_listings import guess_region
    notice_cnt, award_cnt = defaultdict(int), defaultdict(int)
    for it in full_live["analytics"]["입찰공고"]:
        reg = it.get("지역") or guess_region(it.get("발주기관", ""))
        if reg in REGIONS:
            notice_cnt[reg] += 1
    for it in full_live["analytics"]["낙찰정보"]:
        reg = guess_region(it.get("발주기관", ""))
        if reg in REGIONS:
            award_cnt[reg] += 1

    rows = []
    for region in REGIONS:
        s = school_counts.get(region, {})
        notice, award = notice_cnt.get(region, 0), award_cnt.get(region, 0)
        activity = notice + award
        total = s.get("total", 0)
        penetration = round(activity / total * 100, 2) if total else 0
        rows.append({
            "region": region, "office": s.get("office", region),
            "elem": s.get("elem", 0), "middle": s.get("middle", 0), "total": total,
            "strength": region in STRENGTH,
            "g2b_notice": notice, "g2b_award": award, "g2b_active": 0,
            "activity": activity, "penetration": penetration,
            "public": s.get("public", 0), "private": total - s.get("public", 0),
            "public_ratio": s.get("public_ratio", 0),
        })
    pen_values = sorted(r["penetration"] for r in rows)
    median_pen = pen_values[len(pen_values)//2] if pen_values else 0
    for r in rows:
        r["opportunity"] = r["total"] >= 500 and r["penetration"] <= median_pen

    tot_elem = sum(r["elem"] for r in rows)
    tot_mid = sum(r["middle"] for r in rows)
    tot_all = sum(r["total"] for r in rows)
    strength_total = sum(r["total"] for r in rows if r["strength"])
    tot_public = sum(r["public"] for r in rows)
    totals = {
        "elem": tot_elem, "middle": tot_mid, "all": tot_all,
        "strength_total": strength_total,
        "strength_share": round(strength_total/tot_all*100, 1) if tot_all else 0,
        "notice": sum(r["g2b_notice"] for r in rows), "award": sum(r["g2b_award"] for r in rows),
        "median_penetration": median_pen,
        "public": tot_public, "public_ratio": round(tot_public/tot_all*100, 1) if tot_all else 0,
    }
    return rows, totals


# ---------- 2) AI_ROWS (AI·에듀테크) ----------
def matches_ai(title):
    if any(x in title for x in EXCLUDE_ALWAYS):
        return []
    return [k for k in AI_KEYWORDS if k.upper() in title.upper()]


def classify_biz(title):
    if any(k in title for k in ["콘텐츠 개발","콘텐츠개발","인정도서","교재 개발","교재개발","도서 개발"]):
        return "콘텐츠·인정도서 개발"
    if any(k in title for k in ["플랫폼","포털","시스템 구축","시스템구축","솔루션 구축","ISP","정보화전략","고도화","유지보수"]):
        return "플랫폼·시스템 구축"
    if any(k in title for k in ["연수","교원 역량","역량강화","직무연수","위탁교육","교육 위탁","전문가 양성","양성과정"]):
        return "위탁교육 연수"
    if any(k in title for k in ["행사","박람회","경진대회","콘서트","전시"]):
        return "행사·홍보 운영"
    if any(k in title for k in ["연구용역","연구 용역","학술연구"]):
        return "정책·연구 용역"
    return "기타"


def build_ai_rows(full_live):
    sys.path.insert(0, ".")
    from fetch_g2b_listings import guess_region

    def norm(s):
        return "".join((s or "").replace("[사전규격]", "").split())

    RANK = {"낙찰정보": 3, "입찰공고": 2, "사전규격": 1}
    by_key = {}

    def consider(label, it, amount, date_fields):
        kws = matches_ai(it.get("공고명", ""))
        if not kws:
            return
        org = it.get("발주기관") or it.get("낙찰업체", "")
        if "교육청" not in org and "학교" not in org:
            return
        region = it.get("지역") or guess_region(org, it.get("공고명", ""))
        region = region if region in REGIONS else "기타"
        row = {
            "status": label, "title": it.get("공고명"), "org": org, "region": region,
            "amount": amount, "date": next((it.get(f) for f in date_fields if it.get(f)), None),
            "url": it.get("url"), "keywords": kws, "biztype": classify_biz(it.get("공고명", "")),
            "자격": it.get("자격"),
        }
        dkey = (norm(it.get("공고명", "")), org)
        prev = by_key.get(dkey)
        if prev is None or RANK.get(label, 0) > RANK.get(prev["status"], 0):
            by_key[dkey] = row

    for it in full_live["analytics"]["입찰공고"]:
        consider("입찰공고", it, it.get("예산", 0), ["마감일", "공고일"])
    for it in full_live["analytics"]["사전규격"]:
        consider("사전규격", it, it.get("예산", 0), ["마감일", "공고일"])
    for it in full_live["analytics"]["낙찰정보"]:
        amt = it.get("낙찰금액", 0)
        consider("낙찰정보", it, amt, ["개찰일"])

    rows = list(by_key.values())
    rows.sort(key=lambda r: -r["amount"])
    return rows


# ---------- 3) LEADING_* (AI 선도학교) ----------
def build_leading(neis_export, data_rows):
    leading = neis_export.get("leading_schools", [])
    by_region = defaultdict(lambda: {"count": 0, "초": 0, "중": 0, "고": 0})
    for r in leading:
        reg = r.get("소속지역")
        by_region[reg]["count"] += 1
        grade = r.get("학교급")
        if grade in ("초", "중", "고"):
            by_region[reg][grade] += 1
    neis_by_region = {r["region"]: r for r in data_rows}
    leading_by_region = []
    for reg, v in by_region.items():
        neis_total = neis_by_region.get(reg, {}).get("total", 0)
        leading_em = v["초"] + v["중"]
        pen = round(leading_em/neis_total*100, 2) if neis_total else 0
        leading_by_region.append({
            "region": reg, "total": v["count"], "elem": v["초"], "middle": v["중"], "high": v["고"],
            "neis_total_em": neis_total, "penetration_em_pct": pen,
        })
    return leading, leading_by_region, leading  # LEADING_ROWS, LEADING_BY_REGION, LEADING_ENRICHED(같은 데이터)


# ---------- 4) PIPE (영업파이프라인, 기회점수 포함) ----------
def build_pipe(pipeline_export, g2b_full, data_rows):
    market_by_region = {r["지역"]: r for r in g2b_full["region"]}
    neis_by_region = {r["region"]: r for r in data_rows}
    own_by_region = pipeline_export.get("byRegion", {})

    combined = []
    for region in REGIONS:
        own = own_by_region.get(region, {"count": 0, "amount": 0})
        mkt = market_by_region.get(region, {"건수": 0, "예산": 0})
        school = neis_by_region.get(region, {"total": 0})
        no_market = mkt.get("건수", 0) == 0
        share = round(own["count"]/mkt["건수"]*100, 1) if mkt.get("건수") else None
        combined.append({
            "region": region, "own_count": own["count"], "own_amount": own["amount"],
            "market_count": mkt.get("건수", 0), "market_amount": mkt.get("예산", 0),
            "school_total": school.get("total", 0), "share_pct": share, "no_market_data": no_market,
            "strength": region in STRENGTH,
        })
    max_school = max((c["school_total"] for c in combined), default=1) or 1
    max_market = max((c["market_amount"] for c in combined), default=1) or 1
    for c in combined:
        school_norm = c["school_total"]/max_school*100
        market_norm = c["market_amount"]/max_market*100
        pen_norm = min(c["share_pct"], 100) if c["share_pct"] is not None else 0
        c["opportunity_score"] = round(school_norm*0.35 + market_norm*0.35 + (100-pen_norm)*0.30, 1)

    return {
        "records": pipeline_export.get("records", []),
        "kpi": {
            "total": pipeline_export.get("kpi", {}).get("total", 0),
            "totalTarget": pipeline_export.get("kpi", {}).get("totalTarget", 0),
            "totalBilled": 0, "avgRate": 0,
            "byStatus": pipeline_export.get("kpi", {}).get("byStatus", {}),
            "byContract": pipeline_export.get("kpi", {}).get("byContract", {}),
        },
        "byRegion": combined,
        "byRep": pipeline_export.get("byRep", {}),
        "byField": pipeline_export.get("byField", {}),
        "byMonth": pipeline_export.get("byMonth", {}),
    }


def build_missed_opportunities(ai_rows, pipeline_records, top_n=30):
    """AI·에듀테크 관련 낙찰 건 중 발주기관이 자사 파이프라인에 전혀 없는 건.
    기관명 문자열 매칭만 쓴다(공고명은 우리 내부 파이프라인 명명과 달라 매칭 불가) -
    "그 기관과의 접점이 시트에 전혀 없다"는 약한 신호일 뿐, 확정적 판단이 아니다."""
    known_orgs = {r.get("org", "").strip() for r in pipeline_records if r.get("org")}
    missed = [
        r for r in ai_rows
        if r.get("status") == "낙찰정보" and r.get("org", "").strip() and r["org"].strip() not in known_orgs
    ]
    missed.sort(key=lambda r: r.get("date") or "", reverse=True)
    return [
        {"title": r.get("title"), "org": r.get("org"), "region": r.get("region"),
         "amount": r.get("amount"), "date": r.get("date"), "url": r.get("url")}
        for r in missed[:top_n]
    ]


def main():
    template_path = sys.argv[1] if len(sys.argv) > 1 else "dashboard_template.html"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "live/neis_dashboard_full.html"

    full_live = load("live/full_live.json")
    neis_export = load("live/neis_full_export.json")
    g2b_full = load("live/g2b_full_export.json")
    pipeline_export = load("live/own_pipeline_export.json")
    try:
        kosis_finance = load("live/kosis_edu_finance.json")
    except FileNotFoundError:
        kosis_finance = {"regions": [], "note": ""}
    try:
        competitor_g2b = load("live/competitor_g2b_export.json")
    except FileNotFoundError:
        competitor_g2b = {"competitor_totals": {}, "all_competitors": [], "region_matrix": [], "theme_matrix": [], "records": []}
    try:
        competitor_content = load("live/competitor_content_export.json")
    except FileNotFoundError:
        competitor_content = {"captured_date": "", "companies": {}}
    try:
        competitor_finance = load("live/competitor_finance_export.json")
    except FileNotFoundError:
        competitor_finance = {"data_source": "", "note": "", "companies": {}}
    competitor_training = {"g2b": competitor_g2b, "content": competitor_content, "finance": competitor_finance}

    data_rows, totals = build_data_totals(neis_export, full_live)
    ai_rows = build_ai_rows(full_live)
    leading_rows, leading_by_region, leading_enriched = build_leading(neis_export, data_rows)
    pipe = build_pipe(pipeline_export, g2b_full, data_rows)
    pipe["missed_opportunities"] = build_missed_opportunities(ai_rows, pipeline_export.get("records", []))

    # ---------- 5) BETA (경쟁사 트렌드 + 파이프라인 모멘텀 + 낙찰가 추정 + 추세 예측, 전부 "베타" 표시) ----------
    win_a = an.enrich_win_region(full_live["analytics"]["낙찰정보"], full_live["analytics"]["입찰공고"])
    beta = bf.build_beta(win_a, pipeline_export.get("records", []), open_bids=full_live["analytics"]["입찰공고"])

    html = open(template_path, encoding="utf-8").read()
    subs = {
        "__DATA_JSON__": data_rows, "__TOTALS_JSON__": totals, "__AI_ROWS_JSON__": ai_rows,
        "__LEADING_ROWS_JSON__": leading_rows, "__LEADING_BY_REGION_JSON__": leading_by_region,
        "__LEADING_ENRICHED_JSON__": leading_enriched, "__G2B_FULL_JSON__": g2b_full, "__PIPE_JSON__": pipe,
        "__BETA_JSON__": beta, "__KOSIS_FINANCE_JSON__": kosis_finance,
        "__COMPETITOR_TRAINING_JSON__": competitor_training,
    }
    for token, value in subs.items():
        if token not in html:
            print(f"WARNING: 템플릿에 {token} 없음", file=sys.stderr)
            continue
        html = html.replace(token, json.dumps(value, ensure_ascii=False))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # history_tracker.py가 참고할 요약(전체 AI_ROWS를 또 커밋하지 않기 위해 최소 정보만)
    with open("live/_ai_rows_count.json", "w", encoding="utf-8") as f:
        json.dump(ai_rows, f, ensure_ascii=False)

    print(f"saved {out_path}: 학교데이터 {len(data_rows)}지역, AI건 {len(ai_rows)}, 선도학교 {len(leading_rows)}, "
          f"G2B상세 {len(g2b_full.get('detail', []))}, 자사파이프라인 {len(pipe['records'])}, "
          f"베타-경쟁사트렌드 {len(beta['competitor_trend'])}, 베타-모멘텀 {len(beta['pipeline_momentum'])}, "
          f"경쟁사연수-낙찰 {len(competitor_g2b.get('records', []))}, "
          f"경쟁사연수-콘텐츠 {len(competitor_content.get('companies', {}))}개사, "
          f"경쟁사연수-재무 {sum(1 for c in competitor_finance.get('companies', {}).values() if c.get('available'))}개사")


if __name__ == "__main__":
    main()
