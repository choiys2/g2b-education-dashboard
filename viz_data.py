#!/usr/bin/env python3
"""
시각화 보강용 집계 - 대시보드에 아직 실리지 않은 history/ 누적 데이터를 차트용으로 묶는다(API 호출 없음).
combine_dashboard.py 가 build(pipeline_records) 결과를 __VIZ_JSON__ 으로 넣는다. 공개 범위는 숫자·공개 기관명뿐.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SELF = "비바샘연수원"
COMPS = ["아이스크림", "티처빌", SELF, "한교원"]


def _jsonl(p):
    p = HERE / p
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def _short_org(o):
    o = re.sub(r"\s+", " ", o or "").strip()
    parts = o.split(" ")
    if len(parts) > 1 and re.search(r"교육청$|지원청$|학교$|연수원$|교육원$|진흥원$", parts[-1]):
        return parts[-1][:24]
    return o[:24]


def topic_month(today):
    import training_topics as tt
    names = {t[0]: t[1] for t in tt.TOPICS}
    start = (today.replace(day=1) - timedelta(days=330)).replace(day=1)
    months = []
    m = start
    while m <= today:
        months.append(m.strftime("%Y-%m"))
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    grid = defaultdict(Counter)
    n = 0
    for r in _jsonl("history/training_bids.jsonl"):
        mo = (r.get("d") or "")[:7]
        if mo not in months or not tt.is_training_bid(r.get("t"), r.get("o")):
            continue
        n += 1
        for tid in tt.classify_topics(r.get("t")):
            grid[tid][mo] += 1
    order = sorted(grid, key=lambda k: -sum(grid[k].values()))
    return {"months": months, "rows": [{"id": k, "name": names.get(k, k), "counts": [grid[k][m] for m in months]} for k in order],
            "bids": n}


def rfp_funnel(today):
    import training_topics as tt
    since = (today - timedelta(days=60)).isoformat()
    bids = [r for r in _jsonl("history/training_bids.jsonl") if (r.get("d") or "") >= since and tt.is_training_bid(r.get("t"), r.get("o"))]
    ana = _jsonl("history/rfp_analysis.jsonl")
    return {"bids": len(bids), "with_files": sum(1 for r in bids if r.get("f")),
            "analyzed": sum(1 for r in ana if r.get("ai") and (r.get("d") or "") >= since)}


def contracts_views(today):
    cs = [c for c in _jsonl("history/competitor_contracts.jsonl") if c.get("date")]
    months = sorted({c["date"][:7] for c in cs})[-12:]
    share = {m: {k: 0 for k in COMPS} for m in months}
    for c in cs:
        if c["date"][:7] in share and c.get("competitor") in COMPS:
            share[c["date"][:7]][c["competitor"]] += c.get("amount") or 0
    prices = [{"c": c["competitor"], "a": c.get("amount") or 0, "r": c.get("region", "")} for c in cs if c.get("competitor") in COMPS and c.get("amount")]
    by_org = defaultdict(lambda: {"own": 0, "comp": 0, "amt": 0, "n": 0, "who": Counter(), "r": ""})
    for c in cs:
        o = by_org[c.get("org", "")]
        o["n"] += 1
        o["r"] = c.get("region", "")
        if c.get("competitor") == SELF:
            o["own"] += 1
        else:
            o["comp"] += 1
            o["amt"] += c.get("amount") or 0
            o["who"][c.get("competitor")] += 1
    comp_only = sorted([{"org": _short_org(k), "r": v["r"], "n": v["comp"], "amt": v["amt"], "who": v["who"].most_common(1)[0][0]}
                        for k, v in by_org.items() if k and not v["own"] and v["comp"]], key=lambda x: -x["amt"])[:15]
    return {"share_months": months, "share": share, "prices": prices, "comp_only": comp_only}


def org_bubble(today):
    import training_topics as tt
    since = (today - timedelta(days=365)).isoformat()
    own = Counter(c.get("org", "") for c in _jsonl("history/competitor_contracts.jsonl") if c.get("competitor") == SELF)
    agg = defaultdict(lambda: {"n": 0, "amt": 0, "r": ""})
    for r in _jsonl("history/training_bids.jsonl"):
        if (r.get("d") or "") < since or not tt.is_training_bid(r.get("t"), r.get("o")):
            continue
        a = agg[r.get("o", "")]
        a["n"] += 1
        a["amt"] += r.get("a") or 0
        a["r"] = r.get("r", "")
    rows = [{"org": _short_org(k), "r": v["r"], "n": v["n"], "avg": round(v["amt"] / v["n"]) if v["n"] else 0, "own": own.get(k, 0)}
            for k, v in agg.items() if k]
    return sorted(rows, key=lambda x: -x["n"])[:40]


def course_timeline():
    c = defaultdict(Counter)
    for r in _jsonl("history/competitor_new_courses.jsonl"):
        c[(r.get("first_seen") or "")[:7]][r.get("company")] += 1
    months = sorted(k for k in c if k)[-12:]
    return {"months": months, "counts": {m: dict(c[m]) for m in months}}


def kpi_series(today):
    rows = _jsonl("history/daily_stats.jsonl")
    rows = [r for r in rows if r.get("date")][-120:]
    keys = ["ai_rows_count", "g2b_total_detail", "own_pipeline_total", "own_pipeline_target"]
    return {"dates": [r["date"] for r in rows], "series": {k: [r.get(k) for r in rows] for k in keys}}


def brief_tags():
    files = sorted((HERE / "briefings").glob("20*.json"))[-35:]
    weeks = defaultdict(Counter)
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        dt = date.fromisoformat(d["date"])
        wk = (dt - timedelta(days=dt.weekday())).isoformat()
        for s in d.get("sections", []):
            if s.get("id") not in ("education", "edtech"):
                continue
            for it in s.get("items", []):
                for t in it.get("tags", []):
                    weeks[wk][t] += 1
    stop = {"안내", "최우선", "공지", "속보", "경쟁사", "해외"}
    for c in weeks.values():
        for t in stop:
            c.pop(t, None)
    tot = Counter()
    for c in weeks.values():
        tot.update(c)
    top = [t for t, _ in tot.most_common(8)]
    wl = sorted(weeks)
    return {"weeks": wl, "tags": top, "counts": {t: [weeks[w][t] for w in wl] for t in top}}


def channel_mix(records):
    """운영DT 사업을 발주 주체로 나눈 추정 채널 비중(총예산 기준). 학교 = B2S, 그 외 기관 = B2G."""
    import own_pipeline_export as ope
    b2g = b2s = 0
    for r in records or []:
        amt = ope.to_num(r.get("targetAmount"))
        if re.search(r"학교$|유치원$|학교\s", r.get("org") or ""):
            b2s += amt
        else:
            b2g += amt
    tot = b2g + b2s
    return {"b2g": b2g, "b2s": b2s, "b2g_share": round(b2g / tot * 100, 1) if tot else None, "n": len(records or []),
            "baseline": 80, "target": 40}


# ---------------------------------------------------------------- 실행 추적 보강(2026-10-08)
def lifecycle(today):
    """시도별 영업 생애주기: 개척(자사 0건) · 첫 수주(1건) · 재계약(같은 기관 2건+) · 확대(자사 기관 3곳+)"""
    cs = _jsonl("history/competitor_contracts.jsonl")
    REG = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
    out = {}
    for r in REG:
        own = [c for c in cs if c.get("region") == r and c.get("competitor") == SELF]
        comp = [c for c in cs if c.get("region") == r and c.get("competitor") != SELF]
        orgs = Counter(c.get("org") for c in own)
        stage = "확대" if len(orgs) >= 3 else "재계약" if any(v >= 2 for v in orgs.values()) else "첫 수주" if own else "개척"
        out[r] = {"stage": stage, "own": len(own), "orgs": len(orgs), "comp": len(comp),
                  "own_amt": sum(c.get("amount") or 0 for c in own), "comp_amt": sum(c.get("amount") or 0 for c in comp)}
    return out


def sales_calendar(today, pipeline_records):
    """연간 영업 캘린더(12개월): 연수 입찰 계절성 · 재계약 예상 · 자사 연수 시작 · 교육청 예산 일정(고정)"""
    import training_topics as tt
    months = [((today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)).strftime("%Y-%m") for i in range(12)]
    season = Counter()
    for r in _jsonl("history/training_bids.jsonl"):
        if tt.is_training_bid(r.get("t"), r.get("o")) and r.get("d"):
            season[int(r["d"][5:7])] += 1
    renew = Counter()
    for c in _jsonl("history/competitor_contracts.jsonl"):
        if c.get("date"):
            renew[int(c["date"][5:7])] += 1
    start = Counter()
    for r in pipeline_records or []:
        d = str(r.get("trainStart") or "")
        m = re.search(r"(20\d{2})\D(\d{1,2})", d) or re.search(r"^(\d{1,2})[./월]", d)
        if m:
            start[int(m.group(2) if m.lastindex == 2 else m.group(1))] += 1
    budget = {1: "신학년 계획·예산 배정", 3: "1차 추경 준비", 4: "추경 편성", 5: "추경 집행", 6: "상반기 정산",
              8: "2학기 연수 발주", 9: "본예산 요구", 10: "본예산 편성·국감", 11: "연말 집행(불용 방지)", 12: "연말 집행·이월 확정"}
    rows = []
    for m in months:
        mo = int(m[5:])
        rows.append({"m": m, "season": season.get(mo, 0), "renew": renew.get(mo, 0), "start": start.get(mo, 0), "budget": budget.get(mo, "")})
    return {"months": rows}


def pipe_views(pipeline_records, today):
    """운영DT 기반: 상태 칸반·영업자 성과(익명)·리드타임(계약→연수 시작→종료)"""
    import own_pipeline_export as ope
    from ops_insights import parse_date
    recs = pipeline_records or []
    kan = defaultdict(list)
    for r in recs:
        kan[(r.get("status") or "미정").strip()[:8]].append({"c": (r.get("courseName") or "")[:40], "o": (r.get("org") or "")[:20],
                                                            "r": r.get("region", ""), "a": ope.to_num(r.get("targetAmount"))})
    reps = defaultdict(lambda: {"n": 0, "amt": 0, "rate": []})
    lead = {"contract_to_start": [], "start_to_end": [], "recruit_len": []}
    for r in recs:
        rp = reps[r.get("salesRep") or "(미정)"]
        rp["n"] += 1
        rp["amt"] += ope.to_num(r.get("targetAmount"))
        t, a = ope.to_num(r.get("targetCount")), ope.to_num(r.get("appliedCount"))
        if t:
            rp["rate"].append(min(200, a / t * 100))
        cd, ts, te, rs, re_ = (parse_date(r.get(k)) for k in ("contractDate", "trainStart", "trainEnd", "recruitStart", "recruitEnd"))
        if cd and ts and 0 <= (ts - cd).days <= 365:
            lead["contract_to_start"].append((ts - cd).days)
        if ts and te and 0 <= (te - ts).days <= 365:
            lead["start_to_end"].append((te - ts).days)
        if rs and re_ and 0 <= (re_ - rs).days <= 180:
            lead["recruit_len"].append((re_ - rs).days)
    reps_out = [{"rep": k, "n": v["n"], "amt": v["amt"], "rate": round(sum(v["rate"]) / len(v["rate"]), 1) if v["rate"] else None}
                for k, v in reps.items()]
    return {"kanban": {k: v for k, v in sorted(kan.items(), key=lambda x: -len(x[1]))}, "reps": reps_out, "lead": lead}


def quote_guide():
    """학교 견적 가이드: 학교·교육청 연수 수의계약 금액 분포(사분위)"""
    rows = _jsonl("history/edu_contracts.jsonl")
    def q(a):
        a = sorted(a)
        return {"n": len(a), "p25": a[len(a) // 4], "median": a[len(a) // 2], "p75": a[3 * len(a) // 4]} if len(a) >= 4 else None
    sch = [r["amount"] for r in rows if re.search(r"학교$|유치원$", r.get("org", ""))]
    off = [r["amount"] for r in rows if not re.search(r"학교$|유치원$", r.get("org", ""))]
    remote = [r["amount"] for r in rows if re.search(r"원격", r.get("title", ""))]
    group = [r["amount"] for r in rows if re.search(r"집합|워크숍|연수회|캠프|실습", r.get("title", ""))]
    return {"school": q(sch), "office": q(off), "remote": q(remote), "group": q(group), "n": len(rows)}


def build(pipeline_records=None, today=None):
    today = today or date.today()
    out = {"generated": today.isoformat()}
    for k, fn in (("topic_month", lambda: topic_month(today)), ("rfp_funnel", lambda: rfp_funnel(today)),
                  ("contracts", lambda: contracts_views(today)), ("org_bubble", lambda: org_bubble(today)),
                  ("courses", course_timeline), ("kpi", lambda: kpi_series(today)), ("tags", brief_tags),
                  ("channel", lambda: channel_mix(pipeline_records)), ("lifecycle", lambda: lifecycle(today)),
                  ("calendar", lambda: sales_calendar(today, pipeline_records)), ("pipe", lambda: pipe_views(pipeline_records, today)),
                  ("quote", quote_guide)):
        try:
            out[k] = fn()
        except Exception as e:
            out[k] = {"error": str(e)[:200]}
    return out


if __name__ == "__main__":
    r = build([])
    print(json.dumps({k: (list(v.keys()) if isinstance(v, dict) else len(v)) for k, v in r.items()}, ensure_ascii=False))
    print(json.dumps(r["topic_month"]["rows"][:2], ensure_ascii=False)[:400], r["rfp_funnel"], r["tags"]["tags"])
