#!/usr/bin/env python3
"""
전략 인텔리전스(관리 탭 '🧠 전략 인텔리전스' 칸) + CP '비상 강점 5분야 온도계' 데이터.

  관리 칸(관리 비밀번호 암호문 안 data-p): 예측 추적·이슈 수명 곡선·주간 종합·예산 레이더·연수 수요 캘린더·
  제안서 초안 재료·경쟁사 낙찰 패턴·경쟁사 연수 비교·빅테크 대비·교대 지도·연수+교재 결합 추천·브리핑 품질 점수.
  CP 온도계(strength5): 분야별 소식 '건수'만(제목·출처 없음) - 방법론 비노출.
  모든 값은 저장소에 이미 쌓인 기록(history/·strategy_briefings/·static_data/)에서 계산하고, 외부 호출은 하지 않는다.
"""
import html
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

E = html.escape
HERE = Path(__file__).resolve().parent
H = HERE / "history"
KST = timezone(timedelta(hours=9))
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
COMP = ["티처빌", "아이스크림", "비바샘연수원", "한국교원캠퍼스", "에듀니티"]


def today():
    return datetime.now(KST).date()


def _jsonl(p):
    try:
        return [json.loads(l) for l in (H / p).read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def _json(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _sido(s):
    s = s or ""
    if "전남광주" in s:
        return "전남"
    for k in SIDO:
        if k in s:
            return k
    for a, b in [("서울", "서울"), ("경기", "경기"), ("강원", "강원"), ("충청북", "충북"), ("충청남", "충남"), ("전라북", "전북"), ("전북특별", "전북"), ("전라남", "전남"), ("경상북", "경북"), ("경상남", "경남"), ("제주", "제주")]:
        if a in s:
            return b
    return ""


# ── 소식 모음: 교육청 소식(누적) + 레이더 최근 7일, 제목 기준 중복 제거 ──
def news_pool():
    out, seen = [], set()
    for r in _jsonl("edu_office_signals.jsonl"):
        t = (r.get("t") or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append({"d": r.get("d", ""), "t": t, "s": _sido(r.get("s")), "u": r.get("u", ""), "src": r.get("src", ""), "tp": r.get("tp") or [], "plan": bool(r.get("plan"))})
    R = _json(H / "edutech_radar.json", {}) or {}
    for it in R.get("items") or []:
        t = (it.get("title") or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append({"d": (it.get("date") or "")[:10], "t": t, "s": _sido(t), "u": it.get("orig") or it.get("url", ""), "src": it.get("source", ""), "tp": [], "plan": False})
    ch = R.get("channels") or {}
    for v in (ch.values() if isinstance(ch, dict) else []):
        for it in v or []:
            t = (it.get("title") or "").strip()
            if t and t not in seen:
                seen.add(t)
                out.append({"d": (it.get("date") or "")[:10], "t": t, "s": _sido(t), "u": it.get("url", ""), "src": it.get("source", ""), "tp": [], "plan": False, "ch": 1, "sum": (it.get("summary") or "")[:160]})
    return out


TOPICS = [  # 이슈 수명 곡선·결합 추천에 쓰는 주제(키워드는 제목 기준)
    ("AI 부정행위·평가", r"부정행위|커닝|AI\s?안경|스마트\s?안경|평가\s?(혁신|설계|신뢰)|서·논술|서논술"),
    ("빅테크 교사 연수", r"MS|마이크로소프트|구글|AWS|아마존|빅테크|오픈AI|엔비디아"),
    ("AI·디지털 교육", r"AI|인공지능|디지털|에듀테크|코딩|바이브"),
    ("독서·인문", r"독서|북웨이브|책\s?쓰|도서관|인문|그림책|한 학기 한 권"),
    ("진로·진학", r"진로|진학|대입|수시|학생부|전환기"),
    ("기초학력·수학", r"기초학력|수해력|문해력|수학|느린\s?학습"),
    ("교권·생활지도", r"교권|민원|생활지도|학교폭력|위기\s?학생"),
    ("늘봄·돌봄", r"늘봄|돌봄|방과후"),
]
STRENGTH5 = [  # 비상 강점 5분야(CP 온도계)
    ("인문소양·독서", "📚", r"독서|북웨이브|책\s?쓰|도서관|인문|그림책|한 학기 한 권|문해"),
    ("진로·진학", "🧭", r"진로|진학|대입|수시|학생부|전환기|면접"),
    ("한국사·역사", "🏯", r"한국사|역사|독도|근현대|통일교육|평화"),
    ("과학·탐구", "🔬", r"과학|탐구|STEAM|실험|영재|발명"),
    ("수학", "📐", r"수학|수해력|연산"),
]


def series(pool, rx, days=14):
    t0 = today()
    ds = [(t0 - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    c = Counter(r["d"] for r in pool if re.search(rx, r["t"]))
    return ds, [c.get(d, 0) for d in ds]


def trend_of(v):
    a, b = sum(v[-4:]) / 4, sum(v[-11:-4]) / 7 if len(v) >= 11 else 0
    if sum(v) == 0:
        return "조용"
    if b == 0 and a > 0:
        return "새로 뜸"
    r = a / b if b else 0
    return "상승" if r >= 1.3 else "하강" if r <= .7 else "유지"


# ── ② 예측 추적 · ④ 주간 종합 · ⑭ 품질 점수 (전략 브리핑 복호본) ──
STOP = set("이번 주 다음 가능성 확인 필요 신호 여부 확대 추진 관련 교육 교사 학교 연수 시장 정책 공고 건수 발표 증가 감소 중 및 등 수 의 후 전".split())


def kw(s):
    return [w for w in re.findall(r"[가-힣A-Za-z]{2,}", re.sub(r"<[^>]+>", "", s or "")) if w not in STOP][:8]


def forecast_track(issues, pool):
    out = []
    for iss in issues:
        d0 = iss.get("date", "")
        if not d0 or d0 > (today() - timedelta(days=2)).isoformat():
            continue
        for w in iss.get("watch") or []:
            ks = kw(w.get("issue", "") + " " + w.get("kpi_signal", ""))
            if not ks:
                continue
            hits = [r for r in pool if r["d"] > d0 and sum(1 for k in ks if k in r["t"]) >= min(2, len(ks))]
            n = len(hits)
            out.append({"d": d0, "issue": re.sub(r"<[^>]+>", "", w.get("issue", "")), "fc": re.sub(r"<[^>]+>", "", w.get("forecast", "")), "n": n,
                        "st": "신호 확인" if n >= 3 else "약한 신호" if n else "아직 없음", "ex": [{"t": h["t"], "u": h["u"], "d": h["d"]} for h in sorted(hits, key=lambda x: x["d"], reverse=True)[:2]]})
    return out[:24]


def weekly(issues):
    t0 = today()
    wk = [i for i in issues if i.get("date", "") >= (t0 - timedelta(days=7)).isoformat()]
    if not wk:
        return None
    strip = lambda s: re.sub(r"<[^>]+>", "", s or "")
    heads = [strip(s) for i in wk for s in (i.get("summary") or [])[:2]][:6]
    seen, dec = set(), []
    for i in wk:
        for o in i.get("opportunities") or []:
            k = strip(o.get("idea"))[:24]
            if k not in seen:
                seen.add(k)
                dec.append({"idea": strip(o.get("idea")), "action": strip(o.get("action")), "timing": strip(o.get("timing")), "d": i.get("date")})
    seen, nxt = set(), []
    for i in wk:
        for w in i.get("watch") or []:
            k = strip(w.get("issue"))[:20]
            if k not in seen:
                seen.add(k)
                nxt.append({"issue": strip(w.get("issue")), "kpi": strip(w.get("kpi_signal")), "fc": strip(w.get("forecast"))})
    return {"from": wk[-1].get("date"), "to": wk[0].get("date"), "n": len(wk), "heads": heads, "decide": dec[:3], "next": nxt[:3]}


def quality(issues):
    out = []
    for i in issues:
        tn = i.get("top_news") or []
        urls = [x.get("url", "") for x in tn]
        orig = sum(1 for u in urls if u and "news.google" not in u) / max(1, len(urls))
        div = len({x.get("source") for x in tn}) / max(1, len(tn))
        ch = i.get("changes") or []
        sep = sum(1 for c in ch if c.get("fact") and c.get("interpretation")) / max(1, len(ch))
        cnt = 1 if 5 <= len(tn) <= 10 else .5 if tn else 0
        comp = (1 if 3 <= len(i.get("summary") or []) <= 5 else .5) * .4 + (1 if len(i.get("opportunities") or []) >= 3 else .5) * .3 + (1 if len(i.get("watch") or []) >= 3 else .5) * .3
        sc = round(orig * 30 + div * 20 + sep * 20 + cnt * 15 + comp * 15)
        out.append({"d": i.get("date"), "score": sc, "orig": round(orig * 100), "div": round(div * 100), "sep": round(sep * 100), "n": len(tn)})
    return sorted(out, key=lambda x: x["d"] or "")[-30:]


# ── ⑤ 예산 레이더 ──
BUDGET_RX = r"예산|의회|본예산|추경|삭감|증액|재정"
TOPIC_TAG = [("연수", r"연수|교원|교사"), ("AI", r"AI|인공지능|디지털|에듀테크"), ("독서", r"독서|도서|책"), ("진로", r"진로|진학"), ("늘봄", r"늘봄|돌봄"), ("기초학력", r"기초학력|문해|수해")]


def budget_radar(pool):
    since = (today() - timedelta(days=21)).isoformat()
    by = defaultdict(list)
    for r in pool:
        if r["d"] >= since and re.search(BUDGET_RX, r["t"]) and r["s"]:
            by[r["s"]].append(r)
    rows = []
    for s in SIDO:
        L = sorted(by.get(s, []), key=lambda x: x["d"], reverse=True)
        tags = Counter(tg for r in L for tg, rx in TOPIC_TAG if re.search(rx, r["t"]))
        cut = sum(1 for r in L if re.search(r"삭감|감액|축소|험로", r["t"]))
        rows.append({"s": s, "n": len(L), "tags": dict(tags), "cut": cut, "items": [{"t": r["t"], "u": r["u"], "d": r["d"]} for r in L[:4]],
                     "score": len(L) * 2 + sum(tags.values()) - cut})
    return sorted(rows, key=lambda x: -x["score"])


# ── ⑥ 연수 수요 캘린더(과거 연수 계약 월 + 발주계획) ──
TRAIN_RX = r"연수|원격|직무|역량\s?강화|교원\s?교육"


def demand_calendar():
    t0 = today()
    hist = defaultdict(Counter)
    for r in _jsonl("competitor_contracts.jsonl") + _jsonl("competitor_wins.jsonl"):
        org, dt = r.get("org", ""), r.get("date", "")
        if not dt or not re.search(r"교육청|교육지원청", org):
            continue
        s = _sido(org) or _sido(r.get("region", ""))
        if s:
            hist[s][int(dt[5:7])] += 1
    plans = defaultdict(list)
    for r in _jsonl("order_plans.jsonl"):
        if re.search(TRAIN_RX, r.get("t", "")) and r.get("m"):
            s = _sido(r.get("r", "")) or _sido(r.get("o", ""))
            if s:
                plans[s].append({"t": r.get("t", ""), "m": int(r["m"]), "a": r.get("a", 0), "o": r.get("o", "")})
    rows = []
    for s in SIDO:
        mon = hist.get(s, Counter())
        nxt = []
        for k in range(0, 4):  # 이번 달 포함 4개월
            y, m = t0.year + (t0.month - 1 + k) // 12, (t0.month - 1 + k) % 12 + 1
            start = date(y, m, 1)
            exp = mon.get(m, 0) + sum(1 for p in plans.get(s, []) if p["m"] == m)
            if exp:
                dday = (start - timedelta(days=30) - t0).days if k else None  # 이번 달은 '진행 중'
                nxt.append({"ym": f"{y}-{m:02d}", "n": exp, "dday": dday})
        rows.append({"s": s, "months": [mon.get(m, 0) for m in range(1, 13)], "plans": plans.get(s, [])[:5], "next": nxt,
                     "alert": any(x["dday"] is not None and x["dday"] <= 7 for x in nxt)})  # 제안서 준비 시작점(D-30)이 1주 안
    return rows


# ── ⑧ 경쟁사 낙찰 패턴 ──
BANDS = [("1천만 미만", 0, 1e7), ("1천~3천만", 1e7, 3e7), ("3천만~1억", 3e7, 1e8), ("1억 이상", 1e8, 1e18)]


def win_pattern():
    rows = _jsonl("competitor_contracts.jsonl")
    for r in _jsonl("competitor_wins.jsonl"):
        rows.append({"competitor": r.get("competitor"), "course": r.get("course", ""), "org": r.get("org", ""), "region": r.get("region", ""), "amount": r.get("amount"), "date": r.get("date", ""), "method": "입찰"})
    by = defaultdict(list)
    for r in rows:
        try:
            a = float(r.get("amount") or 0)
        except Exception:
            a = 0
        if r.get("competitor") and a > 0:
            by[r["competitor"]].append((a, r))
    out = []
    for c, L in sorted(by.items(), key=lambda x: -len(x[1])):
        am = [a for a, _ in L]
        reg = Counter(_sido(r.get("org", "")) or _sido(r.get("region", "")) for _, r in L)
        th = Counter(n for _, r in L for n, rx in TOPICS if re.search(rx, r.get("course", "")))
        out.append({"c": c, "n": len(L), "sum": sum(am), "med": statistics.median(am), "bands": [sum(1 for a in am if lo <= a < hi) for _, lo, hi in BANDS],
                    "reg": [k for k, _ in reg.most_common(4) if k], "themes": [k for k, _ in th.most_common(3)],
                    "suic": sum(1 for _, r in L if "수의" in (r.get("method") or ""))})
    return {"bands": [b[0] for b in BANDS], "rows": out[:6]}


# ── ⑨ 경쟁사 연수 주제 비교 · ⑩ 빅테크 대비 · ⑬ 결합 추천 ──
CTOP = [("AI·디지털", r"AI|인공지능|디지털|챗GPT|클로드|Claude|코딩|에듀테크|자동화"), ("수업·평가", r"수업|평가|과정중심|서·논술|프로젝트|질문"),
        ("독서·인문", r"독서|인문|문학|그림책|글쓰기|역사|철학"), ("진로·진학", r"진로|진학|입시|학생부"), ("생활지도·교권", r"생활지도|교권|학급|상담|민원|관계"),
        ("기초학력·문해", r"기초학력|문해|수해|느린"), ("교과 전문", r"국어|영어|수학|과학|사회|음악|미술|체육"), ("힐링·교양", r"힐링|마음|건강|요가|여행|교양|취미|경제")]


def course_compare():
    cat = (_json(H / "competitor_course_catalog.json", {}) or {}).get("companies") or {}
    new = _jsonl("competitor_new_courses.jsonl")
    since = (today() - timedelta(days=60)).isoformat()
    rows = []
    for co, v in cat.items():
        cs = v.get("courses") or []
        cnt = Counter(n for c in cs for n, rx in CTOP if re.search(rx, (c.get("title") or "") + " " + (c.get("category") or "")))
        nw = Counter(n for r in new if r.get("company") == co and r.get("first_seen", "") >= since for n, rx in CTOP if re.search(rx, r.get("title", "")))
        bundle = sum(1 for c in cs if re.search(r"연수\s?\+|\+\s?(도서|교구|교재)", c.get("title") or ""))
        rows.append({"co": co, "total": len(cs), "cnt": [cnt.get(n, 0) for n, _ in CTOP], "new": [nw.get(n, 0) for n, _ in CTOP], "bundle": bundle})
    own = next((r for r in rows if r["co"] == "비바샘연수원"), None)
    gaps = []
    if own:
        for i, (n, _) in enumerate(CTOP):
            oth = max([r["cnt"][i] for r in rows if r["co"] != "비바샘연수원"] or [0])
            if oth and own["cnt"][i] * 3 < oth:
                gaps.append(n)
    newest = sorted([r for r in new if r.get("first_seen", "") >= since], key=lambda r: r.get("first_seen", ""), reverse=True)[:12]
    return {"topics": [n for n, _ in CTOP], "rows": rows, "gaps": gaps, "newest": [{"co": r.get("company"), "t": r.get("title"), "d": r.get("first_seen"), "p": r.get("price")} for r in newest]}


BIGTECH_RX = r"MS|마이크로소프트|Microsoft|구글|Google|AWS|아마존|빅테크|오픈AI|OpenAI|엔비디아|앤트로픽|Anthropic"


def bigtech(pool):
    news = [r for r in pool if re.search(BIGTECH_RX, r["t"]) and re.search(r"교사|교원|연수|학교|교육", r["t"])]
    news = sorted(news, key=lambda r: r["d"], reverse=True)[:10]
    cat = (_json(H / "competitor_course_catalog.json", {}) or {}).get("companies") or {}
    own = [c for c in (cat.get("비바샘연수원") or {}).get("courses") or [] if re.search(r"AI|인공지능|디지털|챗GPT|클로드|Claude|코딩|자동화|에듀테크", c.get("title") or "")]
    credit = sum(1 for c in own if re.search(r"학점", c.get("credit") or ""))
    subj = sum(1 for c in own if re.search(r"국어|영어|수학|과학|사회|교과|수업", c.get("title") or ""))
    evalc = sum(1 for c in own if re.search(r"평가|과정중심|피드백", c.get("title") or ""))
    return {"news": [{"t": r["t"], "u": r["u"], "d": r["d"]} for r in news], "own_n": len(own), "own": [{"t": c.get("title"), "cr": c.get("credit"), "p": c.get("price")} for c in own[:12]],
            "credit": credit, "subj": subj, "eval": evalc}


def bundle_reco(pool, curves, cc):
    rising = [c for c in curves if c["trend"] in ("상승", "새로 뜸") or sum(c["v"][-7:]) >= 5]
    tmap = {"AI 부정행위·평가": "수업·평가", "빅테크 교사 연수": "AI·디지털", "AI·디지털 교육": "AI·디지털", "독서·인문": "독서·인문", "진로·진학": "진로·진학",
            "기초학력·수학": "기초학력·문해", "교권·생활지도": "생활지도·교권", "늘봄·돌봄": "힐링·교양"}
    out = []
    for c in rising[:5]:
        ct = tmap.get(c["name"])
        i = cc["topics"].index(ct) if ct in cc["topics"] else -1
        own = next((r for r in cc["rows"] if r["co"] == "비바샘연수원"), None)
        oth = [(r["co"], r["cnt"][i]) for r in cc["rows"] if r["co"] != "비바샘연수원"] if i >= 0 else []
        out.append({"issue": c["name"], "trend": c["trend"], "n7": sum(c["v"][-7:]), "ctopic": ct or "-", "own": own["cnt"][i] if own and i >= 0 else 0,
                    "rival": max(oth, key=lambda x: x[1]) if oth else None, "bundle_rival": max([r["bundle"] for r in cc["rows"] if r["co"] != "비바샘연수원"] or [0])})
    return out


# ── ⑪ 교대 지도 ──
UNI_GEO = {"서울교육대학교": (37.4897, 127.0154), "경인교육대학교": (37.4546, 126.6969), "춘천교육대학교": (37.8768, 127.7438), "청주교육대학교": (36.6236, 127.4708),
           "공주교육대학교": (36.4521, 127.1214), "전주교육대학교": (35.8128, 127.1394), "광주교육대학교": (35.1801, 126.9061), "진주교육대학교": (35.1868, 128.0886),
           "대구교육대학교": (35.8364, 128.5900), "부산교육대학교": (35.1971, 129.0726), "한국교원대학교": (36.6097, 127.3567), "제주대학교 교육대학": (33.5048, 126.5296),
           "이화여자대학교 초등교육과": (37.5618, 126.9468)}
RIVAL_RX = [("YBM", r"YBM|와이비엠"), ("천재교육", r"천재"), ("미래엔", r"미래엔"), ("동아출판", r"동아출판"), ("아이스크림", r"아이스크림"), ("티처빌", r"티처빌"), ("비상", r"비상교육|비바샘")]


def univ_map(pool):
    D = _json(HERE / "static_data/industry_trend_2027.json", {}) or {}
    unis = D.get("universities_edu") or []
    try:
        import textbook_authors as ta
        au = ta.edu_univ_authors() or {}
    except Exception:
        au = {}
    rows = []
    for u in unis:
        nm = u.get("name", "")
        sh = (u.get("short") or nm).replace("교육대학교", "교대")
        keyw = [sh[:2], nm[:2]]
        mou = []
        for r in pool:
            if re.search(r"교대|교육대학교|교원대|교육대학|초등교육과", r["t"]) and re.search(r"협약|MOU|맞손|공동연구|협력", r["t"]) and any(k and k in r["t"] for k in [sh, nm[:4]]):
                who = [n for n, rx in RIVAL_RX if re.search(rx, r["t"] + " " + r.get("sum", ""))]
                mou.append({"t": r["t"], "u": r["u"], "d": r["d"], "who": who})
        a = au.get(nm) or au.get(u.get("short")) or []
        ll = UNI_GEO.get(nm)
        rows.append({"n": nm, "sh": u.get("short") or nm, "s": u.get("sido", ""), "ll": ll, "au": len(a), "mou": mou[:3],
                     "rival": sorted({w for m in mou for w in m["who"] if w != "비상"}), "own": any("비상" in m["who"] for m in mou)})
    return rows


# ── ⑫ CP 강점 5분야 온도계(건수만) ──
def strength5(pool=None):
    pool = pool if pool is not None else news_pool()
    out = []
    for name, ic, rx in STRENGTH5:
        ds, v = series(pool, rx, 14)
        out.append({"name": name, "ic": ic, "v": v, "n7": sum(v[-7:]), "prev7": sum(v[:7]), "trend": trend_of(v)})
    return {"asof": today().isoformat(), "days": series(pool, "x", 14)[0], "rows": out}


# ── 묶음 ──
def payload(issues=None):
    pool = news_pool()
    if issues is None:
        try:
            import strategy_crypto
            r = strategy_crypto.load_all()
            issues = r.get("issues") or []
        except Exception:
            issues = []
    issues = sorted([i for i in issues if isinstance(i, dict)], key=lambda x: x.get("date", ""), reverse=True)
    days = series(pool, "x", 14)[0]
    curves = []
    for n, rx in TOPICS:
        _, v = series(pool, rx, 14)
        curves.append({"name": n, "v": v, "trend": trend_of(v), "peak": days[v.index(max(v))] if any(v) else ""})
    cc = course_compare()
    sido_sig = {s: Counter() for s in SIDO}
    for r in pool:
        if r["s"] in sido_sig and r["d"] >= (today() - timedelta(days=30)).isoformat():
            for n, rx in TOPICS:
                if re.search(rx, r["t"]):
                    sido_sig[r["s"]][n] += 1
    return {"asof": today().isoformat(), "days": days, "curves": curves, "forecast": forecast_track(issues, pool), "weekly": weekly(issues),
            "quality": quality(issues), "budget": budget_radar(pool), "calendar": demand_calendar(), "wins": win_pattern(), "courses": cc,
            "bigtech": bigtech(pool), "bundle": bundle_reco(pool, curves, cc), "univ": univ_map(pool),
            "sido_topics": {s: c.most_common(5) for s, c in sido_sig.items()}, "has_brief": bool(issues)}


def build(sec=None, issues=None):
    try:
        p = payload(issues)
    except Exception as e:  # 칸 하나 실패가 관리 탭 전체를 막지 않게
        print(f"[경고] strategy_intel 실패: {type(e).__name__}: {str(e)[:120]}")
        return ""
    print(f"전략 인텔리전스: 곡선 {len(p['curves'])} · 예측 {len(p['forecast'])} · 예산 {sum(1 for b in p['budget'] if b['n'])}개 시도 · 교대 {len(p['univ'])} · 브리핑 {'있음' if p['has_brief'] else '없음'}")
    return ('<section class="panel si-wrap"><div class="panel-head"><div><p class="panel-title">🧠 전략 인텔리전스</p>'
            '<p class="panel-desc">브리핑·교육청 소식·나라장터 계약·경쟁사 연수 기록을 묶어 판단 근거를 보여 줍니다(관리자 전용, 매일 갱신)</p></div></div>'
            f'<div id="siRoot" data-p="{E(json.dumps(p, ensure_ascii=False, separators=(",", ":")))}"><p style="color:var(--muted);">불러오는 중…</p></div></section>')


if __name__ == "__main__":
    import sys
    iss = None
    if len(sys.argv) > 1:
        iss = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sys.argv[1:]]
    p = payload(iss)
    print(json.dumps({k: (v if k in ("weekly", "bundle") else (len(v) if isinstance(v, (list, dict)) else v)) for k, v in p.items()}, ensure_ascii=False, indent=1)[:3000])
    print(json.dumps(strength5(), ensure_ascii=False)[:600])
