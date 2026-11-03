#!/usr/bin/env python3
"""
관리 탭 '경영 종합' — 2027 목표 경로 트래커(대표 전용).

월별 매출(MGMT_JSON 의 years[].m)로 '최근 12개월(TTM) B2G 비중'을 매달 계산하고,
기준점(직전 확정 연도 12월 TTM) → 2027 경영계획 B2G 비중(plan27.path, 없으면 target)으로 가는
월 단위 직선 목표 경로와 비교한다. 경로보다 높으면 '목표를 맞추려면 TTM B2C+B2S 가 얼마 더 필요한지'를 역산한다.
B2G = 교육청 단체(b2s) + 위탁 용역(b2g) — mgmt_owner 와 같은 공식 기준.
"""
import html
from datetime import date

E = html.escape


def _plan27(M):
    P = (M.get("plan27") or {}).get("path") or {}
    for y, a in zip(P.get("years") or [], P.get("target") or []):
        if y == 2027 and a is not None:
            return float(a), "2027 경영계획"
    t = M.get("target") or {}
    if t.get("b2g") is not None:
        return float(t["b2g"]), f"{t.get('y', '')} 목표"
    return 40.0, "가정 40%"


def monthly(M):
    """[(y, m, G(B2G), N(B2C+B2S), 예상월 여부)] 시간순"""
    fc = {int(k): int(v) for k, v in (M.get("fc_from") or {}).items()}
    out = []
    for r in sorted(M.get("years") or [], key=lambda r: r["y"]):
        m = r.get("m") or {}
        if not m:
            continue
        for i in range(12):
            b2c, b2s, b2g = (float((m.get(k) or [0] * 12)[i] or 0) for k in ("b2c", "b2s", "b2g"))
            if b2c == b2s == b2g == 0 and r["y"] >= date.today().year:
                continue  # 아직 안 온 달
            out.append((r["y"], i + 1, b2s + b2g, b2c, r["y"] in fc and i + 1 >= fc[r["y"]]))
    return out


def ttm(series):
    """[(y, m, share%, G12, N12, 예상 포함 여부)] — 12개월이 쌓인 달부터"""
    out = []
    for i in range(11, len(series)):
        win = series[i - 11:i + 1]
        G, N = sum(x[2] for x in win), sum(x[3] for x in win)
        if G + N > 0:
            out.append((series[i][0], series[i][1], G / (G + N) * 100, G, N, any(x[4] for x in win)))
    return out


def path(T, target):
    """기준점 = 2027년 이전 마지막 확정 12월 TTM. 기준점 → 2027-12 목표까지 월 직선."""
    base = next((t for t in reversed(T) if t[1] == 12 and t[0] < 2027 and not t[5]), None) or (T[0] if T else None)
    if not base:
        return None, lambda y, m: None
    b_idx = base[0] * 12 + base[1]
    e_idx = 2027 * 12 + 12
    span = max(e_idx - b_idx, 1)

    def at(y, m):
        k = y * 12 + m
        if k <= b_idx:
            return None
        return base[2] + (target - base[2]) * min((k - b_idx) / span, 1)
    return base, at


def analyze(M):
    if not M:
        return None
    T = ttm(monthly(M))
    if not T:
        return None
    target, src = _plan27(M)
    base, at = path(T, target)
    actual = [t for t in T if not t[5]]
    cur = actual[-1] if actual else T[-1]
    pv = at(cur[0], cur[1])
    gap = cur[2] - pv if pv is not None else None
    need = None
    if pv:
        s = pv / 100
        need = cur[3] * (1 - s) / s - cur[4]  # B2G 금액 유지 시 경로 비중을 맞추는 데 필요한 TTM B2C+B2S 추가액
    prev = next((t for t in reversed(actual[:-1]) if (t[0], t[1]) == ((cur[0] - 1, cur[1]))), None)
    return {"T": T, "target": target, "src": src, "base": base, "at": at, "cur": cur, "path_now": pv, "gap": gap,
            "need": need, "yoy": (cur[2] - prev[2]) if prev else None, "asof": M.get("asof")}


def _eok(v):
    return f"{v:,.1f}억" if v is not None else "-"


def _svg(A, w=640, h=200):
    T = A["T"][-36:]
    pts = [(i, t[2], t[5]) for i, t in enumerate(T)]
    pth = [(i, A["at"](t[0], t[1])) for i, t in enumerate(T)]
    vals = [p[1] for p in pts] + [p[1] for p in pth if p[1] is not None] + [A["target"]]
    lo, hi = max(min(vals) - 5, 0), min(max(vals) + 5, 100)
    X = lambda i: 36 + i / max(len(T) - 1, 1) * (w - 50)
    Y = lambda v: 10 + (hi - v) / (hi - lo or 1) * (h - 40)
    act = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v, f in pts if not f)
    fc = [(i, v) for i, v, f in pts if f]
    if fc and any(not f for _, _, f in pts):
        last = max(i for i, _, f in pts if not f)
        fc = [(last, pts[last][1])] + fc
    fcs = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in fc)
    ps = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pth if v is not None)
    grid = "".join(f"<line x1='36' x2='{w - 14}' y1='{Y(g):.1f}' y2='{Y(g):.1f}' stroke='var(--border)'/><text x='30' y='{Y(g) + 4:.1f}' font-size='10' text-anchor='end' fill='var(--muted)'>{g:.0f}%</text>"
                   for g in range(int(lo // 10 * 10 + 10), int(hi) + 1, 10))
    labs = "".join(f"<text x='{X(i):.1f}' y='{h - 8}' font-size='10' text-anchor='middle' fill='var(--muted)'>'{str(t[0])[2:]}.{t[1]}</text>"
                   for i, t in enumerate(T) if t[1] in (1, 7))
    return (f"<svg viewBox='0 0 {w} {h}' style='width:100%;max-width:{w}px;height:auto;' role='img' aria-label='TTM B2G 비중과 목표 경로'>{grid}{labs}"
            f"<polyline points='{ps}' fill='none' stroke='var(--muted)' stroke-width='2' stroke-dasharray='5 4'/>"
            f"<polyline points='{act}' fill='none' stroke='#4f8cff' stroke-width='2.5'/>"
            + (f"<polyline points='{fcs}' fill='none' stroke='#4f8cff' stroke-width='2' stroke-dasharray='2 3' opacity='.7'/>" if fcs else "")
            + "</svg>")


def build(sec, M=None):
    if M is None:
        try:
            M = __import__("mgmt_owner").load()
        except Exception:
            M = None
    A = analyze(M)
    if not A:
        return sec("2027 목표 경로 트래커", "월별 최근 12개월 B2G 비중 vs 목표 경로",
                   '<p class="tt-note">월별 실적이 없습니다: GitHub Secret <code>MGMT_JSON</code> 의 years[].m(월별 b2c·b2s·b2g)이 있으면 채워집니다.</p>')
    c, g = A["cur"], A["gap"]
    col = "#dc2626" if g is not None and g > 2 else "#f59e0b" if g is not None and g > 0 else "#10b981"
    verdict = ("목표 경로보다 높음 — B2C+B2S 보강 필요" if g is not None and g > 0 else "목표 경로 이내") if g is not None else "경로 기준점 이전"
    tile = lambda k, v, s="", cc="var(--ink)": (f"<div style='padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--surface-2);'>"
                                                 f"<div style='font-size:12px;color:var(--muted);'>{k}</div><div style='font-size:20px;font-weight:800;color:{cc};'>{v}</div>"
                                                 f"<div style='font-size:11.5px;color:var(--muted);'>{s}</div></div>")
    tiles = ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px;'>"
             + tile(f"TTM B2G 비중 ({c[0]}.{c[1]})", f"{c[2]:.1f}%", f"전년 같은 달 대비 {A['yoy']:+.1f}%p" if A["yoy"] is not None else "")
             + tile("이번 달 목표 경로", f"{A['path_now']:.1f}%" if A["path_now"] is not None else "-", f"기준 {A['base'][0]}.12 {A['base'][2]:.1f}% → 2027.12 {A['target']:.0f}% ({E(A['src'])})")
             + tile("경로 대비", f"{g:+.1f}%p" if g is not None else "-", verdict, col)
             + tile("경로 맞추려면 TTM B2C+B2S", f"+{_eok(A['need'])}" if A["need"] and A["need"] > 0 else "충족", f"B2G 금액 {_eok(c[3])} 유지 가정 · 현재 B2C+B2S {_eok(c[4])}")
             + "</div>")
    rows = "".join(f"<tr><td>{t[0]}.{t[1]}{' (예상 포함)' if t[5] else ''}</td><td class='num'>{t[2]:.1f}%</td>"
                   f"<td class='num'>{'' if A['at'](t[0], t[1]) is None else format(A['at'](t[0], t[1]), '.1f') + '%'}</td>"
                   f"<td class='num'>{'' if A['at'](t[0], t[1]) is None else format(t[2] - A['at'](t[0], t[1]), '+.1f')}</td>"
                   f"<td class='num'>{_eok(t[3])}</td><td class='num'>{_eok(t[4])}</td></tr>" for t in reversed(A["T"][-12:]))
    body = (tiles + _svg(A)
            + "<p class='tt-note'>파란 실선 = 실적 TTM B2G 비중 · 파란 점선 = 예상 월 포함 · 회색 점선 = 목표 경로(기준점 → 2027.12 직선). "
              "B2G = 교육청 단체 + 위탁 용역. '필요 B2C+B2S' 는 B2G 금액을 그대로 둘 때 경로 비중을 맞추는 TTM 개인·학교 매출 추가액(추정).</p>"
            + f"<details><summary style='cursor:pointer;font-weight:700;'>최근 12개월 표</summary><div class='tbl-wrap'><table><thead><tr><th>월</th><th class='num'>TTM B2G</th><th class='num'>경로</th>"
              f"<th class='num'>차이(%p)</th><th class='num'>TTM B2G 금액</th><th class='num'>TTM B2C+B2S</th></tr></thead><tbody>{rows}</tbody></table></div></details>")
    return sec("2027 목표 경로 트래커 (대표 전용)", f"최근 12개월(TTM) B2G 비중을 매달 목표 경로와 비교 · 경영실적 기준 {E(str(A['asof'] or '-'))}", body)


def pack_md(M=None):
    if M is None:
        try:
            M = __import__("mgmt_owner").load()
        except Exception:
            M = None
    A = analyze(M)
    if not A:
        return []
    c = A["cur"]
    out = [f"## 2027 목표 경로 (TTM B2G 비중, 기준 {A['asof'] or '-'})", "",
           f"- 현재 {c[0]}.{c[1]} TTM B2G 비중 **{c[2]:.1f}%** · 이번 달 목표 경로 {A['path_now']:.1f}% · 차이 **{A['gap']:+.1f}%p**" if A["gap"] is not None
           else f"- 현재 {c[0]}.{c[1]} TTM B2G 비중 **{c[2]:.1f}%**",
           f"- 경로: {A['base'][0]}.12 {A['base'][2]:.1f}% → 2027.12 {A['target']:.0f}% ({A['src']}), 월 직선"]
    if A["need"] and A["need"] > 0:
        out.append(f"- 경로를 맞추려면 TTM B2C+B2S **+{A['need']:,.1f}억** 필요(B2G 금액 {c[3]:,.1f}억 유지 가정, 현재 B2C+B2S {c[4]:,.1f}억)")
    out += ["", "| 월 | TTM B2G | 경로 | 차이 |", "|---|---|---|---|"]
    for t in A["T"][-12:]:
        p = A["at"](t[0], t[1])
        out.append(f"| {t[0]}.{t[1]}{' (예상)' if t[5] else ''} | {t[2]:.1f}% | {'' if p is None else f'{p:.1f}%'} | {'' if p is None else f'{t[2] - p:+.1f}'} |")
    return out + [""]
