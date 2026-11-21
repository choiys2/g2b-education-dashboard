#!/usr/bin/env python3
"""
데이터 시각화 확장 10종(사용자 승인 2026-11-21).
  CP(일반 화면) 7종: build_cp() -> {"패널키": [html, ...], "home": html}
    #1 연수 수요 타이밍(시도×주)  #2 발주 계획 흐름(지역×계약방식)  #7 연수 입찰 금액 분포  -> 나라장터 종합(g2bfull)
    #3 정책 주제 흐름(주제×주·시도×주제) -> 전략 브리핑(strategy)
    #4 경쟁사 활동 타임라인 -> 경쟁사(competitor)
    #5 핵심 지표 추세(월·주 단위 누적 기록) -> 앱 홈(타일)
    #6 교과서 여론 점유 추이 -> 교과서 채택(adopt)
  관리 3종: build(sec) -> 관리 탭 칸 HTML
    #8 시군 잠재시장(교원×학원)  #9 학교 수의계약 점유(미상 비율 함께)  #10 시도 재정 증감
그림은 SVG 문자열로 만들고(외부 텍스트는 모두 escape), 입체 효과는 화면의 공통 입체 변환이 덧입힌다.
히트맵 칸처럼 입체가 어울리지 않는 그림은 class="v3d-no" 로 제외한다.
CP 문구에는 출처·수집 방식·도구명을 쓰지 않는다(방법론 비노출).
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape as h
from pathlib import Path

ROOT = Path(__file__).parent
HIST = ROOT / "history"
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
PAL = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#f97316"]
EMPTY = '<p class="cpv-note">데이터 준비 중</p>'
SHORT = {"AI 부정행위·평가": "AI평가", "빅테크 교사 연수": "빅테크", "AI·디지털 교육": "AI·디지털", "독서·인문": "독서·인문", "진로·진학": "진로", "기초학력·수학": "기초학력", "교권·생활지도": "교권", "늘봄·돌봄": "늘봄"}
OWN = ' stroke="#111" stroke-width="1.5"'


def _jl(name):
    p = HIST / name
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _js(name):
    p = HIST / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def _n(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _d(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _eok(v):
    v = v or 0
    return f"{v / 1e8:,.1f}억" if v >= 1e8 else f"{v / 1e4:,.0f}만"


def _card(icon, title, sub, body, note=""):
    return (f'<section class="cpv-card"><header><span class="cpv-ic">{icon}</span><div><b>{h(title)}</b><small>{h(sub)}</small></div></header>'
            f'{body}{f"<p class=cpv-note>{h(note)}</p>" if note else ""}</section>')


def _heat(c, mx):
    a = 0 if not mx else min(1, c / mx)
    return f"rgba(79,70,229,{0.08 + a * 0.82:.2f})"


# ---------- #1 연수 수요 타이밍 ----------
def timing():
    ns = _js("neis_schedule.json")
    regions = ns.get("regions") or []
    if not regions:
        return ""
    start = _d(ns.get("from")) or date.today()
    start -= timedelta(days=start.weekday())
    weeks = [start + timedelta(days=7 * i) for i in range(20)]
    tb = _jl("training_bids.jsonl")
    by_m = Counter(str(x.get("d") or "")[5:7] for x in tb if x.get("d"))  # 지난 1년 같은 달 연수 공고 수
    W, LX, CW, RH, TOP = 760, 46, 35, 19, 62
    rows = []
    for r in regions:
        st = {}
        for lv in (r.get("levels") or {}).values():
            v0, v1, ex = _d(lv.get("방학식") or lv.get("겨울방학")), _d(lv.get("개학") or lv.get("방학 종료")), _d(lv.get("시험"))
            for i, w in enumerate(weeks):
                we = w + timedelta(days=6)
                if v0 and v1 and v0 <= we and w <= v1:
                    st[i] = st.get(i, 0) + 1
                if ex and w <= ex <= we:
                    st.setdefault(("x", i), 1)
        rows.append((r.get("region", ""), st, len(r.get("levels") or {}) or 1))
    H = TOP + RH * len(rows) + 30
    s = [f'<svg class="cpv-svg v3d-no" viewBox="0 0 {W} {H}" role="img" aria-label="시도별 주간 학사 일정과 연수 공고 시기">']
    mx = max(by_m.values() or [1])
    for i, w in enumerate(weeks):
        x = LX + i * CW
        if i == 0 or w.day <= 7:
            s.append(f'<text x="{x + 2}" y="12" class="cpv-l">{w.month}월</text>')
        n = by_m.get(f"{w.month:02d}", 0) / 4.3
        bh = 0 if not mx else 34 * min(1, n / (mx / 4.3))
        s.append(f'<rect x="{x + 6}" y="{52 - bh:.1f}" width="{CW - 12}" height="{bh:.1f}" rx="2" fill="#f59e0b" opacity=".85"><title>{w:%m/%d} 주 · 지난해 같은 달 연수 공고 주평균 {n:.1f}건</title></rect>')
    s.append(f'<text x="{LX - 4}" y="48" text-anchor="end" class="cpv-l">공고</text>')
    for j, (nm, st, nl) in enumerate(rows):
        y = TOP + j * RH
        s.append(f'<text x="{LX - 6}" y="{y + 13}" text-anchor="end" class="cpv-l">{h(nm)}</text>')
        for i in range(len(weeks)):
            v = st.get(i, 0) / nl
            fill = f"rgba(14,165,233,{0.12 + v * 0.75:.2f})" if v else "var(--surface-2)"
            s.append(f'<rect x="{LX + i * CW + 1}" y="{y + 1}" width="{CW - 2}" height="{RH - 2}" rx="3" fill="{fill}"><title>{h(nm)} {weeks[i]:%m/%d} 주{" · 방학" if v else ""}{" · 시험" if st.get(("x", i)) else ""}</title></rect>')
            if st.get(("x", i)):
                s.append(f'<circle cx="{LX + i * CW + CW / 2}" cy="{y + RH / 2}" r="3.2" fill="#ef4444"/>')
    s.append(f'<g transform="translate({LX},{H - 12})" class="cpv-l"><rect width="12" height="9" fill="rgba(14,165,233,.7)"/><text x="16" y="9">방학(초·중·고 비율)</text>'
             f'<circle cx="150" cy="5" r="3.5" fill="#ef4444"/><text x="158" y="9">시험 주</text><rect x="230" width="12" height="9" fill="#f59e0b"/><text x="246" y="9">지난해 같은 달 연수 공고</text></g></svg>')
    peak = sorted(by_m.items(), key=lambda x: -x[1])[:3]
    note = "연수 공고가 많은 달: " + ", ".join(f"{int(m)}월 {c}건" for m, c in peak) + " · 시험 주·방학 직전은 연수 집중이 어렵고, 방학 중·개학 전후가 제안 적기입니다."
    return _card("🗓️", "연수 수요 타이밍", f"시도별 학사 일정 × 지난 1년 연수 공고 시기 · 기준 {ns.get('generated', '')[:10]}", "".join(s), note)


# ---------- #2 발주 계획 흐름 ----------
def plans():
    op = _jl("order_plans.jsonl")
    if not op:
        return ""
    agg = defaultdict(Counter)
    cnt = Counter()
    for x in op:
        r = x.get("r") or "기타"
        agg[r][x.get("how") or "기타"] += _n(x.get("a"))
        cnt[r] += 1
    tot_how = Counter()
    for r in agg.values():
        tot_how.update(r)
    hows = [k for k, _ in tot_how.most_common()]
    top = sorted(agg, key=lambda r: -sum(agg[r].values()))[:10]
    mx = max(sum(agg[r].values()) for r in top) or 1
    W, LX, BW, RH = 760, 60, 560, 30
    H = 30 + RH * len(top) + 26
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="지역별 발주 계획 금액과 계약 방식">']
    for j, r in enumerate(top):
        y, x = 24 + j * RH, LX
        s.append(f'<text x="{LX - 8}" y="{y + 15}" text-anchor="end" class="cpv-l">{h(r)}</text>')
        for k, hw in enumerate(hows):
            v = agg[r].get(hw, 0)
            if v <= 0:
                continue
            w = BW * v / mx
            s.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w, 1):.1f}" height="20" fill="{PAL[k % len(PAL)]}"><title>{h(r)} · {h(hw)} {_eok(v)}</title></rect>')
            x += w
        s.append(f'<text x="{x + 12:.1f}" y="{y + 15}" class="cpv-v">{_eok(sum(agg[r].values()))} · {cnt[r]}건</text>')
    s.append(f'<g transform="translate({LX},{H - 12})" class="cpv-l">' + "".join(
        f'<rect x="{i * 110}" width="12" height="9" fill="{PAL[i % len(PAL)]}"/><text x="{i * 110 + 16}" y="9">{h(hw)}</text>' for i, hw in enumerate(hows)) + "</g></svg>")
    tot = sum(_n(x.get("a")) for x in op)
    sole = sum(_n(x.get("a")) for x in op if x.get("how") == "수의계약")
    note = f"전체 {len(op):,}건 · {_eok(tot)} 중 수의계약 {_eok(sole)}({sole / tot * 100 if tot else 0:.0f}%) — 수의계약 물량은 사전 접촉이 곧 수주로 이어집니다."
    return _card("🧭", "발주 계획 흐름", "지역별 발주 계획 금액 × 계약 방식(상위 10개 지역)", "".join(s), note)


# ---------- #7 연수 입찰 금액 분포 ----------
BUCKETS = [("2천만 미만", 0, 2e7), ("2천만~5천만", 2e7, 5e7), ("5천만~1억", 5e7, 1e8), ("1억~3억", 1e8, 3e8), ("3억 이상", 3e8, 1e18)]


def amounts():
    tb = [dict(x, a=_n(x.get("a"))) for x in _jl("training_bids.jsonl") if _n(x.get("a")) > 0]
    if not tb:
        return ""
    c = Counter()
    s_amt = Counter()
    for x in tb:
        for nm, lo, hi in BUCKETS:
            if lo <= x["a"] < hi:
                c[nm] += 1
                s_amt[nm] += x["a"]
    W, H, LX, BH = 760, 250, 40, 150
    mx = max(c.values()) or 1
    bw = 100
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="연수 입찰 금액대별 건수">']
    for i, (nm, _, _) in enumerate(BUCKETS):
        x = LX + 30 + i * 140
        bh = BH * c[nm] / mx
        y = 30 + BH - bh
        s.append(f'<rect x="{x}" y="{y:.1f}" width="{bw}" height="{max(bh, 1):.1f}" fill="{PAL[i]}"><title>{nm} · {c[nm]}건 · 합계 {_eok(s_amt[nm])}</title></rect>'
                 f'<text x="{x + bw / 2}" y="{y - 14:.1f}" text-anchor="middle" class="cpv-v">{c[nm]}건</text>'
                 f'<text x="{x + bw / 2}" y="{30 + BH + 20}" text-anchor="middle" class="cpv-l">{nm}</text>'
                 f'<text x="{x + bw / 2}" y="{30 + BH + 36}" text-anchor="middle" class="cpv-l">{_eok(s_amt[nm])}</text>')
    s.append("</svg>")
    med = sorted(x["a"] for x in tb)[len(tb) // 2]
    top = max(c, key=c.get)
    note = f"금액이 있는 연수 공고 {len(tb)}건 · 중앙값 {_eok(med)} · 가장 많은 구간은 '{top}'({c[top]}건)입니다."
    return _card("💰", "연수 입찰 금액 분포", "금액대별 공고 건수와 합계(지난 1년)", "".join(s), note)


# ---------- #3 정책 주제 흐름 ----------
def topics():
    from strategy_intel import TOPICS
    sig = _jl("edu_office_signals.jsonl")
    if not sig:
        return ""
    ds_ = [_d(x.get("d")) for x in sig if _d(x.get("d"))]
    end = max(ds_, default=date.today())
    first = max(min(ds_, default=end), end - timedelta(days=69))
    span = (end - first).days + 1
    step = 7 if span >= 42 else (2 if span > 21 else 1)  # 기록이 짧으면 하루·이틀 단위
    n_bins = max(2, -(-span // step))
    wk = [end - timedelta(days=step * i) for i in range(n_bins - 1, -1, -1)]
    grid = defaultdict(Counter)
    sido = defaultdict(Counter)
    for x in sig:
        d0 = _d(x.get("d"))
        if not d0:
            continue
        t = x.get("t") or ""
        hits = [n for n, rx in TOPICS if re.search(rx, t)]
        for n in hits:
            sido[x.get("s") or "기타"][n] += 1
            for w in wk:
                if w <= d0 < w + timedelta(days=step):
                    grid[w][n] += 1
    names = [n for n, _ in TOPICS]
    # 쌓은 영역(주제 흐름)
    W, H, LX, TOP, PH = 760, 260, 40, 14, 180
    mx = max((sum(grid[w].values()) for w in wk), default=0) or 1
    dx = (W - LX - 150) / (len(wk) - 1)
    base = [0.0] * len(wk)
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="주별 교육청 소식 주제 흐름">']
    for k, n in enumerate(names):
        top_ = [base[i] + grid[w][n] for i, w in enumerate(wk)]
        pts = [f"{LX + i * dx:.1f},{TOP + PH - PH * top_[i] / mx:.1f}" for i in range(len(wk))]
        bot = [f"{LX + i * dx:.1f},{TOP + PH - PH * base[i] / mx:.1f}" for i in reversed(range(len(wk)))]
        s.append(f'<polygon points="{" ".join(pts + bot)}" fill="{PAL[k % len(PAL)]}" opacity=".82"><title>{h(n)} · 10주 {sum(grid[w][n] for w in wk)}건</title></polygon>')
        s.append(f'<rect x="{W - 140}" y="{TOP + k * 22}" width="12" height="12" rx="2" fill="{PAL[k % len(PAL)]}"/><text x="{W - 122}" y="{TOP + k * 22 + 11}" class="cpv-l">{h(n)} {sum(grid[w][n] for w in wk)}</text>')
        base = top_
    for i, w in enumerate(wk):
        if i % max(1, len(wk) // 7) == 0 or i == len(wk) - 1:
            s.append(f'<text x="{LX + i * dx:.1f}" y="{TOP + PH + 18}" text-anchor="middle" class="cpv-l">{w:%m/%d}</text>')
    s.append("</svg>")
    flow = "".join(s)
    # 시도 × 주제 히트맵
    rows = [r for r in SIDO if sum(sido[r].values())]
    mxh = max((sido[r][n] for r in rows for n in names), default=1) or 1
    CW, RH, LX2 = 74, 20, 46
    H2 = 40 + RH * len(rows)
    s = [f'<svg class="cpv-svg v3d-no" viewBox="0 0 {LX2 + CW * len(names) + 10} {H2}" role="img" aria-label="시도별 주제 빈도">']
    for k, n in enumerate(names):
        s.append(f'<text x="{LX2 + k * CW + CW / 2}" y="28" text-anchor="middle" class="cpv-l">{h(SHORT.get(n, n[:5]))}</text>')
    for j, r in enumerate(rows):
        y = 36 + j * RH
        s.append(f'<text x="{LX2 - 6}" y="{y + 14}" text-anchor="end" class="cpv-l">{h(r)}</text>')
        for k, n in enumerate(names):
            v = sido[r][n]
            s.append(f'<rect x="{LX2 + k * CW + 1}" y="{y}" width="{CW - 2}" height="{RH - 2}" rx="3" fill="{_heat(v, mxh)}"><title>{h(r)} · {h(n)} {v}건</title></rect>'
                     + (f'<text x="{LX2 + k * CW + CW / 2}" y="{y + 13}" text-anchor="middle" class="cpv-c">{v}</text>' if v else ""))
    s.append("</svg>")
    rec, pre = Counter(), Counter()
    for x in sig:
        d0 = _d(x.get("d"))
        if not d0:
            continue
        bucket = rec if d0 > end - timedelta(days=7) else (pre if d0 > end - timedelta(days=14) else None)
        if bucket is not None:
            bucket.update(n for n, rx in TOPICS if re.search(rx, x.get("t") or ""))
    up = [n for n in sorted(names, key=lambda n: -(rec[n] - pre[n])) if rec[n] > pre[n]][:2] or [max(names, key=lambda n: rec[n])]
    unit = {7: "주", 2: "2일", 1: "일"}[step]
    note = f"최근 7일 늘어난 주제: {', '.join(up)} · 시도 표에서 진한 칸이 그 교육청의 현재 관심사입니다."
    return _card("🌊", "교육청 정책 주제 흐름", f"{unit} 단위 주제별 소식 건수({first:%m/%d}~{end:%m/%d}) · 시도 × 주제(누적)",
                 flow + '<h5 class="cpv-h">시도 × 주제</h5>' + h2wrap("".join(s)), note)


def h2wrap(svg):
    return f'<div class="cpv-fit">{svg}</div>'


# ---------- #4 경쟁사 활동 타임라인 ----------
def rivals():
    ow = _jl("org_watch.jsonl")
    if not ow:
        return ""
    months = []
    t = date.today().replace(day=1)
    for _ in range(12):
        months.append(t)
        t = (t - timedelta(days=1)).replace(day=1)
    months.reverse()
    orgs = [o for o, _ in Counter(x.get("org") for x in ow if x.get("org")).most_common(5)]
    W, LX, RH = 760, 108, 46
    dx = (W - LX - 30) / 11
    H = 40 + RH * len(orgs) + 20
    amx = max(_n(x.get("amount")) for x in ow) or 1
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="경쟁사 월별 계약·낙찰">']
    for i, m in enumerate(months):
        s.append(f'<text x="{LX + i * dx:.1f}" y="18" text-anchor="middle" class="cpv-l">{m:%y.%m}</text>')
    for j, o in enumerate(orgs):
        y = 44 + j * RH
        s.append(f'<line x1="{LX - 10}" y1="{y}" x2="{W - 20}" y2="{y}" stroke="var(--border)" stroke-dasharray="3 4"/>'
                 f'<text x="{LX - 18}" y="{y + 4}" text-anchor="end" class="cpv-l">{h(o)}</text>')
        cells = defaultdict(lambda: [0, 0, 0])
        for x in ow:
            if x.get("org") != o:
                continue
            d0 = _d(x.get("date"))
            if not d0:
                continue
            key = d0.replace(day=1)
            if key in months:
                c = cells[key]
                c[0 if x.get("kind") == "contract" else 1] += 1
                c[2] += _n(x.get("amount"))
        for m, (nc, nw, a) in cells.items():
            i = months.index(m)
            r = 5 + 13 * (a / amx) ** 0.5
            col = "#ef4444" if nw else "#0ea5e9"
            s.append(f'<circle cx="{LX + i * dx:.1f}" cy="{y}" r="{r:.1f}" fill="{col}" opacity=".85"><title>{h(o)} {m:%Y-%m} · 계약 {nc} · 낙찰 {nw} · {_eok(a)}</title></circle>')
    s.append(f'<g transform="translate({LX},{H - 10})" class="cpv-l"><circle cx="5" cy="-3" r="5" fill="#0ea5e9"/><text x="14" y="1">계약만</text><circle cx="80" cy="-3" r="5" fill="#ef4444"/><text x="89" y="1">낙찰 포함(원 크기=금액)</text></g></svg>')
    recent = Counter(x.get("org") for x in ow if (_d(x.get("date")) or date.min) >= date.today() - timedelta(days=60))
    note = "최근 60일 활동: " + ", ".join(f"{o} {n}건" for o, n in recent.most_common(3)) if recent else ""
    return _card("🏁", "경쟁사 활동 타임라인", "월별 계약·낙찰(최근 12개월, 활동 많은 5개사)", "".join(s), note)


# ---------- #5 핵심 지표 추세(앱 홈) ----------
def _spark(vals, col):
    if not vals:
        return ""
    W, H = 160, 44
    mx = max(vals) or 1
    pts = [(i * W / max(1, len(vals) - 1), H - 6 - (H - 12) * v / mx) for i, v in enumerate(vals)]
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return (f'<svg class="cpv-spark" viewBox="0 0 {W} {H}" aria-hidden="true"><polygon points="0,{H} {p} {W},{H}" fill="{col}" opacity=".18"/>'
            f'<polyline points="{p}" fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round"/><circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4" fill="{col}"/></svg>')


def kpis():
    t = date.today()
    mon = []
    m = t.replace(day=1)
    for _ in range(12):
        mon.append(m.strftime("%Y-%m"))
        m = (m - timedelta(days=1)).replace(day=1)
    mon.reverse()
    tb = Counter(str(x.get("d") or "")[:7] for x in _jl("training_bids.jsonl"))
    ow = Counter(str(x.get("date") or "")[:7] for x in _jl("org_watch.jsonl"))
    sig = _jl("edu_office_signals.jsonl")
    wk0 = t - timedelta(days=t.weekday())
    weeks = [wk0 - timedelta(days=7 * i) for i in range(11, -1, -1)]
    sg = [sum(1 for x in sig if (_d(x.get("d")) or date.min) >= w and (_d(x.get("d")) or date.min) < w + timedelta(days=7)) for w in weeks]
    first_sig = min((_d(x.get("d")) for x in sig if _d(x.get("d"))), default=t)
    dc = Counter(_d(x.get("d")) for x in sig if _d(x.get("d")))
    days = [t - timedelta(days=i) for i in range(min(30, (t - first_sig).days), 0, -1)]  # 기록 시작일부터, 오늘(진행 중) 제외
    sg = [dc.get(d0, 0) for d0 in days]
    items = [("연수 입찰 공고", "월별 · 지난달까지", [tb.get(k, 0) for k in mon][:-1], "#f59e0b", "건"),
             ("교육청 소식", "일별 · 최근 7일 합계", sg, "#4f46e5", "건"),
             ("경쟁사 계약·낙찰", "월별 · 지난달까지", [ow.get(k, 0) for k in mon][:-1], "#ef4444", "건")]
    cards = []
    for nm, sub, vals, col, u in items:
        if not any(vals):
            continue
        if len(vals) < 2:
            continue
        if "7일" in sub:  # 일별 기록은 최근 7일 합계를 그 앞 7일과 비교
            last = sum(vals[-7:])
            prev = sum(vals[-14:-7]) if len(vals) >= 14 else 0
        else:
            last = vals[-1]
            base = vals[-4:-1] if len(vals) > 3 else vals[:-1]
            prev = sum(base) / len(base) if base else 0
        ch = "" if not prev else (f'<em class="up">▲ {((last / prev) - 1) * 100:.0f}%</em>' if last >= prev else f'<em class="dn">▼ {(1 - last / prev) * 100:.0f}%</em>')
        cards.append(f'<div class="cpv-k"><small>{h(nm)} · {h(sub)}</small><b>{last:,}{u}</b>{ch}{_spark(vals, col)}</div>')
    if not cards:
        return ""
    return f'<section class="cpv-home"><h4>📈 핵심 지표 추세 <small>마지막 완료 구간 · 직전 평균 대비</small></h4><div class="cpv-ks">{"".join(cards)}</div></section>'


# ---------- #6 교과서 여론 점유 ----------
def opinion():
    o = _js("opinion_radar.json")
    wk = o.get("weekly") or {}
    if not wk:
        return ""
    weeks = sorted({w for v in wk.values() for w in v})
    tot = {w: sum(v.get(w, 0) for v in wk.values()) for w in weeks}
    weeks = [w for w in weeks if tot[w] >= 50]  # 막 시작한 주는 표본이 적어 뺀다
    if not weeks:
        return ""
    brands = sorted(wk, key=lambda b: -sum(wk[b].values()))
    W, LX, BW, RH = 760, 60, 600, 30
    H = 20 + RH * len(weeks) + 28
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="주별 교과서 브랜드 언급 점유">']
    for j, w in enumerate(weeks):
        y, x = 16 + j * RH, LX
        s.append(f'<text x="{LX - 8}" y="{y + 15}" text-anchor="end" class="cpv-l">{h(w[5:])}</text>')
        for k, b in enumerate(brands):
            v = wk[b].get(w, 0) / tot[w] if tot[w] else 0
            if v <= 0:
                continue
            bw = BW * v
            s.append(f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="20" fill="{PAL[k % len(PAL)]}"{OWN if b == "비상" else ""}><title>{h(w)} 주 · {h(b)} {v * 100:.1f}%</title></rect>'
                     + (f'<text x="{x + bw / 2:.1f}" y="{y + 14}" text-anchor="middle" class="cpv-c" fill="#fff">{v * 100:.0f}%</text>' if bw > 40 else ""))
            x += bw
    s.append(f'<g transform="translate({LX},{H - 10})" class="cpv-l">' + "".join(
        f'<rect x="{i * 100}" y="-9" width="12" height="9" fill="{PAL[i % len(PAL)]}"/><text x="{i * 100 + 16}" y="0">{h(b)}</text>' for i, b in enumerate(brands)) + "</g></svg>")
    share = o.get("share") or []
    note = "기간 전체 점유: " + ", ".join(f"{x.get('brand')} {x.get('pct')}%" for x in share[:3]) if share else ""
    return _card("🗣️", "교과서 여론 점유 추이", f"주별 브랜드 언급 점유(100% 막대) · 최근 {o.get('window_days', '')}일", "".join(s), note)


def build_cp():
    out = {}
    for key, fn in (("adopt", opinion),):  # 나라장터 종합·전략·경쟁사는 화면의 연동 보기(필터)로 그린다
        try:
            html = fn()
        except Exception as e:  # 한 그림 오류가 화면 전체를 막지 않게
            print(f"  cp_viz {fn.__name__} 건너뜀: {str(e)[:120]}")
            html = ""
        if html:
            out.setdefault(key, []).append(html)
    try:
        out["home"] = kpis()
    except Exception as e:
        print(f"  cp_viz kpis 건너뜀: {str(e)[:120]}")
    return out


# ================= 관리 3종 =================
def market_map():
    sm = (_js("schoolinfo_market.json").get("schools")) or []
    ac = (_js("academy_stats.json").get("rows")) or []
    if not sm:
        return ""
    tch, sch = Counter(), Counter()
    for x in sm:
        k = f"{x.get('s', '')} {x.get('g', '')}".strip()
        tch[k] += x.get("t") or 0
        sch[k] += 1
    acad = Counter()
    for r in ac:
        if r.get("gu"):
            acad[f"{r.get('sd', '')} {r.get('gu', '')}".strip()] += r.get("n") or 0
    top = [k for k, _ in tch.most_common(30)]
    lab = set(sorted(top, key=lambda k: -(tch[k] / max(tch[top[0]], 1) + acad.get(k, 0) / max(max(acad.values(), default=1), 1)))[:6])
    W, H, L, B = 760, 380, 60, 330
    xm = max(tch[k] for k in top) or 1
    ym = max((acad.get(k, 0) for k in top), default=0) or 1
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="시군별 교원 수와 학원 수">'
         f'<line x1="{L}" y1="{B}" x2="{W - 20}" y2="{B}" stroke="var(--border)"/><line x1="{L}" y1="20" x2="{L}" y2="{B}" stroke="var(--border)"/>'
         f'<text x="{W - 20}" y="{B + 24}" text-anchor="end" class="cpv-l">교원 수 →</text><text x="{L + 6}" y="30" class="cpv-l">↑ 학원 수</text>']
    for i, k in enumerate(top):
        x = L + (W - L - 40) * tch[k] / xm
        y = B - (B - 40) * acad.get(k, 0) / ym
        r = 4 + 10 * (sch[k] / max(sch[t] for t in top)) ** 0.5
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{PAL[i % len(PAL)]}" opacity=".8"><title>{h(k)} · 교원 {tch[k]:,} · 학원 {acad.get(k, 0):,} · 학교 {sch[k]}</title></circle>')
        if k in lab:
            s.append(f'<text x="{x - r - 3:.1f}" y="{y + 4:.1f}" text-anchor="end" class="cpv-v">{h(k)}</text>')
    s.append("</svg>")
    note = (f"교원 수 상위 30개 시군(원 크기=학교 수). 오른쪽 위일수록 B2S(교원)·B2C(학원·학부모) 동시 공략 지역 · 학교 {len(sm):,}교 기준"
            + (f" · 학원 자료와 시군 이름이 맞지 않는 {sum(1 for k in top if not acad.get(k))}곳은 아래쪽(0)에 표시" if any(not acad.get(k) for k in top) else ""))
    return _card("🗺️", "#8 시군 잠재시장(교원 × 학원)", "샘몰·B2S 우선 공략 지역 판단용", "".join(s), note)


def school_share():
    ec = _jl("edu_contracts.jsonl")
    if not ec:
        return ""
    c = Counter((x.get("vendor") or "업체 미상") for x in ec)
    a = Counter()
    for x in ec:
        a[x.get("vendor") or "업체 미상"] += _n(x.get("amount"))
    order = [k for k, _ in c.most_common(8)]
    W, LX, BW, RH = 760, 110, 520, 28
    H = 20 + RH * len(order) + 10
    mx = max(c.values()) or 1
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="학교 수의계약 업체별 건수">']
    for j, k in enumerate(order):
        y = 14 + j * RH
        own = "비바샘" in k or "비상" in k
        col = "#10b981" if own else ("#cbd5e1" if k in ("업체 미상", "기타", "기타 법인") else "#6366f1")
        s.append(f'<text x="{LX - 8}" y="{y + 14}" text-anchor="end" class="cpv-l">{h(k[:10])}</text>'
                 f'<rect x="{LX}" y="{y}" width="{max(2, BW * c[k] / mx):.1f}" height="18" fill="{col}"><title>{h(k)} {c[k]}건 · {_eok(a[k])}</title></rect>'
                 f'<text x="{LX + BW * c[k] / mx + 8:.1f}" y="{y + 14}" class="cpv-v">{c[k]}건 · {_eok(a[k])}</text>')
    s.append("</svg>")
    unk = sum(c[k] for k in ("업체 미상", "기타", "기타 법인"))
    sido = Counter(x.get("sido") for x in ec)
    note = (f"전체 {len(ec)}건 · {_eok(sum(a.values()))} · 업체 미상·기타 {unk}건({unk / len(ec) * 100:.0f}%) — 점유율 판단 전 보완 필요 · "
            f"수록 지역 {', '.join(f'{k} {v}' for k, v in sido.most_common())}")
    return _card("🏫", "#9 학교 수의계약 업체 점유", "업체별 건수·금액(미상 비율 함께 표시)", "".join(s), note)


def finance():
    f = (_js("eduinfo_finance.json").get("finance")) or {}
    rows = []
    for sd, yrs in f.items():
        ys = sorted(yrs)
        y0 = ys[-3] if len(ys) >= 3 else (ys[0] if ys else None)  # 최근 3개년(첫해→최근)
        if y0 and y0 != ys[-1] and yrs[y0].get("out") and yrs[ys[-1]].get("out"):
            rows.append((sd, y0, ys[-1], yrs[y0]["out"], yrs[ys[-1]]["out"]))
    if not rows:
        return ""
    rows.sort(key=lambda r: r[4] / r[3])
    W, LX, RH = 760, 60, 24
    H = 34 + RH * len(rows) + 10
    mid = 420
    s = [f'<svg class="cpv-svg" viewBox="0 0 {W} {H}" role="img" aria-label="시도 교육청 세출 증감률">'
         f'<line x1="{mid}" y1="20" x2="{mid}" y2="{H - 6}" stroke="var(--border)"/><text x="{mid}" y="14" text-anchor="middle" class="cpv-l">0%</text>']
    mx = max(abs(r[4] / r[3] - 1) for r in rows) or 1
    for j, (sd, y0, y1, a0, a1) in enumerate(rows):
        y = 26 + j * RH
        p = a1 / a0 - 1
        w = 300 * abs(p) / mx
        x = mid if p >= 0 else mid - w
        s.append(f'<text x="{LX}" y="{y + 13}" class="cpv-l">{h(sd)}</text>'
                 f'<rect x="{x:.1f}" y="{y}" width="{max(w, 1):.1f}" height="16" fill="{"#10b981" if p >= 0 else "#ef4444"}"><title>{h(sd)} 세출 {y0} {_eok(a0)} → {y1} {_eok(a1)}</title></rect>'
                 f'<text x="{(mid + w + 6) if p >= 0 else (mid - w - 6):.1f}" y="{y + 13}" text-anchor="{"start" if p >= 0 else "end"}" class="cpv-v">{p * 100:+.1f}%</text>')
    s.append("</svg>")
    dn = [r[0] for r in rows if r[4] < r[3]]
    note = f"{rows[0][1]}→{rows[0][2]} 세출 증감 · 감소 {len(dn)}곳({', '.join(dn[:6])}) — 감소 시도는 연수 예산 축소 가능성, 제안 단가·방식 조정 대상"
    return _card("🏛️", "#10 시도 교육재정 증감", "세출 총계 기준 증감률(최근 3개년)", "".join(s), note)


def build(sec=None):
    parts = []
    try:
        import cp_viz_data
        parts.append(cp_viz_data.build_admin())  # #7 주제 버블맵 · #8 경쟁사 레이더 · #10 시도 스코어카드
    except Exception as e:  # noqa: BLE001
        print(f"  cp_viz_data 관리 건너뜀: {str(e)[:120]}")
    for fn in (market_map, school_share, finance):
        try:
            parts.append(fn())
        except Exception as e:
            print(f"  cp_viz {fn.__name__} 건너뜀: {str(e)[:120]}")
    body = "".join(p for p in parts if p)
    return f'<div class="cpv-wrap">{body or EMPTY}</div>'


if __name__ == "__main__":
    d = build_cp()
    print({k: (len(v) if isinstance(v, list) else len(v or "")) for k, v in d.items()}, len(build()))
