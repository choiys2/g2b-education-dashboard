#!/usr/bin/env python3
"""
B2G영업 탭 고도화 4종 - 이미 모은 데이터를 엮기만 한다(API 호출 없음, combine_dashboard.py 가 부른다).

  A. budget_capacity : 지방교육재정알리미 시도 세입·세출·차액 x 계약 점유 x 교원 수 -> 시도별 예산 여력·영업 우선순위
  C. recruit_alerts  : 운영DT 목표인원·신청현황·신청기간 -> 모집률 조기경보(경과 기간 대비 신청률)
  E. recontract      : 계약정보(수의 포함) 계약일 + 1년 -> 경쟁사 재발주 예상 캘린더(D-60 선제 접촉)
  F. venue_plan      : 운영DT 연수 일정(집합·혼합형) x 관광공사 장소 x 기상청 예보 -> 집합연수 운영 지원

결과는 암호화된 대시보드에만 실린다. 운영DT 사업명이 들어가므로 history/(공개 저장소)에는 쓰지 않는다.
"""
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SELF = "비바샘연수원"
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
LONG = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
        "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원",
        "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
        "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주"}


def short_region(s):
    s = (s or "").strip()
    if s in REGIONS:
        return s
    if s in LONG:
        return LONG[s]
    for r in REGIONS:
        if s.startswith(r):
            return r
    return ""


def parse_date(s, default_year=None):
    import pipeline_comms
    return pipeline_comms.parse_date(str(s or ""), default_year or date.today().year)


def num(s):
    """'123명', '1,234', '120/200' -> 앞 숫자"""
    m = re.search(r"\d[\d,]*", str(s or ""))
    return int(m.group(0).replace(",", "")) if m else 0


# ---------------------------------------------------------------- A. 예산 여력
def budget_capacity(finance, contracts, schools, today=None):
    """finance: {시도: {연도: {in,out,diff}}}, contracts: 계약 레코드, schools: [{s, t}]"""
    fin = {}
    for k, v in (finance or {}).items():
        r = short_region(k)
        if r:
            fin[r] = v
    if not fin:
        return {"available": False}
    years = sorted({y for v in fin.values() for y in v})
    y = max((yy for yy in years if sum(1 for v in fin.values() if v.get(yy, {}).get("out")) >= 10), default=years[-1])
    py = str(int(y) - 1)
    own, tot = defaultdict(int), defaultdict(int)
    own_n = defaultdict(int)
    for c in contracts or []:
        r = c.get("region")
        if r not in REGIONS:
            continue
        tot[r] += c.get("amount") or 0
        if c.get("competitor") == SELF:
            own[r] += c.get("amount") or 0
            own_n[r] += 1
    teachers = defaultdict(int)
    for s in schools or []:
        teachers[s.get("s")] += s.get("t") or 0
    rows = []
    for r in REGIONS:
        cur, prev = fin.get(r, {}).get(y, {}), fin.get(r, {}).get(py, {})
        if not cur.get("out"):
            continue
        diff = cur.get("diff", (cur.get("in") or 0) - cur["out"])
        rows.append({"region": r, "in": cur.get("in", 0), "out": cur["out"], "diff": diff,
                     "diff_rate": round(diff / cur["in"] * 100, 1) if cur.get("in") else None,
                     "out_growth": round((cur["out"] / prev["out"] - 1) * 100, 1) if prev.get("out") else None,
                     "diff_prev": prev.get("diff"),
                     "teachers": teachers.get(r, 0),
                     "out_per_teacher": round(cur["out"] / teachers[r]) if teachers.get(r) else None,
                     "mkt": tot.get(r, 0), "own": own.get(r, 0), "own_n": own_n.get(r, 0),
                     "share": round(own[r] / tot[r] * 100, 1) if tot.get(r) else None})
    # 점수: 순위 백분위로 정규화(시도 간 규모 차이가 커서 값 비례보다 안정적)
    def pct(key):
        vals = sorted(x[key] or 0 for x in rows)
        return {id(x): vals.index(x[key] or 0) / max(1, len(vals) - 1) * 100 for x in rows}
    p_diff, p_rate, p_t, p_mkt = pct("diff"), pct("diff_rate"), pct("teachers"), pct("mkt")
    for x in rows:
        room = 100 - min(100, x["share"] if x["share"] is not None else 0)
        x["score"] = round(p_diff[id(x)] * 0.25 + p_rate[id(x)] * 0.15 + p_t[id(x)] * 0.25 + p_mkt[id(x)] * 0.15 + room * 0.20, 1)
        if x["diff_prev"] and x["diff"] < x["diff_prev"] * 0.8:
            x["flag"] = "여력 감소"
        elif (x["share"] or 0) < 10 and x["score"] >= 55:
            x["flag"] = "공략 우선"
        elif (x["share"] or 0) >= 30:
            x["flag"] = "수성"
        else:
            x["flag"] = ""
    rows.sort(key=lambda x: -x["score"])
    nat = {k: sum(x[k] or 0 for x in rows) for k in ("in", "out", "diff")}
    return {"available": True, "year": y, "prev_year": py, "years": years, "rows": rows, "national": nat,
            "contract_span": [min((c["date"] for c in contracts or [] if c.get("date")), default=""),
                              max((c["date"] for c in contracts or [] if c.get("date")), default="")]}


# ---------------------------------------------------------------- C. 모집률 조기경보
def recruit_alerts(records, today=None):
    today = today or date.today()
    out = []
    for i, r in enumerate(records or []):
        if re.search(r"완료|종료|취소|정산", str(r.get("status") or "")):
            continue
        tgt, app = num(r.get("targetCount")), num(r.get("appliedCount"))
        s, e = parse_date(r.get("recruitStart")), parse_date(r.get("recruitEnd"))
        if not tgt or not e:
            continue
        if s and s > e:
            s = None
        rate = app / tgt
        if s and today < s:
            continue  # 모집 전
        days_left = (e - today).days
        if days_left < -14:
            continue  # 마감 2주 지난 건은 경보 대상 아님
        if s:
            span = max(1, (e - s).days + 1)
            elapsed = min(1.0, max(0.02, ((today - s).days + 1) / span))
        else:
            elapsed = 1.0 if days_left < 0 else None
        if days_left < 0:
            level = "미달 마감" if rate < 1 else "달성"
        elif rate >= 1:
            level = "달성"
        elif elapsed is None:
            level = "주의" if days_left <= 7 and rate < 0.7 else "정상"
        elif rate < elapsed * 0.6 or (days_left <= 7 and rate < 0.7):
            level = "경보"
        elif rate < elapsed * 0.9:
            level = "주의"
        else:
            level = "정상"
        proj = min(9.99, rate / elapsed) if elapsed else None
        out.append({"i": i, "course": r.get("courseName", ""), "org": r.get("org", ""), "region": r.get("region", ""),
                    "field": r.get("field", ""), "target": tgt, "applied": app, "rate": round(rate * 100, 1),
                    "elapsed": round(elapsed * 100) if elapsed else None, "proj": round(proj * 100) if proj else None,
                    "start": s.isoformat() if s else "", "end": e.isoformat(), "days_left": days_left,
                    "short": max(0, tgt - app), "level": level})
    order = {"경보": 0, "주의": 1, "미달 마감": 2, "정상": 3, "달성": 4}
    out.sort(key=lambda x: (order[x["level"]], x["days_left"]))
    cnt = defaultdict(int)
    for x in out:
        cnt[x["level"]] += 1
    open_ = [x for x in out if x["days_left"] >= 0]
    return {"items": out, "counts": dict(cnt),
            "open_target": sum(x["target"] for x in open_), "open_applied": sum(x["applied"] for x in open_),
            "short_total": sum(x["short"] for x in out if x["level"] in ("경보", "주의"))}


# ---------------------------------------------------------------- E. 재계약 캘린더
def norm_title(t):
    t = re.sub(r"\(?20\d{2}\)?\s*(년|학년도)?\.?|\d+\s*(기|차|회)|제\s*\d+", " ", t or "")
    t = re.sub(r"용역|위탁|운영|계약|변경|[\s\W_]+", "", t)
    return t


def sim(a, b):
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0
    A = {a[i:i + 2] for i in range(len(a) - 1)}
    B = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(A & B) / max(1, min(len(A), len(B)))


def recontract(contracts, today=None, ahead=150, behind=21):
    today = today or date.today()
    cs = [{**c, "_d": date.fromisoformat(c["date"][:10])} for c in contracts or [] if c.get("date")]
    items = []
    for c in cs:
        try:
            ann = c["_d"].replace(year=c["_d"].year + 1)
        except ValueError:
            ann = c["_d"] + timedelta(days=365)
        dd = (ann - today).days
        if not -behind <= dd <= ahead:
            continue
        # 이미 재발주됐는지: 같은 기관·비슷한 사업명 계약이 원 계약 200일 뒤에 있으면
        again = [x for x in cs if x is not c and x.get("org") == c.get("org") and (x["_d"] - c["_d"]).days >= 200
                 and sim(x.get("course"), c.get("course")) >= 0.6]
        again.sort(key=lambda x: x["_d"])
        items.append({"date": c["date"][:10], "ann": ann.isoformat(), "dday": dd, "contact": (ann - timedelta(days=60)).isoformat(),
                      "competitor": c.get("competitor"), "course": c.get("course"), "org": c.get("org"),
                      "region": c.get("region"), "amount": c.get("amount") or 0, "method": c.get("method") or "",
                      "kind": "방어" if c.get("competitor") == SELF else "탈환",
                      "renewed": ({"date": again[0]["date"][:10], "competitor": again[0].get("competitor")} if again else None)})
    items.sort(key=lambda x: x["ann"])
    months = defaultdict(lambda: defaultdict(lambda: {"n": 0, "amt": 0}))
    for x in items:
        if x["renewed"]:
            continue
        m = months[x["ann"][:7]][x["competitor"]]
        m["n"] += 1
        m["amt"] += x["amount"]
    pend = [x for x in items if not x["renewed"]]
    return {"items": items, "months": {k: dict(v) for k, v in sorted(months.items())},
            "summary": {"pending": len(pend), "win_back": sum(1 for x in pend if x["kind"] == "탈환"),
                        "win_back_amt": sum(x["amount"] for x in pend if x["kind"] == "탈환"),
                        "defend": sum(1 for x in pend if x["kind"] == "방어"),
                        "defend_amt": sum(x["amount"] for x in pend if x["kind"] == "방어"),
                        "now": sum(1 for x in pend if x["dday"] <= 60),
                        "renewed": sum(1 for x in items if x["renewed"])},
            "ahead": ahead, "span": [min((c["date"] for c in cs), default=""), max((c["date"] for c in cs), default="")]}


# ---------------------------------------------------------------- F. 집합연수 운영 지원
OFFLINE = re.compile(r"집합|대면|블렌디드|혼합|워크숍|워크샵|캠프|합숙|오프라인|현장|연수회|설명회|박람회|아카데미|포럼|세미나|컨퍼런스|콘퍼런스")
CITY = {"서울": "서울", "인천": "인천", "경기": "수원", "강원": "춘천", "충북": "청주", "세종": "세종", "대전": "대전",
        "전북": "전주", "광주": "광주", "전남": "광주", "대구": "대구", "부산": "부산", "울산": "울산", "경남": "창원",
        "경북": "안동", "충남": "홍성", "제주": "제주"}
SEASON = {1: "한파·폭설", 2: "한파·폭설", 3: "황사·미세먼지", 4: "황사·미세먼지", 5: "", 6: "장마 시작",
          7: "장마·폭염", 8: "폭염·태풍", 9: "태풍", 10: "", 11: "", 12: "한파·폭설"}


def venue_plan(records, venues, weather, today=None, ahead=60):
    today = today or date.today()
    regions = (venues or {}).get("regions", {})
    wx = {c["city"]: c for c in (weather or {}).get("cities", [])}
    wdates = (weather or {}).get("dates") or [today.strftime("%Y%m%d"), (today + timedelta(days=1)).strftime("%Y%m%d")]
    items, online = [], 0
    for i, r in enumerate(records or []):
        if re.search(r"완료|종료|취소", str(r.get("status") or "")):
            continue
        st = parse_date(r.get("trainStart"))
        if not st or not -3 <= (st - today).days <= ahead:
            continue
        blob = f"{r.get('courseName', '')} {r.get('field', '')} {r.get('gisu', '')}"
        if not OFFLINE.search(blob):
            online += 1
            continue
        reg = short_region(r.get("region")) or short_region(r.get("org"))
        vs = regions.get(reg, [])
        pick = [v for v in vs if v.get("k") == "연수·회의"][:3]
        pick += [v for v in vs if v.get("k") == "숙박"][:5 - len(pick)]
        en = parse_date(r.get("trainEnd")) or st
        w = None
        city = wx.get(CITY.get(reg, ""))
        if city:
            for key, ds in zip(("today", "tomorrow", "d2"), wdates):
                d = date(int(ds[:4]), int(ds[4:6]), int(ds[6:]))
                if st <= d <= en and city.get(key):
                    f = city[key]
                    risk = (f.get("pop") or 0) >= 60 or (f.get("tmax") or 0) >= 33 or (f.get("tmin") if f.get("tmin") is not None else 99) <= -10
                    w = {"date": d.isoformat(), "city": city["city"], **f, "risk": bool(risk)}
                    break
        items.append({"i": i, "course": r.get("courseName", ""), "org": r.get("org", ""), "region": reg,
                      "start": st.isoformat(), "end": en.isoformat(), "dday": (st - today).days,
                      "target": num(r.get("targetCount")), "mode": OFFLINE.search(blob).group(0),
                      "venues": [{k: v.get(k) for k in ("n", "k", "addr", "tel", "x", "y")} for v in pick],
                      "venue_total": len(vs), "weather": w, "season": SEASON.get(st.month, "")})
    items.sort(key=lambda x: x["start"])
    return {"items": items, "online_upcoming": online, "ahead": ahead,
            "checklist": ["장소 가계약(D-45)", "강사·보조인력 확정(D-30)", "참가자 안내 공문·숙박 배정(D-21)",
                          "교재·명찰·수료증 인쇄(D-10)", "날씨·교통 재확인, 우천·폭염 대체 동선(D-3)", "출결·만족도 조사 준비(D-1)"]}


def build(records, contracts, finance, schools, venues, weather, today=None):
    today = today or date.today()
    out = {"generated": today.isoformat()}
    for k, fn in (("budget", lambda: budget_capacity(finance, contracts, schools, today)),
                  ("recruit", lambda: recruit_alerts(records, today)),
                  ("recontract", lambda: recontract(contracts, today)),
                  ("venue_plan", lambda: venue_plan(records, venues, weather, today))):
        try:
            out[k] = fn()
        except Exception as e:  # 한 기능 오류가 대시보드 조합 전체를 막지 않게
            out[k] = {"error": str(e)[:200]}
    return out


def load_inputs():
    def j(p, default):
        try:
            return json.loads((HERE / p).read_text(encoding="utf-8"))
        except Exception:
            return default
    contracts = []
    p = HERE / "history" / "competitor_contracts.jsonl"
    if p.exists():
        contracts = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    finance = j("live/eduinfo_export.json", {}).get("finance") or j("history/eduinfo_finance.json", {}).get("finance") or {}
    schools = j("history/schoolinfo_market.json", {}).get("schools", [])
    venues = j("live/tour_venues.json", None) or j("history/tour_venues.json", {})
    weather = j("live/weather.json", {})
    return contracts, finance, schools, venues, weather


if __name__ == "__main__":
    import sys
    recs = json.loads((HERE / "live" / "own_pipeline_export.json").read_text(encoding="utf-8")).get("records", [])
    res = build(recs, *load_inputs())
    print(json.dumps({k: (v.get("summary") or v.get("counts") or len(v.get("rows", v.get("items", [])))) if isinstance(v, dict) else v
                      for k, v in res.items()}, ensure_ascii=False))
