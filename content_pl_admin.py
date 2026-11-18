#!/usr/bin/env python3
"""
🔒 관리 탭 '콘텐츠 손익' 칸 — 과정별 손익 엑셀(참고 데이터)의 원가·외주비·공헌이익 분석 (2026-11-18)

  원자료: 비공개 저장소 content_pl/course_pl.json (tools/course_pl_import.py 로 만든다)
  일반 화면(콘텐츠·매출 탭)에는 매출·판매 수만 싣고, 제작비·외주비·손익은 여기(관리 비밀번호 뒤)에만 둔다.
  공헌이익 = 매출 − 외주비(제작비+심사비+지급수수료). 엑셀의 '강좌별 손익'은 내부 원가·판관비 배분이 섞여 있어 참고로만 보인다.
"""
import json
from collections import defaultdict
from pathlib import Path

import training_plan as tp

HERE = Path(__file__).parent
E = tp.E
NOTE = tp.NOTE
OP = {"자율", "1학점 미만", "1학점", "2학점", "4학점(비노출)"}


def load():
    try:
        d = __import__("strategy_room")._private()
    except Exception:  # noqa: BLE001
        d = None
    for base in ([d] if d else []) + [HERE / "_private", HERE / "private.local"]:
        f = base / "content_pl" / "course_pl.json"
        if f.is_file():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def W(v):
    v = v or 0
    return f"{v / 1e8:,.2f}억" if abs(v) >= 1e8 else f"{v / 1e4:,.0f}만"


def build(sec):
    D = load()
    if not D:
        return sec("콘텐츠 손익", "", f"<p style='{NOTE}'>데이터 준비 중</p>")
    C = [c for c in D.get("courses") or [] if c.get("cr") in OP]
    rev = sum(c["rev"] for c in C)
    ext = sum(c.get("ext", 0) for c in C)
    prod = sum(c.get("prod", 0) for c in C)
    cm = rev - ext
    inv = [c for c in C if c.get("prod", 0) > 0]
    unrec = [c for c in inv if c["rev"] < c.get("ext", 0)]
    tiles = tp._tiles({"items": [["누적 매출", W(rev), f"운영 {len(C)}개 과정 · {D.get('as_of', '')} 기준"], ["외주비 합계", W(ext), f"제작비 {W(prod)} 포함"],
                                 ["공헌이익(매출−외주비)", W(cm), f"공헌이익률 {cm / rev * 100:.1f}%" if rev else "-"],
                                 ["외주비 미회수 과정", f"{len(unrec)}개", f"제작비가 든 {len(inv)}개 중 · 미회수 {W(sum(c.get('ext', 0) - c['rev'] for c in unrec))}"]]})
    g = defaultdict(lambda: [0, 0, 0, 0, 0])
    for c in C:
        x = g[c.get("ty") or "-"]
        x[0] += 1; x[1] += c["rev"]; x[2] += c.get("ext", 0); x[3] += c.get("prod", 0); x[4] += c.get("r12", 0)
    trows = [[f"<b>{k}</b>", n, W(r), W(e), W(r - e), f"{(r - e) / r * 100:.0f}%" if r else "-", W(p / n), f"{r / e:.1f}배" if e else "외주비 없음", W(r12 / n)]
             for k, (n, r, e, p, r12) in sorted(g.items(), key=lambda kv: -kv[1][1])]
    by_cm = sorted(C, key=lambda c: -(c["rev"] - c.get("ext", 0)))
    lab = lambda c: f"{c['n']} [{c.get('ty', '-')}·{c.get('pass', '')}]"
    top = [[i + 1, lab(c), W(c["rev"]), W(c.get("ext", 0)), W(c["rev"] - c.get("ext", 0))] for i, c in enumerate(by_cm[:15])]
    low = [[i + 1, lab(c), W(c["rev"]), W(c.get("ext", 0)), W(c["rev"] - c.get("ext", 0)), W(c.get("r12", 0))] for i, c in enumerate(sorted(C, key=lambda c: c["rev"] - c.get("ext", 0))[:15])]
    # 최근 합격(최근 2개 연도) 과정의 제작비 회수 진행
    years = sorted({c["pass"][:2] for c in C if c.get("pass")})
    recent = [c for c in inv if c.get("pass", "")[:2] in years[-2:]]
    rec = [[lab(c), W(c.get("prod", 0)), W(c["rev"]), f"{c['rev'] / c['prod'] * 100:.0f}%", W(c.get("r12", 0))] for c in sorted(recent, key=lambda c: c["rev"] / c["prod"])]
    body = (tiles
            + tp._table({"h": "개발 구분별 수익 구조", "head": ["구분", "과정", "누적 매출", "외주비", "공헌이익", "공헌이익률", "과정당 제작비", "매출/외주비", "과정당 최근 12개월"], "rows": trows})
            + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(420px,100%),1fr));gap:16px;'>"
            + "<div>" + tp._table({"h": "공헌이익 TOP 15", "head": ["#", "과정", "매출", "외주비", "공헌이익"], "rows": top}) + "</div>"
            + "<div>" + tp._table({"h": "공헌이익 하위 15(외주비 미회수)", "head": ["#", "과정", "매출", "외주비", "공헌이익", "최근 12개월"], "rows": low}) + "</div></div>"
            + tp._table({"h": f"최근 합격 과정(20{years[-2] if len(years) > 1 else ''}~) 제작비 회수율", "head": ["과정", "제작비", "누적 매출", "회수율", "최근 12개월"], "rows": rec or [["-", "-", "-", "-", "-"]]})
            + tp._box({"text": "<b>읽는 법</b> — 공헌이익은 매출에서 외주비(제작비·심사비·지급수수료)만 뺀 값입니다. 내부 인건비·판관비 배분은 빠져 있어 실제 이익보다 큽니다. "
                               "외주비 미회수 과정 중 최근 12개월 매출이 있는 과정은 SET·라이브로 회수를 앞당기고, 매출이 0이면 통합·폐강을 검토하세요."})
            + f"<p style='{NOTE}'>{E(D.get('note') or '')} 분석 범위: 자율·학점 과정(폐강·개발예정·제작중단 제외).</p>")
    return sec("콘텐츠 손익", f"과정별 손익 참고 데이터({E(D.get('as_of') or '')} 누적) — 제작비·외주비·공헌이익은 이 칸에서만 봅니다", body)
