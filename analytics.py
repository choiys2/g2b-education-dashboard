#!/usr/bin/env python3
"""
전략 대시보드 분석 엔진.
fetch_g2b_listings.py가 모은 입찰공고/사전규격/낙찰정보(교육청·연수원 발주 건)를 집계해
KPI, 월별 추이, 지역/기관 랭킹, 정책 키워드 빈도, 사업유형 분류, 경쟁사 랭킹,
규칙 기반 인사이트 문구를 만든다.

중요: "AI 인사이트"라고 부르지만 LLM을 호출하지 않는다. 전부 결정적 규칙/통계라서
재현 가능하고 무료·오프라인으로 동작한다. 실제 LLM 기반 요약이 필요하면 별도 API
연동이 필요하다는 점을 대시보드에도 명시한다(과장 방지).
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

POLICY_KEYWORDS = [
    "AIDT", "AI", "교원연수", "기초학력", "SEL", "논술", "디지털교육",
    "수업혁신", "IB", "고교학점제", "창체", "늘봄", "원격연수", "위탁교육",
    "역량강화", "디지털교과서", "선도교사", "컨소시엄", "직무연수",
]

BIZ_TYPE_RULES = [
    ("AI", ["인공지능", "AIDT", " AI ", "AI활용", "AI 활용", "AI기반", "AI.디지털"]),
    ("연수", ["연수", "직무연수", "역량강화"]),
    ("플랫폼", ["플랫폼", "포털", "시스템 구축", "시스템 개발", "시스템 고도화"]),
    ("콘텐츠", ["콘텐츠", "교재", "자료 개발", "자료개발"]),
    ("SW", ["SW", "소프트웨어", "솔루션", "유지보수", "라이선스"]),
    ("에듀테크", ["에듀테크", "디지털교육", "디지털교과서", "디지털지식"]),
    ("교구", ["교구", "기자재", "장비", "설비"]),
]


def classify_biz_type(title):
    for label, kws in BIZ_TYPE_RULES:
        if any(k in title for k in kws):
            return label
    return "기타"


def keyword_frequency(items, title_key="공고명"):
    counts = defaultdict(int)
    for it in items:
        title = it.get(title_key, "")
        for kw in POLICY_KEYWORDS:
            if kw in title:
                counts[kw] += 1
    return sorted(({"키워드": k, "빈도": v} for k, v in counts.items()), key=lambda x: x["빈도"], reverse=True)


def biz_type_breakdown(items, title_key="공고명"):
    counts = defaultdict(int)
    for it in items:
        counts[classify_biz_type(it.get(title_key, ""))] += 1
    return sorted(({"유형": k, "건수": v} for k, v in counts.items()), key=lambda x: x["건수"], reverse=True)


def _parse_date(s):
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def month_key(date_str):
    return date_str[:7] if date_str and len(date_str) >= 7 else None


def filter_by_recency(items, date_key, days_back, today=None):
    today = today or date.today()
    cutoff = today - timedelta(days=days_back)
    out = []
    for it in items:
        d = _parse_date(it.get(date_key, ""))
        if d and cutoff <= d <= today:
            out.append(it)
    return out


def filter_by_window(items, date_key, start_days_ago, end_days_ago, today=None):
    """[today-start_days_ago, today-end_days_ago) 구간만."""
    today = today or date.today()
    start = today - timedelta(days=start_days_ago)
    end = today - timedelta(days=end_days_ago)
    out = []
    for it in items:
        d = _parse_date(it.get(date_key, ""))
        if d and start <= d < end:
            out.append(it)
    return out


def monthly_trend(spec_items, bid_items, win_items):
    months = set()
    spec_by_m, bid_by_m, win_by_m = defaultdict(int), defaultdict(int), defaultdict(int)
    for it in spec_items:
        m = month_key(it.get("공고일", ""))
        if m:
            spec_by_m[m] += 1
            months.add(m)
    for it in bid_items:
        m = month_key(it.get("공고일", ""))
        if m:
            bid_by_m[m] += 1
            months.add(m)
    for it in win_items:
        m = month_key(it.get("개찰일", ""))
        if m:
            win_by_m[m] += 1
            months.add(m)
    ordered = sorted(months)
    return {
        "months": ordered,
        "사전규격": [spec_by_m[m] for m in ordered],
        "입찰공고": [bid_by_m[m] for m in ordered],
        "낙찰": [win_by_m[m] for m in ordered],
    }


def region_stats(bid_items):
    cnt, budget = defaultdict(int), defaultdict(int)
    for it in bid_items:
        r = it.get("지역") or "전국"
        cnt[r] += 1
        budget[r] += it.get("예산", 0) or 0
    regions = sorted(cnt.keys(), key=lambda r: cnt[r], reverse=True)
    return [{"지역": r, "건수": cnt[r], "예산": budget[r]} for r in regions]


def org_ranking(bid_items, top_n=20):
    cnt, budget = defaultdict(int), defaultdict(int)
    for it in bid_items:
        org = it.get("발주기관") or "-"
        cnt[org] += 1
        budget[org] += it.get("예산", 0) or 0
    orgs = sorted(cnt.keys(), key=lambda o: budget[o], reverse=True)[:top_n]
    return [
        {"기관": o, "건수": cnt[o], "총예산": budget[o], "평균사업비": round(budget[o] / cnt[o]) if cnt[o] else 0}
        for o in orgs
    ]


def enrich_win_region(win_items, bid_items):
    """낙찰정보엔 지역 필드가 없어서, 같은 공고번호의 입찰공고에서 지역을 찾아 붙인다."""
    region_by_key = {}
    for b in bid_items:
        key = b.get("_bid_key")
        if key:
            region_by_key[key] = b.get("지역", "전국")
    for w in win_items:
        w["지역"] = region_by_key.get(w.get("_bid_key"), "전국")
    return win_items


def competitor_ranking(win_items, top_n=30):
    cnt, amt = defaultdict(int), defaultdict(int)
    rates = defaultdict(list)
    last_date = {}
    orgs_by_company = defaultdict(lambda: defaultdict(int))
    regions_by_company = defaultdict(lambda: defaultdict(int))
    for it in win_items:
        co = it.get("낙찰업체") or "-"
        if co == "-":
            continue
        cnt[co] += 1
        amt[co] += it.get("낙찰금액", 0) or 0
        rate_v = it.get("낙찰율(%)", "")
        if rate_v not in (None, "", "nan"):
            try:
                rates[co].append(float(rate_v))
            except (TypeError, ValueError):
                pass
        d = it.get("개찰일", "")
        if d and (co not in last_date or d > last_date[co]):
            last_date[co] = d
        orgs_by_company[co][it.get("발주기관", "-")] += 1
        regions_by_company[co][it.get("지역", "전국")] += 1

    companies = sorted(cnt.keys(), key=lambda c: amt[c], reverse=True)[:top_n]
    out = []
    for c in companies:
        avg_rate = round(sum(rates[c]) / len(rates[c]), 1) if rates[c] else None
        top_org = max(orgs_by_company[c].items(), key=lambda kv: kv[1])[0] if orgs_by_company[c] else "-"
        top_region = max(regions_by_company[c].items(), key=lambda kv: kv[1])[0] if regions_by_company[c] else "-"
        out.append({
            "낙찰업체": c,
            "낙찰건수": cnt[c],
            "총낙찰금액": amt[c],
            "평균낙찰률": avg_rate,
            "최근수주일": last_date.get(c, "-"),
            "주요수주기관": top_org,
            "주요지역": top_region,
        })
    return out


def _pct_change(new, old):
    if old == 0:
        return None
    return round((new - old) / old * 100, 1)


def generate_insights(bid_analytics, spec_action, win_analytics, top_recommend, today=None):
    """이번주/전월 대비 비교 기반 규칙형 인사이트 문장 리스트."""
    today = today or date.today()
    insights = []

    this_week_bid = filter_by_recency(bid_analytics, "공고일", 7, today)
    prev_week_bid = filter_by_window(bid_analytics, "공고일", 14, 7, today)
    diff = len(this_week_bid) - len(prev_week_bid)
    trend_word = "증가" if diff > 0 else ("감소" if diff < 0 else "보합")
    insights.append(f"이번주 입찰공고 {len(this_week_bid)}건 (전주 {len(prev_week_bid)}건 대비 {trend_word}, {diff:+d}건)")

    this_month_kw = keyword_frequency(filter_by_recency(bid_analytics + spec_action, "공고일", 30, today))
    prev_month_kw = keyword_frequency(filter_by_window(bid_analytics, "공고일", 60, 30, today))
    prev_map = {k["키워드"]: k["빈도"] for k in prev_month_kw}
    rising = sorted(
        ((k["키워드"], k["빈도"], k["빈도"] - prev_map.get(k["키워드"], 0)) for k in this_month_kw),
        key=lambda x: x[2], reverse=True,
    )
    if rising and rising[0][2] > 0:
        insights.append(f'최근 30일 급상승 키워드: "{rising[0][0]}" ({prev_map.get(rising[0][0], 0)}건 → {rising[0][1]}건)')
    elif this_month_kw:
        insights.append(f'최근 30일 최다 키워드: "{this_month_kw[0]["키워드"]}" ({this_month_kw[0]["빈도"]}건)')

    this_month_orgs = org_ranking(filter_by_recency(bid_analytics, "공고일", 30, today), top_n=50)
    prev_month_orgs = {o["기관"]: o["총예산"] for o in org_ranking(filter_by_window(bid_analytics, "공고일", 60, 30, today), top_n=50)}
    org_growth = sorted(
        ((o["기관"], o["총예산"], o["총예산"] - prev_month_orgs.get(o["기관"], 0)) for o in this_month_orgs),
        key=lambda x: x[2], reverse=True,
    )
    if org_growth and org_growth[0][2] > 0:
        b = org_growth[0][1] / 100_000_000
        insights.append(f'예산 증가 기관: "{org_growth[0][0]}" (최근 30일 발주 예산 {b:.1f}억, 전월 대비 +{org_growth[0][2]/100_000_000:.1f}억)')

    recent_regions = region_stats(filter_by_recency(bid_analytics, "공고일", 30, today))
    if recent_regions:
        top_r = recent_regions[0]
        insights.append(f'최근 30일 최다 발주 지역: {top_r["지역"]} ({top_r["건수"]}건, {top_r["예산"]/100_000_000:.1f}억)')

    recent_win = filter_by_recency(win_analytics, "개찰일", 60, today)
    top_competitors = competitor_ranking(recent_win, top_n=3)
    if top_competitors:
        tc = top_competitors[0]
        insights.append(f'최근 60일 최다 낙찰: "{tc["낙찰업체"]}" ({tc["낙찰건수"]}건, {tc["총낙찰금액"]/100_000_000:.1f}억, 평균낙찰률 {tc["평균낙찰률"]}%)')

    upcoming = [x for x in spec_action if x.get("점수", 0) >= 45]
    if upcoming:
        insights.append(f'사전규격 단계에서 {len(upcoming)}건이 조기 포착됨 — 입찰공고 전환 시 선제 대응 가능 (예: "{upcoming[0]["공고명"].replace("[사전규격] ", "")}")')

    if top_recommend:
        names = ", ".join(x["공고명"] for x in top_recommend[:3])
        insights.append(f"자체 스코어링 기준 최우선 추천 사업: {names}")

    return insights
