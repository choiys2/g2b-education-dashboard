#!/usr/bin/env python3
"""
시각화 고도화 데이터(사용자 승인 2026-11-21, A·B·C 묶음).
화면이 시도·기간 필터로 다시 그릴 수 있도록 '숫자 위주'의 작은 표만 내보낸다(제목은 40자 이내).
  build_data()  -> CP 연동 차트용 데이터(연수 공고·발주계획·교육청 소식·경쟁사 활동·학사일정·시군 학교 수)
  build_admin() -> 관리 탭 3종 SVG(주제 시장 버블맵 · 경쟁사 레이더 · 시도 스코어카드)
수주 흐름(발주계획 → 공고 → 낙찰 확인)은 제목 낱말 겹침으로 잇고, 연결 정확도를 함께 싣는다.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from html import escape as h
from pathlib import Path

ROOT = Path(__file__).parent
HIST = ROOT / "history"
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
TRAIN_RE = re.compile(r"연수|교원|교사|역량\s?강화|직무|원격\s?교육|에듀테크|AI|인공지능|디지털|코딩|캠프|독서|진로|컨설팅|교육\s?운영|프로그램\s?운영|특강|워크숍")
STOP = {"2024", "2025", "2026", "2027", "2028", "용역", "위탁", "운영", "사업", "및", "관련", "추진", "년", "년도", "학년도", "제", "외", "등", "의", "을", "를", "위한", "통한"}
COL = {"own": "#10b981", "rival": "#ef4444", "market": "#3b82f6", "warn": "#f59e0b"}


def _jl(name):
    p = HIST / name
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _js(name):
    try:
        return json.loads((HIST / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _n(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _si(r):
    r = str(r or "")
    for i, s in enumerate(SIDO):
        if r.startswith(s) or s in r[:6]:
            return i
    return -1


def _tok(t):
    t = re.sub(r"[\(\)\[\]「」『』<>·,./\-_:;'\"“”‘’]", " ", str(t or ""))
    return {w for w in t.split() if len(w) >= 2 and w not in STOP and not re.fullmatch(r"\d+(년|년도)?", w)}


def _jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def _topics():
    from strategy_intel import TOPICS
    return TOPICS


def build_data():
    TOP = _topics()
    tnames = [n for n, _ in TOP]
    tb = _jl("training_bids.jsonl")
    ow = _jl("org_watch.jsonl")
    op = [x for x in _jl("order_plans.jsonl") if TRAIN_RE.search(x.get("t") or "")]
    # 낙찰 확인: 경쟁사 계약·낙찰 제목과 겹치는 연수 공고
    awards = [(_tok(x.get("t")), _si(x.get("region"))) for x in ow]
    B, btok = [], []
    for x in tb:
        tt = _tok(x.get("t")); si = _si(x.get("r"))
        won = any(_jac(tt, a) >= .45 and (sa < 0 or si < 0 or sa == si) for a, sa in awards)
        ti = next((i for i, (_, rx) in enumerate(TOP) if re.search(rx, x.get("t") or "")), -1)
        B.append([str(x.get("d") or "")[:10], si, round(_n(x.get("a")) / 1e8, 3), ti, 1 if won else 0, (x.get("t") or "")[:40], (x.get("o") or "")[:24]])
        btok.append((tt, si, str(x.get("d") or "")[:10]))
    hows = [k for k, _ in Counter(x.get("how") or "기타" for x in op).most_common()]
    P, linked = [], 0
    for x in op:
        tt, si, d0 = _tok(x.get("t")), _si(x.get("r")), str(x.get("d") or "")[:10]
        lk = any(_jac(tt, b) >= .4 and (si < 0 or bs < 0 or si == bs) and bd >= d0[:7] for b, bs, bd in btok)
        linked += lk
        P.append([d0, si, round(_n(x.get("a")) / 1e8, 3), hows.index(x.get("how") or "기타"), 1 if lk else 0])
    S = []
    for x in _jl("edu_office_signals.jsonl"):
        t = x.get("t") or ""
        m = sum(1 << i for i, (_, rx) in enumerate(TOP) if re.search(rx, t))
        S.append([str(x.get("d") or "")[:10], _si(x.get("s")), m])
    orgs = [k for k, _ in Counter(x.get("org") for x in ow if x.get("org")).most_common(8)]
    W = [[str(x.get("date") or "")[:10], _si(x.get("region")), orgs.index(x["org"]), 1 if x.get("kind") == "win" else 0, round(_n(x.get("amount")) / 1e8, 3)]
         for x in ow if x.get("org") in orgs]
    # 학사일정(시도별 주간 방학 비율·시험 주)
    ns = _js("neis_schedule.json")
    cal = {}
    if ns.get("regions"):
        from datetime import datetime
        d0 = datetime.strptime(ns.get("from", date.today().isoformat())[:10], "%Y-%m-%d").date()
        d0 -= timedelta(days=d0.weekday())
        weeks = [d0 + timedelta(days=7 * i) for i in range(20)]
        pd = lambda s: datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None
        for r in ns["regions"]:
            lv = (r.get("levels") or {}).values()
            vac, ex = [0] * 20, [0] * 20
            for L in lv:
                v0, v1, e = pd(L.get("방학식") or L.get("겨울방학")), pd(L.get("개학") or L.get("방학 종료")), pd(L.get("시험"))
                for i, w in enumerate(weeks):
                    if v0 and v1 and v0 <= w + timedelta(days=6) and w <= v1:
                        vac[i] += 1
                    if e and w <= e <= w + timedelta(days=6):
                        ex[i] = 1
            n = max(1, len(r.get("levels") or {}))
            cal[r.get("region")] = [[round(v / n, 2) for v in vac], ex]
        cal = {"weeks": [w.isoformat() for w in weeks], "rows": cal}
    # 시군 학교·교원 수(3단계 드릴다운용)
    sch = defaultdict(lambda: [0, 0])
    for x in _js("schoolinfo_market.json").get("schools") or []:
        k = f"{x.get('s', '')}|{x.get('g', '')}"
        sch[k][0] += 1
        sch[k][1] += int(x.get("t") or 0)
    return {"asof": date.today().isoformat(), "sido": SIDO, "topics": tnames, "hows": hows, "orgs": orgs,
            "B": B, "P": P, "S": S, "W": W, "cal": cal, "sch": dict(sch),
            "link": {"plans": len(P), "linked": linked, "bids": len(B), "won": sum(b[4] for b in B)}}


# ---------------- 관리 3종 ----------------
def _card(icon, title, sub, body, note=""):
    return (f'<section class="cpv-card"><header><span class="cpv-ic">{icon}</span><div><b>{h(title)}</b><small>{h(sub)}</small></div></header>'
            f'{body}{f"<p class=cpv-note>{h(note)}</p>" if note else ""}</section>')


def _split(rows, key_date, months=6):
    t = date.today()
    a, b = (t - timedelta(days=30 * months)).isoformat(), (t - timedelta(days=60 * months)).isoformat()
    rec = [r for r in rows if key_date(r) >= a]
    pre = [r for r in rows if b <= key_date(r) < a]
    return rec, pre


def topic_bubbles():
    TOP = _topics()
    tb, ow = _jl("training_bids.jsonl"), _jl("org_watch.jsonl")
    rec, pre = _split(tb, lambda r: str(r.get("d") or ""))
    rows = []
    for n, rx in TOP:
        hit = [x for x in tb if re.search(rx, x.get("t") or "")]
        if not hit:
            continue
        r1 = sum(1 for x in rec if re.search(rx, x.get("t") or "")); r0 = sum(1 for x in pre if re.search(rx, x.get("t") or ""))
        amt = sum(_n(x.get("a")) for x in hit) / 1e8
        riv = sum(1 for x in ow if re.search(rx, x.get("t") or ""))
        rows.append((n, len(hit), amt, (r1 - r0) / max(1, r0) * 100, riv / max(1, len(hit))))
    if not rows:
        return ""
    W, H, L, B = 760, 380, 60, 320
    gx = [r[3] for r in rows]; g0, g1 = min(-50, min(gx)), max(50, max(gx))
    cm = max(r[1] for r in rows) or 1; am = max(r[2] for r in rows) or 1
    X = lambda g: L + (W - L - 40) * (g - g0) / (g1 - g0); Y = lambda c: B - (B - 40) * c / cm
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="연수 주제 시장 버블맵">',
         f'<line x1="{L}" y1="{B}" x2="{W - 20}" y2="{B}" stroke="var(--border)"/><line x1="{X(0):.1f}" y1="30" x2="{X(0):.1f}" y2="{B}" stroke="var(--border)" stroke-dasharray="4 4"/>',
         f'<text x="{W - 20}" y="{B + 22}" text-anchor="end" class="cpv-l">성장률(최근 6개월 vs 이전) →</text><text x="{L}" y="24" class="cpv-l">↑ 공고 건수</text>']
    big = {r[0] for r in sorted(rows, key=lambda r: -r[2])[:3]} | {r[0] for r in rows if r[3] > 0}
    for n, c, a, g, rs in sorted(rows, key=lambda r: -r[2]):
        r = 8 + 26 * (a / am) ** .5
        col = COL["rival"] if rs >= .3 else (COL["warn"] if rs >= .1 else COL["own"])
        s.append(f'<circle cx="{X(g):.1f}" cy="{Y(c):.1f}" r="{r:.1f}" fill="{col}" opacity=".78"><title>{h(n)} · 공고 {c}건 · {a:.1f}억 · 성장 {g:+.0f}% · 경쟁사 계약 비율 {rs * 100:.0f}%</title></circle>'
                 + (f'<text x="{X(g):.1f}" y="{Y(c) - r - 4:.1f}" text-anchor="middle" class="cpv-v">{h(n)}</text>' if n in big else ""))
    s.append("</svg>")
    best = max(rows, key=lambda r: (r[3] > 0) * r[2] * (1 - r[4]))
    return _card("🫧", "#7 연수 주제 시장 버블맵", "원 크기=공고 금액 · 가로=성장률 · 세로=건수 · 색=경쟁사 계약 비율(초록<10%·노랑<30%·빨강) · 이름 없는 원은 마우스를 올리면 보임", "".join(s),
                 f"오른쪽 위 초록 원이 '크고·자라고·경쟁 약한' 주제입니다 — 현재 1순위: {best[0]}")


def rival_radar():
    ow = _jl("org_watch.jsonl")
    TOP = _topics()
    orgs = [k for k, _ in Counter(x.get("org") for x in ow if x.get("org")).most_common(4)]
    if not orgs:
        return ""
    rec, pre = _split(ow, lambda r: str(r.get("date") or ""))
    axes = ["건수", "금액", "지역 폭", "주제 폭", "성장"]
    raw = {}
    for o in orgs:
        L = [x for x in ow if x.get("org") == o]
        r1 = sum(1 for x in rec if x.get("org") == o); r0 = sum(1 for x in pre if x.get("org") == o)
        raw[o] = [len(L), sum(_n(x.get("amount")) for x in L), len({x.get("region") for x in L if x.get("region")}),
                  len({n for x in L for n, rx in TOP if re.search(rx, x.get("t") or "")}), (r1 + 1) / (r0 + 1)]
    mx = [max(raw[o][i] for o in orgs) or 1 for i in range(5)]
    import math
    cx, cy, R = 240, 200, 150
    pt = lambda i, v: (cx + R * v * math.sin(2 * math.pi * i / 5), cy - R * v * math.cos(2 * math.pi * i / 5))
    s = ['<svg class="cpv-svg" viewBox="0 0 760 400" role="img" aria-label="경쟁사 레이더">']
    for k in (.25, .5, .75, 1):
        s.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, k) for i in range(5))) + '" fill="none" stroke="var(--border)"/>')
    for i, a in enumerate(axes):
        x, y = pt(i, 1.12); s.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" class="cpv-l">{a}</text>')
    pal = [COL["rival"], "#f97316", "#8b5cf6", "#0ea5e9"]
    for j, o in enumerate(orgs):
        v = [raw[o][i] / mx[i] for i in range(5)]
        s.append(f'<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v[i]) for i in range(5))) + f'" fill="{pal[j]}" fill-opacity=".16" stroke="{pal[j]}" stroke-width="2.4"/>')
        s.append(f'<rect x="520" y="{70 + j * 34}" width="14" height="14" rx="3" fill="{pal[j]}"/><text x="542" y="{82 + j * 34}" class="cpv-v">{h(o)}</text>'
                 f'<text x="542" y="{97 + j * 34}" class="cpv-l">{raw[o][0]}건 · {raw[o][1] / 1e8:.0f}억 · {raw[o][2]}개 시도</text>')
    s.append("</svg>")
    lead = max(orgs, key=lambda o: raw[o][4])
    return _card("🕸️", "#8 경쟁사 레이더", "건수·금액·지역 폭·주제 폭·성장(최근 6개월/이전) — 각 축 최댓값 기준", "".join(s),
                 f"성장 속도가 가장 빠른 곳: {lead}({raw[lead][4]:.1f}배) — 넓게 퍼진 다각형일수록 전방위 경쟁자입니다")


def scorecard():
    tb, op, sig, ow = _jl("training_bids.jsonl"), _jl("order_plans.jsonl"), _jl("edu_office_signals.jsonl"), _jl("org_watch.jsonl")
    sch = Counter(x.get("s") for x in (_js("schoolinfo_market.json").get("schools") or []))
    t = date.today(); y1, h0, h1 = (t - timedelta(days=365)).isoformat(), (t - timedelta(days=180)).isoformat(), (t - timedelta(days=360)).isoformat()
    met = {
        "학교 수": {s: sch.get(s, 0) for s in SIDO},
        "연수 공고(1년)": Counter(SIDO[_si(x.get("r"))] for x in tb if _si(x.get("r")) >= 0 and str(x.get("d")) >= y1),
        "발주계획 금액": defaultdict(float),
        "교육청 소식": Counter(SIDO[_si(x.get("s"))] for x in sig if _si(x.get("s")) >= 0),
        "경쟁사 활동": Counter(SIDO[_si(x.get("region"))] for x in ow if _si(x.get("region")) >= 0 and str(x.get("date")) >= y1),
    }
    for x in op:
        if _si(x.get("r")) >= 0:
            met["발주계획 금액"][SIDO[_si(x.get("r"))]] += _n(x.get("a")) / 1e8
    rank = lambda d: {s: i + 1 for i, s in enumerate(sorted(SIDO, key=lambda s: -d.get(s, 0)))}
    now = Counter(SIDO[_si(x.get("r"))] for x in tb if _si(x.get("r")) >= 0 and str(x.get("d")) >= h0)
    prev = Counter(SIDO[_si(x.get("r"))] for x in tb if _si(x.get("r")) >= 0 and h1 <= str(x.get("d")) < h0)
    rn, rp = rank(now), rank(prev)
    keys = list(met)
    R = {k: rank(met[k]) for k in keys}
    tot = {s: sum(R[k][s] for k in keys) for s in SIDO}
    order = sorted(SIDO, key=lambda s: tot[s])
    CW, RH, LX = 112, 24, 58
    s = [f'<svg class="cpv-svg v3d-no" viewBox="0 0 {LX + CW * len(keys) + 90} {40 + RH * 17}" role="img" aria-label="시도 스코어카드">']
    for k_i, k in enumerate(keys):
        s.append(f'<text x="{LX + k_i * CW + CW / 2}" y="24" text-anchor="middle" class="cpv-l">{h(k)}</text>')
    s.append(f'<text x="{LX + CW * len(keys) + 45}" y="24" text-anchor="middle" class="cpv-l">공고 순위 변화</text>')
    for j, sd in enumerate(order):
        y = 32 + j * RH
        s.append(f'<text x="{LX - 6}" y="{y + 16}" text-anchor="end" class="cpv-v">{j + 1}. {h(sd)}</text>')
        for k_i, k in enumerate(keys):
            r = R[k][sd]; v = met[k].get(sd, 0)
            a = .85 - (r - 1) / 16 * .75
            s.append(f'<rect x="{LX + k_i * CW + 2}" y="{y}" width="{CW - 4}" height="{RH - 3}" rx="4" fill="rgba(59,130,246,{a:.2f})"><title>{h(sd)} · {h(k)} {v:,.1f} · {r}위</title></rect>'
                     f'<text x="{LX + k_i * CW + CW / 2}" y="{y + 15}" text-anchor="middle" class="cpv-c">{r}위</text>')
        d = rp.get(sd, 17) - rn.get(sd, 17)
        s.append(f'<text x="{LX + CW * len(keys) + 45}" y="{y + 15}" text-anchor="middle" class="cpv-v" fill="{COL["own"] if d > 0 else COL["rival"] if d < 0 else "var(--muted)"}">{"▲" + str(d) if d > 0 else "▼" + str(-d) if d < 0 else "–"}</text>')
    s.append("</svg>")
    up = [sd for sd in SIDO if rp.get(sd, 17) - rn.get(sd, 17) >= 3]
    return _card("🏅", "#10 시도 스코어카드", "17개 시도 × 5개 지표 순위(진할수록 상위) · 오른쪽 = 연수 공고 순위의 최근 6개월 변화", "".join(s),
                 f"종합 상위: {', '.join(order[:3])} · 공고 순위가 3계단 이상 오른 시도: {', '.join(up) or '없음'}")


def build_admin():
    out = []
    for fn in (topic_bubbles, rival_radar, scorecard):
        try:
            out.append(fn())
        except Exception as e:  # 한 그림 오류가 칸 전체를 막지 않게
            print(f"  cp_viz_data {fn.__name__} 건너뜀: {str(e)[:120]}")
    return "".join(x for x in out if x)


if __name__ == "__main__":
    d = build_data()
    print({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in d.items()}, d["link"], len(json.dumps(d, ensure_ascii=False)) // 1024, "KB")
    print(len(build_admin()))
