#!/usr/bin/env python3
"""
🔒 관리 탭 '경영 종합' 맨 위 — 교원연수 2030 방향 · 셀별 2027 실행안 (2026-11-16 사용자 지시)

  원자료: 비공개 저장소 strategy_room/training_plan_2027.json (대외비 전략 문서 요약)
          공개 저장소에는 화면 틀만 두고, 수치·문장은 전부 비공개 JSON 에서 읽는다.
  블록 종류(t): box · tiles · cards · table · steps · timeline · bars · bars2
  셀 실행안이 추가되면 JSON sections 에 항목만 더하면 된다(코드 수정 불필요).
"""
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
NOTE = "color:var(--muted);font-size:12.5px;"
C2 = "#94a3b8"


def load():
    try:
        d = __import__("strategy_room")._private()
    except Exception:  # noqa: BLE001
        d = None
    for base in ([d] if d else []) + [HERE / "_private", HERE / "private.local"]:
        f = base / "strategy_room" / "training_plan_2027.json"
        if f.is_file():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def _rich(t):
    """전부 이스케이프한 뒤 <b> 만 되살린다."""
    return re.sub(r"&lt;(/?)b&gt;", r"<\1b>", E(str(t)))


def _h(t):
    return f"<h4 style='margin:16px 0 6px;font-size:14px;'>{E(t)}</h4>" if t else ""


def _num(v):
    return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"


def _box(b):
    return f"<div style='margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--surface-2);border-radius:6px;font-size:13px;line-height:1.65;'>{_rich(b['text'])}</div>"


def _tiles(b):
    return ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:8px;'>"
            + "".join(f"<div style='padding:10px 12px;border:1px solid var(--border);border-radius:10px;min-width:0;'><div style='{NOTE}'>{E(l)}</div>"
                      f"<div style='font-size:20px;font-weight:800;line-height:1.3;'>{E(v)}</div><div style='{NOTE}'>{E(s)}</div></div>" for l, v, s in b["items"])
            + "</div>")


def _cards(b):
    return (_h(b.get("h")) + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:8px;margin-top:8px;'>"
            + "".join(f"<div style='padding:10px 12px;border:1px solid var(--border);border-top:3px solid var(--accent);border-radius:8px;font-size:13px;line-height:1.6;'><b>{E(t)}</b><div style='margin-top:4px;'>{_rich(x)}</div></div>" for t, x in b["items"])
            + "</div>")


def _table(b):
    th = "".join(f"<th style='text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap;'>{E(x)}</th>" for x in b["head"])
    tr = "".join("<tr>" + "".join(f"<td style='padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:top;'>{_rich(c)}</td>" for c in r) + "</tr>" for r in b["rows"])
    return _h(b.get("h")) + f"<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:12.5px;min-width:520px;'><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>"


def _steps(b):
    n = len(b["items"])
    return (_h(b.get("h")) + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(140px,100%),1fr));gap:6px;'>"
            + "".join(f"<div style='padding:8px 10px;border-radius:8px;background:var(--surface-2);font-size:12.5px;'><div style='{NOTE}'>{i + 1}/{n}</div><b>{E(t)}</b><div style='{NOTE}'>{E(k)}</div></div>" for i, (t, k) in enumerate(b["items"]))
            + "</div>")


def _timeline(b):
    return (_h(b.get("h")) + "<div style='border-left:2px solid var(--border);margin-left:6px;padding-left:12px;'>"
            + "".join(f"<div style='position:relative;margin:8px 0;font-size:13px;line-height:1.55;'><span style='position:absolute;left:-18px;top:5px;width:10px;height:10px;border-radius:50%;background:var(--accent);'></span>"
                      f"<b>{E(when)}</b> <span style='padding:1px 7px;border-radius:9px;background:var(--surface-2);font-size:11.5px;'>{E(tag)}</span><div>{_rich(x)}</div></div>" for when, tag, x in b["items"])
            + "</div>")


def _bars(b):
    rows = b["rows"]
    mx = max([v for _, v in rows] + [1])
    u = b.get("unit", "")
    out = "".join(f"<div style='display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12.5px;'><span style='width:42%;max-width:240px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' title='{E(k)}'>{E(k)}</span>"
                  f"<span style='flex:1;height:11px;background:var(--surface-2);border-radius:6px;'><span style='display:block;height:100%;width:{v / mx * 100:.1f}%;background:var(--accent);border-radius:6px;'></span></span>"
                  f"<b style='width:70px;text-align:right;flex:none;'>{E(_num(v))}{E(u)}</b></div>" for k, v in rows)
    return _h(b.get("h")) + out + (f"<div style='{NOTE}margin-top:4px;'>{_rich(b['note'])}</div>" if b.get("note") else "")


def _bars2(b):
    a, c = b.get("legend", ["전", "후"])
    mx = max([max(x, y) for _, x, y in b["rows"]] + [1])
    leg = (f"<div style='{NOTE}margin-bottom:4px;'><span style='display:inline-block;width:10px;height:10px;background:{C2};border-radius:2px;'></span> {E(a)} "
           f"<span style='display:inline-block;width:10px;height:10px;background:var(--accent);border-radius:2px;margin-left:8px;'></span> {E(c)}</div>")
    bar = lambda v, col: (f"<div style='display:flex;align-items:center;gap:6px;'><span style='flex:1;height:9px;background:var(--surface-2);border-radius:5px;'>"
                          f"<span style='display:block;height:100%;width:{v / mx * 100:.1f}%;background:{col};border-radius:5px;'></span></span><span style='width:44px;text-align:right;font-size:12px;'>{E(_num(v))}</span></div>")
    rows = "".join(f"<div style='display:flex;gap:8px;align-items:center;margin:6px 0;font-size:12.5px;'><span style='width:42%;max-width:200px;flex:none;'>{E(k)}"
                   f"<span style='{NOTE}display:block;'>{'+' if y >= x else ''}{(y - x) / x * 100 if x else 0:.0f}%</span></span>"
                   f"<div style='flex:1;min-width:0;'>{bar(x, C2)}{bar(y, 'var(--accent)')}</div></div>" for k, x, y in b["rows"])
    return _h(b.get("h")) + leg + rows + (f"<div style='{NOTE}margin-top:4px;'>{_rich(b['note'])}</div>" if b.get("note") else "")


R = {"box": _box, "tiles": _tiles, "cards": _cards, "table": _table, "steps": _steps, "timeline": _timeline, "bars": _bars, "bars2": _bars2}


def build(sec):
    D = load()
    if not D:
        return ""
    out = []
    for i, s in enumerate(D.get("sections", [])):
        body = []
        for b in s.get("blocks", []):
            try:
                body.append(R[b["t"]](b))
            except Exception as e:  # noqa: BLE001 — 블록 하나가 깨져도 나머지는 보인다
                print(f"[경고] 경영 종합 전략 블록 건너뜀: {type(e).__name__}")
        inner = "".join(body)
        out.append(sec(E(s["title"]), E(s.get("desc", "")),
                       f"<details open><summary style='cursor:pointer;{NOTE}padding:2px 0;'>펼치기 · 접기</summary>{inner}</details>"))
        if i == 0 and D.get("sim"):  # 2030 방향 바로 아래: 2027 매출 시나리오 시뮬레이터(브라우저에서 계산)
            out.append(sec("2027 매출 시나리오 시뮬레이터", "막대를 움직이면 총매출·B2G 비중·기여이익이 바로 다시 계산됩니다. 기준선은 2027 매출 계획.",
                           f"<div id='tpSim' data-p='{E(json.dumps(D['sim'], ensure_ascii=False))}'><p style='{NOTE}'>계산기를 불러오는 중입니다.</p></div>"))
    return "".join(out)


def build_quote(sec):
    """🔒 관리 탭 '영업 도구' — 블렌디드 견적·수익 계산기(값은 비공개 JSON, 계산은 브라우저)."""
    D = load()
    if not D or not D.get("quote"):
        return sec("블렌디드 견적·수익 계산기", "", f"<p style='{NOTE}'>데이터 준비 중</p>")
    return sec("블렌디드 견적·수익 계산기", "교육청 미팅 전에 구성을 고르면 견적·예상 마진·5억까지 필요한 건수가 나옵니다.",
               f"<div id='tpQuote' data-p='{E(json.dumps(D['quote'], ensure_ascii=False))}'><p style='{NOTE}'>계산기를 불러오는 중입니다.</p></div>")
