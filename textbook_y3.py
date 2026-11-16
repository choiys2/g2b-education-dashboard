#!/usr/bin/env python3
"""
🔒 관리 탭 '3년차 교과서' 칸 (2026-11-16 사용자 지시: 총판 성적표 옆)

  원자료: 비공개 저장소 textbook/2027_high_elective.json (사업관리Core '2027 고등 선택과목 채택 결과보고' 수치화)
          - 회사 내부 실적이라 공개 저장소에 두지 않는다. 배포 때 _private/ 로 내려받아 관리 비밀번호 암호문 안에만 싣는다.
  구성: ① 핵심 숫자 ② 시장·출판사 판도 ③ 선택과목 성과 ④ 과목군·과목 지도(지킨다·뒤집는다·넓힌다) ⑤ 미출원 시장
        ⑥ 인사이트 ⑦ 연수원 연계 제안(데이터·상품·KPI)
"""
import html
import json
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
NOTE = "color:var(--muted);font-size:12.5px;"
VS = "var(--accent)"
OTH = "#94a3b8"
PUB_C = {"비상교육": VS, "미래엔": "#f59e0b", "천재교과서": "#ef4444", "아이스크림미디어": "#10b981", "엔이능률": "#8b5cf6", "와이비엠": "#0ea5e9", "동아출판": "#64748b"}


def load():
    try:
        d = __import__("strategy_room")._private()
    except Exception:  # noqa: BLE001
        d = None
    for base in ([d] if d else []) + [HERE / "_private", HERE / "private.local"]:
        f = base / "textbook" / "2027_high_elective.json"
        if f.is_file():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def _tile(lab, val, sub=""):
    return (f"<div style='padding:10px 12px;border:1px solid var(--border);border-radius:10px;min-width:0;'><div style='{NOTE}'>{E(lab)}</div>"
            f"<div style='font-size:22px;font-weight:800;line-height:1.3;'>{val}</div><div style='{NOTE}'>{E(sub)}</div></div>")


def _hbars(rows, unit="%", mx=None, label_w=110, fmt=lambda v: f"{v:g}"):
    """rows: [(라벨, 값, 색)]"""
    mx = mx or max([v for _, v, _ in rows] + [1])
    return "".join(f"<div style='display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12.5px;'><span style='width:{label_w}px;flex:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{E(k)}</span>"
                   f"<span style='flex:1;height:11px;background:var(--surface-2);border-radius:6px;'><span style='display:block;height:100%;width:{max(0, v) / mx * 100:.1f}%;background:{c};border-radius:6px;'></span></span>"
                   f"<b style='width:64px;text-align:right;flex:none;'>{E(fmt(v))}{E(unit)}</b></div>" for k, v, c in rows)


def _box(t):
    return f"<div style='margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--surface-2);border-radius:6px;font-size:13px;line-height:1.65;'>{t}</div>"


def _grid(*cols, minw=300):
    return f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min({minw}px,100%),1fr));gap:16px;'>" + "".join(f"<div style='min-width:0;'>{c}</div>" for c in cols) + "</div>"


def _h(t, s=""):
    return f"<h4 style='margin:14px 0 6px;font-size:14px;'>{E(t)}{f' <span style={chr(39)}{NOTE}font-weight:500;{chr(39)}>{E(s)}</span>' if s else ''}</h4>"


def _band(gap, rank):
    if rank == 1 and gap < 10:
        return ("지킨다", "#f59e0b")
    if rank == 1:
        return ("1위", "#10b981")
    if gap >= -6:
        return ("뒤집는다", "#3b82f6")
    return ("넓힌다", "#94a3b8")


def build(sec):
    D = load()
    if not D:
        return sec("3년차 교과서", "채택 결과 자료가 비공개 저장소에 올라오면 채워집니다.", "")
    K = D["kpi"]
    # ① 핵심 숫자
    tiles = ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;'>"
             + _tile("선택과목 점유율", f"{K['elective_share']}% · {K['elective_rank']}위", f"2위 {K['second'][0]} {K['second'][1]}% · 출원 기준 {K['applied_share']}%")
             + _tile("1위 과목", f"{K['first_subjects']}개", f"출원 {K['applied']}과목 중 {K['first_subjects'] / K['applied'] * 100:.1f}%")
             + _tile("과학 전 과목 1위", f"{K['sci_first']}/15", f"과학 과목군 점유율 {K['sci_share']}%")
             + _tile("3년차(진로·융합) 목표 채택률", f"{K['y3_actual']}%", f"목표 {K['y3_target']}% → {K['y3_actual'] / K['y3_target'] * 100:.1f}% 달성")
             + _tile("미출원 검토 과목", f"{K['unapplied']}개", f"시장 {K['unapplied_copies']}만 부 · 우선 {K['priority_unapplied'][0]}과목 {K['priority_unapplied'][1]}만 부")
             + "</div>")
    s1 = sec("3년차 교과서 — 2027 고등 선택과목 채택 결과", f"{E(D.get('source', ''))} 기준 · 관리 탭 전용(회사 내부 실적)", tiles
             + _box("<b>한 줄 요약</b> — " + _rich(D.get("summary", ""))))
    # ② 시장·출판사 판도
    M = D["market"]
    lv = "".join(f"<div style='display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12.5px;'><span style='width:44px;'>{E(n)}</span>"
                 f"<span style='flex:1;display:flex;height:14px;border-radius:6px;overflow:hidden;background:var(--surface-2);'>"
                 f"<span title='검정' style='width:{g / 3733 * 100:.1f}%;background:{VS};'></span><span title='국정' style='width:{k / 3733 * 100:.1f}%;background:#cbd5e1;'></span></span>"
                 f"<b style='width:72px;text-align:right;'>{g + k:,}억</b></div>" for n, g, k in M["levels"])
    pubs = _hbars([(n, s, PUB_C.get(n, OTH)) for n, s, _, _ in D["publishers"]], mx=25)
    grow = _hbars([(n, g, VS if n == "비상교육" else OTH) for n, _, _, g in D["growth"] if g > 0], unit="%", mx=70)
    s2 = sec("시장·출판사 판도", f"2027 교과서 시장 {M['total_eok']:,}억 원(검정 {M['geomjeong_eok']:,} + 국정 {M['gukjeong_eok']:,}) · 평균정가 적용 추정치(실매출 아님)",
             _grid(_h("학교급별 시장(억 원)", "■ 검정 ■ 국정") + lv
                   + "<div style='font-size:12.5px;margin-top:8px;'>" + " · ".join(f"<b>{E(n)}</b> 비상 {s}% {r}위(1위 {E(t)})" for n, s, r, t in D["levels_rank"]) + "</div>",
                   _h("검정 전체 출판사 점유율", "초·중·고 합산") + pubs,
                   _h("2015 개정 → 2022 개정 주문부수 증가율", "비교 가능한 출판사") + grow
                   + f"<p style='{NOTE}'>{_rich(D.get('growth_note', ''))}</p>"))
    # ③ 선택과목 성과
    es = "".join(f"<div style='display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center;margin:5px 0;font-size:12.5px;'><span>{E(n)}</span><span>"
                 f"<span style='display:block;height:9px;width:{a / 35 * 100:.1f}%;background:{PUB_C.get(n, OTH)};border-radius:4px;' title='전체 과목 기준 {a}%'></span>"
                 f"<span style='display:block;height:9px;margin-top:2px;width:{b / 35 * 100:.1f}%;background:{PUB_C.get(n, OTH)};opacity:.45;border-radius:4px;' title='출원 과목 기준 {b}%'></span></span></div>"
                 for n, a, b in D["elective_share"][:6])
    fc = _hbars([(n, v, PUB_C.get(n, OTH)) for n, v in D["first_count"]], unit="과목", mx=26)
    ta = _hbars([(n, v, VS) for n, v in D["type_avg"]], mx=70, label_w=80)
    pt = _hbars([(f"{n} ({c}종)", v, PUB_C.get(n, OTH)) for n, c, v in D["per_title"]], unit="부", mx=60000, label_w=120, fmt=lambda v: f"{v:,}")
    s3 = sec("선택과목 성과", f"고등 선택(일반·진로·융합) 국·영·수·과·사 {K['total_subjects']}과목 · 비상 {K['elective_copies']:,}부(시장환산 약 {K['elective_value_eok']}억)",
             _grid(_h("출판사별 점유율", "진한 막대 = 전체 과목 기준 · 옅은 막대 = 비상 출원 과목 기준") + es,
                   _h("과목별 1위 수") + fc,
                   _h("선택 유형별 비상 평균 점유율(과학)") + ta + _h("종당 평균 주문부수", "적은 종수·높은 집중도") + pt))
    # ④ 과목군·과목 지도
    G = "".join(f"<div style='padding:8px 10px;border:1px solid var(--border);border-radius:10px;'><div style='display:flex;justify-content:space-between;'><b>{E(n)}</b>"
                f"<span style='font-weight:800;color:{'#10b981' if r == 1 else '#f59e0b' if r == 2 else '#ef4444'};'>{r}위</span></div>"
                f"<div style='font-size:20px;font-weight:800;'>{s}%</div><div style='{NOTE}'>출원 기준 {a}% · 1위 {f}/{t}과목(발행 {p})</div></div>"
                for n, r, s, a, f, p, t in D["groups"])
    rows = sorted(D["subjects"], key=lambda r: (["과학", "국어", "사회", "수학", "영어"].index(r[0]), -r[2]))
    tb = ("<div class='tbl-wrap'><table style='table-layout:fixed;min-width:760px;font-size:12.5px;'><colgroup><col style='width:56px'><col style='width:190px'><col><col style='width:56px'><col style='width:100px'><col style='width:80px'><col style='width:84px'></colgroup>"
          "<thead><tr><th>과목군</th><th>과목</th><th>비상 점유율</th><th class='num'>순위</th><th>비교 출판사</th><th class='num'>격차</th><th>전략</th></tr></thead><tbody>"
          + "".join(f"<tr><td>{E(g)}</td><td>{E(n)}{f' <span style={chr(39)}{NOTE}{chr(39)}>({E(t)})</span>' if t else ''}</td>"
                    f"<td><span style='display:inline-block;width:70%;max-width:220px;height:9px;background:var(--surface-2);border-radius:5px;vertical-align:middle;'><span style='display:block;height:100%;width:{s / 75 * 100:.1f}%;background:{VS};border-radius:5px;'></span></span> <b>{s}%</b></td>"
                    f"<td class='num'>{r}</td><td>{E(o)}</td><td class='num' style='color:{'#10b981' if gp >= 0 else '#ef4444'};'>{gp:+.1f}%p</td>"
                    f"<td><span style='display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;background:color-mix(in srgb, {_band(gp, r)[1]} 22%, var(--surface-2));'>{_band(gp, r)[0]}</span></td></tr>"
                    for g, n, s, r, o, gp, t in rows) + "</tbody></table></div>"
          f"<p style='{NOTE}'>격차: 1위 과목은 2위 대비, 그 외는 1위 대비. 지킨다 = 1위지만 격차 10%p 미만 · 뒤집는다 = 1위와 6%p 이내 · 넓힌다 = 그 밖의 2위 이하.</p>")
    keep = [n for g, n, s, r, o, gp, t in D["subjects"] if r == 1 and gp < 10]
    flip = [n for g, n, s, r, o, gp, t in D["subjects"] if r != 1 and gp >= -6]
    s4 = sec("과목군·과목 지도 — 지킨다·뒤집는다·넓힌다", f"지킨다 {len(keep)}과목 · 뒤집는다 {len(flip)}과목",
             f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:12px;'>{G}</div>" + tb)
    # ⑤ 미출원 시장
    cc = {"예체능": "#ec4899", "핵심": VS, "교양": "#10b981"}
    ua = _hbars([(n, v, cc.get(c, OTH)) for n, v, c in D["unapplied_top"]], unit="만", mx=36, label_w=140)
    ug = _hbars([(f"{n} ({k}과목)", v, OTH) for n, k, v in D["unapplied_groups"]], unit="만", mx=72, label_w=110)
    pr = "".join(f"<div style='font-size:12.5px;margin:3px 0;'>• <b>{E(n)}</b> {v}만 부 <span style='{NOTE}'>1위 {E(w)}</span></div>" for n, v, w in D["priority_unapplied"])
    EE = D["etc_elective"]
    s5 = sec("미출원 시장", f"미출원 {K['unapplied']}과목 · 시장 {K['unapplied_copies']}만 부(타 출판사 주문 합계)",
             _grid(_h("규모 상위 15과목(만 부)", "■ 핵심 과목군 ■ 예체능 ■ 교양") + ua,
                   _h("과목군별 미출원 규모(만 부)") + ug + _h("우선 검토 — 국어·사회 인접 6과목") + pr
                   + f"<p style='{NOTE}'>예체능·기술가정·정보·한문·교양 출원 14과목 점유율 {EE['applied_share']}%({EE['rank']}위, 1위 {E(EE['leader'][0])} {EE['leader'][1]}%와 박빙).</p>"))
    # ⑥ 인사이트 ⑦ 연수원 연계 제안
    ins = ("<ol style='margin:0;padding-left:20px;font-size:13px;line-height:1.75;'>" + "".join(f"<li>{_rich(x)}</li>" for x in D.get("insights", [])) + "</ol>")
    prop = _tbl(D.get("proposals", []))
    data = ("<ul style='margin:6px 0 0;padding-left:20px;font-size:13px;line-height:1.75;'>" + "".join(f"<li>{_rich(x)}</li>" for x in D.get("data_links", [])) + "</ul>")
    s6 = sec("인사이트 · 연수원 연계 제안", "교과서 채택 성과를 연수 사업으로 잇는 방법 — 지킨다·뒤집는다·넓힌다를 연수로 지원",
             _h("인사이트") + ins + _h("연수원 연계 제안", "실행안 · 근거 · KPI") + prop + _h("연계하면 좋은 데이터") + data)
    return s1 + s2 + s3 + s4 + s5 + s6


def _rich(t):
    """비공개 자료 문장: 전부 이스케이프하고 <b> 만 되살린다(CLAUDE.md 보안 4)."""
    return E(t or "").replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")


def _tbl(rows):
    return ("<div class='tbl-wrap'><table style='table-layout:fixed;min-width:820px;font-size:12.5px;'><colgroup><col style='width:190px'><col><col style='width:230px'><col style='width:170px'></colgroup>"
            "<thead><tr><th>제안</th><th>실행안</th><th>근거</th><th>KPI</th></tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{'<b>' + E(c) + '</b>' if i == 0 else E(c)}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
            + "</tbody></table></div>")


if __name__ == "__main__":
    import os
    os.environ.setdefault("PRIVATE_DATA_DIR", str(HERE.parent / "vs-insight-private"))
    sec = lambda t, d, b: f"<section class='panel'><p class='panel-title'>{t}</p><p class='panel-desc'>{d}</p>{b}</section>"
    print(len(build(sec)))
