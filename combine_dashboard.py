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
import json, os, re, sys
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
    # 2026 지정 AI 중점학교·AI·디지털 선도학교(시도교육청 공개 명단, ai_schools_2026.py가 엑셀에서 생성).
    # 없으면 예전 한국과학창의재단 2022 코호트(odcloud)로 돌아간다.
    try:
        leading = load("static_data/ai_schools_2026.json")["schools"]
    except FileNotFoundError:
        leading = neis_export.get("leading_schools", [])
    by_region = defaultdict(lambda: {"count": 0, "초": 0, "중": 0, "고": 0, "ai": 0, "dig": 0})
    for r in leading:
        reg = r.get("소속지역")
        by_region[reg]["count"] += 1
        grade = r.get("학교급")
        if grade in ("초", "중", "고"):
            by_region[reg][grade] += 1
        by_region[reg]["ai"] += "AI 중점" in (r.get("사업") or [])
        by_region[reg]["dig"] += "디지털 선도" in (r.get("사업") or [])
    neis_by_region = {r["region"]: r for r in data_rows}
    leading_by_region = []
    for reg, v in by_region.items():
        neis_total = neis_by_region.get(reg, {}).get("total", 0)
        leading_em = v["초"] + v["중"]
        pen = round(leading_em/neis_total*100, 2) if neis_total else 0
        leading_by_region.append({
            "region": reg, "total": v["count"], "elem": v["초"], "middle": v["중"], "high": v["고"],
            "ai": v["ai"], "dig": v["dig"],
            "neis_total_em": neis_total, "penetration_em_pct": pen,
        })
    # 학교알리미 교원·학생 수(schoolinfo_export.py, SCHOOLINFO_KEY 있을 때만)
    try:
        si = load("live/schoolinfo_export.json").get("schools", {})
        by_name = {}
        for v in si.values():
            by_name.setdefault(v["name"], []).append(v)
        for s in leading:
            hits = by_name.get(s.get("학교명")) or []
            if len(hits) == 1:  # 동명 학교가 여러 시도에 있으면 붙이지 않는다(오매칭 방지)
                s["teachers"], s["students"] = hits[0].get("teachers"), hits[0].get("students")
    except FileNotFoundError:
        pass
    score_schools(leading)
    return leading, leading_by_region, leading  # LEADING_ROWS, LEADING_BY_REGION, LEADING_ENRICHED(같은 데이터)


SIDO_SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
              "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원",
              "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
              "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}


def score_schools(schools):
    """B2S 영업 우선순위 점수(100). 공개 데이터만 쓴다(자사 영업 기록은 넣지 않음).
      사업 30: 두 사업 겸임 30 / AI 중점 20 / 디지털 선도 15  (AI 예산이 학교로 내려가는 사업일수록 높게)
      AI 중점 유형 15: 선도형 15 / 중심형 10 / 문화확산형·기타 5
      강점 권역 20: 자사 강점 10개 시도
      학교장터 구매력 20: 2025 시도별 학교 1곳당 학교장터 구매액(최대 시도 대비)
      연락 가능 10: 대표전화 확보 / 고교 5: 고교학점제·AI 선택과목으로 교원 연수 수요가 큰 학교급"""
    try:
        sc = load("static_data/school_contract_national_2025.json")
        per = {SIDO_SHORT.get(r["sido"], r["sido"]): r["amt"] / r["n"] for r in sc.get("by_sido", []) if r.get("n")}
    except FileNotFoundError:
        per = {}
    top = max(per.values() or [1])
    for s in schools:
        progs = s.get("사업") or []
        parts = {}
        parts["사업"] = 30 if s.get("겸임") else (20 if "AI 중점" in progs else 15)
        t = s.get("ai_type") or ""
        parts["유형"] = 15 if t.startswith("선도형") else 10 if t.startswith("중심형") else 5 if "AI 중점" in progs else 0
        parts["강점권역"] = 20 if s.get("소속지역") in STRENGTH else 0
        parts["구매력"] = round(20 * per.get(s.get("소속지역"), 0) / top)
        parts["연락"] = 10 if s.get("tel") else 0
        parts["학교급"] = 5 if s.get("학교급") == "고" else 0
        s["score"] = sum(parts.values())
        s["score_parts"] = parts


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
        "source": pipeline_export.get("source", {}),
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


def build_new_courses(days=180):
    """경쟁사 연수원 신규 강좌(competitor_course_catalog_scrape.py가 주 1회 누적).
    이벤트가 아니라 강좌 카탈로그에 새로 올라온 연수과정만 담는다."""
    from datetime import date, timedelta
    try:
        catalog = load("history/competitor_course_catalog.json")
    except FileNotFoundError:
        catalog = {"captured_date": "", "companies": {}}
    rows = []
    try:
        with open("history/competitor_new_courses.jsonl", encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        pass
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = sorted((r for r in rows if (r.get("first_seen") or "") >= cutoff),
                  key=lambda r: (r.get("first_seen") or "", r.get("company") or ""), reverse=True)

    # 전체 강좌 목록(현재 카탈로그). 저장된 title이 옛 파서 결과일 수 있어 원문(context)으로
    # 다시 파싱한다. 대시보드 용량을 위해 context 자체는 싣지 않는다.
    from catalog_field_parser import parse_fields
    courses = {}
    for name, c in catalog.get("companies", {}).items():
        out, seen = [], set()
        for it in c.get("courses", []):
            if not it.get("url") or it["url"] in seen:
                continue
            seen.add(it["url"])
            f = parse_fields(name, it.get("title") or "", it.get("context") or "")
            if f.get("title") == (it.get("title") or ""):  # 파싱 실패 시 저장값 유지
                f = {k: it.get(k) for k in ("title", "category", "credit", "price", "orig_price")}
            if (f.get("title") or "").strip() in ("", "상세보기", "미리보기"):
                continue  # 버튼 문구가 제목으로 잡힌 카드(파싱 실패) - 목록에서 제외
            out.append({**f, "url": it["url"]})
        courses[name] = out
    return {
        "captured_date": catalog.get("captured_date"),
        "window_days": days,
        "catalog_counts": {n: len(v) for n, v in courses.items()},
        "courses": courses,
        "rows": rows,
    }


def _sheets_ops():
    """sheets_ops.py 결과 + 결과보고 초안(report_drafts.py)"""
    try:
        d = load("live/sheets_ops.json")
    except FileNotFoundError:
        d = {"available": False}
    try:
        d["reports"] = load("live/report_drafts.json")
    except FileNotFoundError:
        d["reports"] = None
    return d


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
    new_courses = build_new_courses()
    import content_gap
    competitor_training = {
        "g2b": competitor_g2b, "content": competitor_content, "finance": competitor_finance,
        "new_courses": new_courses,
        # 3사 공통 분류 갭·주제 공백 백로그·신규 출시 추이(강좌 행에 'std' 분류도 채워 넣는다)
        "content_gap": content_gap.build(new_courses["courses"], new_courses["rows"], "비바샘연수원"),
        # 아이스크림·티처빌 결합상품(연수+도서·교구·이용권·상품)
        "bundles": __import__("bundle_products").build(),
    }

    # 입찰공고 최근 12개월 -> 초·중·고 연수 주제 수요와 2027 개발 추천(나라장터 종합 탭)
    import training_topics
    training_topic_data = training_topics.build_from_files(new_courses["courses"], "비바샘연수원", full_live)

    # B2S 학교 타깃 레이더 + 샘몰 상품 기획 보드(B2S·샘몰 기획 탭) - 위 데이터 재조합, API 호출 없음
    import b2s_board
    b2s = b2s_board.build(full_live, new_courses["courses"], new_courses["rows"], training_topic_data, "비바샘연수원")

    data_rows, totals = build_data_totals(neis_export, full_live)
    ai_rows = build_ai_rows(full_live)
    leading_rows, leading_by_region, leading_enriched = build_leading(neis_export, data_rows)
    try:
        ai_brief = load("live/ai_insights.json")
    except FileNotFoundError:
        ai_brief = None
    try:
        ai_drafts = load("live/ai_drafts.json")
    except FileNotFoundError:
        ai_drafts = {}
    rfp = {"items": [], "total": 0, "skipped": 0}
    if os.path.exists("history/rfp_analysis.jsonl"):
        _rows = [json.loads(l) for l in open("history/rfp_analysis.jsonl", encoding="utf-8") if l.strip()]
        import bid_fit, rfp_analysis
        _ok, _seen = [], set()
        for r in sorted([r for r in _rows if r.get("ai") and rfp_analysis.relevant(r)], key=lambda r: r["d"], reverse=True):
            nt = rfp_analysis.norm_title(r["t"])
            if nt in _seen:  # 재공고는 최신 한 건만
                continue
            _seen.add(nt)
            _ok.append({**r, "fit": bid_fit.judge(r["ai"])})
        _prof = bid_fit.load_profile()
        rfp = {"items": _ok[:30], "total": len(_ok), "skipped": sum(1 for r in _rows if not r.get("ai")),
               "profile": {k: _prof[k] for k in ("name", "hq_region", "company_size", "industry_codes")}}
    import b2s_demand
    b2s_market = b2s_demand.build()
    if b2s_market.get("available"):
        b2s_demand.write_csv("live/b2s_schools.csv")
    try:
        banner_market = load("live/banner_market.json")
    except FileNotFoundError:
        banner_market = {"available": False}
    try:
        pipe_comms = load("live/pipeline_comms.json")
    except FileNotFoundError:
        pipe_comms = {"available": False}
    try:
        tour = load("live/tour_venues.json")
    except FileNotFoundError:
        tour = {"regions": {}}
    try:
        weather = load("live/weather.json")
    except FileNotFoundError:
        weather = {"cities": []}
    import early_warning
    cov = {t["id"]: t["coverage"] for t in training_topic_data.get("topics", [])}
    early = early_warning.build(full_live, cov)
    try:
        contracts = load("live/competitor_contract_export.json")
    except FileNotFoundError:
        contracts = {"status": "아직 수집 전", "competitors": [], "records": []}
    try:
        _ai = load("static_data/ai_schools_2026.json")
        ai_school_status = {k: _ai[k] for k in ("source", "captured", "xlsx", "status")}
    except FileNotFoundError:
        ai_school_status = {"status": []}
    pipe = build_pipe(pipeline_export, g2b_full, data_rows)
    import exec_summary
    exec_data = exec_summary.build(full_live=full_live, topics=training_topic_data, contracts=contracts, banner=banner_market,
                                   pipe=pipe, comms=pipe_comms, b2s_market=b2s_market, rfp=rfp, early=early,
                                   leading_n=len(leading_rows), new_courses=new_courses.get("rows"), tour=tour,
                                   weather=weather, ai_brief=ai_brief)
    with open("live/_exec_inputs.json", "w", encoding="utf-8") as f:
        json.dump(exec_data, f, ensure_ascii=False)
    try:
        exec_data["story"] = load("live/exec_story.json")
    except FileNotFoundError:
        exec_data["story"] = None
    # B2G영업 고도화: 예산 여력(A)·모집 경보(C)·재계약 캘린더(E)·집합연수 운영 지원(F) - ops_insights.py
    import ops_insights
    _c, _fin, _sch, _ven, _wx = ops_insights.load_inputs()
    ops = ops_insights.build(pipeline_export.get("records", []), _c, _fin, _sch, tour if tour.get("regions") else _ven, weather)
    try:
        _copy = load("live/recruit_copy.json")
        for it in (ops.get("recruit") or {}).get("items", []):
            if it["course"] in _copy.get("items", {}):
                it["copy"] = _copy["items"][it["course"]]
        ops["recruit"]["copy_date"] = _copy.get("date")
    except (FileNotFoundError, KeyError, TypeError):
        pass
    pipe["missed_opportunities"] = build_missed_opportunities(ai_rows, pipeline_export.get("records", []))

    # ---------- 5) BETA (경쟁사 트렌드 + 파이프라인 모멘텀 + 낙찰가 추정 + 추세 예측, 전부 "베타" 표시) ----------
    win_a = an.enrich_win_region(full_live["analytics"]["낙찰정보"], full_live["analytics"]["입찰공고"])
    beta = bf.build_beta(win_a, pipeline_export.get("records", []), open_bids=full_live["analytics"]["입찰공고"])

    html = open(template_path, encoding="utf-8").read()
    subs = {
        "__DATA_JSON__": data_rows, "__TOTALS_JSON__": totals, "__AI_ROWS_JSON__": ai_rows,
        "__LEADING_ROWS_JSON__": leading_rows, "__LEADING_BY_REGION_JSON__": leading_by_region,
"__G2B_FULL_JSON__": g2b_full, "__PIPE_JSON__": pipe,
        "__BETA_JSON__": beta, "__KOSIS_FINANCE_JSON__": kosis_finance,
        "__COMPETITOR_TRAINING_JSON__": competitor_training,
        "__TRAINING_TOPICS_JSON__": training_topic_data,
        "__AI_SCHOOL_STATUS_JSON__": ai_school_status,
        "__EARLY_WARNING_JSON__": early, "__CONTRACTS_JSON__": contracts,
        "__WEATHER_JSON__": weather, "__AI_BRIEF_JSON__": ai_brief,
        "__RFP_JSON__": rfp, "__AI_DRAFTS_JSON__": ai_drafts, "__TOUR_JSON__": tour, "__PIPE_COMMS_JSON__": pipe_comms, "__BANNER_JSON__": banner_market, "__EXEC_JSON__": exec_data, "__B2S_MARKET_JSON__": b2s_market,
        "__B2S_BOARD_JSON__": b2s, "__OPS_JSON__": ops, "__VIZ_JSON__": __import__("viz_data").build(pipeline_export.get("records", [])),
        "__SHEETS_OPS_JSON__": _sheets_ops(),
        "__WF_BADGES_JSON__": __import__("workflows").badge_map(),
        "__ADMIN_JSON__": __import__("admin_structure").encrypted_blob((exec_data or {}).get("sources")),
        "__EDU_CNTR_JSON__": __import__("edu_contracts").build(),
    }
    for token, value in subs.items():
        if token not in html:
            print(f"WARNING: 템플릿에 {token} 없음", file=sys.stderr)
            continue
        html = html.replace(token, json.dumps(value, ensure_ascii=False))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 주간 보고(weekly_digest.py)가 쓰는 입력 묶음 - 대시보드와 같은 계산 결과를 그대로 넘긴다
    with open("live/_weekly_inputs.json", "w", encoding="utf-8") as f:
        json.dump({"bids": full_live["analytics"]["입찰공고"], "early": early,
                   "topics": training_topic_data.get("topics", [])[:8], "new_courses": new_courses["rows"],
                   "contracts": contracts.get("competitors", [])}, f, ensure_ascii=False)

    # history_tracker.py가 참고할 요약(전체 AI_ROWS를 또 커밋하지 않기 위해 최소 정보만)
    with open("live/_ai_rows_count.json", "w", encoding="utf-8") as f:
        json.dump(ai_rows, f, ensure_ascii=False)

    print(f"saved {out_path}: 학교데이터 {len(data_rows)}지역, AI건 {len(ai_rows)}, 선도학교 {len(leading_rows)}, "
          f"G2B상세 {len(g2b_full.get('detail', []))}, 자사파이프라인 {len(pipe['records'])}, "
          f"베타-경쟁사트렌드 {len(beta['competitor_trend'])}, 베타-모멘텀 {len(beta['pipeline_momentum'])}, "
          f"경쟁사연수-낙찰 {len(competitor_g2b.get('records', []))}, "
          f"경쟁사연수-콘텐츠 {len(competitor_content.get('companies', {}))}개사, "
          f"경쟁사연수-재무 {sum(1 for c in competitor_finance.get('companies', {}).values() if c.get('available'))}개사, "
          f"경쟁사연수-신규콘텐츠 {len(competitor_training['new_courses']['rows'])}건, "
          f"경쟁사연수-전체강좌 {sum(competitor_training['new_courses']['catalog_counts'].values())}건")


if __name__ == "__main__":
    main()
