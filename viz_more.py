#!/usr/bin/env python3
"""
시각화 확장 11종(사용자 승인 2026-11-22 "12번 빼고 모두").
  CP(나라장터 종합) — build_cp():
    #2 트리맵(시도 → 주제, 눌러서 확대)  #9 17개 시도 미니 격자  #6 사건과 함께 보는 공고 흐름(학사·정책 일정 주석)
  관리 칸(vizx 🎨 경영 시각화, ADMIN_PASSWORD 암호화) — build(sec):
    #1 마리메코 점유 지도  #3 와플(100칸) 점유  #4 덤벨(자사 vs 경쟁사)  #5 막대 레이스
    #7 매출 워터폴(전년→올해)  #8 시간 여행(지난달 오늘 vs 오늘)  #10 불릿 차트(KPI × 기준선)
  #11 전 화면 교차 강조는 화면 스크립트(data-sd 를 단 모든 그림·표 행).
외부 텍스트는 모두 escape. CP 문구에는 출처·수집 방식·도구명을 쓰지 않는다(방법론 비노출).
매출 수치는 Secret(MGMT_JSON) 에서만 읽어 관리 칸 암호문 안에만 싣는다.
"""
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from html import escape as h

from cp_viz import _jl, _n, _d, _eok, _card, SIDO, EMPTY

OWN = "비바샘연수원"
RIV = ("아이스크림", "티처빌")
VCOL = {OWN: "var(--own)", "아이스크림": "var(--rival)", "티처빌": "var(--cv8)", "기타": "#94a3b8"}
TODAY = date.today()
TILE = {"서울": (2, 1), "인천": (1, 1), "경기": (2, 2), "강원": (3, 1), "충남": (1, 3), "세종": (2, 3), "충북": (3, 2), "대전": (2, 4), "경북": (4, 2),
        "전북": (1, 4), "대구": (3, 4), "울산": (4, 4), "광주": (1, 5), "경남": (3, 5), "부산": (4, 5), "전남": (2, 5), "제주": (1, 6)}


def _sd(r):
    r = str(r or "")
    return next((s for s in SIDO if r.startswith(s)), "")


def _svg(W, H, label, body, cls="cpv-svg"):
    return f'<svg class="{cls}" viewBox="0 0 {W} {H}" role="img" aria-label="{h(label)}">{body}</svg>'


def _legend(items):
    return '<div class="sx-leg">' + "".join(f'<span><i style="background:{c}"></i>{h(n)}</span>' for n, c in items) + "</div>"


def _tbl(head, rows):
    return ('<div class="tbl-wrap"><table class="data"><thead><tr>' + "".join(f"<th>{h(x)}</th>" for x in head) + "</tr></thead><tbody>"
            + "".join("<tr" + (f' data-sd="{h(r[0])}"' if r and r[0] in SIDO else "") + ">" + "".join(f"<td>{h(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")


def _vend(v):
    return v if v in (OWN,) + RIV else "기타"


def _topics():
    from sales_analysis import _topics as t
    return t()


def _bids(days=365):
    from sales_analysis import _ok_title
    cut = TODAY - timedelta(days=days)
    out = []
    for x in _jl("training_bids.jsonl"):
        d = _d(x.get("d"))
        if d and d >= cut and _ok_title(x.get("t")):
            out.append({"d": d, "sd": _sd(x.get("r")), "a": _n(x.get("a")), "t": str(x.get("t") or "")})
    return out


def _contracts(days=365):
    cut = TODAY - timedelta(days=days)
    out = []
    for x in _jl("competitor_contracts.jsonl"):
        d = _d(x.get("date"))
        if d and d >= cut:
            out.append({"d": d, "sd": _sd(x.get("region")), "v": _vend(x.get("competitor")), "a": _n(x.get("amount"))})
    for x in _jl("competitor_wins.jsonl"):
        d = _d(x.get("date"))
        if d and d >= cut:
            out.append({"d": d, "sd": _sd(x.get("region")), "v": _vend(x.get("competitor")), "a": _n(x.get("amount"))})
    return out


def _months(n=12):
    out = []
    for i in range(n - 1, -1, -1):
        y, m = TODAY.year + (TODAY.month - 1 - i) // 12, (TODAY.month - 1 - i) % 12 + 1
        out.append(f"{y}-{m:02d}")
    return out


# ================= CP =================
def _squarify(items, x, y, w, hh):
    """items: [(값, 키)] 내림차순 -> [(키, x, y, w, h)] (단순 줄 배치 squarify)"""
    out = []
    items = [(v, k) for v, k in items if v > 0]
    tot = sum(v for v, _ in items)
    if not items or tot <= 0:
        return out
    rest = list(items)
    while rest:
        horiz = w >= hh
        side = hh if horiz else w
        row, best = [], None
        scale = (w * hh) / sum(v for v, _ in rest)
        for it in rest:
            trial = row + [it]
            s = sum(v for v, _ in trial) * scale
            thick = s / side
            worst = max(max((v * scale) / thick / thick, thick * thick / (v * scale)) for v, _ in trial)
            if best is not None and worst > best:
                break
            row, best = trial, worst
        s = sum(v for v, _ in row) * scale
        thick = s / side
        off = 0
        for v, k in row:
            ln = v * scale / thick
            if horiz:
                out.append((k, x, y + off, thick, ln))
            else:
                out.append((k, x + off, y, ln, thick))
            off += ln
        if horiz:
            x, w = x + thick, w - thick
        else:
            y, hh = y + thick, hh - thick
        rest = rest[len(row):]
    return out


def treemap():
    B = _bids()
    if not B:
        return _card("🌳", "연수 공고 금액 트리맵", "", EMPTY)
    T = _topics()
    S = defaultdict(float)
    ST = defaultdict(lambda: defaultdict(float))
    for b in B:
        if not b["sd"] or b["a"] <= 0:
            continue
        S[b["sd"]] += b["a"]
        tp = next((n for n, rx in T if rx.search(b["t"])), "기타 연수")
        ST[b["sd"]][tp] += b["a"]
    W, H = 780, 380
    tot = sum(S.values()) or 1
    rects = _squarify(sorted(((v, k) for k, v in S.items()), reverse=True), 0, 0, W, H)
    PAL = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6", "#f97316", "#84cc16", "#ec4899", "#0891b2"]
    tcol = {n: PAL[i % len(PAL)] for i, (n, _) in enumerate(T)}
    tcol["기타 연수"] = "#94a3b8"
    s = []
    for k, x, y, w, hh in rects:
        sub = _squarify(sorted(((v, n) for n, v in ST[k].items()), reverse=True), x + 2, y + 18, max(w - 4, 1), max(hh - 20, 1))
        s.append(f'<g class="vm-tm" data-sd="{h(k)}" data-tm="{h(k)}" style="cursor:pointer"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hh:.1f}" fill="var(--surface-2)" stroke="var(--surface)" stroke-width="2"/>')
        for n, sx, sy, sw, sh in sub:
            s.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="{tcol.get(n, "#94a3b8")}" opacity=".75" stroke="var(--surface)"><title>{h(k)} · {h(n)} · {_eok(ST[k][n])}</title></rect>')
        if w > 46 and hh > 22:
            s.append(f'<text x="{x + 4:.1f}" y="{y + 13:.1f}" style="font-size:12px;font-weight:800;fill:var(--ink)">{h(k)} {S[k] / tot * 100:.0f}%</text>')
        s.append("</g>")
    zoom = []
    for k in S:
        sub = _squarify(sorted(((v, n) for n, v in ST[k].items()), reverse=True), 0, 0, W, H)
        z = [f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="{tcol.get(n, "#94a3b8")}" opacity=".8" stroke="var(--surface)" stroke-width="2"><title>{h(n)} · {_eok(ST[k][n])}</title></rect>'
             + (f'<text x="{sx + 6:.1f}" y="{sy + 18:.1f}" style="font-size:13px;font-weight:800;fill:#fff">{h(n)}</text><text x="{sx + 6:.1f}" y="{sy + 34:.1f}" style="font-size:12px;fill:#fff">{_eok(ST[k][n])}</text>' if sw > 70 and sh > 40 else "")
             for n, sx, sy, sw, sh in sub]
        zoom.append(f'<div class="vm-tz" data-tz="{h(k)}" hidden><button type="button" class="sx-pb" data-tmb="1">← 전국</button> <b>{h(k)}</b> <small>{_eok(S[k])}</small>' + _svg(W, H, f"{k} 주제별 공고 금액", "".join(z)) + "</div>")
    top = max(S, key=S.get)
    body = f'<div class="vm-tmw v3d-no"><div class="vm-tm0">{_svg(W, H, "시도와 주제별 연수 공고 금액", "".join(s))}</div>{"".join(zoom)}</div>' + _legend([(n, c) for n, c in tcol.items()])
    note = f"지난 1년 연수 공고 금액 {_eok(tot)} · 가장 큰 시장 {top}({S[top] / tot * 100:.0f}%). 시도 칸을 누르면 주제별로 확대됩니다."
    return _card("🌳", "연수 공고 금액 트리맵", "면적 = 공고 금액 · 시도 → 주제", body, note)


def minis():
    B = _bids(400)
    ms = _months(12)
    C = {s: Counter() for s in SIDO}
    for b in B:
        k = b["d"].isoformat()[:7]
        if b["sd"] and k in ms:
            C[b["sd"]][k] += 1
    if not any(C.values()):
        return ""
    mx = max(max(c.values() or [0]) for c in C.values()) or 1
    cells = []
    for sd, (gx, gy) in TILE.items():
        v = [C[sd][k] for k in ms]
        a, b = sum(v[-3:]), sum(v[-6:-3])
        arrow, col = ("▲", "var(--own)") if a > b else ("▼", "var(--rival)") if a < b else ("–", "var(--muted)")
        pts = " ".join(f"{4 + i * 92 / 11:.1f},{38 - c / mx * 30:.1f}" for i, c in enumerate(v))
        cells.append(f'<div class="vm-mini" data-sd="{h(sd)}" style="grid-column:{gx};grid-row:{gy}"><b>{h(sd)}</b><span style="color:{col}">{arrow} {a}</span>'
                     f'<svg viewBox="0 0 100 42" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="var(--market)" stroke-width="2.2"/><polyline points="4,40 {pts} 96,40" fill="var(--market)" opacity=".12" stroke="none"/></svg>'
                     f'<title>{h(sd)} · 최근 3개월 {a}건(이전 3개월 {b}건)</title></div>')
    up = [sd for sd in SIDO if sum(C[sd][k] for k in ms[-3:]) > sum(C[sd][k] for k in ms[-6:-3])]
    note = f"선 = 월별 연수 공고 수(지난 12개월, 같은 눈금) · 숫자 = 최근 3개월 건수. 이전 3개월보다 늘어난 곳 {len(up)}곳: {', '.join(up[:8])}."
    return _card("🔲", "17개 시도 미니 격자", "지도 모양 배치 · 시도별 공고 추세", f'<div class="vm-minis v3d-no">{"".join(cells)}</div>', note)


EVENTS = [  # (날짜, 이름, 종류) — 학사·정책 공통 일정(공개 정보)
    ("2025-12-15", "교육청 예산 확정기", "예산"), ("2026-01-05", "겨울방학", "학사"), ("2026-03-02", "새 학기", "학사"),
    ("2026-06-03", "지방선거·교육감 선거", "정책"), ("2026-07-22", "여름방학", "학사"), ("2026-08-24", "2학기 개학", "학사"),
    ("2026-11-19", "수능", "학사"), ("2026-11-28", "중등 임용 1차", "학사"), ("2026-12-15", "교육청 예산 확정기", "예산"),
]


def events_chart(admin=False):
    B = _bids(400)
    if not B:
        return ""
    start = TODAY - timedelta(days=364)
    start = start - timedelta(days=start.weekday())
    wk = Counter()
    for b in B:
        if b["d"] >= start:
            wk[(b["d"] - start).days // 7] += 1
    n = (TODAY - start).days // 7 + 1
    W, H, L, T = 780, 250, 34, 60
    mx = max(wk.values() or [1])
    X = lambda i: L + i * (W - L - 16) / max(n - 1, 1)
    Y = lambda v: H - 30 - v / mx * (H - T - 34)
    pts = " ".join(f"{X(i):.1f},{Y(wk.get(i, 0)):.1f}" for i in range(n))
    s = [f'<polyline points="{L},{H - 30} {pts} {X(n - 1):.1f},{H - 30}" fill="var(--market)" opacity=".12" stroke="none"/>',
         f'<polyline points="{pts}" fill="none" stroke="var(--market)" stroke-width="2.5"/>']
    ev = list(EVENTS)
    if admin:
        try:
            prev = None
            for x in sorted(_jl("daily_stats.jsonl"), key=lambda r: str(r.get("date"))):
                v = _n(x.get("g2b_total_detail"))
                if prev and prev > 0 and v < prev * .6:
                    ev.append((str(x.get("date")), "수집 이상", "데이터"))
                prev = v
        except Exception:  # noqa: BLE001
            pass
    ecol = {"학사": "var(--cv2)", "정책": "var(--rival)", "예산": "var(--warn)", "데이터": "#94a3b8"}
    lane = 0
    for dstr, nm, kind in sorted(ev):
        d = _d(dstr)
        if not d or d < start or d > TODAY + timedelta(days=14):
            continue
        i = (d - start).days / 7
        x = X(min(i, n - 1 + 2))
        y = 16 + (lane % 3) * 15
        lane += 1
        fut = d > TODAY
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y + 3}" y2="{H - 30}" stroke="{ecol[kind]}" stroke-width="1.5" stroke-dasharray="{"2 3" if fut else "4 3"}"/>'
                 f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{ecol[kind]}"/><text x="{x + 6 if x < W - 130 else x - 6:.1f}" y="{y + 4:.1f}" text-anchor="{"start" if x < W - 130 else "end"}" style="font-size:11px;font-weight:700;fill:var(--ink)">{h(nm)}{" (예정)" if fut else ""}</text>')
    for i in range(0, n):
        d = start + timedelta(days=7 * i)
        if d.day <= 7 and (i == 0 or (start + timedelta(days=7 * (i - 1))).month != d.month):
            s.append(f'<text x="{X(i):.1f}" y="{H - 12}" text-anchor="middle" class="cpv-l" style="font-size:11px">{d.month}월</text>')
    pk = max(wk, key=wk.get)
    pd_ = start + timedelta(days=7 * pk)
    note = f"주별 연수 공고 수에 학사·정책 일정을 겹쳤습니다. 가장 많았던 주 {pd_.isoformat()}~ ({wk[pk]}건). 새 학기·예산 확정 뒤에 공고가 몰리는 흐름을 확인하세요."
    legend = _legend([("학사 일정", ecol["학사"]), ("정책", ecol["정책"]), ("예산", ecol["예산"])] + ([("수집 이상", ecol["데이터"])] if admin else []))
    return _card("📌", "사건과 함께 보는 공고 흐름", "주별 연수 공고 수 × 학사·정책 일정", '<div class="v3d-no">' + _svg(W, H, "주별 공고와 일정 주석", "".join(s)) + "</div>" + legend, note)


def build_cp():
    out = []
    for fn in (treemap, minis, events_chart):
        try:
            x = fn()
            if x:
                out.append(x)
        except Exception as e:  # noqa: BLE001
            print(f"  viz_more {fn.__name__} 건너뜀: {str(e)[:120]}")
    return out


# ================= 관리 =================
def marimekko():
    B, C = _bids(), _contracts()
    if not B or not C:
        return _card("🧱", "마리메코 점유 지도", "", EMPTY)
    S = Counter()
    for b in B:
        if b["sd"]:
            S[b["sd"]] += b["a"]
    V = defaultdict(Counter)
    for c in C:
        if c["sd"]:
            V[c["sd"]][c["v"]] += 1
    sds = [sd for sd, _ in S.most_common() if S[sd] > 0]
    tot = sum(S[sd] for sd in sds) or 1
    W, H, L, T = 780, 340, 40, 20
    x = L
    s = []
    for sd in sds:
        w = (W - L - 10) * S[sd] / tot
        vv = V.get(sd) or Counter()
        n = sum(vv.values())
        y = T
        if n:
            for v in (OWN,) + RIV + ("기타",):
                if not vv.get(v):
                    continue
                hh = (H - T - 40) * vv[v] / n
                s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w - 1.5, .5):.1f}" height="{hh:.1f}" fill="{VCOL[v]}" opacity=".85" data-sd="{h(sd)}"><title>{h(sd)} · {"자사" if v == OWN else h(v)} {vv[v]}건({vv[v] / n * 100:.0f}%) · 시장 {_eok(S[sd])}</title></rect>')
                y += hh
        else:
            s.append(f'<rect x="{x:.1f}" y="{T}" width="{max(w - 1.5, .5):.1f}" height="{H - T - 40}" fill="var(--surface-2)" data-sd="{h(sd)}"><title>{h(sd)} · 확인된 계약 없음 · 시장 {_eok(S[sd])}</title></rect>')
        if w > 24:
            s.append(f'<text x="{x + w / 2:.1f}" y="{H - 24}" text-anchor="middle" style="font-size:11.5px;font-weight:800;fill:var(--ink)">{h(sd)}</text><text x="{x + w / 2:.1f}" y="{H - 10}" text-anchor="middle" class="cpv-l" style="font-size:10px">{S[sd] / tot * 100:.0f}%</text>')
        x += w
    s.append(f'<text x="{L - 6}" y="{T + 10}" text-anchor="end" class="cpv-l" style="font-size:10px">100%</text><text x="{L - 6}" y="{H - 40}" text-anchor="end" class="cpv-l" style="font-size:10px">0</text>')
    big_weak = [sd for sd in sds[:6] if V.get(sd) and V[sd][OWN] / max(sum(V[sd].values()), 1) < .2]
    note = f"칸 폭 = 지난 1년 연수 공고 금액(시장 크기) · 칸 높이 = 확인된 계약 중 업체별 비중. 큰 시장인데 자사 비중이 20% 미만: {', '.join(big_weak) or '없음'} — 우선 공략 대상."
    return _card("🧱", "마리메코 점유 지도", "시장 크기 × 업체 점유", '<div class="v3d-no">' + _svg(W, H, "시도별 시장 크기와 업체 점유", "".join(s)) + "</div>"
                 + _legend([("자사", VCOL[OWN]), ("아이스크림", VCOL["아이스크림"]), ("티처빌", VCOL["티처빌"]), ("기타", VCOL["기타"]), ("계약 확인 안 됨", "var(--surface-2)")]), note)


def waffle():
    C = _contracts()
    if not C:
        return _card("🧇", "와플 차트 · 100칸 점유", "", EMPTY)

    def grid(cnt, label):
        tot = sum(cnt.values()) or 1
        cells, order = [], [v for v in (OWN,) + RIV + ("기타",) if cnt.get(v)]
        k = {v: round(cnt[v] / tot * 100) for v in order}
        diff = 100 - sum(k.values())
        if order:
            k[max(order, key=lambda v: cnt[v])] += diff
        for v in order:
            cells += [v] * max(k[v], 0)
        cells = cells[:100]
        sq = "".join(f'<rect x="{(i % 10) * 17}" y="{(i // 10) * 17}" width="15" height="15" rx="3" fill="{VCOL[v]}"><title>{"자사" if v == OWN else h(v)} {k[v]}칸</title></rect>' for i, v in enumerate(cells))
        own = k.get(OWN, 0)
        return f'<div class="vm-wf"><b>{h(label)}</b>{_svg(170, 170, label, sq, "cpv-svg vm-wfs")}<p>자사 <strong>{own}</strong>칸 / 100</p></div>'
    cn, am = Counter(), Counter()
    for c in C:
        cn[c["v"]] += 1
        am[c["v"]] += c["a"]
    body = f'<div class="vm-wfw v3d-no">{grid(cn, "계약 건수")}{grid(am, "계약 금액")}</div>' + _legend([("자사", VCOL[OWN]), ("아이스크림", VCOL["아이스크림"]), ("티처빌", VCOL["티처빌"]), ("기타", VCOL["기타"])])
    note = f"지난 1년 확인된 계약 {sum(cn.values())}건 · {_eok(sum(am.values()))} 기준. 건수 칸보다 금액 칸이 적으면 소액 위주라는 뜻입니다."
    return _card("🧇", "와플 차트 · 100칸 점유", "확인된 계약 중 업체별 몫", body, note)


def dumbbell():
    C = _contracts()
    O, R = Counter(), Counter()
    for c in C:
        if not c["sd"]:
            continue
        if c["v"] == OWN:
            O[c["sd"]] += 1
        elif c["v"] in RIV:
            R[c["sd"]] += 1
    sds = sorted([sd for sd in SIDO if O[sd] or R[sd]], key=lambda sd: -(R[sd] - O[sd]))
    if not sds:
        return _card("🏋️", "덤벨 차트 · 자사 vs 경쟁사", "", EMPTY)
    W, L = 780, 70
    H = 30 + 24 * len(sds)
    mx = max(max(O.values() or [0]), max(R.values() or [0])) or 1
    X = lambda v: L + v / mx * (W - L - 60)
    s = [f'<line x1="{X(0)}" x2="{X(0)}" y1="14" y2="{H - 10}" stroke="var(--border)"/>']
    for i, sd in enumerate(sds):
        y = 26 + i * 24
        a, b = O[sd], R[sd]
        s.append(f'<g data-sd="{h(sd)}"><text x="{L - 8}" y="{y + 4}" text-anchor="end" style="font-size:12px;font-weight:700;fill:var(--ink)">{h(sd)}</text>'
                 f'<line x1="{X(a):.1f}" x2="{X(b):.1f}" y1="{y}" y2="{y}" stroke="var(--border)" stroke-width="5" stroke-linecap="round"/>'
                 f'<circle cx="{X(b):.1f}" cy="{y}" r="7" fill="var(--rival)"><title>{h(sd)} 경쟁사 {b}건</title></circle><circle cx="{X(a):.1f}" cy="{y}" r="7" fill="var(--own)"><title>{h(sd)} 자사 {a}건</title></circle>'
                 f'<text x="{max(X(a), X(b)) + 12:.1f}" y="{y + 4}" class="cpv-l" style="font-size:11px">{a} vs {b} ({a - b:+d})</text></g>')
    gap = [sd for sd in sds if R[sd] - O[sd] >= 3][:5]
    note = f"지난 1년 확인된 계약 건수(경쟁사 = 아이스크림+티처빌). 간격이 큰 순서로 정렬했습니다. 3건 이상 뒤진 곳: {', '.join(gap) or '없음'}."
    return _card("🏋️", "덤벨 차트 · 자사 vs 경쟁사", "초록 = 자사 · 빨강 = 경쟁사", '<div class="v3d-no">' + _svg(W, H, "시도별 자사와 경쟁사 계약 건수", "".join(s)) + "</div>", note)


def race():
    ev = []
    for x in _jl("competitor_contracts.jsonl"):
        d = _d(x.get("date"))
        if d:
            ev.append((d, _vend(x.get("competitor")) if x.get("competitor") in (OWN,) + RIV else str(x.get("competitor") or "기타")[:10], _n(x.get("amount"))))
    for x in _jl("org_watch.jsonl"):
        d = _d(x.get("date"))
        if d:
            ev.append((d, str(x.get("org") or "기타")[:10], _n(x.get("amount"))))
    ms = _months(12)
    if not ev:
        return ""
    cum = Counter()
    for d, v, a in ev:
        if d.isoformat()[:7] < ms[0]:
            cum[v] += a
    frames = []
    for k in ms:
        for d, v, a in ev:
            if d.isoformat()[:7] == k:
                cum[v] += a
        frames.append((k, cum.most_common(8)))
    names = sorted({v for _, top in frames for v, _ in top})
    data = {"f": [[k, [[v, round(a / 1e6, 1)] for v, a in top]] for k, top in frames]}
    NEU = ["#6366f1", "#0ea5e9", "#a855f7", "#14b8a6", "#84cc16", "#ec4899", "#64748b", "#0891b2", "#eab308", "#78716c"]
    others = [v for v in names if v not in VCOL or v == "기타"]
    col = {v: (VCOL[v] if v in VCOL and v != "기타" else NEU[others.index(v) % len(NEU)]) for v in names}
    last = frames[-1][1]
    mx = last[0][1] if last else 1
    rows = "".join(f'<div class="vm-rr" data-n="{h(v)}" style="transform:translateY({i * 34}px)"><span class="vm-rn">{"자사" if v == OWN else h(v)}</span><span class="vm-rb"><i style="width:{a / mx * 100:.1f}%;background:{col[v]}"></i></span><em>{_eok(a)}</em></div>' for i, (v, a) in enumerate(last))
    body = (f'<div class="vm-race v3d-no" data-race="{h(json.dumps(data, ensure_ascii=False))}" data-col="{h(json.dumps(col, ensure_ascii=False))}">'
            f'<div class="sx-play"><button type="button" class="sx-pb" data-vm="race">▶ 12개월 레이스</button><b class="vm-rk">{h(frames[-1][0])}</b></div>'
            f'<div class="vm-rrs" style="height:{34 * max(len(last), 1)}px">{rows}</div></div>')
    note = "교원연수 관련 업체의 누적 계약 금액(상위 8곳)이 월별로 어떻게 순위가 바뀌는지 재생합니다. 업체명은 계약 기록 기준입니다."
    return _card("🏁", "막대 레이스 · 누적 계약 금액", "월별 누적 상위 8곳", body, note)


def _mgmt():
    try:
        import mgmt_owner
        return mgmt_owner.load()
    except Exception:  # noqa: BLE001
        return None


def waterfall(M):
    if not M:
        return _card("🧮", "매출 워터폴 · 전년 → 올해", "", '<p class="cpv-note">데이터 준비 중</p>')
    Y = {r["y"]: r for r in M.get("years") or []}
    c = Y.get(TODAY.year) or Y.get(max(Y))
    p = Y.get(c["y"] - 1)
    if not p:
        return ""
    steps = [("위탁 용역", c["b2g"] - p["b2g"]), ("교육청 단체", c["b2s"] - p["b2s"]), ("개인(B2C)", c["b2c"] - p["b2c"])]
    other = (c["tot"] - p["tot"]) - sum(v for _, v in steps)
    if abs(other) > .05:
        steps.append(("기타", other))
    W, H, L, B = 780, 300, 60, 40
    vals = [p["tot"]]
    run = p["tot"]
    for _, v in steps:
        run += v
        vals.append(run)
    lo, hi = min(0, min(vals)), max(vals) * 1.1
    Y_ = lambda v: H - B - (v - lo) / (hi - lo) * (H - B - 20)
    bw = (W - L - 20) / (len(steps) + 2) * .6
    gx = lambda i: L + (i + .5) * (W - L - 20) / (len(steps) + 2) - bw / 2
    s = [f'<rect x="{gx(0):.1f}" y="{Y_(p["tot"]):.1f}" width="{bw:.1f}" height="{Y_(lo) - Y_(p["tot"]):.1f}" rx="4" fill="#94a3b8"/><text x="{gx(0) + bw / 2:.1f}" y="{Y_(p["tot"]) - 6:.1f}" text-anchor="middle" class="cpv-v" style="font-size:12px">{p["tot"]:,.1f}억</text><text x="{gx(0) + bw / 2:.1f}" y="{H - 18}" text-anchor="middle" class="cpv-l" style="font-size:12px">{p["y"]}</text>']
    run = p["tot"]
    for i, (nm, v) in enumerate(steps, 1):
        a, b = run, run + v
        top, bot = max(a, b), min(a, b)
        colr = "var(--own)" if v >= 0 else "var(--rival)"
        s.append(f'<rect x="{gx(i):.1f}" y="{Y_(top):.1f}" width="{bw:.1f}" height="{max(Y_(bot) - Y_(top), 1):.1f}" rx="4" fill="{colr}"><title>{h(nm)} {v:+,.1f}억</title></rect>'
                 f'<text x="{gx(i) + bw / 2:.1f}" y="{Y_(top) - 6:.1f}" text-anchor="middle" class="cpv-v" style="font-size:12px">{v:+,.1f}억</text>'
                 f'<text x="{gx(i) + bw / 2:.1f}" y="{H - 18}" text-anchor="middle" class="cpv-l" style="font-size:12px">{h(nm)}</text>'
                 f'<line x1="{gx(i - 1) + bw:.1f}" x2="{gx(i):.1f}" y1="{Y_(a):.1f}" y2="{Y_(a):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>')
        run = b
    i = len(steps) + 1
    s.append(f'<rect x="{gx(i):.1f}" y="{Y_(c["tot"]):.1f}" width="{bw:.1f}" height="{Y_(lo) - Y_(c["tot"]):.1f}" rx="4" fill="var(--market)"/><text x="{gx(i) + bw / 2:.1f}" y="{Y_(c["tot"]) - 6:.1f}" text-anchor="middle" class="cpv-v" style="font-size:12px">{c["tot"]:,.1f}억</text><text x="{gx(i) + bw / 2:.1f}" y="{H - 18}" text-anchor="middle" class="cpv-l" style="font-size:12px">{c["y"]}{"E" if c["y"] == TODAY.year else ""}</text>')
    worst = min(steps, key=lambda z: z[1])
    best = max(steps, key=lambda z: z[1])
    note = f"{p['y']} {p['tot']:,.1f}억 → {c['y']}{'(예상)' if c['y'] == TODAY.year else ''} {c['tot']:,.1f}억. 가장 크게 줄어든 곳: {worst[0]}({worst[1]:+,.1f}억), 가장 크게 늘어난 곳: {best[0]}({best[1]:+,.1f}억)."
    return _card("🧮", "매출 워터폴 · 전년 → 올해", "매출 변화를 원인별로 분해", '<div class="v3d-no">' + _svg(W, H, "매출 증감 워터폴", "".join(s)) + "</div>", note)


TT_KEYS = [("g2b_total_detail", "교육청·연수원 발주(누적)", 1, "건"), ("ai_rows_count", "AI·에듀테크 발주", 1, "건"), ("ai_rows_amount_sum", "AI·에듀테크 발주 금액", 1e8, "억"),
           ("own_pipeline_total", "자사 영업 파이프라인", 1, "건"), ("own_pipeline_target", "파이프라인 목표 금액", 1e8, "억")]


def timetravel():
    L = sorted([x for x in _jl("daily_stats.jsonl") if _d(x.get("date"))], key=lambda r: r["date"])
    if len(L) < 10:
        return ""
    rows = [[x["date"]] + [round(_n(x.get(k)) / div, 1) for k, _, div, _ in TT_KEYS] for x in L]
    cur = rows[-1]
    target = (TODAY - timedelta(days=30)).isoformat()
    i0 = max(i for i, r in enumerate(rows) if r[0] <= target) if any(r[0] <= target for r in rows) else 0
    meta = [[nm, unit] for _, nm, _, unit in TT_KEYS]

    def cards(a, b):
        out = []
        for j, (nm, unit) in enumerate(meta, 1):
            va, vb = a[j], b[j]
            d = vb - va
            cl = "var(--own)" if d > 0 else "var(--rival)" if d < 0 else "var(--muted)"
            out.append(f'<div class="vm-tt"><small>{h(nm)}</small><b>{vb:,.1f}{unit}</b><span>{h(a[0])}: {va:,.1f}{unit}</span><em style="color:{cl}">{d:+,.1f}{unit}</em></div>')
        return "".join(out)
    body = (f'<div class="vm-ttw" data-tt="{h(json.dumps({"r": rows, "m": meta}, ensure_ascii=False))}">'
            f'<label class="vm-ttl">⏪ 비교 시점 <input type="range" class="vm-ttr" min="0" max="{len(rows) - 2}" value="{i0}" aria-label="비교 날짜"> <b class="vm-ttd">{h(rows[i0][0])}</b> → 오늘 {h(cur[0])}</label>'
            f'<div class="vm-tts">{cards(rows[i0], cur)}</div></div>')
    note = f"매일 남긴 핵심 숫자 {len(rows)}일 치({rows[0][0]}부터)를 되감아 지금과 비교합니다. 기본은 '지난달 오늘'입니다."
    return _card("⏪", "시간 여행 · 그때 vs 지금", "슬라이더로 비교 날짜를 고르세요", body, note)


def bullets(M):
    K = []
    if M:
        try:
            Y = {r["y"]: r for r in M["years"]}
            c, p = Y.get(TODAY.year), Y.get(TODAY.year - 1)
            from mgmt_owner import g_share
            tgt = ((M.get("plan27") or {}).get("path") or {}).get("target") or []
            t27 = float(tgt[2]) if len(tgt) > 2 and tgt[2] else float(M["target"]["b2g"])
            if c:
                K.append(("B2G 비중(낮을수록 좋음)", g_share(c), t27, [t27 + 25, t27 + 10, 0], "%", True))
            if c and p:
                K.append((f"{c['y']} 매출(예상)", c["tot"], p["tot"], [p["tot"] * .8, p["tot"] * .95, p["tot"] * 1.3], "억", False))
                on_c, on_p = c["b2c"] + c["b2s"], p["b2c"] + p["b2s"]
                K.append(("개인+단체 매출", on_c, on_p * 1.3, [on_p * .9, on_p * 1.1, on_p * 1.6], "억", False))
        except Exception as e:  # noqa: BLE001
            print(f"  viz_more 불릿 매출 건너뜀: {type(e).__name__}")
    B = _bids(800)
    t = TODAY
    cur = sum(1 for b in B if b["d"] > t - timedelta(days=90))
    ly = sum(1 for b in B if t - timedelta(days=455) < b["d"] <= t - timedelta(days=365))
    if ly:
        K.append(("연수 공고(최근 90일)", cur, ly, [ly * .7, ly * .9, ly * 1.4], "건", False))
    C = _contracts(120)
    own = sum(1 for c in C if c["v"] == OWN and c["d"] > t - timedelta(days=30))
    own_p = sum(1 for c in C if c["v"] == OWN and t - timedelta(days=60) < c["d"] <= t - timedelta(days=30))
    K.append(("자사 계약(최근 30일)", own, max(own_p, 1), [own_p * .7, own_p, max(own_p * 1.6, 3)], "건", False))
    if not K:
        return _card("🎯", "불릿 차트 · KPI × 기준선", "", EMPTY)
    W, L, R = 780, 200, 70
    H = 20 + 44 * len(K)
    s = []
    for i, (nm, v, ref, bands, unit, rev) in enumerate(K):
        y = 14 + i * 44
        mx = max(v, ref, bands[0] if rev else bands[-1]) * 1.08 or 1
        X = lambda a, mx=mx: L + max(a, 0) / mx * (W - L - R)
        if rev:  # 낮을수록 좋음: 0~기준 = 좋음, 기준~+10 = 보통, 그 위 = 나쁨
            zones = [(0, ref, "#e2e8f0"), (ref, ref + 10, "#cbd5e1"), (ref + 10, mx, "#94a3b8")]
        else:  # 높을수록 좋음: 0~bands[0] = 나쁨, ~bands[1] = 보통, 그 위 = 좋음
            zones = [(0, bands[0], "#94a3b8"), (bands[0], bands[1], "#cbd5e1"), (bands[1], mx, "#e2e8f0")]
        for a, b, sh in zones:
            b = min(b, mx)
            if b > a:
                s.append(f'<rect x="{X(a):.1f}" y="{y}" width="{X(b) - X(a):.1f}" height="26" fill="{sh}" opacity=".7"/>')
        good = (v <= ref) if rev else (v >= ref)
        s.append(f'<rect x="{L}" y="{y + 8}" width="{max(X(v) - L, 1):.1f}" height="10" rx="3" fill="{"var(--own)" if good else "var(--rival)"}"><title>{h(nm)} {v:,.1f}{unit}</title></rect>'
                 f'<line x1="{X(ref):.1f}" x2="{X(ref):.1f}" y1="{y + 2}" y2="{y + 24}" stroke="var(--ink)" stroke-width="3"><title>기준 {ref:,.1f}{unit}</title></line>'
                 f'<text x="{L - 10}" y="{y + 17}" text-anchor="end" style="font-size:12.5px;font-weight:800;fill:var(--ink)">{h(nm)}</text>'
                 f'<text x="{W - R + 8}" y="{y + 17}" style="font-size:12px;font-weight:800;fill:{"var(--own)" if good else "var(--rival)"}">{v:,.1f}{unit}</text>')
    note = "막대 = 현재 값, 검은 세로선 = 기준(B2G 비중은 2027 계획, 매출은 전년, 개인+단체는 전년 × 1.3, 공고는 작년 같은 90일, 자사 계약은 이전 30일). 바탕 띠는 나쁨·보통·좋음 구간입니다."
    return _card("🎯", "불릿 차트 · KPI × 기준선", "초록 = 기준 달성 · 빨강 = 미달", '<div class="v3d-no">' + _svg(W, H, "KPI 불릿 차트", "".join(s)) + "</div>", note)


def _safe(fn, *a):
    try:
        return fn(*a) or ""
    except Exception as e:  # noqa: BLE001
        print(f"  viz_more {fn.__name__} 건너뜀: {str(e)[:140]}")
        return ""


def build(sec=None):
    M = _mgmt()
    parts = [_safe(bullets, M), _safe(waterfall, M), _safe(timetravel), _safe(marimekko), _safe(waffle), _safe(dumbbell), _safe(race), _safe(events_chart, True)]
    body = "".join(p for p in parts if p)
    return f'<div class="cpv-wrap"><div class="cpv-grid">{body or EMPTY}</div></div>'


if __name__ == "__main__":
    a = build()
    print("admin", len(a))
    print("cp", [len(x) for x in build_cp()])
