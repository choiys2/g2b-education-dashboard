#!/usr/bin/env python3
"""
관리 탭 대표 전용 '경영 실적' 화면 - 손익 추이 · 월별 계절성 · 수강 기반(이수자) · 목표 대비 진척 · 3사 비교 · 연수 정산 현황.

- 실적 수치: GitHub Secret MGMT_JSON(경영실적·이수자 명단의 연도별 합계, 개인 정보 없음)에서만 읽는다.
  로컬 시험은 mgmt.local.json(gitignore). 없으면 해당 칸은 '미등록'으로 두고 나머지는 그대로 그린다.
- 결과 HTML 은 admin_structure.build_html 에 붙어 ADMIN_PASSWORD 로 암호화된다. history/·live/·브리핑(공개)에는 쓰지 않는다.
- 정산 현황은 이미 걸러진 sheets_ops 결과(기관·연수명·금액)만 쓴다.
"""
import html
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from plan2027 import legend, so_line, stack_svg, table, tile, tiles

HERE = Path(__file__).parent
E = html.escape
CH = [("b2c", "개인(B2C)", "#10b981"), ("b2s", "단체(B2S)", "#4f8cff"), ("b2g", "위탁(B2G)", "#f59e0b")]
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
    b2g_sh = c["b2g"] / c["tot"] * 100 if c and c["tot"] else 0
    ts = [tile("2026 매출(예상)", eok(c["tot"]), f"전년 {eok(p['tot'])} 대비 {pct(c['tot'], p['tot'])}", c["tot"] < p["tot"]),
          tile("영업이익(공통비 배분 전)", eok(c["op"]), f"배분 후 {eok(c.get('op_after'))} · 전년 {eok(p['op'])}", c["op"] < 0),
          tile(f"1~{fc - 1}월 실적", eok(ytd), f"연간 예상의 {ytd / c['tot'] * 100:.0f}% · 남은 {13 - fc}개월 {eok(c['tot'] - ytd)} 필요" if ytd else "", bool(ytd and ytd / c["tot"] < 0.6)),
          tile("위탁(B2G) 비중", f"{b2g_sh:.0f}%", f"2027 목표 {M['target']['b2g']}% 이하", b2g_sh > M["target"]["b2g"])]
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
    t = M["target"]
    rows = []
    for r in M["years"]:
        g = r["b2g"] / r["tot"] * 100 if r["tot"] else 0
        g2 = (r["b2g"] + r["b2s"]) / r["tot"] * 100 if r["tot"] else 0
        rows.append((f"{r['y']}{'E' if r['y'] == 2026 else ''}", g, g2, r))
    bar = lambda lab, g, g2: (f'<div style="display:grid;grid-template-columns:56px 1fr 190px;gap:8px;align-items:center;margin:5px 0;font-size:12.5px;">'
                              f'<b>{lab}</b><span style="position:relative;display:flex;height:18px;border-radius:4px;overflow:hidden;background:var(--surface-2);">'
                              f'<i style="width:{100 - g:.1f}%;background:#10b981;"></i><i style="width:{g:.1f}%;background:#f59e0b;"></i>'
                              f'<i style="position:absolute;left:{100 - t["b2g"]}%;top:-2px;bottom:-2px;border-left:2px dashed var(--ink);"></i></span>'
                              f'<span class="num">위탁 {g:.0f}% · 교육청 포함 {g2:.0f}%</span></div>')
    c = rows[-1][3]
    need_on = c["b2g"] * t["b2cs"] / t["b2g"]
    return (legend([("개인+단체(B2C+B2S)", "#10b981"), ("위탁(B2G)", "#f59e0b"), (f"{t['y']} 목표선(B2G {t['b2g']}%)", "var(--ink)")])
            + "".join(bar(a, g, g2) for a, g, g2, _ in rows)
            + f"<p class='tt-note'>구분: {E(M.get('def') or '')}. '교육청 포함'은 교육청 단체 원격연수까지 B2G로 본 비중입니다(보고 기준을 하나로 정해야 함 → 2027 경영계획 ② 참고).</p>"
            + so_line(f"2026년 예상 위탁 {eok(c['b2g'])}을 그대로 두면 목표 비중({t['b2g']}:{t['b2cs']})을 맞추는 데 개인+단체 매출이 {eok(need_on)} 필요합니다"
                      f"(현재 {eok(c['b2c'] + c['b2s'])}, {pct(need_on, c['b2c'] + c['b2s'])}). 비중은 위탁이 줄어서도 맞춰지므로, 비중보다 '개인+단체 금액'을 KPI로 따로 보세요."))


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


# ---------------------------------------------------------------- 이번 주 할 일 칸: 연수 정산 현황
def build_settle(sec, so=None):
    if so is None:
        try:
            so = json.loads((HERE / "live/sheets_ops.json").read_text(encoding="utf-8"))
        except Exception:
            so = {}
    st = (so or {}).get("settle") or {}
    rows = st.get("rows") or []
    if not rows:
        return sec("교육청 연수 정산 현황", "구글시트 '정산관리' 탭 기준", "<p class='tt-note'>정산관리 시트 데이터가 아직 없습니다(다음 자동 배포 후 채워짐).</p>")
    won = lambda v: f"{(v or 0) / 1e8:,.2f}억"
    ended = [r for r in rows if r.get("days") is not None and r["days"] >= 0]
    claimed = [r for r in rows if r.get("claim")]
    inv = [r for r in rows if r.get("invoice")]
    slip = [r for r in rows if r.get("slip")]
    steps = [("연수 종료", len(ended), sum(r.get("budget") or 0 for r in ended)), ("청구", len(claimed), sum(r["claim"] for r in claimed)),
             ("계산서 발행", len(inv), sum(r.get("claim") or 0 for r in inv)), ("매출 전표", len(slip), sum(r.get("claim") or 0 for r in slip))]
    flow = '<span style="color:var(--muted);align-self:center;">→</span>'.join(
        f'<div style="flex:1;min-width:120px;padding:8px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);">'
        f'<div style="font-size:11.5px;color:var(--muted);">{E(n)}</div><div class="num" style="font-size:20px;font-weight:800;">{c:,}건</div>'
        f'<div class="num" style="font-size:11.5px;color:var(--muted);">{won(a)}</div></div>' for n, c, a in steps)
    fl = Counter(r["flag"] for r in rows if r.get("flag"))
    late = sorted([r for r in rows if r.get("flag")], key=lambda r: -(r.get("days") or 0))[:15]
    lt = table(["구분", "지역", "기관", "연수명", "종료 후", "청구액"],
               [[f"<b style='color:#ef4444;'>{E(r['flag'])}</b>", E(r.get("region") or ""), E(r.get("org") or ""), E(r.get("course") or ""),
                 f"{r['days']}일" if r.get("days") is not None else "-", won(r.get("claim"))] for r in late], (4, 5)) if late else "<p class='tt-note'>처리할 정산 경보가 없습니다.</p>"
    mo = defaultdict(float)
    for r in claimed:
        mo[r.get("month") or "미정"] += r["claim"]
    mos = "".join(f"<span class='fit' style='margin:2px 6px 2px 0;'>{E(k)} {won(v)}</span>" for k, v in sorted(mo.items()))
    chips = " ".join(f"<span class='fit fit-불가'>{E(k)} {v}건</span>" for k, v in fl.items()) or "<span class='fit fit-가능'>경보 없음</span>"
    return sec("교육청 연수 정산 현황", f"구글시트 '정산관리' {len(rows)}건 · 연수 종료 → 청구 → 계산서 → 전표 단계별 건수·금액 · 조회 {E(str(so.get('fetched') or '-'))}",
               f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 10px;'>{flow}</div><p style='margin:0 0 6px;font-size:13px;'>{chips}</p>{lt}"
               + (f"<p style='font-weight:800;margin:12px 0 4px;'>청구월별 청구액</p><div>{mos}</div>" if mos else "")
               + so_line("종료 후 30일이 지나도 청구 전인 건, 청구했는데 14일 넘게 계산서가 없는 건부터 처리하세요. 정산이 늦으면 매출 인식 달이 밀려 월 실적과 연말 착지가 함께 흔들립니다."))
