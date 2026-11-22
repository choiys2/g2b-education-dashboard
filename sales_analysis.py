#!/usr/bin/env python3
"""
📈 영업 분석(사용자 승인 2026-11-21 "모두 진행해줘").
  관리 칸(salesx, ADMIN_PASSWORD 암호화) — build(sec):
    C4 이번 주 변화 3가지 · A1 수주 가능성 점수(+C2 비교 창) · A2 공고 예보(가능성 포함) · B2 영업 골든타임 달력
    B1 흐름도(계획→공고→결과) · A3/B4 계약 금액 벤치마크 · A4/B5 재구매 레이더 · A5/B6/B7 과정 공백·주제 순위·기회 매트릭스
    B3 경쟁사 영토 재생 · A6 진짜 변화 vs 수집 문제 · A7 2027 매출 구성 시뮬레이터
  CP(나라장터 종합) — build_cp(): A2 공고 예보 달력(사실만, 가능성 없음) + C1 관심 기관 즐겨찾기 자리
모든 계산은 규칙 기반(외부 유료 API 없음). 외부 텍스트는 전부 escape. 표본이 적은 결과는 '추정'으로 표시.
CP 문구에는 출처·수집 방식·도구명을 쓰지 않는다(방법론 비노출).
"""
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from html import escape as h

from cp_viz import _jl, _js, _n, _d, _eok, _card, SIDO, EMPTY
from cp_viz_data import _tok, _jac, TRAIN_RE

OWN = "비바샘연수원"
RIVALS = ("아이스크림", "티처빌")
COLV = {OWN: "var(--own)", "아이스크림": "var(--rival)", "티처빌": "var(--cv8)", "기타": "#94a3b8", "미확인": "#cbd5e1"}
TODAY = date.today()
# 연수와 무관한 공사·시설·물품(예: '모듈러 임시교사 제작·설치', '연수원 증축 건설사업관리')은 분석에서 뺀다
EXCL = re.compile(r"공사|건설|증축|신축|개축|리모델링|설치|모듈러|임시\s?교사|감리|감독권한|임차|구매|물품|급식|청소|경비|시설\s?관리|보수|철거|설계|조경|전기|통신\s?공사|소방|차량|버스|식자재|인쇄|제작\s?납품"
                  r"|세탁|침구|기숙사|유지\s?관리|유지\s?보수|재해\s?복구|통역|정보\s?통신|시스템\s?(구축|고도화)|서버|장비|홈페이지|전산"
                  r"|학생\s?(국외|해외)|학생국외|어학\s?연수|해외\s?(영어)?\s?체험|국제\s?교류|수학여행|현장\s?체험\s?학습|교사동|석면|내진|폐기물|체전|체육대회")
TEACH = re.compile(r"연수|교원|교사|직무|역량\s?강화|원격\s?교육|에듀테크|컨설팅|워크숍|특강|교육\s?운영|코칭|아카데미")


def _ok_title(t):
    t = str(t or "")
    return bool(TEACH.search(t)) and not EXCL.search(t)


def _ok(o):  # 기관 비교 키: 마지막 단어(예: '경상북도교육청 경상북도교육청연수원' -> '경상북도교육청연수원')
    o = str(o or "").strip()
    return o.split()[-1] if o else ""


def _topics():
    from strategy_intel import TOPICS, STRENGTH5
    out = [(n, re.compile(p)) for n, p in TOPICS]
    have = {n for n, _ in out}
    for n, _i, p in STRENGTH5:
        toks = set(n.split("·"))
        if n not in have and not any(toks & set(x.split("·")) for x in have):
            out.append((n, re.compile(p)))
    return out


def _strength():
    from strategy_intel import STRENGTH5
    return [(n, re.compile(p)) for n, _i, p in STRENGTH5]


# ---------------- 공통 데이터 ----------------
def _load():
    D = {}
    D["TB"] = [dict(x, a=_n(x.get("a")), dd=_d(x.get("d")), cd=_d(x.get("c")), ok=_ok(x.get("o")), tok=_tok(x.get("t"))) for x in _jl("training_bids.jsonl") if _d(x.get("d")) and _ok_title(x.get("t"))]
    D["CC"] = [dict(x, a=_n(x.get("amount")), dd=_d(x.get("date")), ok=_ok(x.get("org"))) for x in _jl("competitor_contracts.jsonl") if _d(x.get("date"))]
    D["CW"] = [dict(x, a=_n(x.get("amount")), dd=_d(x.get("date"))) for x in _jl("competitor_wins.jsonl")]
    D["OW"] = [dict(x, a=_n(x.get("amount")), dd=_d(x.get("date"))) for x in _jl("org_watch.jsonl")]
    D["OP"] = [dict(x, a=_n(x.get("a")), dd=_d(x.get("d")), ok=_ok(x.get("o")), tok=_tok(x.get("t"))) for x in _jl("order_plans.jsonl") if TRAIN_RE.search(str(x.get("t") or "")) and _ok_title(x.get("t"))]
    D["SIG"] = _jl("edu_office_signals.jsonl")
    D["DS"] = _jl("daily_stats.jsonl")
    D["PW"] = _jl("pipeline_watch.jsonl")
    D["CAT"] = (_js("competitor_course_catalog.json") or {}).get("companies") or {}
    win = {}
    for x in D["CW"]:
        if x.get("_key"):
            win[str(x["_key"])] = (x.get("competitor") or "기타", x["a"])
    for x in D["OW"]:
        if x.get("kind") == "win" and x.get("k") and str(x["k"]) not in win:
            win[str(x["k"])] = ("기타", x["a"])
    D["WIN"] = win
    by_org = defaultdict(list)
    for x in D["TB"]:
        by_org[x["ok"]].append(x)
    D["TB_ORG"] = by_org
    cc_org = defaultdict(list)
    for x in D["CC"]:
        cc_org[x["ok"]].append(x)
    D["CC_ORG"] = cc_org
    return D


def _vend(name):
    n = str(name or "")
    return n if n in (OWN,) + RIVALS else "기타"


def _svg(W, H, label, body, cls="cpv-svg"):
    return f'<svg class="{cls}" viewBox="0 0 {W} {H}" role="img" aria-label="{h(label)}">{body}</svg>'


def _legend(items):
    return '<div class="sx-leg">' + "".join(f'<span><i style="background:{c}"></i>{h(n)}</span>' for n, c in items) + "</div>"


def _tbl(head, rows, cls=""):
    return (f'<div class="tbl-wrap {cls}"><table class="data"><thead><tr>' + "".join(f"<th>{h(x)}</th>" for x in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")


def _url(u):
    u = str(u or "")
    return u if re.match(r"^https://[A-Za-z0-9.-]+\.(go\.kr|or\.kr|kr|com)/", u) else ""


def _link(t, u, n=46):
    t = str(t or "")
    t = t[:n] + ("…" if len(t) > n else "")
    u = _url(u)
    return f'<a href="{h(u)}" target="_blank" rel="noopener noreferrer">{h(t)}</a>' if u else h(t)


# ---------------- C4 이번 주 변화 3가지 ----------------
def weekly(D):
    t = TODAY
    w0, w1 = t - timedelta(days=7), t - timedelta(days=14)
    out = []
    cur = [x for x in D["TB"] if x["dd"] > w0]
    pre = [x for x in D["TB"] if w1 < x["dd"] <= w0]
    if cur or pre:
        d = len(cur) - len(pre)
        out.append((abs(d) / max(len(pre), 1), "📣", f"연수 공고 {len(cur)}건(지난주 {len(pre)}건, {'+' if d >= 0 else ''}{d}) · 금액 {_eok(sum(x['a'] for x in cur))}"))
    oc = Counter(x["ok"] for x in cur if x["ok"])
    if oc:
        o, n = oc.most_common(1)[0]
        out.append((n / max(len(cur), 1) + .3, "🏢", f"이번 주 가장 많이 낸 기관: {o} {n}건"))
    for v in (OWN,) + RIVALS:
        a = [x for x in D["CC"] if x.get("competitor") == v and x["dd"] > t - timedelta(days=30)]
        b = [x for x in D["CC"] if x.get("competitor") == v and t - timedelta(days=60) < x["dd"] <= t - timedelta(days=30)]
        if a or b:
            d = len(a) - len(b)
            out.append((abs(d) / max(len(b), 1) * (1.2 if v == OWN else 1), "🟢" if v == OWN else "🔴", f"{'자사' if v == OWN else v} 계약 최근 30일 {len(a)}건(이전 30일 {len(b)}건, {'+' if d >= 0 else ''}{d}) · {_eok(sum(x['a'] for x in a))}"))
    near = [x for x in D["TB"] if x["cd"] and t <= x["cd"] <= t + timedelta(days=7)]
    if near:
        out.append((len(near) / 10, "⏰", f"7일 안에 마감되는 공고 {len(near)}건 · {_eok(sum(x['a'] for x in near))}"))
    out.sort(key=lambda x: -x[0])
    if not out:
        return ""
    body = '<ol class="sx-wk">' + "".join(f"<li><span>{i}</span>{h(s)}</li>" for _, i, s in out[:3]) + "</ol>"
    return _card("📝", "이번 주 변화 3가지", f"{w0.isoformat()} ~ {t.isoformat()} · 변화 폭이 큰 순", body, "주간 보고 첫 줄로 그대로 쓰셔도 됩니다(규칙 계산, 매주 갱신).")


# ---------------- A1 수주 가능성 점수 + C2 비교 창 ----------------
def _score(x, D, S5, own_amts):
    pts, why = 20, []
    past = [y for y in D["TB_ORG"].get(x["ok"], []) if y["k"] != x["k"] and y["dd"] < x["dd"]]
    if past:
        v = min(20, 6 + 4 * len(past))
        pts += v
        why.append(f"반복 발주 기관(과거 {len(past)}건) +{v}")
    cc = D["CC_ORG"].get(x["ok"], [])
    own = [y for y in cc if y.get("competitor") == OWN]
    riv = [y for y in cc if y.get("competitor") in RIVALS]
    if own:
        pts += 25
        why.append(f"자사 계약 이력 {len(own)}건 +25")
    if riv and not own:
        v = min(15, 5 * len(riv))
        pts -= v
        why.append(f"경쟁사 단골({len(riv)}건) -{v}")
    t = str(x.get("t") or "")
    hit = [n for n, rx in S5 if rx.search(t)]
    if hit:
        pts += 20
        why.append(f"강점 분야({hit[0]}) +20")
    elif re.search(r"AI|인공지능|디지털|원격", t):
        pts += 8
        why.append("디지털·원격 +8")
    a = x["a"]
    if 2e7 <= a < 3e8:
        pts += 15
        why.append("주력 금액대(2천만~3억) +15")
    elif 0 < a < 2e7:
        pts += 8
        why.append("소액(수의계약 영역) +8")
    elif a >= 3e8:
        pts += 4
        why.append("대형(협력 검토) +4")
    if x["cd"]:
        left = (x["cd"] - TODAY).days
        if left >= 5:
            pts += 10
            why.append(f"준비 기간 {left}일 +10")
        elif left >= 2:
            pts += 4
            why.append(f"준비 기간 {left}일 +4")
        else:
            why.append(f"마감 임박({left}일)")
    return max(0, min(100, pts)), why, riv, own


def _similar(x, D, n=3):
    c = []
    for y in D["TB"]:
        if y["k"] == x["k"] or y["dd"] >= x["dd"]:
            continue
        s = _jac(x["tok"], y["tok"]) + (.25 if y["ok"] == x["ok"] else 0)
        if s >= .3:
            c.append((s, y))
    c.sort(key=lambda z: -z[0])
    return [y for _, y in c[:n]]


def win_score(D):
    S5 = _strength()
    own_amts = [x["a"] for x in D["CC"] if x.get("competitor") == OWN]
    open_ = [x for x in D["TB"] if (x["cd"] and x["cd"] >= TODAY) or (not x["cd"] and x["dd"] >= TODAY - timedelta(days=10))]
    if not open_:
        return _card("🎯", "수주 가능성 점수 · 입찰 우선순위", "진행 중 공고", EMPTY)
    rows = []
    for x in open_:
        sc, why, riv, own = _score(x, D, S5, own_amts)
        rows.append((sc, x, why, riv, own))
    rows.sort(key=lambda z: (-z[0], z[1]["cd"] or TODAY))
    items = []
    for sc, x, why, riv, own in rows[:20]:
        col = "var(--own)" if sc >= 60 else "var(--warn)" if sc >= 45 else "#94a3b8"
        sim = _similar(x, D)
        simh = "".join(
            f"<li>{h(y['d'])} · {_link(y.get('t'), y.get('u'), 40)} · {h(_eok(y['a']))}"
            + (f" → <b>{h(D['WIN'][y['k']][0])}</b>" + (f" {h(_eok(D['WIN'][y['k']][1]))}" if D['WIN'][y['k']][1] else "") if y["k"] in D["WIN"] else " → 결과 미확인")
            + "</li>" for y in sim) or "<li>비슷한 과거 공고 없음</li>"
        rv = Counter(y.get("competitor") for y in riv)
        rvh = " · ".join(f"{h(k)} {v}건" for k, v in rv.most_common()) or "기록 없음"
        items.append(
            f'<details class="sx-q"><summary><b class="sx-sc" style="background:{col}">{sc}</b><span class="sx-qt">{_link(x.get("t"), x.get("u"), 52)}'
            f'<small>{h(x.get("r") or "")} · {h(x["ok"])} · {h(_eok(x["a"]))} · 마감 {h(x.get("c") or "-")}</small></span></summary>'
            f'<div class="sx-qd"><div class="sx-why">' + "".join(f"<span>{h(w)}</span>" for w in why) + "</div>"
            f'<div class="sx-cmp"><div><b>🔍 비슷한 과거 공고 · 결과</b><ul>{simh}</ul></div><div><b>⚔️ 이 기관의 경쟁사 계약</b><p>{rvh}</p>'
            f'<b>🟢 자사 계약</b><p>{len(own)}건{(" · 최근 " + h(max(y["date"] for y in own))) if own else ""}</p></div></div></div></details>')
    top = sum(1 for r in rows if r[0] >= 60)
    note = f"진행 중 공고 {len(rows)}건 중 60점 이상(초록) {top}건. 점수는 기관 이력·강점 분야·금액대·준비 기간을 더한 규칙 기반 추정이며, 낙찰 결과가 쌓이면 가중치를 다시 맞춥니다. 줄을 누르면 비슷한 과거 공고·결과·경쟁사 이력이 열립니다."
    return _card("🎯", "수주 가능성 점수 · 입찰 우선순위 (추정)", "상위 20건 · 점수순", '<div class="sx-ql">' + "".join(items) + "</div>", note)


# ---------------- A2 공고 예보 ----------------
def _forecast(D):
    t = TODAY
    months = [(t.year + (t.month - 1 + i) // 12, (t.month - 1 + i) % 12 + 1) for i in range(3)]
    F = {m: [] for m in months}
    recent = [x for x in D["TB"] if x["dd"] >= t - timedelta(days=75)]
    seen = set()
    for x in D["TB"]:  # 작년 이맘때 공고 -> 올해 반복 예상
        nd = x["dd"] + timedelta(days=365)
        key = (nd.year, nd.month)
        if key not in F or nd < t - timedelta(days=3):
            continue
        if any(y["ok"] == x["ok"] and _jac(x["tok"], y["tok"]) >= .35 for y in recent):
            continue
        sig = (x["ok"], tuple(sorted(x["tok"]))[:4])
        if sig in seen:
            continue
        seen.add(sig)
        F[key].append({"kind": "작년 이맘때 공고", "d": nd, "t": x.get("t"), "o": x["ok"], "r": x.get("r"), "a": x["a"], "u": x.get("u"), "p": "보통"})
    for x in D["OP"]:  # 발주 계획 중 아직 공고 전
        try:
            m = int(str(x.get("m") or "0")[:2])
        except ValueError:
            continue
        if not 1 <= m <= 12:
            continue
        yr = t.year if m >= t.month else t.year + 1
        if "2027" in str(x.get("t")) and m < 3:
            yr = 2027
        key = (yr, m)
        if key not in F:
            continue
        if any(y["ok"] == x["ok"] and _jac(x["tok"], y["tok"]) >= .4 for y in D["TB_ORG"].get(x["ok"], [])):
            continue
        F[key].append({"kind": "발주 계획 예정", "d": date(yr, m, 1), "t": x.get("t"), "o": x["ok"], "r": x.get("r"), "a": x["a"], "u": "", "p": "높음" if key == months[0] else "보통"})
    for k in F:
        F[k].sort(key=lambda z: -z["a"])
    return months, F


def forecast(D, cp=False):
    months, F = _forecast(D)
    if not any(F.values()):
        return _card("📅", "다음 3개월 공고 예보", "", EMPTY)
    cols = []
    for (y, m) in months:
        L = F[(y, m)]
        tot = sum(z["a"] for z in L)
        li = "".join(
            f'<li><em class="sx-k{0 if z["kind"].startswith("작년") else 1}">{h(z["kind"])}</em>{_link(z["t"], z["u"], 38)}'
            f'<small>{h(z["r"] or "")} · {h(z["o"])} · {h(_eok(z["a"]))}{"" if cp else " · 가능성 " + h(z["p"])}</small></li>' for z in L[:8])
        more = f'<p class="cpv-note">외 {len(L) - 8}건</p>' if len(L) > 8 else ""
        cols.append(f'<div class="sx-fc"><h5>{y}.{m:02d} <span>{len(L)}건 · {h(_eok(tot))}</span></h5><ul>{li or "<li>예정 없음</li>"}</ul>{more}</div>')
    n = sum(len(v) for v in F.values())
    if cp:
        note = f"작년 같은 시기에 공고를 냈던 기관과 발주 계획상 예정인 사업을 달별로 모았습니다(총 {n}건). 이미 올해 비슷한 공고가 나온 기관은 뺐습니다."
        return _card("📅", "다음 3개월 공고 예보", "작년 이맘때 공고 · 발주 계획 예정", f'<div class="sx-fcs">{"".join(cols)}</div>', note)
    note = f"총 {n}건. 가능성: 이번 달 발주 계획 = 높음, 작년 반복·다음 달 이후 계획 = 보통(1년 치 기록이라 추정). 영업 접촉은 공고 4~6주 전이 적기입니다."
    return _card("📅", "다음 3개월 공고 예보 (가능성 포함)", "선제 영업 대상", f'<div class="sx-fcs">{"".join(cols)}</div>', note)


# ---------------- B2 영업 골든타임 달력 ----------------
TERMS = [("겨울방학", 1, 1, 2, 28, "#e0f2fe"), ("학기 초", 3, 1, 3, 31, "#dcfce7"), ("여름방학", 7, 20, 8, 25, "#fef9c3"), ("2학기 초", 9, 1, 9, 30, "#dcfce7"), ("새 학년 계획기", 11, 1, 12, 31, "#ede9fe")]


def golden(D):
    if not D["TB"]:
        return ""
    wk = Counter()
    am = Counter()
    for x in D["TB"]:
        w = min(52, x["dd"].isocalendar()[1])
        wk[w] += 1
        am[w] += x["a"]
    W, H, L, T, cw = 780, 190, 30, 44, 14
    mx = max(wk.values()) or 1
    s = []
    for nm, m1, d1, m2, d2, col in TERMS:
        a = date(2026, m1, d1).isocalendar()[1]
        b = date(2026, m2, d2).isocalendar()[1]
        a, b = min(a, 52), min(b if b > 1 else 52, 52)
        s.append(f'<rect x="{L + (a - 1) * cw}" y="{T - 30}" width="{(b - a + 1) * cw}" height="{H - T - 10}" fill="{col}" opacity=".8"/><text x="{L + (a - 1) * cw + 2}" y="{T - 18}" class="cpv-l" style="font-size:10px">{h(nm)}</text>')
    for w in range(1, 53):
        c = wk.get(w, 0)
        bh = 90 * c / mx
        y = T + 90 - bh
        s.append(f'<rect x="{L + (w - 1) * cw + 1}" y="{y:.1f}" width="{cw - 2}" height="{max(bh, .5):.1f}" rx="2" fill="var(--market)"><title>{w}주 · 공고 {c}건 · {_eok(am.get(w, 0))}</title></rect>')
    for m in range(1, 13):
        w = date(2026, m, 1).isocalendar()[1]
        w = 1 if m == 1 else w
        s.append(f'<text x="{L + (w - 1) * cw}" y="{T + 108}" class="cpv-l" style="font-size:11px">{m}월</text>')
    top = sorted(wk.items(), key=lambda z: -z[1])[:3]
    tops = ", ".join(f"{w}주({(date.fromisocalendar(2026, w, 1)).strftime('%m.%d')}~, {c}건)" for w, c in top)
    note = f"공고가 가장 몰린 주: {tops}. 배경 띠는 일반 학사일정 기준입니다 — 띠 시작 3~4주 전에 제안서·견적을 준비해 두세요."
    return _card("🗓️", "영업 골든타임 달력", "주별 연수 공고 수 × 학사일정", '<div class="v3d-no">' + _svg(W, H, "주별 공고 수와 학사일정", "".join(s)) + "</div>", note)


# ---------------- B1 흐름도(계획 → 공고 → 결과) ----------------
def flow(D):
    OP, TB = D["OP"], D["TB"]
    if not TB:
        return ""
    linked_bids = set()
    lp = 0
    for p in OP:
        best = None
        for y in D["TB_ORG"].get(p["ok"], []):
            if _jac(p["tok"], y["tok"]) >= .4:
                best = y
                break
        if best:
            lp += 1
            linked_bids.add(best["k"])
    up = len(OP) - lp
    out = Counter()
    for x in TB:
        w = D["WIN"].get(x["k"])
        out[_vend(w[0]) if w else "미확인"] += 1
    n_tb = len(TB)
    W, H = 780, 300
    s = []

    def node(x, y, hgt, col, lab, side):
        s.append(f'<rect x="{x}" y="{y:.1f}" width="16" height="{hgt:.1f}" rx="3" fill="{col}"/><text x="{x - 8 if side == "l" else x + 24}" y="{y + hgt / 2 + 4:.1f}" class="cpv-l" text-anchor="{"end" if side == "l" else "start"}" style="font-size:12.5px">{h(lab)}</text>')

    def band(x1, y1, x2, y2, w, col, tip):
        m = (x1 + x2) / 2
        s.append(f'<path d="M{x1},{y1 + w / 2:.1f} C{m},{y1 + w / 2:.1f} {m},{y2 + w / 2:.1f} {x2},{y2 + w / 2:.1f}" stroke="{col}" stroke-width="{max(w, 1.5):.1f}" fill="none" opacity=".35"><title>{h(tip)}</title></path>')
    # 크기: 제곱근 비율(작은 흐름도 보이게) · 결과 미확인은 점선으로만
    S = lambda v: 6 + 9 * math.sqrt(v)
    y0 = 20
    hl, hu = S(lp), S(up)
    ht = S(n_tb)
    node(190, y0, hl, "var(--own)", f"계획→공고 {lp}건", "l")
    node(190, y0 + hl + 16, hu, "#94a3b8", f"아직 공고 전 {up}건", "l")
    node(400, y0, ht, "var(--market)", f"연수 공고 {n_tb}건", "r")
    band(206, y0, 400, y0, hl, "var(--own)", f"계획에서 이어진 공고 {lp}건")
    yy, yc = y0, y0
    for k in (OWN, "아이스크림", "티처빌", "기타"):
        v = out.get(k, 0)
        if not v:
            continue
        hh = S(v)
        lab = ("자사" if k == OWN else k) + f" {v}건"
        node(600, yy, hh, COLV[k], lab, "r")
        band(416, yc, 600, yy, hh, COLV[k], lab)
        yc += hh
        yy += hh + 12
    if out.get("미확인"):
        hh = 34
        node(600, yy + 6, hh, COLV["미확인"], f"결과 미확인 {out['미확인']}건", "r")
        s.append(f'<path d="M416,{y0 + ht * .7:.1f} C508,{y0 + ht * .7:.1f} 508,{yy + 23:.1f} 600,{yy + 23:.1f}" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5 5" fill="none"/>')
        yy += hh + 18
    H = int(max(y0 + hl + hu + 16, y0 + ht, yy) + 20)
    unk = out.get("미확인", 0)
    note = (f"발주 계획 {len(OP)}건 중 {lp}건({lp / max(len(OP), 1) * 100:.0f}%)이 공고로 이어졌고, 공고 {n_tb}건 중 결과 확인 {n_tb - unk}건입니다. "
            f"연결은 같은 기관 + 제목 유사도 기준(추정). 결과 미확인이 많아 업체별 비중은 참고용입니다.")
    return _card("🔀", "계획 → 공고 → 낙찰 흐름", "누가 가져갔나", '<div class="v3d-no">' + _svg(W, H, "계획 공고 낙찰 흐름", "".join(s)) + "</div>", note)


# ---------------- A3/B4 계약 금액 벤치마크 ----------------
def _q(v, p):
    if not v:
        return 0
    v = sorted(v)
    i = (len(v) - 1) * p
    lo = math.floor(i)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (i - lo)


def price(D):
    G = defaultdict(list)
    for x in D["CC"]:
        if x["a"] > 0:
            G[_vend(x.get("competitor"))].append(x["a"])
    ks = [k for k in (OWN,) + RIVALS if len(G.get(k, [])) >= 3]
    if not ks:
        return _card("💰", "계약 금액 벤치마크", "", EMPTY)
    allv = [v for k in ks for v in G[k]]
    lo, hi = math.log10(max(min(allv), 1e5)), math.log10(max(allv))
    W, H, L, R = 780, 70 + 60 * len(ks), 130, 30
    X = lambda v: L + (math.log10(max(v, 1e5)) - lo) / max(hi - lo, .1) * (W - L - R)
    s = []
    for e in range(int(lo), int(hi) + 1):
        for m in (1, 3):
            v = m * 10 ** e
            if 10 ** lo <= v <= 10 ** hi:
                s.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="20" y2="{H - 30}" stroke="var(--border)"/><text x="{X(v):.1f}" y="{H - 12}" text-anchor="middle" class="cpv-l" style="font-size:11px">{_eok(v)}</text>')
    rows = []
    for i, k in enumerate(ks):
        v = G[k]
        y = 40 + i * 60
        q1, md, q3 = _q(v, .25), _q(v, .5), _q(v, .75)
        p5, p95 = _q(v, .05), _q(v, .95)
        col = COLV[k]
        nm = "자사" if k == OWN else k
        s.append(f'<text x="{L - 10}" y="{y + 5}" text-anchor="end" class="cpv-l" style="font-size:13px;font-weight:800">{h(nm)}</text>'
                 f'<line x1="{X(p5):.1f}" x2="{X(p95):.1f}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="2"/>'
                 f'<rect x="{X(q1):.1f}" y="{y - 14}" width="{max(X(q3) - X(q1), 2):.1f}" height="28" rx="6" fill="{col}" opacity=".35" stroke="{col}"><title>{h(nm)} 가운데 50%: {_eok(q1)}~{_eok(q3)}</title></rect>'
                 f'<line x1="{X(md):.1f}" x2="{X(md):.1f}" y1="{y - 16}" y2="{y + 16}" stroke="{col}" stroke-width="3"/>')
        for a in v:
            s.append(f'<circle cx="{X(a):.1f}" cy="{y + 22}" r="2" fill="{col}" opacity=".5"/>')
        meth = Counter(x.get("method") or "-" for x in D["CC"] if _vend(x.get("competitor")) == k)
        rows.append([h(nm), f"{len(v)}건", h(_eok(md)), f"{h(_eok(q1))} ~ {h(_eok(q3))}", h(_eok(sum(v))), " · ".join(f"{h(a)} {b}" for a, b in meth.most_common(3))])
    om = _q(G.get(OWN, []), .5)
    rm = _q([a for k in RIVALS for a in G.get(k, [])], .5)
    note = (f"건당 계약 금액 기준(차시 정보가 없어 단가가 아닌 건 규모 비교). 자사 중앙값 {_eok(om)} vs 경쟁사 {_eok(rm)} — "
            + ("자사가 더 작은 건 위주: 중형(5천만+) 공고 비중을 늘릴 여지." if om < rm else "자사가 더 큰 건 위주: 소액 수의계약 시장 방어 점검."))
    return _card("💰", "계약 금액 벤치마크", "업체별 건당 금액 분포(로그 눈금) · 상자 = 가운데 50%", '<div class="v3d-no">' + _svg(W, H, "업체별 계약 금액 분포", "".join(s)) + "</div>" + _tbl(["업체", "건수", "중앙값", "가운데 50%", "합계", "계약 방식"], rows), note)


# ---------------- A4/B5 재구매 레이더 ----------------
def repurchase(D):
    O = {}
    for ok, L in D["CC_ORG"].items():
        if not ok:
            continue
        L = sorted(L, key=lambda x: x["dd"])
        own = [x for x in L if x.get("competitor") == OWN]
        riv = [x for x in L if x.get("competitor") in RIVALS]
        last = L[-1]
        gaps = [(b["dd"] - a["dd"]).days for a, b in zip(own, own[1:]) if (b["dd"] - a["dd"]).days > 20]
        cyc = sum(gaps) / len(gaps) if gaps else 365
        since_own = (TODAY - own[-1]["dd"]).days if own else None
        st = "own" if own and not riv else "mix" if own else "riv"
        flag = ""
        if own and last.get("competitor") in RIVALS and last["dd"] > own[-1]["dd"]:
            flag = "경쟁사로 넘어감"
        elif own and since_own > max(cyc * 1.2, 120 if gaps else 300):
            flag = "재구매 시기 지남"
        elif not own and len(riv) >= 2:
            flag = "경쟁사 단골(전환 타깃)"
        O[ok] = {"n": len(L), "own": len(own), "riv": len(riv), "since": (TODAY - last["dd"]).days, "cyc": cyc, "st": st, "flag": flag,
                 "r": last.get("region") or "", "lastv": last.get("competitor"), "amt": sum(x["a"] for x in L), "own_last": own[-1]["date"] if own else ""}
    if not O:
        return _card("🔁", "재구매 레이더", "", EMPTY)
    W, H, L_, B = 780, 320, 50, 40
    mxx = max(v["since"] for v in O.values()) or 1
    mxy = max(v["n"] for v in O.values()) or 1
    X = lambda d: L_ + d / mxx * (W - L_ - 20)
    Y = lambda n: H - B - (math.log(n + 1) / math.log(mxy + 1)) * (H - B - 20)
    col = {"own": "var(--own)", "mix": "var(--cv6)", "riv": "var(--rival)"}
    s = [f'<rect x="{X(mxx * .5):.1f}" y="10" width="{W - 20 - X(mxx * .5):.1f}" height="{H - B - 10}" fill="var(--warn)" opacity=".08"/>'
         f'<text x="{W - 24}" y="26" text-anchor="end" class="cpv-l" style="font-size:11px">오래 안 산 곳 →</text>'
         f'<line x1="{L_}" x2="{W - 20}" y1="{H - B}" y2="{H - B}" stroke="var(--border)"/>'
         f'<text x="{L_}" y="{H - 12}" class="cpv-l" style="font-size:11px">마지막 계약 후 경과일(0 ~ {mxx}일)</text>'
         f'<text x="12" y="20" class="cpv-l" style="font-size:11px">계약 횟수</text>']
    for ok, v in sorted(O.items(), key=lambda z: z[1]["n"]):
        r = 3 + min(9, math.sqrt(v["amt"] / 1e7))
        ring = ' stroke="var(--ink)" stroke-width="2"' if v["flag"] in ("재구매 시기 지남", "경쟁사로 넘어감") else ""
        s.append(f'<circle cx="{X(v["since"]):.1f}" cy="{Y(v["n"]):.1f}" r="{r:.1f}" fill="{col[v["st"]]}" opacity=".65"{ring}><title>{h(ok)} · {v["n"]}건(자사 {v["own"]}) · 마지막 {v["since"]}일 전 · {h(v["flag"] or "정상")}</title></circle>')
    fl = sorted([(ok, v) for ok, v in O.items() if v["flag"]], key=lambda z: ({"경쟁사로 넘어감": 0, "재구매 시기 지남": 1}.get(z[1]["flag"], 2), -z[1]["amt"]))
    rows = [[h(v["flag"]), h(ok), h(v["r"]), f'{v["own"]} / {v["riv"]}', h(v["own_last"] or "-"), f'{v["since"]}일 전({h(v["lastv"] or "")})', h(_eok(v["amt"]))] for ok, v in fl[:25]]
    c = Counter(v["flag"] for v in O.values() if v["flag"])
    note = (f"기관 {len(O)}곳 · 경쟁사로 넘어감 {c.get('경쟁사로 넘어감', 0)} · 재구매 시기 지남 {c.get('재구매 시기 지남', 0)} · 경쟁사 단골 {c.get('경쟁사 단골(전환 타깃)', 0)}. "
            "주기는 자사 계약 간격 평균(1건뿐이면 1년 가정) — 테두리 원부터 연락하세요.")
    return _card("🔁", "재구매 레이더 (B2S·기관)", "초록 = 자사 고객 · 보라 = 공동 · 빨강 = 경쟁사만 · 원 크기 = 누적 금액",
                 '<div class="v3d-no">' + _svg(W, H, "기관별 재구매 산점도", "".join(s)) + "</div>" + _tbl(["상태", "기관", "지역", "자사/경쟁사", "자사 마지막", "마지막 계약", "누적"], rows), note)


# ---------------- A5 과정 공백 · B6 주제 순위 · B7 기회 매트릭스 ----------------
def _cat_titles(D, who):
    c = (D["CAT"].get(who) or {}).get("courses") or []
    return [str(x.get("title") or "") + " " + str(x.get("category") or "") for x in c]


def gaps(D):
    T = _topics()
    cut = TODAY - timedelta(days=365)
    dem = Counter()
    for x in D["TB"]:
        if x["dd"] >= cut:
            for n, rx in T:
                if rx.search(str(x.get("t") or "")):
                    dem[n] += 1
    for x in D["SIG"]:
        for n, rx in T:
            if rx.search(str(x.get("t") or "")):
                dem[n] += .5
    comp, own = Counter(), Counter()
    for who in RIVALS:
        for t in _cat_titles(D, who):
            for n, rx in T:
                if rx.search(t):
                    comp[n] += 1
    for x in D["CC"]:
        if x.get("competitor") in RIVALS:
            for n, rx in T:
                if rx.search(str(x.get("course") or "")):
                    comp[n] += 2
    for t in _cat_titles(D, OWN):
        for n, rx in T:
            if rx.search(t):
                own[n] += 1
    names = [n for n, _ in T if dem[n] or comp[n]]
    if not names:
        return _card("🧩", "과정 공백 · 기회 매트릭스", "", EMPTY)
    sd, sc, so = sum(dem[n] for n in names) or 1, sum(comp[n] for n in names) or 1, sum(own[n] for n in names) or 1
    md, mc = sorted(dem[n] / sd for n in names)[len(names) // 2], sorted(comp[n] / sc for n in names)[len(names) // 2]
    W, H, P = 780, 360, 50
    mxd = max(dem[n] / sd for n in names) or 1
    mxc = max(comp[n] / sc for n in names) or 1
    X = lambda v: P + math.sqrt(v / mxc) * (W - 2 * P)
    Y = lambda v: H - P - math.sqrt(v / mxd) * (H - 2 * P)
    s = [f'<rect x="{P}" y="{P / 2}" width="{X(mc) - P:.1f}" height="{Y(md) - P / 2:.1f}" fill="var(--own)" opacity=".10"/>',
         f'<text x="{P + 6}" y="{P / 2 + 16}" class="cpv-l" style="font-size:12px;font-weight:800;fill:var(--own)">지금 들어갈 칸 (수요↑ 경쟁↓)</text>',
         f'<line x1="{X(mc):.1f}" x2="{X(mc):.1f}" y1="{P / 2}" y2="{H - P}" stroke="var(--border)" stroke-dasharray="4 4"/>',
         f'<line x1="{P}" x2="{W - P}" y1="{Y(md):.1f}" y2="{Y(md):.1f}" stroke="var(--border)" stroke-dasharray="4 4"/>',
         f'<text x="{W - P}" y="{H - 14}" text-anchor="end" class="cpv-l" style="font-size:11px">경쟁 강도(경쟁사 과정·계약, 제곱근 눈금) →</text>',
         f'<text x="{P}" y="{P / 2 - 4}" class="cpv-l" style="font-size:11px">↑ 수요(공고·교육청 계획)</text>']
    rows = []
    for i, n in enumerate(names):
        d, c, o = dem[n] / sd, comp[n] / sc, own[n] / so
        r = 8 + min(26, math.sqrt(own[n]) * 3)
        q = "들어갈 칸" if d >= md and c < mc else "격전지" if d >= md else "틈새" if c < mc else "포화"
        s.append(f'<circle cx="{X(c):.1f}" cy="{Y(d):.1f}" r="{r:.1f}" fill="var(--cv{i % 8 + 1})" opacity=".55"><title>{h(n)} · 수요 {d * 100:.0f}% · 경쟁 {c * 100:.0f}% · 자사 과정 {own[n]}개</title></circle>'
                 f'<text x="{X(c):.1f}" y="{Y(d) + 4:.1f}" text-anchor="middle" class="cpv-v" style="font-size:12px">{h(n)}</text>')
        rows.append((d - o, [h(n), h(q), f"{d * 100:.0f}%", f"{c * 100:.0f}%", f"{own[n]}개({o * 100:.0f}%)", f"{(d - o) * 100:+.0f}%p"]))
    rows.sort(key=lambda z: -z[0])
    best = [r[1][0] for r in rows if r[0] > 0][:3]
    note = f"공백(수요 비중 − 자사 과정 비중)이 큰 주제: {', '.join(best) or '없음'}. 원 크기 = 자사 과정 수. 신규 과정·SET 기획 우선순위로 쓰세요."
    return _card("🧩", "과정 공백 · 2×2 기회 매트릭스", "주제별 수요 × 경쟁 강도 × 자사 과정", '<div class="v3d-no">' + _svg(W, H, "주제 기회 매트릭스", "".join(s)) + "</div>"
                 + _tbl(["주제", "칸", "수요 비중", "경쟁 비중", "자사 과정", "공백"], [r[1] for r in rows]), note)


def bump(D):
    T = _topics()
    ms = []
    y, m = TODAY.year, TODAY.month
    for i in range(11, -1, -1):
        yy, mm = y + (m - 1 - i) // 12, (m - 1 - i) % 12 + 1
        ms.append(f"{yy}-{mm:02d}")
    C = {k: Counter() for k in ms}
    for x in D["TB"]:
        k = x["d"][:7]
        if k in C:
            for n, rx in T:
                if rx.search(str(x.get("t") or "")):
                    C[k][n] += 1
    ms = [k for k in ms if sum(C[k].values()) >= 3]
    if len(ms) < 3:
        return ""
    names = [n for n, _ in T if sum(C[k][n] for k in ms)]
    R = {}
    for k in ms:
        order = sorted(names, key=lambda n: (-C[k][n], n))
        R[k] = {n: order.index(n) + 1 for n in order}
    k0 = ms[-4 if len(ms) >= 4 else 0]
    up = sorted(names, key=lambda n: R[ms[-1]][n] - R[k0][n])[:2]
    W, H, L, Rr = 780, 60 + 30 * len(names), 20, 150
    X = lambda i: L + i * (W - L - Rr) / max(len(ms) - 1, 1)
    Y = lambda r: 30 + (r - 1) * 30
    s = [f'<text x="{X(i):.1f}" y="{H - 8}" text-anchor="middle" class="cpv-l" style="font-size:11px">{k[2:4]}.{k[5:]}</text>' for i, k in enumerate(ms)]
    for j, n in enumerate(names):
        col = f"var(--cv{j % 8 + 1})"
        pts = " ".join(f"{X(i):.1f},{Y(R[k][n]):.1f}" for i, k in enumerate(ms))
        hi = n in up or R[ms[-1]][n] == 1
        s.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="{4 if hi else 2}" opacity="{.95 if hi else .22}"/>')
        for i, k in enumerate(ms):
            s.append(f'<circle cx="{X(i):.1f}" cy="{Y(R[k][n]):.1f}" r="{5 if hi else 3}" fill="{col}" opacity="{1 if hi else .35}"><title>{h(n)} · {k} · {R[k][n]}위 ({C[k][n]}건)</title></circle>')
        s.append(f'<text x="{X(len(ms) - 1) + 10:.1f}" y="{Y(R[ms[-1]][n]) + 4:.1f}" class="cpv-l" style="font-size:12px;{"font-weight:800" if hi else "opacity:.6"}">{R[ms[-1]][n]}. {h(n)}{" ▲" if n in up else ""}</text>')
    note = f"최근 3개월 사이 순위가 가장 오른 주제(▲ 진하게): {', '.join(up)}. 오르는 주제는 다음 학기 공고가 늘 가능성이 큽니다. 이번 달은 진행 중이라 순위가 바뀔 수 있습니다."
    return _card("📶", "연수 주제 순위 변화", "월별 공고 제목 기준 순위(1위 = 가장 많음)", '<div class="v3d-no">' + _svg(W, H, "주제 순위 변화", "".join(s)) + "</div>", note)


# ---------------- B3 경쟁사 영토 재생 ----------------
TILE = {"서울": (2, 1), "인천": (1, 1), "경기": (2, 2), "강원": (3, 1), "충남": (1, 3), "세종": (2, 3), "충북": (3, 2), "대전": (2, 4), "경북": (4, 2),
        "전북": (1, 4), "대구": (3, 4), "울산": (4, 4), "광주": (1, 5), "경남": (3, 5), "부산": (4, 5), "전남": (2, 5), "제주": (1, 6)}


def territory(D):
    ev = [(x["dd"], x.get("region") or "", _vend(x.get("competitor"))) for x in D["CC"]]
    ev += [(x["dd"], x.get("region") or "", _vend(x.get("competitor"))) for x in D["CW"] if x["dd"]]
    ev = [e for e in ev if e[2] != "기타" and any(str(e[1]).startswith(s) for s in SIDO)]
    if len(ev) < 10:
        return ""
    ms = []
    for i in range(11, -1, -1):
        yy, mm = TODAY.year + (TODAY.month - 1 - i) // 12, (TODAY.month - 1 - i) % 12 + 1
        ms.append(date(yy, mm, 1))
    frames = []
    for fi, m0 in enumerate(ms):
        lo = (m0 - timedelta(days=90))
        nxt = date(m0.year + (m0.month // 12), m0.month % 12 + 1, 1)
        c = defaultdict(Counter)
        for d, r, v in ev:
            if lo <= d < nxt:
                sd = next(s for s in SIDO if str(r).startswith(s))
                c[sd][v] += 1
        tiles = []
        for sd, (gx, gy) in TILE.items():
            cc = c.get(sd)
            if cc:
                v, n = cc.most_common(1)[0]
                col = COLV[v]
                tip = f"{sd} · " + " · ".join(f"{'자사' if k == OWN else k} {a}" for k, a in cc.most_common())
            else:
                v, n, col, tip = "", 0, "var(--surface-2)", f"{sd} · 기록 없음"
            tiles.append(f'<g data-sd="{h(sd)}"><rect x="{gx * 64}" y="{gy * 50 - 40}" width="60" height="46" rx="8" fill="{col}" opacity="{.85 if n else 1}"><title>{h(tip)}</title></rect>'
                         f'<text x="{gx * 64 + 30}" y="{gy * 50 - 18}" text-anchor="middle" style="font-size:13px;font-weight:800;fill:{"#fff" if n else "var(--muted)"}">{h(sd)}</text>'
                         f'<text x="{gx * 64 + 30}" y="{gy * 50 - 2}" text-anchor="middle" style="font-size:11px;fill:{"#fff" if n else "var(--muted)"}">{n or ""}</text></g>')
        own_n = sum(1 for sd in c if c[sd].most_common(1)[0][0] == OWN)
        frames.append(f'<div class="sx-frame" data-f="{fi}"{"" if fi == len(ms) - 1 else " hidden"}><b class="sx-fm">{m0.year}.{m0.month:02d} <small>최근 3개월 · 자사 우세 {own_n}곳</small></b>'
                      + _svg(360, 300, f"{m0.year}년 {m0.month}월 시도별 우세 업체", "".join(tiles), "cpv-svg sx-tile") + "</div>")
    ctl = f'<div class="sx-play"><button type="button" class="sx-pb" data-sx="play">▶ 12개월 재생</button><input type="range" class="sx-rg" min="0" max="{len(ms) - 1}" value="{len(ms) - 1}" aria-label="월 선택"></div>'
    body = f'<div class="sx-terr v3d-no">{ctl}{"".join(frames)}</div>' + _legend([("자사", COLV[OWN]), ("아이스크림", COLV["아이스크림"]), ("티처빌", COLV["티처빌"]), ("기록 없음", "var(--surface-2)")])
    return _card("🗺️", "경쟁사 영토 지도 · 시간 재생", "시도별 최근 3개월 계약·낙찰 건수 1위 업체", body, "▶를 누르면 지난 12개월 동안 영토가 어떻게 바뀌었는지 재생됩니다. 칸 숫자 = 1위 업체 건수.")


# ---------------- A6 진짜 변화 vs 수집 문제 ----------------
def anomalies(D):
    S = []
    for x in D["DS"]:
        d = _d(x.get("date"))
        if d:
            S.append((d, x))
    S.sort(key=lambda z: z[0])
    if len(S) < 5:
        return ""
    fails = {str(x.get("at") or "")[:10] for x in D["PW"] if x.get("fail") or str(x.get("status") or "").lower() in ("fail", "failure", "error")}
    rows, marks = [], []
    keys = [("g2b_total_detail", "교육청·연수원 발주 누적"), ("ai_rows_count", "AI·에듀테크 발주")]
    for key, nm in keys:
        vals = [(d, _n(x.get(key))) for d, x in S if x.get(key) is not None]
        for i in range(1, len(vals)):
            (d0, a), (d1, b) = vals[i - 1], vals[i]
            if a <= 0:
                continue
            ch = (b - a) / a
            if abs(ch) < .25:
                continue
            after = [v for d, v in vals[i + 1:i + 6]]
            before = [v for d, v in vals[max(0, i - 7):i - 1]]
            if ch > 0 and any(v >= b * .88 for v in before):
                kind, why = "앞선 하락의 복구", "직전 며칠의 낮은 값이 원래 수준으로 돌아옴"
            elif ch < 0 and any(v >= a * .88 for v in after):
                kind, why = "수집 문제 의심", "며칠 안에 원래 수준으로 돌아옴"
            elif d1.isoformat() in fails:
                kind, why = "수집 문제 의심", "같은 날 수집 실패 기록"
            elif not after:
                kind, why = "확인 중", "다음 날 값 대기"
            else:
                kind, why = "시장 변화 가능", "회복 없음 — 원인 확인 필요"
            rows.append([h(d1.isoformat()), h(nm), f"{a:,.0f} → {b:,.0f} ({ch * 100:+.0f}%)", h(kind), h(why)])
            marks.append((d1, kind))
    vals = [(d, _n(x.get("g2b_total_detail"))) for d, x in S][-120:]
    W, H, L = 780, 170, 50
    mx = max(v for _, v in vals) or 1
    X = lambda i: L + i * (W - L - 20) / max(len(vals) - 1, 1)
    Y = lambda v: H - 30 - v / mx * (H - 50)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(vals))
    s = [f'<polyline points="{pts}" fill="none" stroke="var(--market)" stroke-width="2.5"/>',
         f'<text x="{L}" y="16" class="cpv-l" style="font-size:11px">교육청·연수원 발주 누적(최근 {len(vals)}일)</text>']
    idx = {d: i for i, (d, _) in enumerate(vals)}
    for d, k in marks:
        if d in idx:
            col = "var(--warn)" if k.startswith("수집") else "#94a3b8" if k.startswith(("앞선", "확인")) else "var(--rival)"
            s.append(f'<circle cx="{X(idx[d]):.1f}" cy="{Y(vals[idx[d]][1]):.1f}" r="6" fill="{col}"><title>{d} · {h(k)}</title></circle>')
    s.append(f'<text x="{L}" y="{H - 8}" class="cpv-l" style="font-size:11px">{vals[0][0]}</text><text x="{W - 20}" y="{H - 8}" text-anchor="end" class="cpv-l" style="font-size:11px">{vals[-1][0]}</text>')
    tb_last = max((x["dd"] for x in D["TB"]), default=None)
    fresh = f"연수 공고 최신 날짜 {tb_last} ({(TODAY - tb_last).days}일 전)" if tb_last else "연수 공고 기록 없음"
    note = f"하루 25% 넘게 바뀐 날을 자동 표시. 며칠 안에 원래 수준으로 돌아오면 '수집 문제 의심'(노랑), 아니면 '시장 변화 가능'(빨강). {fresh}."
    body = '<div class="v3d-no">' + _svg(W, H, "일별 지표와 급변일", "".join(s)) + "</div>" + (_tbl(["날짜", "지표", "변화", "판정", "근거"], rows[-12:][::-1]) if rows else '<p class="cpv-note">최근 급변 없음 ✅</p>')
    return _card("🚨", "진짜 변화 vs 수집 문제", "일별 지표 급변 자동 판정", body, note)


# ---------------- A7 2027 매출 구성 시뮬레이터 ----------------
def simulator():
    b0, gb, go = 80.0, -15.8, 30.0

    def calc(b0, gb, go):
        B, O = b0, 100 - b0
        yrs = []
        for y in range(2026, 2031):
            B *= 1 + gb / 100
            O *= 1 + go / 100
            yrs.append((y, B, O))
        B27 = b0 * (1 + gb / 100) ** 2
        need = ((1.5 * B27) / (100 - b0)) ** .5 - 1
        return yrs, need
    yrs, need = calc(b0, gb, go)
    bars = "".join(f'<div class="sx-yr"><b>{y}</b><span class="sx-bar"><i style="width:{B / (B + O) * 100:.1f}%;background:var(--market)"></i><i style="width:{O / (B + O) * 100:.1f}%;background:var(--own)"></i></span><em>{B / (B + O) * 100:.0f} : {O / (B + O) * 100:.0f}</em></div>' for y, B, O in yrs)
    body = (f'<div class="sx-sim" data-b0="{b0}" data-gb="{gb}" data-go="{go}">'
            f'<label>2025 B2G 비중 <b class="sx-o" data-o="b0">{b0:.0f}%</b><input type="range" data-k="b0" min="50" max="95" step="1" value="{b0:.0f}"></label>'
            f'<label>B2G 연 성장률 <b class="sx-o" data-o="gb">{gb:+.1f}%</b><input type="range" data-k="gb" min="-30" max="10" step=".1" value="{gb}"></label>'
            f'<label>B2C+B2S 연 성장률 <b class="sx-o" data-o="go">{go:+.0f}%</b><input type="range" data-k="go" min="-10" max="150" step="1" value="{go:.0f}"></label>'
            f'<div class="sx-yrs">{bars}</div>'
            f'<p class="sx-need">2027년 40 : 60을 맞추려면 B2C+B2S가 <b>연 {need * 100:.0f}%</b>씩 자라야 합니다(B2G 성장률 그대로일 때).</p></div>'
            + _legend([("B2G", "var(--market)"), ("B2C+B2S", "var(--own)")]))
    note = "기준값: B2G 약 80%, 2020~2024 B2G 연평균 −15.8%(제공해 주신 기준 수치). 금액이 아닌 비중만 계산하므로 실제 매출액은 이 화면에 저장되지 않습니다. 슬라이더를 움직여 가정을 바꿔 보세요."
    return _card("🧮", "2027 매출 구성 시뮬레이터", "목표 B2G 40 : B2C+B2S 60", body, note)


# ---------------- C1 관심 기관 즐겨찾기 자리 ----------------
def watch_box(scope):
    return _card("⭐", "관심 기관 즐겨찾기", "기관을 추가하면 새 공고를 맨 위에 모아 보여줍니다(이 브라우저에만 저장)",
                 f'<div class="sx-watch" data-scope="{h(scope)}"><p class="cpv-note">데이터 준비 중</p></div>')


# ---------------- 조립 ----------------
def _safe(fn, *a, **k):
    try:
        return fn(*a, **k) or ""
    except Exception as e:  # noqa: BLE001 — 한 그림 오류가 칸 전체를 막지 않게
        print(f"  sales_analysis {fn.__name__} 건너뜀: {str(e)[:140]}")
        return ""


def build(sec=None):
    D = _load()
    parts = [_safe(weekly, D), watch_box("adm"), _safe(win_score, D), _safe(forecast, D), _safe(golden, D), _safe(flow, D), _safe(price, D),
             _safe(repurchase, D), _safe(gaps, D), _safe(bump, D), _safe(territory, D), _safe(anomalies, D), _safe(simulator)]
    body = "".join(p for p in parts if p)
    return f'<div class="cpv-wrap sx-wrap"><div class="cpv-grid">{body or EMPTY}</div></div>'


def build_cp():
    D = _load()
    return [x for x in (_safe(forecast, D, cp=True), watch_box("cp")) if x]


if __name__ == "__main__":
    import time
    t = time.time()
    a = build()
    print("admin", len(a), f"{time.time() - t:.1f}s")
    c = build_cp()
    print("cp", [len(x) for x in c])
