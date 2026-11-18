#!/usr/bin/env python3
"""관리 탭 공용 차트(HTML/CSS 막대 - 화면 폭에 맞춰 줄고, 다크 모드는 대시보드 변수 그대로).

- 색은 고정 순서 범주 팔레트(entity 를 따라감, 순위로 바꾸지 않음). 글자는 본문 색, 색은 막대에만.
- 막대마다 title(마우스 올리면 값). 2계열 이상이면 범례를 항상 붙인다.
- 모든 글자는 이스케이프.
"""
import html

E = html.escape
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#8a8a85"]
CO = {"비바샘연수원": PAL[0], "비바샘": PAL[0], "아이스크림": PAL[1], "티처빌": PAL[2]}
CSS = """<style>
.vz{font-size:12.5px;}
.vz-row{display:grid;grid-template-columns:minmax(80px,150px) 1fr minmax(48px,auto);gap:8px;align-items:center;margin:5px 0;}
.vz-lab{color:var(--ink-2,inherit);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.vz-trk{display:flex;gap:2px;height:14px;align-items:stretch;}
.vz-seg{border-radius:0 4px 4px 0;min-width:2px;}
.vz-trk .vz-seg + .vz-seg{border-radius:0;}.vz-trk .vz-seg:last-child{border-radius:0 4px 4px 0;}
.vz-val{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);}
.vz-leg{display:flex;flex-wrap:wrap;gap:4px 14px;margin:0 0 8px;color:var(--muted);font-size:12px;}
.vz-leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px;}
.vz-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 12px;}
.vz-tile{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-2,transparent);}
.vz-tile b{display:block;font-size:22px;font-variant-numeric:tabular-nums;}.vz-tile span{font-size:12px;color:var(--muted);}
.vz-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));gap:18px;}
.vz-h{font-size:13px;font-weight:700;margin:4px 0 8px;}
.vz-cols{display:flex;align-items:flex-end;gap:4px;height:120px;border-bottom:1px solid var(--border);padding-top:14px;}
.vz-col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;min-width:0;height:100%;}
.vz-col div{width:70%;max-width:26px;border-radius:4px 4px 0 0;min-height:2px;}
.vz-col small{font-size:10.5px;color:var(--muted);margin-top:2px;}
.vz-xl{display:flex;gap:4px;}.vz-xl span{flex:1;text-align:center;font-size:10.5px;color:var(--muted);overflow:visible;white-space:nowrap;min-width:0;}
</style>"""


def legend(items):
    return '<div class="vz-leg">' + "".join(f'<span><i style="background:{c}"></i>{E(n)}</span>' for n, c in items) + "</div>"


def hbars(rows, fmt=lambda v: f"{v:,.0f}", color=PAL[0], unit=""):
    """rows: [(라벨, 값) 또는 (라벨, 값, 색)] 한 계열 가로 막대"""
    if not rows:
        return ""
    mx = max(r[1] for r in rows) or 1
    out = []
    for r in rows:
        lab, v = r[0], r[1]
        col = r[2] if len(r) > 2 else color
        out.append(f'<div class="vz-row"><span class="vz-lab" title="{E(str(lab))}">{E(str(lab))}</span>'
                   f'<div class="vz-trk"><div class="vz-seg" style="width:{max(v, 0) / mx * 100:.1f}%;background:{col}" title="{E(str(lab))}: {E(fmt(v))}{E(unit)}"></div></div>'
                   f'<span class="vz-val">{E(fmt(v))}{E(unit)}</span></div>')
    return '<div class="vz">' + "".join(out) + "</div>"


def stacked(rows, series, pct=False):
    """rows: [(라벨, {계열: 값})], series: [(계열, 색)] — 가로 누적 막대 + 범례"""
    if not rows:
        return ""
    tot = {lab: sum(d.get(s, 0) for s, _ in series) for lab, d in rows}
    mx = max(tot.values()) or 1
    out = [legend(series)]
    for lab, d in rows:
        t = tot[lab] or 1
        base = t if pct else mx
        segs = "".join(f'<div class="vz-seg" style="width:{d.get(s, 0) / base * 100:.1f}%;background:{c}" title="{E(lab)} · {E(s)}: {d.get(s, 0):,}{f" ({d.get(s, 0) / t * 100:.0f}%)" if pct else ""}"></div>'
                       for s, c in series if d.get(s, 0))
        out.append(f'<div class="vz-row"><span class="vz-lab">{E(lab)}</span><div class="vz-trk">{segs}</div><span class="vz-val">{tot[lab]:,}</span></div>')
    return '<div class="vz">' + "".join(out) + "</div>"


def cols(points, color=PAL[0], fmt=lambda v: f"{v:,.0f}"):
    """points: [(x라벨, 값)] 세로 막대(시간 흐름)"""
    if not points:
        return ""
    mx = max(v for _, v in points) or 1
    show = len(points) <= 12  # 막대가 많으면 숫자는 마우스 올릴 때만(선택적 라벨)
    bars = "".join(f'<div class="vz-col" title="{E(x)}: {E(fmt(v))}"><small>{E(fmt(v)) if v and show else ""}</small><div style="height:{v / mx * 85:.0f}%;background:{color}"></div></div>' for x, v in points)
    step = 1 if len(points) <= 12 else 3
    xl = "".join(f"<span>{E(x) if i % step == 0 else ''}</span>" for i, (x, _) in enumerate(points))
    return f'<div class="vz"><div class="vz-cols">{bars}</div><div class="vz-xl">{xl}</div></div>'


def tiles(items):
    """items: [(큰 값, 설명)]"""
    return '<div class="vz-tiles">' + "".join(f'<div class="vz-tile"><b>{E(str(v))}</b><span>{E(d)}</span></div>' for v, d in items) + "</div>"


def grid(*blocks):
    return '<div class="vz-grid">' + "".join(f'<div><p class="vz-h">{E(t)}</p>{b}</div>' for t, b in blocks if b) + "</div>"
