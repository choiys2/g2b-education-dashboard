#!/usr/bin/env python3
"""
관리 탭 '2027 경영계획' 섹션 - 계획(시크릿) × 시트 실적 × 공개 데이터로 의사결정 화면 11종을 만든다.

- 계획 수치: GitHub Secret PLAN_2027_JSON(plan_extract.py 출력)에서만 읽는다. 로컬 시험은 plan_2027.local.json(gitignore).
  계획이 없으면 계획이 필요한 칸은 '미등록'으로 두고, 실적·공개 데이터만으로 되는 화면은 그대로 그린다.
- 결과 HTML 은 admin_structure.build_html 에 붙어 ADMIN_PASSWORD 로 암호화된다. history/·live/·브리핑(공개)에는 계획 수치를 쓰지 않는다.
- 개인정보 없음: 시트에서 이미 걸러진 sheets_ops 결과(기관·사업명·금액)만 쓴다.
"""
import html
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
REG = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
CH = [("b2c", "B2C 개인", "#10b981"), ("b2s", "B2S 단체", "#4f8cff"), ("b2g", "B2G 위탁", "#f59e0b"), ("etc", "제품·상품·기타", "#94a3b8")]
ETC_COST = 0.35         # 제품·상품·기타 매출원가율 기본값(계획 JSON 의 r_etc 가 있으면 그 값)
B2G_GM_MIN = 10_000_000  # B2G 건당 최소 이익 기여(가정: 운영 인력 1인 2개월분 수준)


# ---------------------------------------------------------------- 입력
def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _jsonl(p):
    p = HERE / p
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def load_plan():
    raw = os.environ.get("PLAN_2027_JSON", "").strip()
    if not raw and (HERE / "plan_2027.local.json").exists():
        raw = (HERE / "plan_2027.local.json").read_text(encoding="utf-8")
    try:
        p = json.loads(raw) if raw else None
        return p if isinstance(p, dict) and p.get("sales") else None
    except Exception:
        print("[경고] PLAN_2027_JSON 형식 오류 - 계획 칸은 비웁니다")
        return None


def eok(v, d=2):
    return "-" if v is None else f"{v / 1e8:,.{d}f}억"


def pct(a, b, d=0):
    return "-" if not b else f"{a / b * 100:.{d}f}%"


def chan(plan):
    """채널 4개로 묶은 {k: {prev, plan, m[12]}}"""
    out = {k: {"prev": 0, "plan": 0, "m": [0] * 12} for k, _, _ in CH}
    for s in plan.get("sales", []):
        k = s["k"] if s["k"] in ("b2c", "b2s", "b2g") else "etc"
        out[k]["prev"] += s["prev"]
        out[k]["plan"] += s["plan"]
        out[k]["m"] = [a + b for a, b in zip(out[k]["m"], s["m"])]
    return out


def fee_parts(plan):
    g = defaultdict(lambda: {"prev": 0, "plan": 0})
    for f in plan.get("fees", []):
        k = ("tutor" if "튜터" in f["name"] else "cp" if "쉐어" in f["name"] else "card" if "카드" in f["name"] else
             "prod" if "제작비" in f["name"] else "sme" if "SME" in f["name"] else "fixed")
        g[k]["prev"] += f["prev"]
        g[k]["plan"] += f["plan"]
    return g


def model(plan):
    """흑자전환 계산기 계수(계획서 산출근거에서 역산)"""
    c, f, pl = chan(plan), fee_parts(plan), plan["pl"]
    online = c["b2c"]["plan"] + c["b2s"]["plan"]
    r_etc = plan.get("r_etc") or ETC_COST
    etc_cogs = c["etc"]["plan"] * r_etc
    return {
        "b2c": c["b2c"]["plan"], "b2s": c["b2s"]["plan"], "b2g": c["b2g"]["plan"], "etc": c["etc"]["plan"], "b2c_prev": c["b2c"]["prev"],
        "ad": pl["adv"]["plan"], "heads": plan.get("heads") or 12, "prod": f["prod"]["plan"],
        "r_var": round((f["tutor"]["plan"] + f["cp"]["plan"]) / online, 4) if online else 0.28,
        "r_card": round(f["card"]["plan"] / c["b2c"]["plan"], 4) if c["b2c"]["plan"] else 0.041,
        "r_b2g": round((pl["cogs"]["plan"] - etc_cogs) / c["b2g"]["plan"], 4) if c["b2g"]["plan"] else 0.7,
        "r_etc": r_etc, "r_sme": round(f["sme"]["plan"] / f["prod"]["plan"], 4) if f["prod"]["plan"] else 0.25,
        "labor_ph": round(pl["labor"]["plan"] / (plan.get("heads") or 12)),
        "fixed": f["fixed"]["plan"] + pl["dep"]["plan"] + pl["other"]["plan"],
        "op_plan": pl["op"]["plan"],
    }


def sim(m, **kw):
    x = {**m, **kw}
    online = x["b2c"] + x["b2s"]
    rev = online + x["b2g"] + x["etc"]
    cogs = x["b2g"] * x["r_b2g"] + x["etc"] * x["r_etc"]
    sga = x["heads"] * x["labor_ph"] + x["ad"] + online * x["r_var"] + x["b2c"] * x["r_card"] + x["prod"] * (1 + x["r_sme"]) + x["fixed"]
    return {"rev": rev, "gp": rev - cogs, "sga": sga, "op": rev - cogs - sga}


# ---------------------------------------------------------------- 실적(시트·공개 데이터)
def _month(s):
    s = str(s or "")
    m = re.search(r"20\d{2}\D{1,2}(\d{1,2})", s) or re.search(r"(\d{1,2})\s*월", s) or re.fullmatch(r"\s*(\d{1,2})\s*", s)
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 12 else None


def actuals(so):
    """시트 기준 2026 실적: B2G = 정산관리 청구금액(청구월), 온라인 = 콘텐츠DT 월 매출(있는 달만)"""
    b2g_m, b2g_budget, n = [0] * 12, 0, 0
    for r in (so.get("settle") or {}).get("rows", []):
        b2g_budget += r.get("budget") or 0
        mo = _month(r.get("month")) or _month(r.get("end"))
        if r.get("claim") and mo:
            b2g_m[mo - 1] += r["claim"]
            n += 1
    on_m = [0] * 12
    c = so.get("contents") or {}
    for f, d in (c.get("by_field_month") or {}).items():
        for mo, v in d.items():
            if str(mo).isdigit() and 1 <= int(mo) <= 12:
                on_m[int(mo) - 1] += v or 0
    return {"b2g_m": b2g_m, "b2g": sum(b2g_m), "b2g_rows": n, "b2g_budget": b2g_budget,
            "on_m": on_m, "on": sum(on_m), "on_months": sorted(int(m) for m in (c.get("months") or []))}


# ---------------------------------------------------------------- 그림(SVG)
def stack_svg(series, labels, w=760, h=210, neg=None):
    """series: [(name, color, [v..])], neg: 선택(영업이익 등 꺾은선)"""
    n = len(labels)
    tot = [sum(s[2][i] for s in series) for i in range(n)]
    vmax = max(tot + [1])
    lo = min([0] + (neg or [0]))
    hi = max(vmax, max(neg or [0]))
    span = hi - lo or 1
    pl, pb, pt = 52, 24, 8
    cw = (w - pl - 8) / n
    y = lambda v: pt + (hi - v) / span * (h - pb - pt)
    out = [f'<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;font-size:11px;" role="img">']
    for t in (hi, (hi + lo) / 2, lo) if lo < 0 else (hi, hi / 2, 0):
        out.append(f'<line x1="{pl}" x2="{w - 8}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="var(--border)"/>'
                   f'<text x="{pl - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="var(--muted)">{t / 1e8:.1f}억</text>')
    for i, lab in enumerate(labels):
        x0, acc = pl + i * cw + cw * 0.18, 0
        for name, col, vals in series:
            v = vals[i]
            if v > 0:
                out.append(f'<rect x="{x0:.1f}" y="{y(acc + v):.1f}" width="{cw * 0.64:.1f}" height="{y(acc) - y(acc + v):.1f}" fill="{col}" '
                           f'data-tip="{E(lab)} · {E(name)} {v / 1e8:.2f}억"><title>{E(lab)} {E(name)} {v / 1e8:.2f}억</title></rect>')
            acc += max(v, 0)
        out.append(f'<text x="{pl + i * cw + cw / 2:.1f}" y="{h - 6}" text-anchor="middle" fill="var(--muted)">{E(lab)}</text>')
    if neg:
        pts = " ".join(f"{pl + i * cw + cw / 2:.1f},{y(v):.1f}" for i, v in enumerate(neg))
        out.append(f'<polyline points="{pts}" fill="none" stroke="#ef4444" stroke-width="2"/>')
        out += [f'<circle cx="{pl + i * cw + cw / 2:.1f}" cy="{y(v):.1f}" r="3" fill="#ef4444"><title>{E(labels[i])} 영업이익 {v / 1e8:.2f}억</title></circle>' for i, v in enumerate(neg)]
    out.append("</svg>")
    return "".join(out)


def legend(items):
    return "<div style='display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin:6px 0;'>" + "".join(
        f"<span><i style='display:inline-block;width:10px;height:10px;border-radius:2px;background:{c};margin-right:5px;'></i>{E(n)}</span>" for n, c in items) + "</div>"


def tile(lab, val, sub="", warn=False):
    return (f'<div style="flex:1;min-width:150px;padding:10px 12px;border-radius:10px;border:1px solid {"#ef4444" if warn else "var(--border)"};background:var(--surface-2);">'
            f'<div style="font-size:11.5px;color:var(--muted);">{E(lab)}</div><div class="num" style="font-size:21px;font-weight:800;">{E(val)}</div>'
            f'<div style="font-size:11.5px;color:var(--muted);">{E(sub)}</div></div>')


def tiles(ts):
    return '<div style="display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 10px;">' + "".join(ts) + "</div>"


def table(head, rows, num_cols=()):
    th = "".join(f"<th class='{'num' if i in num_cols else ''}'>{E(h)}</th>" for i, h in enumerate(head))
    tb = "".join("<tr>" + "".join(f"<td class='{'num' if i in num_cols else ''}'>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<div class='tbl-wrap'><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>"


def so_line(t):
    return f'<p style="margin:8px 0 0;font-size:13px;"><b>그래서</b> {t}</p>'


NOPLAN = '<p class="tt-note">계획 미등록: GitHub Secret <code>PLAN_2027_JSON</code> 에 plan_extract.py 결과를 넣으면 채워집니다.</p>'


# ---------------------------------------------------------------- 섹션
def s_plan_vs_actual(plan, act):
    if not plan:
        return NOPLAN
    c = chan(plan)
    rev_prev = sum(v["prev"] for v in c.values())
    rev_plan = sum(v["plan"] for v in c.values())
    act_map = {"b2g": act["b2g"], "b2c": None, "b2s": None, "etc": None}
    rows = []
    for k, name, col in CH:
        v = c[k]
        a = act_map[k]
        rows.append([f"<i style='display:inline-block;width:9px;height:9px;background:{col};border-radius:2px;margin-right:5px;'></i>{E(name)}",
                     eok(v["prev"]), pct(v["prev"], rev_prev), "-" if a is None else f"{eok(a)} ({pct(a, v['prev'])})",
                     eok(v["plan"]), pct(v["plan"], rev_plan), f"{(v['plan'] - v['prev']) / v['prev'] * 100:+.0f}%" if v["prev"] else "-"])
    rows.append(["<b>합계</b>", f"<b>{eok(rev_prev)}</b>", "100%", f"온라인 {eok(act['on'])} ({'·'.join(map(str, act['on_months'])) or '-'}월분)",
                 f"<b>{eok(rev_plan)}</b>", "100%", f"{(rev_plan - rev_prev) / rev_prev * 100:+.1f}%"])
    mon = [f"{i + 1}월" for i in range(12)]
    chart = stack_svg([(n, col, c[k]["m"]) for k, n, col in CH], mon)
    five = plan.get("five") or {}
    f_chart = ""
    if five.get("years"):
        f_chart = ("<h4>5개년 매출 구성과 영업이익(빨간 선)</h4>" + stack_svg(
            [(n, col, five.get(k) or [0] * 6) for k, n, col in CH], [f"'{str(y)[2:]}" for y in five["years"]], h=190, neg=five.get("op")))
        sh = [round(b / r * 100) if r else 0 for b, r in zip(five.get("b2g", []), five.get("rev", []))]
        f_chart += f"<p class='tt-note'>B2G 비중: " + " → ".join(f"'{str(y)[2:]} {s}%" for y, s in zip(five["years"], sh)) + "</p>"
    b2g_gap = c["b2g"]["prev"] - act["b2g"]
    return (table(["채널", "'26 예상(계획서)", "비중", "'26 시트 실적(누계)", "'27 계획", "비중", "증감"], rows, (1, 2, 3, 4, 5, 6))
            + "<h4>'27 월별 매출 계획</h4>" + legend([(n, col) for _, n, col in CH]) + chart + f_chart
            + so_line(f"'26 B2G 예상 {eok(c['b2g']['prev'])} 중 정산관리 청구 누계는 {eok(act['b2g'])}입니다. "
                      + (f"남은 {eok(b2g_gap)}이 연말까지 청구돼야 11.19 제출 '26 예상이 맞습니다." if b2g_gap > 0 else "예상치를 이미 넘었습니다. 제출 전 '26 예상을 올려 잡으세요."))
            + "<p class='tt-note'>시트 실적: B2G = 정산관리 청구금액(청구월 기준), 온라인 = 26 콘텐츠DT 월 매출 열(개인·단체 구분 없음). B2C·B2S 를 나눈 실적은 결제 데이터 연동 전까지 비어 있습니다.</p>")


def s_basis(plan, act):
    rows = []
    if plan:
        c = chan(plan)
        prev = sum(v["prev"] for v in c.values())
        rows.append(["A. 순매출(경영계획 양식, 회계 기준)", f"{eok(c['b2g']['prev'])} / {eok(prev)}", pct(c["b2g"]["prev"], prev), "<b>공식 보고·KPI 권장</b> - 손익계획·K-IFRS 와 같은 숫자"])
        if act["b2g_budget"]:
            on = c["b2c"]["prev"] + c["b2s"]["prev"] + c["etc"]["prev"]
            rows.append(["B. 위탁 총액(정산관리 총예산 합)", f"{eok(act['b2g_budget'])} / {eok(act['b2g_budget'] + on)}", pct(act["b2g_budget"], act["b2g_budget"] + on),
                         "영업 규모·수주 실적 설명용(강사료·운영비 등 원가 포함 총액)"])
        rows.append(["C. '27 계획(순매출)", f"{eok(c['b2g']['plan'])} / {eok(sum(v['plan'] for v in c.values()))}", pct(c["b2g"]["plan"], sum(v["plan"] for v in c.values())), "'27 목표 비중"])
    rows.append(["D. 기존 관리 기준(사업 전체 추세)", "-", "기존 보고 수치", "산정 범위·기준 확인 필요(위탁 총액 또는 사업부 전체 기준으로 추정)"])
    return (table(["기준", "B2G / 전체", "B2G 비중", "쓰임"], rows, (1, 2))
            + so_line("같은 사업도 기준에 따라 B2G 비중이 크게 달라집니다. 대외 보고와 KPI 는 A(순매출) 하나로 고정하고, 영업 규모를 말할 때만 B(총액)를 괄호로 함께 적는 것을 권장합니다."))


def s_pl(plan):
    if not plan:
        return NOPLAN
    pl, f = plan["pl"], plan.get("fees", [])
    m_op = pl["op"]["m"]
    cum, run = [], 0
    for v in m_op:
        run += v
        cum.append(run)
    heads = plan.get("heads") or 12
    gm_prev = 1 - pl["cogs"]["prev"] / pl["rev"]["prev"] if pl["rev"]["prev"] else 0
    gm_plan = 1 - pl["cogs"]["plan"] / pl["rev"]["plan"] if pl["rev"]["plan"] else 0
    ts = tiles([tile("매출총이익률", f"{gm_plan * 100:.1f}%", f"'26 {gm_prev * 100:.1f}%"),
                tile("영업이익('27)", eok(pl["op"]["plan"]), f"'26 {eok(pl['op']['prev'])}", True),
                tile("공통비 배부 후", eok(pl.get("op2", {}).get("plan")), "2차 배부 기준", True),
                tile("1인당 매출", eok(pl["rev"]["plan"] / heads), f"인원 {heads}명 유지"),
                tile("흑자 월", ", ".join(f"{i + 1}월" for i, v in enumerate(m_op) if v > 0) or "없음", "월별 영업이익 > 0")])
    lines = [("매출", "rev"), ("매출원가", "cogs"), ("판관비", "sga"), ("· 인건비", "labor"), ("· 지급수수료", "fee"), ("· 광고선전비", "adv"),
             ("· 기타경상비", "other"), ("· 감가상각비", "dep"), ("영업이익", "op")]
    rows = [[E(n), eok(pl[k]["prev"]), eok(pl[k]["plan"]), f"{(pl[k]['plan'] - pl[k]['prev']) / abs(pl[k]['prev']) * 100:+.0f}%" if pl[k]["prev"] else "-"]
            for n, k in lines if k in pl]
    frows = [[E(x["name"]), E(x["basis"]), eok(x["prev"]), eok(x["plan"])] for x in sorted(f, key=lambda x: -x["plan"])]
    rev_m = pl["rev"]["m"]
    chart = stack_svg([("매출", "#10b981", rev_m)], [f"{i + 1}월" for i in range(12)], h=200, neg=m_op)
    return (ts + "<h4>월별 매출(막대)과 영업이익(빨간 선)</h4>" + chart
            + f"<p class='tt-note'>누적 영업이익: 6월 {eok(cum[5])} · 9월 {eok(cum[8])} · 12월 {eok(cum[11])}. 매출이 9·11·12월에 몰려 상반기 적자가 깊습니다.</p>"
            + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;'>"
            + "<div><h4>손익 요약</h4>" + table(["항목", "'26 예상", "'27 계획", "증감"], rows, (1, 2, 3)) + "</div>"
            + "<div><h4>지급수수료 상세</h4>" + table(["항목", "산출근거", "'26", "'27"], frows, (2, 3)) + "</div></div>"
            + so_line(f"판관비 {eok(pl['sga']['plan'])} 중 인건비가 {pct(pl['labor']['plan'], pl['sga']['plan'])}입니다. 매출이 늘어도 고정비가 그대로라 "
                      "흑자는 매출 규모보다 온라인 비중(이익률 약 70%)을 얼마나 빨리 키우느냐에 달려 있습니다. 실제 비용 집행 데이터는 아직 시스템 밖이라 계획 흐름만 보여 줍니다."))


def s_sim(plan):
    if not plan:
        return NOPLAN
    m = model(plan)
    base = sim(m)
    need = -base["op"] / (1 - m["r_var"]) if base["op"] < 0 else 0
    five = plan.get("five") or {}
    gap31 = -(five.get("op") or [0])[-1]
    data = E(json.dumps(m, separators=(",", ":")), quote=True)
    sl = lambda k, lab, mx, st: (f'<label style="display:block;margin:6px 0;font-size:13px;">{E(lab)} <b class="num" data-out="{k}"></b>'
                                 f'<input type="range" data-k="{k}" min="0" max="{mx}" step="{st}" style="width:100%;"></label>')
    return (f'<div id="planSim" data-p="{data}" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;">'
            "<div>" + sl("b2c", "B2C 개인 매출", 1_000_000_000, 10_000_000) + sl("b2s", "B2S 단체 매출", 1_000_000_000, 10_000_000)
            + sl("b2g", "B2G 위탁 매출", 800_000_000, 10_000_000) + sl("etc", "제품·상품·기타", 300_000_000, 5_000_000)
            + sl("ad", "광고선전비", 200_000_000, 5_000_000) + sl("prod", "콘텐츠 제작비", 400_000_000, 10_000_000)
            + sl("heads", "인원(명)", 20, 1)
            + '<button type="button" data-reset style="margin-top:6px;">계획값으로 되돌리기</button></div>'
            '<div><div data-sim-out></div></div></div>'
            + f"<p class='tt-note'>계수(계획서 산출근거 역산): 온라인 변동비(튜터+CP 쉐어) {m['r_var'] * 100:.1f}% · 카드수수료 B2C의 {m['r_card'] * 100:.1f}% · "
              f"B2G 원가율 {m['r_b2g'] * 100:.0f}% · 제품 원가율 {m['r_etc'] * 100:.1f}% · SME 제작비의 {m['r_sme'] * 100:.0f}% · 1인 인건비 {eok(m['labor_ph'])} · 고정비 {eok(m['fixed'])}. "
              f"계획값 그대로 넣으면 영업이익 {eok(base['op'])}(양식 {eok(m['op_plan'])})로 맞습니다.</p>"
            + so_line(f"'27 계획에서 흑자가 되려면 다른 조건이 같을 때 온라인 매출이 약 {eok(need, 1)} 더 필요합니다(기여율 {(1 - m['r_var']) * 100:.0f}%). "
                      f"'31 추정 적자 {eok(gap31)}를 메우는 데는 약 {eok(gap31 / (1 - m['r_var']), 1)}입니다. B2G 1억 증가는 이익 {eok(1e8 * (1 - m['r_b2g']), 1)}, 온라인 1억 증가는 {eok(1e8 * (1 - m['r_var']), 1)} 기여합니다."))


def _decided(res):
    return bool(re.search(r"수주|실패|탈락|아웃|포기", res or ""))


def s_b2g_score(plan, so, lc, pipe):
    b = so.get("bids") or {}
    rows = b.get("recent") or []
    if not rows:
        return '<p class="tt-note">26입찰DT 가 아직 연동되지 않았습니다.</p>'
    r_b2g = model(plan)["r_b2g"] if plan else 0.70
    gm = 1 - r_b2g
    bf = b.get("by_field") or {}
    reg_join, reg_comp = Counter(), Counter()
    for r in rows:
        if r.get("joined"):
            reg_join[r.get("region")] += 1
            if not r.get("won") and r.get("winner"):
                reg_comp[r.get("region")] += 1
    own_orgs = {str(p.get("org") or "")[:30] for p in pipe}
    lc_pt = {"확대": 1.0, "재계약": 0.8, "첫 수주": 0.5, "개척": 0.2}
    out = []
    for r in rows:
        if _decided(r.get("result")):
            continue
        f = bf.get(r.get("field") or "미분류") or {}
        fr = min(1.0, ((f.get("won", 0) + 1) / (f.get("join", 0) + 3)) / 0.5)
        size = min(1.0, (r.get("budget") or 0) * gm / 30_000_000)
        rel = 1.0 if r.get("org") in own_orgs else lc_pt.get((lc.get(r.get("region")) or {}).get("stage"), 0.3)
        comp = reg_comp[r.get("region")] / reg_join[r.get("region")] if reg_join[r.get("region")] else 0.5
        sc = round(35 * size + 30 * fr + 25 * rel + 10 * (1 - comp))
        contrib = (r.get("budget") or 0) * gm
        verdict = "참여" if sc >= 60 else "검토" if sc >= 40 else "보류"
        out.append((sc, r, contrib, verdict, fr, rel, comp))
    out.sort(key=lambda x: -x[0])
    col = {"참여": "#10b981", "검토": "#f59e0b", "보류": "#94a3b8"}
    trs = [[f"<b class='num'>{sc}</b>", f"<span style='color:{col[v]};font-weight:800;'>{v}</span>", E(r.get("posted") or "-"), E(r.get("region") or "-"),
            E((r.get("title") or "")[:46]), E(r.get("field") or "-"), eok(r.get("budget"), 2) if r.get("budget") else "-",
            ("<span style='color:#ef4444;font-weight:700;'>" if contrib < B2G_GM_MIN else "<span>") + (eok(contrib, 2) if contrib else "-") + "</span>",
            f"{fr * 50:.0f}%", f"{rel:.1f}", f"{comp * 100:.0f}%"] for sc, r, contrib, v, fr, rel, comp in out[:20]]
    cnt = Counter(v for _, _, _, v, *_ in out)
    low = sum(1 for _, r, c, *_ in out if r.get("budget") and c < B2G_GM_MIN)
    return (tiles([tile("판단 대상(결과 미기재)", f"{len(out)}건"), tile("참여 권장", f"{cnt['참여']}건"), tile("검토", f"{cnt['검토']}건"),
                   tile("보류", f"{cnt['보류']}건"), tile("이익 기여 1천만 미만", f"{low}건", "예산 × 이익률", bool(low))])
            + table(["점수", "판단", "공고일", "지역", "사업명", "분야", "사업규모", "예상 이익 기여", "분야 승률", "관계", "경쟁 낙찰"], trs, (0, 6, 7, 8, 9, 10))
            + f"<p class='tt-note'>점수 = 이익 기여 규모 35(사업규모 × 이익률 {gm * 100:.0f}%, 3천만 원 이상 만점) + 분야 승률 30(입찰DT 참여 대비 수주, 표본 보정) + 관계 25(운영DT 기존 기관 1.0 · 시도 생애주기 확대 1.0/재계약 0.8/첫 수주 0.5/개척 0.2) + 경쟁 10(그 지역 참여 건 중 타사 낙찰 비율이 낮을수록 높음). 60점 이상 참여, 40~59 검토, 40 미만 보류. 빨간 금액은 건당 최소 이익 기여(가정 1천만 원) 미달.</p>"
            + so_line("B2G 를 줄이는 것이 아니라 이익이 남는 사업만 남기는 것이 계획의 논리입니다. 보류·빨간 금액 건은 참여 전에 원가(강사료·운영 인력)를 다시 계산하세요."))


def s_ad(plan):
    if not plan:
        return NOPLAN
    c = chan(plan)
    ad = plan.get("ad", [])
    tot = sum(a["plan"] for a in ad)
    inc = c["b2c"]["plan"] - c["b2c"]["prev"]
    rows = [[E(a["name"]), E(a["basis"] or "-"), eok(a["plan"], 2), " ".join(f"{i + 1}월" for i, v in enumerate(a["m"]) if v)] for a in ad]
    mrows = [[f"{i + 1}월", eok(sum(a["m"][i] for a in ad), 2), eok(c["b2c"]["m"][i], 2), "<span class='tt-note'>입력 대기</span>", "<span class='tt-note'>입력 대기</span>"] for i in range(12)]
    return (tiles([tile("'27 광고비", eok(tot, 2), f"'26 {eok(sum(a['prev'] for a in ad), 3)}"), tile("B2C 증가 목표", eok(inc, 2), f"{eok(c['b2c']['prev'])} → {eok(c['b2c']['plan'])}"),
                   tile("필요 ROAS(증분)", f"{inc / tot:.1f}배" if tot else "-", "B2C 증가분 ÷ 광고비", True), tile("필요 ROAS(전체)", f"{c['b2c']['plan'] / tot:.1f}배" if tot else "-", "B2C 매출 ÷ 광고비")])
            + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;'>"
            + "<div><h4>채널별 계획</h4>" + table(["채널", "산출근거", "'27", "집행 월"], rows, (2,)) + "</div>"
            + "<div><h4>월별 광고비 × B2C 매출 계획 · 실적</h4>" + table(["월", "광고비 계획", "B2C 계획", "광고비 실적", "B2C 실적"], mrows, (1, 2)) + "</div></div>"
            + so_line(f"광고만으로 B2C 증가분을 만든다면 광고비 1원당 {inc / tot:.1f}원을 벌어야 합니다. 시즌 프로모션(2·3·7·8월)이 몰린 달에 B2C 계획이 뒤따라 오르는지가 첫 점검 포인트입니다." if tot else "광고 계획이 없습니다.")
            + "<p class='tt-note'>실적 칸은 비어 있습니다: 광고 집행·결제 데이터가 아직 시스템 밖입니다. 구글시트에 '27광고DT'(월 · 채널 · 집행액 · 유입 · 가입 · 결제 건수 · 결제액, 개인정보 없이 집계만) 탭을 만들면 이 표와 연결하겠습니다. 샘몰 설계 때 같은 항목의 집계 내보내기를 요구사항에 넣으세요.</p>")


def s_content(plan, so):
    import training_topics as tt
    today = date.today()
    since = (today - timedelta(days=365)).isoformat()
    names = {t[0]: t[1] for t in tt.TOPICS}
    dem = Counter()
    for r in _jsonl("history/training_bids.jsonl"):
        if (r.get("d") or "") >= since and tt.is_training_bid(r.get("t"), r.get("o")):
            for tid in tt.classify_topics(r.get("t") or ""):
                dem[tid] += 1
    sup, sales = Counter(), Counter()
    for c in (so.get("contents") or {}).get("rows", []):
        for tid in tt.classify_topics(f"{c.get('title', '')} {c.get('field', '')}"):
            sup[tid] += 1
            sales[tid] += c.get("total") or 0
    dt, st = sum(dem.values()) or 1, sum(sup.values()) or 1
    prod = 0
    if plan:
        prod = sum(f["plan"] for f in plan.get("fees", []) if "제작비" in f["name"])
    w = {t: (dem[t] / dt) * (1.0 if sup[t] / st < dem[t] / dt else 0.5) for t in names}
    ws = sum(w.values()) or 1
    rows = []
    for t in sorted(names, key=lambda t: -(dem[t] / dt - sup[t] / st)):
        gap = dem[t] / dt - sup[t] / st
        rows.append([E(names[t]), f"{dem[t]:,}", f"{dem[t] / dt * 100:.0f}%", f"{sup[t]:,}", f"{sup[t] / st * 100:.0f}%",
                     f"<b style='color:{'#ef4444' if gap > 0.03 else '#10b981' if gap < -0.03 else 'var(--muted)'};'>{gap * 100:+.0f}%p</b>",
                     eok(sales[t] / sup[t], 3) if sup[t] else "-", eok(prod * w[t] / ws, 2) if prod else "-"])
    top = [names[t] for t in sorted(names, key=lambda t: -(dem[t] / dt - sup[t] / st))[:3]]
    return (table(["주제", "발주 수요(12개월)", "수요 비중", "보유 과정", "보유 비중", "수요-보유", "과정당 누적 매출", "권장 제작비"], rows, (1, 2, 3, 4, 5, 6, 7))
            + f"<p class='tt-note'>수요 = 나라장터 연수 입찰 제목 주제 분류(최근 12개월), 보유 = 26 콘텐츠DT 과정명·분야 같은 분류. 권장 제작비 = '27 제작비 {eok(prod, 2) if prod else '(계획 미등록)'} × 수요 비중(보유가 수요보다 많은 주제는 절반 가중).</p>"
            + so_line(f"수요 대비 보유가 가장 모자란 주제는 {', '.join(top)}입니다. 제작비를 줄이는 해에는 이 주제부터 신규·개편을 배정하고, 보유 비중이 큰 주제는 개편 주기를 늘리세요."))


def s_b2s_map(lc, pipe):
    ai = Counter((s.get("소속지역") or "")[:2] for s in (_j("static_data/ai_schools_2026.json", {}) or {}).get("schools", []))
    ec = _jsonl("history/edu_contracts.jsonl")
    collected = {r.get("sido") for r in ec}
    sch, own_sch = Counter(), Counter()
    for r in ec:
        if r.get("school"):
            sch[r.get("sido")] += 1
            if r.get("vendor") == "비바샘연수원":
                own_sch[r.get("sido")] += 1
    proj = Counter(str(p.get("region") or "")[:2] for p in pipe)
    fin = ((_j("history/eduinfo_finance.json", {}) or {}).get("finance") or {})

    def growth(r):
        f = fin.get(r) or {}
        ys = sorted(f)
        if len(ys) < 2 or not f[ys[-2]].get("in"):
            return None
        return (f[ys[-1]]["in"] - f[ys[-2]]["in"]) / f[ys[-2]]["in"]
    gmax = max([abs(growth(r) or 0) for r in REG] + [0.01])
    amax = max(list(ai.values()) + [1])
    out = []
    for r in REG:
        stage_lc = (lc.get(r) or {}).get("stage", "개척")
        stage = "학교 진입" if own_sch[r] else "B2G 관계" if (stage_lc != "개척" or proj[r]) else "미진출"
        rel = {"학교 진입": 0.6, "B2G 관계": 1.0, "미진출": 0.3}[stage]
        g = growth(r)
        score = round(100 * (0.45 * ai[r] / amax + 0.25 * rel + 0.2 * (max(g or 0, 0) / gmax) + 0.1 * (min(sch[r], 100) / 100)))
        out.append({"r": r, "stage": stage, "lc": stage_lc, "ai": ai[r], "proj": proj[r], "sch": sch[r] if r in collected else None,
                    "own": own_sch[r] if r in collected else None, "g": g, "score": score})
    col = {"학교 진입": "#10b981", "B2G 관계": "#4f8cff", "미진출": "#94a3b8"}
    grid = "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px;margin:8px 0;'>" + "".join(
        f"<div style='border:1px solid {col[o['stage']]};border-left:5px solid {col[o['stage']]};border-radius:8px;padding:7px 9px;background:var(--surface-2);'>"
        f"<div style='font-weight:800;'>{E(o['r'])} <span class='num' style='float:right;'>{o['score']}</span></div>"
        f"<div style='font-size:11.5px;color:var(--muted);'>{E(o['stage'])} · AI중점 {o['ai'] if o['ai'] else '-'}</div></div>" for o in sorted(out, key=lambda o: -o["score"])) + "</div>"
    rows = [[E(o["r"]), f"<b style='color:{col[o['stage']]};'>{E(o['stage'])}</b>", E(o["lc"]), f"{o['proj']}", f"{o['ai']}" if o["ai"] else "명단 없음",
             "미수집" if o["sch"] is None else f"{o['sch']}", "미수집" if o["own"] is None else f"{o['own']}",
             "-" if o["g"] is None else f"{o['g'] * 100:+.1f}%", f"<b>{o['score']}</b>"] for o in sorted(out, key=lambda o: -o["score"])]
    nxt = [o["r"] for o in sorted(out, key=lambda o: -o["score"]) if o["stage"] != "학교 진입"][:5]
    return (legend([(k, v) for k, v in col.items()]) + grid
            + table(["시도", "B2S 단계", "B2G 생애주기", "운영 사업", "AI 중점학교", "학교 연수 수의계약", "자사 수의", "교육재정 세입 증감", "우선순위"], rows, (3, 4, 5, 6, 7, 8))
            + "<p class='tt-note'>우선순위 = AI 중점학교 수 45(정책 수요) + 관계 25(B2G 관계가 있으나 학교 미진입 1.0 · 이미 진입 0.6 · 미진출 0.3) + 교육재정 세입 증가 20 + 학교 연수 수의계약 규모 10. 학교 수의계약은 공개 게시판을 수집하는 3개 시도(서울·부산·전북)만 있습니다.</p>"
            + so_line(f"17개 시도 확산의 다음 순서는 {' → '.join(nxt)}입니다. B2G 관계가 있는 시도부터 학교 단체구매 패키지를 제안하면 신규 개척보다 영업 비용이 낮습니다."))


def s_form(plan, act):
    hdr = ["매출항목", "품목", "'26 시트 실적 합계"] + [f"{i}월" for i in range(1, 13)] + ["비고"]
    lines = [hdr,
             ["용역매출", "교육청 위탁연수(B2G 용역)", act["b2g"]] + act["b2g_m"] + ["정산관리 청구금액·청구월 기준"],
             ["온라인매출", "온라인 연수(개인+단체, 시트상 구분 불가)", act["on"]] + act["on_m"] + [f"26 콘텐츠DT 월 매출 열({','.join(map(str, act['on_months']))}월만 있음)"]]
    if plan:
        lines.append([])
        lines.append(["['27 계획 원본]", "", "계획 합계"] + [f"{i}월" for i in range(1, 13)] + ["산출근거"])
        for s in plan.get("sales", []):
            lines.append([s["k"].upper(), s["name"], s["plan"]] + s["m"] + [s.get("basis", "")])
    import csv
    import io
    import base64
    buf = io.StringIO()
    csv.writer(buf).writerows(lines)
    uri = "data:text/csv;base64," + base64.b64encode(("﻿" + buf.getvalue()).encode("utf-8")).decode()
    today = date.today().isoformat()
    return (f'<p><a href="{uri}" download="경영계획_매출실적_{today}.csv" style="font-weight:800;">⬇ 매출 실적·계획 CSV 내려받기</a> '
            f'<span class="tt-note">(엑셀에서 열림 · 관리 탭 안에서만 생성)</span></p>'
            + table(["행", "'26 시트 실적", "있는 달"], [["B2G 용역(정산관리)", eok(act["b2g"]), f"{sum(1 for v in act['b2g_m'] if v)}개월 · {act['b2g_rows']}건"],
                                                   ["온라인(콘텐츠DT)", eok(act["on"]), f"{', '.join(map(str, act['on_months'])) or '-'}월"]], (1,))
            + so_line("양식 '1.매출' 상세 입력의 '전년 예상실적' 칸에 붙여 넣을 실적 근거입니다. 11.19 제출 전 B2G 는 연말 청구 예정분을, 온라인은 빠진 달을 더해 '26 예상으로 확정하세요.")
            + "<p class='tt-note'>양식(xlsx) 자체를 자동으로 채우는 것은 회사 양식의 수식·검증 칸을 깨뜨릴 위험이 있어 CSV 로 근거만 냅니다.</p>")


def s_ax(plan, so):
    import workflows as wf
    cov = wf.coverage()
    n, auto, part = sum(c["n"] for c in cov), sum(c["auto"] for c in cov), sum(c["part"] for c in cov)
    rep = ((so.get("reports") or {}).get("items") or {}) if isinstance(so.get("reports"), dict) else {}
    # 가정: 사람이 하던 일의 월 소요 시간(자동화 전) - 실측이 아니라 추정
    saved = [("조간 브리핑 지면 구성", "하루 60분 × 22일", 22), ("나라장터 입찰·사전규격 모니터링", "하루 30분 × 22일", 11),
             ("학교·교육청 수의계약 확인", "주 2시간", 8), ("정산·청구 누락 점검", "주 2시간", 8), ("집합연수 준비 점검", "주 1시간", 4),
             ("모집 홍보 문구 작성", "건당 30분 × 월 8건", 4), ("결과보고서 초안", "건당 2시간 × 월 4건", 8), ("경영계획 실적 집계", "연 2회 × 16시간 ÷ 12", 3)]
    h = sum(x[2] for x in saved)
    heads = (plan or {}).get("heads") or 12
    five = (plan or {}).get("five") or {}
    per = [f"'{str(y)[2:]} {r / heads / 1e8:.2f}억" for y, r in zip(five.get("years", []), five.get("rev", []))]
    rows = [[E(c["name"]), f"{c['n']}", f"{c['auto']}", f"{c['part']}", f"{c['none']}", pct(c["auto"], c["n"])] for c in cov]
    return (tiles([tile("업무 단계 자동 연결", f"{auto}/{n}", f"부분 {part} · 목표 23/{n}"), tile("월 절감 시간(추정)", f"{h}시간", f"약 {h / 160:.2f}명분(월 160시간)"),
                   tile("1인당 매출('27)", eok(plan["pl"]["rev"]["plan"] / heads) if plan else "-", f"인원 {heads}명"), tile("결과보고 AI 초안", f"{len(rep)}건", "최근 종료 사업")])
            + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;'>"
            + "<div><h4>업무 플로우별 연결</h4>" + table(["플로우", "단계", "자동", "부분", "없음", "자동률"], rows, (1, 2, 3, 4, 5)) + "</div>"
            + "<div><h4>절감 시간 가정</h4>" + table(["업무", "가정", "월 시간"], [[E(a), E(b), f"{c}"] for a, b, c in saved], (2,)) + "</div></div>"
            + (f"<p class='tt-note'>1인당 매출 추이(인원 {heads}명 유지 가정): {' → '.join(per)}</p>" if per else "")
            + so_line(f"회사 과제1(업무 흐름 중심 AX)의 교원연수 사례로 '업무 {n}단계 중 {auto}단계 자동 연결, 월 약 {h}시간 절감(추정)'을 보고할 수 있습니다. "
                      "남은 갭(B2C 결제·광고, 강사 섭외)을 메우면 23단계가 됩니다. 절감 시간은 실측이 아니므로 분기마다 담당자 확인으로 보정하세요."))


def signals(plan, act, so):
    out = []
    if plan:
        c = chan(plan)
        today = date.today()
        out.append(f"B2G '26 청구 누계 {eok(act['b2g'])} / 예상 {eok(c['b2g']['prev'])} ({pct(act['b2g'], c['b2g']['prev'])}) · 연말까지 {12 - today.month}개월")
        m = model(plan)
        out.append(f"'27 흑자 조건: 온라인 매출 +{eok(-sim(m)['op'] / (1 - m['r_var']), 1)} (현 계획 영업이익 {eok(sim(m)['op'])})")
    fl = (so.get("settle") or {}).get("flags") or {}
    if fl:
        out.append("정산 경보 " + " · ".join(f"{k} {v}건" for k, v in fl.items()))
    pend = [r for r in (so.get("bids") or {}).get("recent", []) if not _decided(r.get("result"))]
    if pend:
        out.append(f"입찰 결과 미기재 {len(pend)}건 - 아래 판단표 확인")
    return out


# ---------------------------------------------------------------- 조립
def build_html(sec):
    plan = load_plan()
    so = _j("live/sheets_ops.json", {}) or {}
    rep = _j("live/report_drafts.json")
    if rep:
        so["reports"] = rep
    pipe = (_j("live/own_pipeline_export.json", {}) or {}).get("records", [])
    try:
        import viz_data
        lc = viz_data.lifecycle(date.today())
    except Exception:
        lc = {}
    act = actuals(so)
    parts = []

    def add(title, desc, fn, *a):
        try:
            parts.append(sec(title, desc, fn(*a)))
        except Exception as e:  # 한 섹션 오류가 관리 탭 전체를 막지 않게
            parts.append(sec(title, desc, f"<p class='tt-note'>이 섹션을 만들지 못했습니다: {E(type(e).__name__)}</p>"))
            print(f"[경고] plan2027 {title}: {type(e).__name__}: {str(e)[:120]}")

    sig = signals(plan, act, so)
    head = ("<div style='padding:10px 14px;border-radius:10px;border:1px solid #f59e0b;background:color-mix(in srgb,#f59e0b 8%,transparent);margin-bottom:10px;'>"
            "<b>오늘의 계획 신호</b><ul style='margin:6px 0 0 18px;padding:0;'>" + "".join(f"<li>{E(s)}</li>" for s in sig) + "</ul></div>") if sig else ""
    status = ("<p class='tt-note'>계획: " + (f"등록됨({plan.get('year')}년 · 인원 {plan.get('heads')}명)" if plan else "미등록") + f" · 시트 조회 {E(str(so.get('fetched') or '-'))}</p>")
    add("① 매출 구성: 계획 대비 실적", "'26 예상·시트 실적·'27 계획을 채널 4개(B2C·B2S·B2G·기타)로 맞대고, 월별·5개년 구성을 봅니다.", lambda: head + status + s_plan_vs_actual(plan, act))
    add("② B2G 비중 기준 맞추기", "같은 사업을 어떤 기준으로 세느냐에 따라 B2G 비중이 달라집니다. 보고용 공식 기준을 하나로 정합니다.", s_basis, plan, act)
    add("③ 손익 흐름 모니터", "월별 매출·영업이익, 손익 요약, 지급수수료 상세(산출근거 포함).", s_pl, plan)
    add("④ 흑자전환 계산기", "슬라이더로 채널 매출·광고비·제작비·인원을 바꾸면 손익이 바로 다시 계산됩니다(계수는 계획서 산출근거에서 역산).", s_sim, plan)
    add("⑤ B2G 수주 판단표", "26입찰DT 중 결과가 아직 없는 공고를 이익 기여·분야 승률·관계·경쟁으로 점수화합니다.", s_b2g_score, plan, so, lc, pipe)
    add("⑥ B2C 광고 효율", "계획 광고비로 B2C 성장 목표를 만들 수 있는지 - 필요 ROAS 와 월별 점검표.", s_ad, plan)
    add("⑦ 콘텐츠 제작 우선순위", "발주 수요(나라장터)와 보유 과정(콘텐츠DT)을 같은 주제 분류로 겹쳐, 제작비를 어디에 쓸지 정합니다.", s_content, plan, so)
    add("⑧ B2S 17개 시도 확산 지도", "시도별 진입 단계와 정책 수요·관계·재정으로 다음 공략 순서를 냅니다.", s_b2s_map, lc, pipe)
    add("⑨ 경영계획 양식 실적 채움", "11.19 매출계획·12.15 손익계획 제출용 '26 실적 근거를 CSV 로 내려받습니다.", s_form, plan, act)
    add("⑩ AX 성과판", "회사 2027 과제1(업무 흐름 중심 AX) 보고용: 자동 연결 단계·절감 시간(추정)·1인당 매출.", s_ax, plan, so)
    return ("<h3 style='margin:4px 0 10px;'>2027 경영계획 (비공개)</h3>" + "".join(parts))


if __name__ == "__main__":
    sec = lambda t, d, b: f'<section class="panel"><div class="panel-head"><div><p class="panel-title">{t}</p><p class="panel-desc">{d}</p></div></div>{b}</section>'
    Path("live").mkdir(exist_ok=True)
    Path("live/plan_preview.html").write_text("<meta charset=utf-8>" + build_html(sec), encoding="utf-8")
    print("plan preview -> live/plan_preview.html")
