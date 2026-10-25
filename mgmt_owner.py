#!/usr/bin/env python3
"""
관리 탭 대표 전용 '경영 실적' 화면 - 손익 추이 · 월별 계절성 · 수강 기반(이수자) · 목표 대비 진척 · 3사 비교 · 연수 정산 현황.

- 실적 수치: GitHub Secret MGMT_JSON(경영실적·이수자 명단의 연도별 합계, 개인 정보 없음)에서만 읽는다.
  로컬 시험은 mgmt.local.json(gitignore). 없으면 해당 칸은 '미등록'으로 두고 나머지는 그대로 그린다.
- 결과 HTML 은 admin_structure.build_html 에 붙어 ADMIN_PASSWORD 로 암호화된다. history/·live/·브리핑(공개)에는 쓰지 않는다.
- 정산 현황은 운영DT(own_pipeline_export.py 가 화이트리스트로 거른 결과: 기관·연수명·날짜·금액)만 쓴다.
"""
import html
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from plan2027 import legend, so_line, stack_svg, table, tile, tiles

HERE = Path(__file__).parent
E = html.escape
# 2027 경영계획(2026.10.25) 공식 기준: B2G = 교육청 단체 + 위탁 용역
CH = [("b2c", "개인·학교(B2C·B2S)", "#10b981"), ("b2s", "교육청 단체(B2G)", "#4f8cff"), ("b2g", "위탁 용역(B2G)", "#f59e0b")]
DEF = "B2G = 교육청 단체(온라인 단체수강) + 위탁(오프라인 용역) · B2C+B2S = 개인(학교 단체구매 포함) + 제품·상품·기타 — 2027 경영계획(2026.10.25) 공식 기준"


def g_share(r):
    """B2G 비중(%) = (교육청 단체 + 위탁) ÷ 총매출"""
    return (r["b2s"] + r["b2g"]) / r["tot"] * 100 if r.get("tot") else 0
CO = {"비바샘": "var(--accent)", "티처빌": "#f59e0b", "아이스크림": "#ec4899", "한국교원": "#94a3b8"}
NOMG = '<p class="tt-note">실적 미등록: GitHub Secret <code>MGMT_JSON</code> 에 실적 합계 JSON 을 넣으면 채워집니다.</p>'


def load():
    raw = os.environ.get("MGMT_JSON", "").strip()
    if not raw and (HERE / "mgmt.local.json").exists():
        raw = (HERE / "mgmt.local.json").read_text(encoding="utf-8")
    try:
        m = json.loads(raw) if raw else None
        return m if isinstance(m, dict) and m.get("years") else None
    except Exception:
        print("[경고] MGMT_JSON 형식 오류 - 경영 실적 칸은 비웁니다")
        return None


def eok(v, d=2):
    return "-" if v is None else f"{v:,.{d}f}억"


def pct(a, b):
    return f"{(a / b - 1) * 100:+.0f}%" if a is not None and b else "-"


def bars_svg(groups, labels, colors, unit="억", w=760, h=220, fmt=lambda v: f"{v:,.1f}"):
    """묶은 막대(음수 허용). groups: {이름: [값..]}, labels: x축"""
    names = list(groups)
    vals = [v for g in groups.values() for v in g if v is not None]
    hi, lo = max(vals + [0]), min(vals + [0])
    span = (hi - lo) or 1
    pl, pb, pt = 48, 24, 10
    cw = (w - pl - 8) / len(labels)
    bw = cw * 0.78 / len(names)
    y = lambda v: pt + (hi - v) / span * (h - pb - pt)
    out = [f'<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;font-size:11px;" role="img">']
    for t in sorted({hi, 0, lo}):
        sw = ' stroke-width="1.5"' if t == 0 else ""
        out.append(f'<line x1="{pl}" x2="{w - 8}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="var(--border)"{sw}/>'
                   f'<text x="{pl - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="var(--muted)">{fmt(t)}{unit}</text>')
    for i, lab in enumerate(labels):
        x0 = pl + i * cw + cw * 0.11
        for j, n in enumerate(names):
            v = groups[n][i]
            if v is None:
                continue
            top, bot = y(max(v, 0)), y(min(v, 0))
            out.append(f'<rect x="{x0 + j * bw:.1f}" y="{top:.1f}" width="{bw * 0.9:.1f}" height="{max(bot - top, 1):.1f}" rx="2" fill="{colors[n]}">'
                       f'<title>{E(str(lab))} {E(n)} {fmt(v)}{unit}</title></rect>')
        out.append(f'<text x="{pl + i * cw + cw / 2:.1f}" y="{h - 6}" text-anchor="middle" fill="var(--muted)">{E(str(lab))}</text>')
    out.append("</svg>")
    return "".join(out)


def hbar(rows, w=360, unit="", color="var(--accent)"):
    """가로 막대 목록 [(이름, 값, 색|None, 꼬리말)]"""
    mx = max([abs(r[1]) for r in rows] + [1])
    return "".join(
        f'<div style="display:grid;grid-template-columns:96px 1fr 120px;gap:8px;align-items:center;margin:4px 0;font-size:12.5px;">'
        f'<span style="font-weight:700;">{E(n)}</span><span style="background:var(--surface-2);border-radius:4px;height:14px;">'
        f'<i style="display:block;height:14px;border-radius:4px;width:{abs(v) / mx * 100:.1f}%;background:{c or color};"></i></span>'
        f'<span class="num" style="text-align:right;">{E(tail or f"{v:,}{unit}")}</span></div>' for n, v, c, tail in rows)


def heat(M):
    """연도 × 월 매출 히트맵(위탁 포함 전체). 2026년 예상 달은 점선 테두리"""
    rows = [r for r in M["years"] if r.get("m")]
    fc = int((M.get("fc_from") or {}).get("2026", 13))
    allv = [sum(r["m"][c][i] for c in ("b2c", "b2s", "b2g")) for r in rows for i in range(12)]
    mx = max(allv + [0.01])
    th = "".join(f"<th class='num' style='padding:4px;'>{m}월</th>" for m in range(1, 13))
    body = ""
    for r in rows:
        cells = ""
        for i in range(12):
            v = sum(r["m"][c][i] for c in ("b2c", "b2s", "b2g"))
            g = r["m"]["b2g"][i]
            est = r["y"] == 2026 and i + 1 >= fc
            cells += (f"<td class='num' title='{r['y']}년 {i + 1}월 {v:.2f}억 (위탁 {g:.2f}억){' · 예상' if est else ''}' "
                      f"style='padding:5px 3px;font-size:11px;background:color-mix(in srgb, var(--accent) {v / mx * 85:.0f}%, transparent);"
                      f"{'outline:1.5px dashed var(--muted);outline-offset:-3px;' if est else ''}{'font-weight:800;' if g > 0.5 else ''}'>{v:.1f}</td>")
        body += f"<tr><td style='font-weight:700;'>{r['y']}{'E' if r['y'] == 2026 else ''}</td>{cells}</tr>"
    return f"<div class='tbl-wrap'><table><thead><tr><th></th>{th}</tr></thead><tbody>{body}</tbody></table></div>"


# ---------------------------------------------------------------- 경영 종합 칸
def s_kpi(M):
    Y = {r["y"]: r for r in M["years"]}
    c, p = Y.get(2026), Y.get(2025)
    fc = int((M.get("fc_from") or {}).get("2026", 13))
    ytd = sum(sum(c["m"][k][:fc - 1]) for k in ("b2c", "b2s", "b2g")) if c and c.get("m") else None
    L = {r["y"]: r for r in M.get("learn") or []}
    ly = max(L) if L else None
    b2g_sh = g_share(c) if c else 0
    tgt = ((M.get("plan27") or {}).get("path") or {}).get("target") or []
    t27 = tgt[2] if len(tgt) > 2 and tgt[2] else M["target"]["b2g"]
    ts = [tile("2026 매출(예상)", eok(c["tot"]), f"전년 {eok(p['tot'])} 대비 {pct(c['tot'], p['tot'])}", c["tot"] < p["tot"]),
          tile("영업이익(공통비 배분 전)", eok(c["op"]), f"배분 후 {eok(c.get('op_after'))} · 전년 {eok(p['op'])}", c["op"] < 0),
          tile(f"1~{fc - 1}월 실적", eok(ytd), f"연간 예상의 {ytd / c['tot'] * 100:.0f}% · 남은 {13 - fc}개월 {eok(c['tot'] - ytd)} 필요" if ytd else "", bool(ytd and ytd / c["tot"] < 0.6)),
          tile("B2G 비중(단체+위탁)", f"{b2g_sh:.0f}%", f"2027 계획 {t27}% · 2030 목표 {M['target']['b2g']}%", b2g_sh > t27)]
    if ly:
        f0 = L[min(L)]
        ts.append(tile(f"이수 교사({ly})", f"{L[ly]['u']:,}명", f"{min(L)}년 {f0['u']:,}명 대비 {pct(L[ly]['u'], f0['u'])}", True))
    return tiles(ts)


def s_pl(M):
    ys = M["years"]
    labs = [f"{r['y']}{'E' if r['y'] == 2026 else ''}" for r in ys]
    svg = stack_svg([(n, col, [r[k] * 1e8 for r in ys]) for k, n, col in CH], labs, neg=[r["op"] * 1e8 for r in ys])
    rows = [[f"<b>{lab}</b>", eok(r["tot"]), eok(r["b2c"]), eok(r["b2s"]), eok(r["b2g"]),
             f"<span style='color:{'#ef4444' if r['op'] < 0 else '#10b981'};font-weight:700;'>{eok(r['op'])}</span>", eok(r.get("op_after")),
             f"{r['tot'] / r['plan_tot'] * 100:.0f}%" if r.get("plan_tot") else "-"] for lab, r in zip(labs, ys)]
    best = max(ys, key=lambda r: r["op"])
    on = [r["b2c"] + r["b2s"] for r in ys]
    return (legend([(n, c) for _, n, c in CH] + [("영업이익(배분 전)", "#ef4444")]) + svg
            + table(["연도", "매출", "개인", "단체", "위탁", "영업이익(배분 전)", "배분 후", "계획 달성"], rows, (1, 2, 3, 4, 5, 6, 7))
            + so_line(f"흑자는 위탁이 {eok(best['b2g'])}였던 {best['y']}년 한 해뿐입니다. 온라인(개인+단체) 매출은 {ys[0]['y']}년 {eok(on[0])} → {ys[-1]['y']}년 예상 {eok(on[-1])}로 "
                      f"{pct(on[-1], on[0])} 줄었습니다. 위탁이 빠지면 적자가 다시 커지는 구조라, 고정비(판관비 {eok(ys[-1]['sga'])})를 받칠 온라인 매출 회복이 1순위입니다."))


def s_season(M):
    out = []
    for r in M["years"]:
        if not r.get("m"):
            continue
        t = [sum(r["m"][c][i] for c in ("b2c", "b2s", "b2g")) for i in range(12)]
        o = [r["m"]["b2c"][i] + r["m"]["b2s"][i] for i in range(12)]
        h1, h2, o1, o2 = sum(t[:8]), sum(t[8:]), sum(o[:8]), sum(o[8:])
        out.append((r["y"], h1 / (h1 + h2) * 100 if h1 + h2 else 0, o1 / (o1 + o2) * 100 if o1 + o2 else 0,
                    (o2 / 4) / (o1 / 8) * 100 - 100 if o1 else 0))
    rows = [[f"<b>{y}{'E' if y == 2026 else ''}</b>", f"{a:.0f}% / {100 - a:.0f}%", f"{b:.0f}% / {100 - b:.0f}%", f"{u:+.0f}%"] for y, a, b, u in out]
    return (heat(M) + "<p class='tt-note'>칸 숫자 = 그달 매출(억, 위탁 포함). 굵은 숫자 = 위탁 0.5억 이상 잡힌 달. 점선 = 2026년 예상치(10~12월).</p>"
            + table(["연도", "1~8월 / 9~12월 (전체)", "1~8월 / 9~12월 (개인+단체)", "9~12월 월평균 증가(개인+단체)"], rows, (1, 2, 3))
            + so_line("위탁 매출은 사업이 끝나는 달에 한꺼번에 잡혀 해마다 몰리는 달이 다릅니다. 온라인 매출만 보면 9~12월이 1~8월보다 월평균 크게 높으므로, "
                      "광고·단체 제안은 8월 말까지 준비를 끝내고 9~11월에 집중하는 것이 맞습니다."))


def s_learn(M):
    L = M.get("learn") or []
    if not L:
        return "<p class='tt-note'>이수자 합계가 없습니다.</p>"
    labs = [str(r["y"]) for r in L]
    svg = stack_svg([("교육청 단체", "#4f8cff", [r["gov"] * 1e8 / 1e4 for r in L]), ("학교 단체", "#8b5cf6", [r["sch"] * 1e8 / 1e4 for r in L]),
                     ("개인", "#10b981", [r["ind"] * 1e8 / 1e4 for r in L])], labs).replace("억", "만 건")
    rows = [[f"<b>{r['y']}</b>", f"{r['n']:,}", f"{r['u']:,}", f"{r['n'] / r['u']:.2f}", f"{r['ret'] * 100:.1f}%" if r.get("ret") else "-",
             f"{r['gov'] / r['n'] * 100:.0f}%", f"{r['ind']:,}"] for r in L]
    last = L[-1]
    lv = last.get("lvl") or {}
    tot = sum(lv.values()) or 1
    lvl = hbar([(k, v, None, f"{v:,}명 · {v / tot * 100:.0f}%") for k, v in sorted(lv.items(), key=lambda x: -x[1]) if v]) if lv else ""
    return (legend([("교육청 단체", "#4f8cff"), ("학교 단체", "#8b5cf6"), ("개인(정기·상시)", "#10b981")]) + svg
            + table(["연도", "이수 건수", "이수 교사(명)", "1인당 과정", "재수강률(최소치)", "교육청 단체 비중", "개인 이수"], rows, (1, 2, 3, 4, 5, 6))
            + (f"<p style='font-weight:800;margin:12px 0 4px;'>{last['y']}년 학교급 구성(이수 건수)</p>{lvl}" if lvl else "")
            + "<p class='tt-note'>이수자 명단 합계(개인 정보 미사용). 교사 수는 '가린 이름+출생 연대+학교명'으로 같은 사람을 묶은 추정치이고, 학교를 옮긴 교사는 다른 사람으로 세어져 재수강률은 실제보다 낮게 나옵니다. 미이수 신청은 명단에 없습니다.</p>"
            + so_line(f"이수의 {last['gov'] / last['n'] * 100:.0f}%가 교육청 단체연수라, 교육청 예산이 줄면 수강 기반도 같이 줄어듭니다. "
                      f"개인 이수는 {last['ind']:,}건으로 버티고 있으니, 단체연수로 처음 만난 교사를 개인 결제로 다시 부르는 재수강 프로그램(이수 직후 다음 과정 제안)이 가장 싼 성장 수단입니다."))


def s_target(M):
    """B2G 비중(단체+위탁) 실적 → '27 계획 → 2030 목표 경로(+엑셀 5개년 경로)"""
    t = M["target"]
    P = (M.get("plan27") or {}).get("path") or {}
    rows = [(f"{r['y']}{'E' if r['y'] == 2026 else ''}", g_share(r), r["b2g"] / r["tot"] * 100 if r["tot"] else 0, False) for r in M["years"] if r["y"] >= 2022]
    for y, a, x in zip(P.get("years", []), P.get("target", []), P.get("excel", [])):
        if y >= 2027 and a is not None:
            rows.append((f"{y}{'' if y == 2027 else 'E'}", a, x, True))
    bar = lambda lab, g, sub, plan: (f'<div style="display:grid;grid-template-columns:56px 1fr 210px;gap:8px;align-items:center;margin:5px 0;font-size:12.5px;">'
                                     f'<b>{lab}</b><span style="position:relative;display:flex;height:18px;border-radius:4px;overflow:hidden;background:var(--surface-2);{"opacity:.7;" if plan else ""}">'
                                     f'<i style="width:{100 - g:.1f}%;background:#10b981;{"background-image:repeating-linear-gradient(45deg,transparent 0 4px,rgba(255,255,255,.35) 4px 7px);" if plan else ""}"></i>'
                                     f'<i style="width:{g:.1f}%;background:#4f8cff;{"background-image:repeating-linear-gradient(45deg,transparent 0 4px,rgba(255,255,255,.35) 4px 7px);" if plan else ""}"></i>'
                                     f'<i style="position:absolute;left:{100 - t["b2g"]}%;top:-2px;bottom:-2px;border-left:2px dashed var(--ink);"></i></span>'
                                     f'<span class="num">B2G {g:.0f}% · {("엑셀 5개년 " + str(sub) + "%") if plan else f"위탁만 {sub:.0f}%"}</span></div>')
    c = M["years"][-1]
    lev = (M.get("plan27") or {}).get("levers2030") or []
    lv = table(["성장 레버", "'27 계획", "2030", "핵심 수단"], [[E(a), eok(b), eok(c_), E(d)] for a, b, c_, d in lev], (1, 2)) if lev else ""
    l27, l30 = sum(x[1] for x in lev), sum(x[2] for x in lev)
    cagr = ((l30 / l27) ** (1 / 3) - 1) * 100 if l27 else 0
    return (legend([("B2C+B2S(개인·학교·상품·기타)", "#10b981"), ("B2G(교육청 단체+위탁)", "#4f8cff"), ("빗금 = 계획·목표 경로", "var(--muted)"), (f"2030 목표선 B2G {t['b2g']}%", "var(--ink)")])
            + "".join(bar(*r) for r in rows)
            + f"<p class='tt-note'>구분: {E(DEF)}. '27은 경영계획 확정치, '28~'30은 목표 경로(가정)이고 오른쪽 '엑셀 5개년'은 8.5개년계획 시트의 완만한 경로입니다.</p>"
            + (f"<p style='font-weight:800;margin:12px 0 4px;'>2030 B2G {t['b2g']}% 달성 레버 (B2C+B2S {eok(l27)} → {eok(l30)}, 연 {cagr:+.0f}%)</p>{lv}" if lv else "")
            + so_line(f"2026년 예상 B2G 비중은 {g_share(c):.0f}%입니다. '27 계획은 B2G 금액을 방어하고 B2C+B2S를 키워 비중을 낮추는 '희석' 전략이라, "
                      + (f"비중보다 'B2C+B2S 금액'('27 {eok(l27)} → '30 {eok(l30)})을 분기 KPI로 따로 보세요." if lev else "비중보다 'B2C+B2S 금액'을 분기 KPI로 따로 보세요.")))


def build_exec(sec, M=None):
    M = M if M is not None else load()
    if not M:
        return sec("경영 실적 (대표 전용)", "", NOMG)
    hd = f"기준: 경영실적 {E(M.get('asof') or '-')} · {E(M.get('learn_asof') or '')} · 단위 억 원(2026년 10~12월은 예상)"
    parts = [s_kpi(M)]
    for t, d, fn in [("① 손익 추이", "연도별 매출 구성(개인·단체·위탁)과 영업이익, 계획 달성률", s_pl),
                     ("② 월별 매출 · 계절성", "연도 × 월 매출 지도와 상·하반기 비중", s_season),
                     ("③ 수강 기반(이수자)", "연수 유형별 이수 건수, 실제 교사 수, 재수강률, 학교급", s_learn),
                     ("④ 목표 대비 진척", f"{M['target']['y']} 목표 B2G {M['target']['b2g']} : B2C+B2S {M['target']['b2cs']} 대비 연도별 비중", s_target)]:
        try:
            parts.append(f"<h4>{t}</h4><p class='tt-note' style='margin-top:-4px;'>{d}</p>" + fn(M))
        except Exception as e:  # 한 칸 오류가 경영 종합 전체를 막지 않게
            parts.append(f"<h4>{t}</h4><p class='tt-note'>이 칸을 만들지 못했습니다: {E(type(e).__name__)}</p>")
            print(f"[경고] mgmt {t}: {type(e).__name__}: {str(e)[:120]}")
    return sec("경영 실적 (대표 전용)", hd, "".join(parts))


# ---------------------------------------------------------------- 경쟁사 변화 칸: 3사 비교
def build_comp3(sec, M=None):
    M = M if M is not None else load()
    C = (M or {}).get("comp3")
    if not C:
        return sec("주요 3사 비교 (대표 전용)", "", NOMG)
    ys = C["years"]
    rev = bars_svg(C["rev"], ys, CO)
    op = bars_svg(C["op"], ys, CO)
    b = C["b2g_same"]
    b2g = bars_svg({k: b[k] for k in ("티처빌", "아이스크림", "한국교원")}, b["years"], CO, unit="건", h=180, fmt=lambda v: f"{v:,.0f}")
    sh, ca = C["share12"], C["catalog"]
    side = (f"<p style='font-weight:800;margin:0 0 4px;'>{E(sh['label'])}</p>" + hbar([(k, v, CO.get(k), f"{v}%") for k, v in sh.items() if k != "label"])
            + f"<p style='font-weight:800;margin:12px 0 4px;'>{E(ca['label'])}</p>" + hbar([(k, v, CO.get(k), f"{v:,}개") for k, v in ca.items() if k != "label"]))
    last = {k: v[-1] for k, v in C["rev"].items()}
    opl = {k: v[-1] for k, v in C["op"].items()}
    grid = lambda a, b_: f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;'><div>{a}</div><div>{b_}</div></div>"
    body = (legend([(k, CO[k]) for k in C["rev"]])
            + grid(f"<p style='font-weight:800;margin:0;'>연수원 매출(억)</p>{rev}", f"<p style='font-weight:800;margin:0;'>영업이익(억)</p>{op}")
            + grid(f"<p style='font-weight:800;margin:0;'>{E(b['label'])}</p>{b2g}", side)
            + f"<p class='tt-note'>출처: {E(C.get('src') or '')}. 경쟁사 손익은 법인 공시 인용이라 연수원 단독 손익과 다를 수 있습니다.</p>"
            + so_line(f"{ys[-1]}년 3사 모두 영업이익이 적자로 돌아섰습니다(티처빌 {opl['티처빌']:+.0f}억 · 아이스크림 {opl['아이스크림']:+.0f}억 · 한국교원 {opl['한국교원']:+.1f}억). "
                      f"매출 규모는 당사가 티처빌의 {last['비바샘'] / last['티처빌'] * 100:.0f}%, 과정 수는 {ca['비바샘'] / ca['티처빌'] * 100:.0f}% 수준입니다. "
                      "업계 전체가 위탁·할인 경쟁으로 이익을 잃는 국면이라, 가격보다 교과 연계·학교 단위 성과 보고로 차별화하는 쪽이 이익을 지키는 길입니다."))
    return sec("주요 3사 비교 (대표 전용)", "매출·영업이익 4개년, 같은 기간 공공 수주 건수, 공공 계약 점유율, 공개 과정 수", body)


# ---------------------------------------------------------------- 이번 주 할 일 칸: 교육청 연수 종료·정산
# 루틴앱 '교육청 연수 종료·정산' 카드와 같은 원본(사업현황공유 › 26운영DT)·같은 단계.
# 늦음 기준 = 올해 그 단계를 마친 건들의 실제 소요일 75% 지점(5건 미만이면 기본값).
STAGES = [("run", "진행 중"), ("notice", "이수통보"), ("report", "결과보고"), ("bill", "계산서"), ("pay", "수금"), ("done", "완료")]
LIM_DEFAULT = {"notice": 14, "report": 30, "bill": 21, "pay": 30}


def _d(s):
    m = re.search(r"(20\d\d)\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})", str(s or ""))
    try:
        return date(int(m[1]), int(m[2]), int(m[3])) if m else None
    except ValueError:
        return None


def _won(s):
    t = re.sub(r"[^\d]", "", str(s or ""))
    return int(t) if t else 0


def _p75(xs):
    if len(xs) < 5:
        return None
    s = sorted(xs)
    return max(0, s[min(len(s) - 1, -(-len(s) * 3 // 4) - 1)])


def settle_units(recs, today=None):
    today = today or date.today()
    out, lags = [], {k: [] for k in LIM_DEFAULT}
    for r in recs:
        org = str(r.get("org") or "").strip()
        end = _d(r.get("trainEnd"))
        if not org or not end:
            continue
        rep_raw = str(r.get("reportDate") or "").strip()
        rp, bl, py = _d(rep_raw), _d(r.get("billDate")), _d(r.get("payDate"))
        nt = bool(str(r.get("notice") or "").strip())
        merged = bool(re.search(r"합산|집합|^x$|^-$", rep_raw, re.I))
        if rp and rp >= end:
            lags["report"].append((rp - end).days)
        if rp and bl and bl >= rp:
            lags["bill"].append((bl - rp).days)
        if bl and py and py >= bl:
            lags["pay"].append((py - bl).days)
        if end > today:
            st, since = "run", None
        elif py or (merged and bl):
            st, since = "done", None
        elif not nt and not rp:
            st, since = "notice", end
        elif not rp and not merged:
            st, since = "report", end
        elif not bl:
            st, since = "bill", rp or end
        else:
            st, since = "pay", bl
        out.append({"org": org, "course": str(r.get("courseName") or "").strip(), "region": str(r.get("region") or "").strip(),
                    "end": end, "st": st, "since": since, "amt": _won(r.get("claimAmount")) or _won(r.get("targetAmount")),
                    "g2b": "나라장터" in str(r.get("contractProgress") or ""), "status": str(r.get("status") or "")})
    lim = {k: (_p75(v) if _p75(v) is not None else LIM_DEFAULT[k]) for k, v in lags.items()}
    lim["notice"] = LIM_DEFAULT["notice"]
    for u in out:
        u["wait"] = max(0, (today - u["since"]).days) if u["since"] else None
        u["late"] = u["st"] in lim and u["wait"] is not None and u["wait"] > lim[u["st"]]
    return out, lim, {k: len(v) for k, v in lags.items()}


def build_settle(sec, pipe=None, today=None):
    if pipe is None:
        try:
            pipe = json.loads((HERE / "live/own_pipeline_export.json").read_text(encoding="utf-8"))
        except Exception:
            pipe = {}
    recs = (pipe or {}).get("records") or []
    title, src = "교육청 연수 종료·정산", "사업현황공유 › 26운영DT (루틴앱 '교육청 연수 종료·정산' 카드와 같은 원본)"
    if not recs or not any(r.get("reportDate") or r.get("billDate") or r.get("payDate") or r.get("notice") for r in recs):
        return sec(title, src, "<p class='tt-note'>운영DT의 정산 열(이수통보·결과보고·계산서발행·수금전표)이 아직 들어오지 않았습니다. 다음 자동 배포 후 채워집니다.</p>")
    today = today or date.today()
    units, lim, n = settle_units(recs, today)
    won = lambda v: f"{v / 1e8:,.2f}억" if v >= 1e7 else f"{v / 1e4:,.0f}만원"
    cnt = Counter(u["st"] for u in units)
    amt = defaultdict(int)
    for u in units:
        amt[u["st"]] += u["amt"]
    late = Counter(u["st"] for u in units if u["late"])
    flow = '<span style="color:var(--muted);align-self:center;">→</span>'.join(
        f'<div style="flex:1;min-width:104px;padding:8px 10px;border-radius:8px;border:1px solid {"#ef4444" if late.get(k) else "var(--border)"};background:var(--surface-2);">'
        f'<div style="font-size:11.5px;color:var(--muted);">{E(lab)}{" 대기" if k not in ("run", "done") else ""}</div>'
        f'<div class="num" style="font-size:20px;font-weight:800;">{cnt.get(k, 0):,}건</div>'
        f'<div class="num" style="font-size:11.5px;color:{"#ef4444" if late.get(k) else "var(--muted)"};">{won(amt[k])}{f" · 늦음 {late[k]}" if late.get(k) else ""}</div></div>'
        for k, lab in STAGES)
    lab = dict(STAGES)
    todo = sorted([u for u in units if u["st"] not in ("run", "done")], key=lambda u: (not u["late"], -(u["wait"] or 0)))
    rows = [[f"<b style='color:{'#ef4444' if u['late'] else 'var(--ink-2)'};'>{E(lab[u['st']])} 대기</b>" + (" <span class='fit fit-불가'>나라장터</span>" if u["g2b"] else ""),
             E(u["region"]), E(u["org"][:24]), E(u["course"][:40]), u["end"].strftime("%m.%d"),
             f"<b style='color:#ef4444;'>{u['wait']}일</b>" if u["late"] else f"{u['wait']}일", won(u["amt"]) if u["amt"] else "-"] for u in todo[:20]]
    unpaid = sum(amt[k] for k in ("notice", "report", "bill", "pay"))
    late_amt = sum(u["amt"] for u in units if u["late"])
    limtxt = " · ".join(f"{lab[k]} {lim[k]}일" + ("" if n.get(k, 0) >= 5 or k == "notice" else "(기본값)") for k in ("notice", "report", "bill", "pay"))
    wk = [u for u in units if u["st"] == "run" and (u["end"] - today).days <= 7]
    body = (f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 10px;'>{flow}</div>"
            + table(["단계", "지역", "기관", "연수명", "종료", "대기", "금액"], rows, (5, 6))
            + (f"<p class='tt-note'>대기 {len(todo)}건 중 20건만 표시(늦은 건·오래 기다린 건 순).</p>" if len(todo) > 20 else "")
            + (f"<p style='margin:10px 0 0;font-size:13px;'>이번 주 끝나는 연수 <b>{len(wk)}건</b>: " + ", ".join(E(f"{u['org'][:14]} {u['end']:%m.%d}") for u in wk[:8]) + "</p>" if wk else "")
            + f"<p class='tt-note'>늦음 기준(올해 그 단계를 마친 건의 소요일 75% 지점): {limtxt}. 대기일 = 앞 단계가 끝난 날부터 오늘까지. "
              "금액은 청구금액, 없으면 총예산. 다기수 묶음 정산은 루틴앱 카드에서 기수별로 확인하세요.</p>"
            + so_line(f"정산이 남은 금액은 {won(unpaid)}이고, 그중 기준보다 늦은 건이 {sum(late.values())}건 {won(late_amt)}입니다. "
                      "결과보고가 밀리면 계산서·수금과 매출 인식 달이 함께 밀리므로, 붉은 칸(늦음)부터 담당자와 이번 주 처리일을 정하세요."))
    return sec(title, f"{src} · 조회 {E(str((pipe.get('source') or {}).get('fetched') or '-'))}", body)


# ---------------------------------------------------------------- 2027 경영계획 확정안(2026.10.25) — 2027 경영계획 칸 맨 위
def _hist(name):
    p = HERE / "history" / name
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def build_plan27(sec, M=None):
    M = M if M is not None else load()
    P = (M or {}).get("plan27")
    if not P:
        return sec("2027 경영계획 확정안", "", NOMG)
    ch = P["channels"]
    p_t, v_t = sum(c["p"] for c in ch), sum(c["v"] for c in ch)
    p_off = next((r["tot"] for r in M.get("years", []) if r["y"] == 2026), None)  # '26E 공식 합계(항목 반올림 합과 0.02억 차이)
    g_p, g_v = sum(c["p"] for c in ch if c["b2g"]), sum(c["v"] for c in ch if c["b2g"])
    dev = P.get("dev") or []
    head = tiles([tile("2027 연수 매출 계획", eok(v_t), f"'26E {eok(p_off or p_t)} 대비 {pct(v_t, p_off or p_t)}"),
                  tile("B2G 비중(단체+위탁)", f"{g_v / v_t * 100:.0f}%", f"'26E {g_p / p_t * 100:.0f}% → 2030 목표 {M['target']['b2g']}%"),
                  tile("인건비 전 기여이익", eok(P["cost"]["contrib_v"]), f"'26E {eok(P['cost']['contrib_p'])} · 직접·변동비 {eok(sum(P['cost']['v']))}"),
                  tile("2027 개발", f"{len(dev)}과정 · {P.get('dev_total', 0):.1f}억", "자체·샘크 30 + 제휴·CP 7"),
                  tile("5개년 매출", f"{P['five']['rev'][-1]:.1f}억('31)", f"영업이익 {P['five']['op'][0]:+.1f} → {P['five']['op'][-1]:+.1f}억")])
    rows = [[E(c["k"]), c["cell"], "B2G" if c["b2g"] else "B2C·B2S", eok(c["p"]), eok(c["v"]), pct(c["v"], c["p"]) if c["p"] else "-"] for c in ch]
    rows.append(["<b>합계</b>", "", "", f"<b>{eok(p_off or p_t)}</b>", f"<b>{eok(v_t)}</b>", pct(v_t, p_off or p_t)])
    mo = P.get("monthly") or {}
    mon = [f"{i + 1}월" for i in range(12)]
    chart = stack_svg([("개인·학교", "#10b981", [v * 1e8 for v in mo.get("ind", [0] * 12)]), ("연수원 몰 상품", "#8b5cf6", [v * 1e8 for v in mo.get("mall", [0] * 12)]),
                       ("제품·기타", "#94a3b8", [v * 1e8 for v in mo.get("etc", [0] * 12)]), ("교육청 단체", "#4f8cff", [v * 1e8 for v in mo.get("grp", [0] * 12)]),
                       ("위탁 용역", "#f59e0b", [v * 1e8 for v in mo.get("svc", [0] * 12)])], mon, h=200)
    h2 = sum(sum(mo.get(k, [0] * 12)[6:]) for k in ("grp", "svc")) / max(sum(sum(mo.get(k, [0] * 12)) for k in ("grp", "svc")), 0.01) * 100
    # KPI 판: 2026 기준값을 옆에 둔다(2027 실적은 1월부터 같은 칸에 쌓임)
    Y = {r["y"]: r for r in M.get("years", [])}
    c26 = Y.get(2026) or {}
    base = {"rev": eok(c26.get("tot")), "b2g_share": f"{g_share(c26):.0f}%" if c26 else "-", "grp": eok(c26.get("b2s")), "svc": eok(c26.get("b2g")),
            "ind": eok(c26.get("b2c")), "dev": "0 / 37 (1월 착수)"}
    kp = table(["셀", "KPI", "2027 목표", "산식·근거", "담당(역할)", "유형", "'26 기준값"],
               [[k[0], E(k[1]), f"<b>{E(k[2])}</b>", E(k[3]), E(k[4]), k[5], base.get(k[6], "1분기 첫 측정")] for k in P["kpis"]])
    cost = table(["비용 그룹", "'26E", "'27", "'27 매출 대비"], [[E(n), eok(a), eok(b), f"{b / v_t * 100:.1f}%"] for n, a, b in zip(P["cost"]["items"], P["cost"]["p"], P["cost"]["v"])], (1, 2, 3))
    road = "".join(f"<div style='flex:1;min-width:150px;padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface-2);'><b style='font-size:12.5px;'>{E(a)}</b>"
                   f"<div style='font-size:12px;color:var(--ink-2);margin-top:4px;line-height:1.5;'>{E(b)}</div></div>" for a, b in P["roadmap"])
    risk = table(["핵심 리스크", "영향", "대응"], [[E(a), E(b), E(c)] for a, b, c in P["risks"]])
    conf = "".join(f"<li>{E(x)}</li>" for x in P["confirmed"])
    svc = Counter(d[3] for d in dev if d[3] != "-")
    dv = table(["#", "구분", "과정(주제)", "착수", "서비스", "'27 신규 투입"], [[i + 1, E(d[0]), E(d[1]), d[2], d[3], f"{d[4]:.1f}백만" if d[4] else "-"] for i, d in enumerate(dev)], (5,))
    sched = " · ".join(f"{k[3:]}월 {v}" for k, v in sorted(svc.items()))
    body = (head + f"<p style='margin:0 0 10px;font-size:13.5px;'><b>{E(P['headline'])}</b></p>"
            + "<h4>① 채널별 매출 '26E → '27</h4>" + table(["항목", "셀", "구분", "'26E", "'27 계획", "증감"], rows, (3, 4, 5))
            + "<h4>② '27 월별 매출 계획(채널별)</h4>" + legend([("개인·학교", "#10b981"), ("연수원 몰 상품", "#8b5cf6"), ("제품·기타", "#94a3b8"), ("교육청 단체", "#4f8cff"), ("위탁 용역", "#f59e0b")]) + chart
            + f"<p class='tt-note'>B2G(단체+위탁) 매출의 {h2:.0f}%가 하반기(7~12월)에 몰립니다. 용역은 4·9·12월 인식, 단체 피크는 8월입니다.</p>"
            + "<h4>③ KPI 체계 (후행 → 선행 분해, 월간 관리)</h4>" + kp
            + "<p class='tt-note'>담당은 역할명만 표시합니다(실명 미저장). 기준값이 없는 전환율·이수 건수 지표는 1분기에 처음 측정해 기준값으로 삼습니다.</p>"
            + "<h4>④ 비용 구조 (인건비·공통비 배분 전)</h4>" + cost
            + "<h4>⑤ 실행 로드맵</h4><div style='display:flex;gap:8px;flex-wrap:wrap;'>" + road + "</div>"
            + "<h4>⑥ 핵심 리스크와 확정 사항</h4>" + risk + f"<ul style='margin:8px 0 0 18px;font-size:13px;line-height:1.7;'>{conf}</ul>"
            + f"<h4>⑦ 2027 개발 {len(dev)}과정 (월별 서비스 개시: {sched})</h4>"
            + f"<details><summary style='cursor:pointer;font-size:13px;'>과정 목록 펼치기</summary>{dv}</details>"
            + so_line(f"'27 계획의 성패는 상반기 선행 지표입니다. 1분기 신규 12과정 착수와 교육청 제안·계약 파이프라인이 늦으면 하반기 집중({h2:.0f}%) 구조상 연말에 만회하기 어렵습니다. "
                      "매월 KPI 판의 선행 지표(수주·샘스쿨·과정 출시)부터 확인하세요."))
    return sec("2027 경영계획 확정안 (대표 전용)", f"{E(P['src'])} · 작성 {E(P['asof'])}", body)


def build_longterm(sec, M=None):
    """2027·2030 중장기 사업관리 방향(2026.10.25 기준) — 자체 개선 아이디어의 기준점"""
    M = M if M is not None else load()
    P = (M or {}).get("plan27")
    if not P:
        return ""
    ph = "".join(f"<div style='flex:1;min-width:220px;padding:12px 14px;border:1px solid var(--border);border-radius:8px;'><b>{E(a)}</b>"
                 f"<div style='font-size:12.5px;color:var(--ink-2);margin-top:6px;line-height:1.6;'>{E(b)}</div></div>" for a, b in P["v2030"])
    pos = table(["포지션", "역할", "2027 씨앗"], [[f"<b>{E(a)}</b>", E(b), E(c)] for a, b, c in P["positions"]])
    dod = "".join(f"<li>{E(x)}</li>" for x in P["dod2028"])
    five = P["five"]
    ft = table(["", *[str(y) for y in five["years"]]], [["매출(억)", *[f"{v:.1f}" for v in five["rev"]]], ["영업이익(억, K-IFRS)", *[f"{v:+.1f}" for v in five["op"]]],
                                                       ["인원(명)", *[str(v) for v in five["heads"]]]], tuple(range(1, 6)))
    body = ("<div style='display:flex;gap:10px;flex-wrap:wrap;'>" + ph + "</div>"
            + f"<h4>2028 완성 기준(Definition of Done)</h4><ul style='margin:4px 0 0 18px;font-size:13px;line-height:1.7;'>{dod}</ul>"
            + "<h4>중장기 참고 방향 — 교사 성장 생태계 4포지션</h4>" + pos
            + "<p class='tt-note'>연수원은 '지식을 전달하는 기관'에서 '교사의 지식이 성장하고 확산되는 생태계'로: 교사 지식 → 콘텐츠 → 브랜드 → 새 연수·서비스·수익. 27 목표에는 미반영(참고 방향).</p>"
            + "<h4>5개년 재무 경로(엑셀 8.5개년계획)</h4>" + ft
            + so_line("대시보드 고도화도 이 방향에 맞춥니다: 2027은 '발굴'(수요·공백 스코어링, 협업 과정 성과), 2028은 '연결·시스템'(LMS 이수통보·교육청 매출 자동 산출, 1ID 이용 조회, 통합 대시보드 자동화)."))
    return sec("중장기 사업관리 방향 — V2030 (2026.10.25 기준)", "발굴 → 연결 → 시스템 · 2028 완성 · 2030 B2G 40 : B2C+B2S 60", body)


# ---------------------------------------------------------------- ② 시도별 예산 위험·기회 지도
def build_budget_map(sec, today=None):
    today = today or date.today()
    y1 = date(today.year - 1, today.month, min(today.day, 28)).isoformat()
    REG = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
    try:
        fin = json.loads((HERE / "history/eduinfo_finance.json").read_text(encoding="utf-8")).get("finance") or {}
    except Exception:
        fin = {}
    try:
        sch = json.loads((HERE / "history/schoolinfo_market.json").read_text(encoding="utf-8")).get("schools") or []
    except Exception:
        sch = []
    bids, plans, own, tot = Counter(), Counter(), Counter(), Counter()
    for r in _hist("training_bids.jsonl"):
        if (r.get("d") or "") >= y1:
            bids[r.get("r")] += r.get("a") or 0
    for r in _hist("order_plans.jsonl"):
        plans[r.get("r")] += r.get("a") or 0
    for r in _hist("competitor_contracts.jsonl"):
        if (r.get("date") or "") >= y1:
            tot[r.get("region")] += r.get("amount") or 0
            if r.get("competitor") == "비바샘연수원":
                own[r.get("region")] += r.get("amount") or 0
    teach = Counter()
    for s_ in sch:
        teach[s_.get("s")] += s_.get("t") or 0
    own_all = sum(own.values()) or 1
    dem_all = sum(bids[g] + plans[g] for g in REG) or 1
    rows = []
    for g in REG:
        f = fin.get(g) or {}
        ys = sorted(f)
        chg = (f[ys[-1]]["out"] / f[ys[-2]]["out"] - 1) * 100 if len(ys) >= 2 and f[ys[-2]].get("out") else None
        dem = (bids[g] + plans[g]) / dem_all
        shr = own[g] / tot[g] if tot[g] else 0
        dep = own[g] / own_all
        opp = dem * (1 - shr) * 100
        risk = dep * 100 * (1.5 if chg is not None and chg < 0 else 1.0)
        kind = ("방어" if dep >= 0.15 else "공략" if dem >= 0.06 and shr < 0.1 else "확대" if shr > 0 and dem >= 0.03 else "관망")
        rows.append((g, dem, shr, dep, chg, teach[g], opp, risk, kind))
    rows.sort(key=lambda r: -(r[6] + r[7]))
    KC = {"공략": "#1F5FD1", "방어": "#B91C1C", "확대": "#15803D", "관망": "var(--muted)"}
    ACT = {"공략": "수요 크고 자사 점유 낮음 → 11~2월 사전 영업, 맞춤형 차시·샘스쿨 제안", "방어": "자사 매출 의존 큼 → 재계약 시점 관리, 예산 축소 대비 '예산 효율형' 패키지",
           "확대": "이미 진입 → 지원청 단위로 횡전개, 학교단체 풀패키지 연결", "관망": "수요·관계 모두 작음 → 공고 모니터링만"}
    tb = table(["시도", "구분", "수요 비중(공고+발주계획)", "자사 점유(계약액)", "자사 매출 중 비중", "교육 세출 증감(최근 결산)", "교원 수", "권장 행동"],
               [[f"<b style='white-space:nowrap;'>{g}</b>", f"<b style='color:{KC[k]};white-space:nowrap;'>{k}</b>", f"{d * 100:.1f}%", f"{s_ * 100:.0f}%", f"{dp * 100:.0f}%",
                 "-" if c is None else f"<span style='color:{'#B91C1C' if c < 0 else 'inherit'};'>{c:+.1f}%</span>", f"{t:,}" if t else "-", E(ACT[k])]
                for g, d, s_, dp, c, t, o, rk, k in rows], (2, 3, 4, 5, 6))
    cnt = Counter(r[8] for r in rows)
    top = [r[0] for r in rows if r[8] == "공략"][:4]
    dfd = [r[0] for r in rows if r[8] == "방어"]
    return sec("시도별 예산 위험·기회 지도 (대표 전용)", "나라장터 연수 공고(12개월)+발주계획 · 공공 연수 계약 점유 · 지방교육재정 세출 추이 · 교원 수를 시도별로 묶어 영업 우선순위를 냅니다.",
               "<p style='margin:0 0 8px;font-size:13px;'>" + " · ".join(f"<b style='color:{KC[k]};'>{k}</b> {v}곳" for k, v in cnt.items()) + "</p>" + tb
               + "<p class='tt-note'>공략 = 수요 비중 6% 이상·자사 점유 10% 미만, 방어 = 자사 계약액의 15% 이상이 몰린 시도, 확대 = 이미 진입·수요 3% 이상. 세출 증감은 지방교육재정알리미 최근 결산 연도 기준이며, 2027 교부금 개편에 따른 미편성 우려(10.20 국감 보도)는 반영 전입니다.</p>"
               + so_line(f"다음 분기 사전 영업 1순위는 {', '.join(top) or '-'}입니다. "
                         + (f"{', '.join(dfd)}은 자사 매출이 몰린 '방어' 시도라 재계약 시점과 예산 편성 동향을 매달 확인하세요." if dfd else "")))


# ---------------------------------------------------------------- ③ 주간 경영보고 자동 초안
def build_weekly(sec, M=None, pipe=None, today=None):
    M = M if M is not None else load()
    today = today or date.today()
    L = []
    if M:
        Y = {r["y"]: r for r in M["years"]}
        c = Y.get(2026)
        fc = int((M.get("fc_from") or {}).get("2026", 13))
        ytd = sum(sum(c["m"][k][:fc - 1]) for k in ("b2c", "b2s", "b2g")) if c and c.get("m") else 0
        L.append(f"1. 실적: 2026 연수 매출 예상 {eok(c['tot'])}(전년 대비 {pct(c['tot'], Y[2025]['tot'])}), 1~{fc - 1}월 누계 {eok(ytd)}(연간 예상의 {ytd / c['tot'] * 100:.0f}%). 영업이익(배분 전) 예상 {eok(c['op'])}.")
        P = M.get("plan27")
        if P:
            v = sum(x["v"] for x in P["channels"]); g = sum(x["v"] for x in P["channels"] if x["b2g"])
            L.append(f"2. 2027 계획: 매출 {eok(v)}, B2G 비중 {g / v * 100:.0f}%, 기여이익 {eok(P['cost']['contrib_v'])}. 1분기 착수 과정 {sum(1 for d in P['dev'] if d[2].startswith('27.0') and int(d[2][3:]) <= 3)}개.")
    ds = _hist("daily_stats.jsonl")
    if len(ds) >= 8:
        a, b = ds[-1], ds[-8]
        L.append(f"3. 시장(최근 7일): 교육청·연수원 발주 누적 {b.get('g2b_total_detail', 0):,} → {a.get('g2b_total_detail', 0):,}건, AI·에듀테크 발주 {a.get('ai_rows_count', 0):,}건({(a.get('ai_rows_amount_sum') or 0) / 1e8:,.1f}억).")
    try:
        cw = __import__("competitor_watch").build(today)
        L.append(f"4. 경쟁사: 최근 30일 변화 {cw['total']}건(7일 {cw['week']}건) — " + (cw["signals"][0]["t"] if cw.get("signals") else "특이사항 없음") + ".")
    except Exception:
        pass
    recs = (pipe or {}).get("records") or []
    if recs:
        units, lim, _ = settle_units(recs, today)
        late = [u for u in units if u["late"]]
        todo = [u for u in units if u["st"] not in ("run", "done")]
        L.append(f"5. 교육청 연수 정산: 정산 대기 {len(todo)}건 {sum(u['amt'] for u in todo) / 1e8:,.2f}억, 기준보다 늦은 건 {len(late)}건 {sum(u['amt'] for u in late) / 1e8:,.2f}억.")
        wk = [u for u in units if u["st"] == "run" and 0 <= (u["end"] - today).days <= 7]
        if wk:
            L.append(f"6. 이번 주 종료 연수 {len(wk)}건 — 이수통보·결과보고 일정 사전 점검.")
    L.append("7. 이번 주 결정 필요: (작성자가 채움)")
    txt = f"[교원연수 Core 주간 경영보고 초안 · {today:%Y-%m-%d}]\n\n" + "\n".join(L)
    tid = "wkRep"
    return sec("주간 경영보고 자동 초안 (대표 전용)", "대시보드·경영실적·정산·경쟁사 데이터로 매 배포 때 다시 씁니다. 복사해 보고 양식에 붙여 넣고 7번만 채우세요.",
               f"<textarea id='{tid}' readonly style='width:100%;min-height:220px;font:13px/1.7 inherit;padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--surface-2);color:var(--ink);'>{E(txt)}</textarea>"
               f"<button type='button' onclick=\"navigator.clipboard.writeText(document.getElementById('{tid}').value);this.textContent='복사됨';\" "
               "style='margin-top:8px;padding:7px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface);cursor:pointer;font-weight:700;'>초안 복사</button>"
               "<p class='tt-note'>주간보고(코워크) 형식에 맞춰 항목 순서를 조정할 수 있습니다.</p>")


# ---------------------------------------------------------------- ①⑤ 재수강 전환 · 역할별 실행 알림
def build_roles(sec, M=None, pipe=None, today=None):
    M = M if M is not None else load()
    today = today or date.today()
    recs = (pipe or {}).get("records") or []
    ROLE = {"notice": "2셀 운영", "report": "2셀 운영", "bill": "정산 담당", "pay": "정산 담당", "run": "2셀 운영"}
    acts = defaultdict(list)
    if recs:
        units, lim, _ = settle_units(recs, today)
        lab = dict(STAGES)
        for u in units:
            if u["late"]:
                acts[ROLE[u["st"]]].append(f"{lab[u['st']]} 지연 {u['wait']}일 — {u['org'][:16]} · {u['course'][:24]}")
            elif u["st"] == "run" and 0 <= (u["end"] - today).days <= 7:
                acts[ROLE["run"]].append(f"이번 주 종료 {u['end']:%m.%d} — {u['org'][:16]} 이수통보 준비")
        for r in recs:  # 모집 경보: 신청 기간 중 신청률 낮은 사업
            rs, re_ = _d(r.get("recruitStart")), _d(r.get("recruitEnd"))
            tgt, app = _won(r.get("targetCount")), _won(r.get("appliedCount"))
            if rs and re_ and rs <= today <= re_ and tgt:
                el = max((today - rs).days, 0) / max((re_ - rs).days, 1)
                if app / tgt < el * 0.7:
                    acts["2셀 영업"].append(f"모집 부진 {app}/{tgt}명(기간 {el * 100:.0f}% 경과) — {str(r.get('org') or '')[:16]}")
    box = "".join(f"<div style='flex:1;min-width:260px;border:1px solid var(--border);border-radius:8px;padding:10px 12px;'><b>{E(k)}</b> <span class='fit'>{len(v)}건</span>"
                  f"<ul style='margin:6px 0 0 16px;padding:0;font-size:12.5px;line-height:1.6;'>{''.join(f'<li>{E(x)}</li>' for x in v[:6])}</ul></div>" for k, v in acts.items()) \
        or "<p class='tt-note'>이번 주 역할별로 처리할 경보가 없습니다.</p>"
    Lr = [r for r in (M or {}).get("learn", []) if r.get("ret")]
    ret = " → ".join(f"{r['y']} {r['ret'] * 100:.0f}%" for r in Lr)
    conv = (f"<h4>① 단체연수 → 개인 재수강 전환</h4><p style='font-size:13px;margin:4px 0;'>재수강률(최소치): {ret or '-'} </p>"
            "<p class='tt-note'>전환율(단체 이수 교사 중 다음 해 개인 결제 비율)은 학사 이수 명단(월 1회, 개인정보 가림)을 받으면 이 칸에 자동 계산됩니다. 연동 전까지는 연도별 재수강률만 표시합니다.</p>")
    return sec("역할별 이번 주 실행 알림 · 재수강 전환 (대표 전용)", "정산 지연·이번 주 종료·모집 부진을 역할별로 묶었습니다. 담당자 실명은 저장하지 않습니다.",
               "<div style='display:flex;gap:10px;flex-wrap:wrap;'>" + box + "</div>" + conv)
