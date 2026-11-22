#!/usr/bin/env python3
"""
관리 탭 '🎭 가상 이사회' 칸(사용자 승인 2026-11-22) — 월 1회 가상 인물 3명(1위 경쟁사 전략팀장·2위 경쟁사 상품 PM·교육청 장학사)이
대시보드 데이터로 비바샘의 약점과 공략법을 토론한 회의록. 레드팀 관점 점검용.
- 데이터: 비공개 저장소 reports/board/YYYY-MM.json (배포 때 _private/ 로 내려받음, 공개 저장소에는 두지 않음)
- 결과 HTML 은 관리 탭 암호문 안에만 들어간다(ADMIN_PASSWORD). 외부 텍스트는 모두 escape.
- 역할극이며 실제 회사·개인의 발언이 아님을 화면에 항상 표시한다.
"""
import json
import os
from html import escape as h
from pathlib import Path

HERE = Path(__file__).parent


def load():
    env = os.environ.get("BOARD_DIR", "").strip()
    for d in ([Path(env)] if env else []) + [HERE / "_private" / "reports" / "board"]:
        fs = sorted(d.glob("????-??.json")) if d.exists() else []
        out = []
        for f in fs:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except ValueError:
                continue
        if out:
            return out
    return []


def _one(r, open_=True):
    facts = "".join(f"<li>{h(x)}</li>" for x in r.get("facts") or [])
    talk = "".join(f'<div class="br-say"><span class="br-ic">{h(x.get("icon", "🗣️"))}</span><div><b>{h(x.get("who", ""))} <small>(가상)</small></b><p>{h(x.get("says", ""))}</p></div></div>'
                   for x in r.get("rounds") or [])
    acts = "".join(f'<tr><td>{h(a.get("what", ""))}</td><td>{h(a.get("core", ""))}</td><td>{h(a.get("when", ""))}</td><td>{h(a.get("kpi", ""))}</td></tr>' for a in r.get("actions") or [])
    return (f'<details class="br-m"{" open" if open_ else ""}><summary><b>{h(r.get("date", ""))} · {h(r.get("title", ""))}</b></summary>'
            f'<p class="br-dis">⚠️ {h(r.get("disclaimer", "가상 인물의 역할극입니다. 실제 회사·개인의 발언이 아닙니다."))}</p>'
            f'<div class="br-facts"><b>📊 회의에 올라온 사실</b><ul>{facts}</ul></div>{talk}'
            f'<div class="br-out"><p><strong>합의</strong> {h(r.get("consensus", ""))}</p><p><strong>반대 의견</strong> {h(r.get("dissent", ""))}</p></div>'
            + (f'<div class="tbl-wrap"><table class="data"><thead><tr><th>실행</th><th>담당</th><th>시기</th><th>KPI</th></tr></thead><tbody>{acts}</tbody></table></div>' if acts else "")
            + "</details>")


def build(sec=None):
    R = load()
    if not R:
        return '<div class="cpv-wrap"><p class="cpv-note">데이터 준비 중 — 첫 회의록이 올라오면 여기에 표시됩니다.</p></div>'
    body = _one(R[-1], True) + "".join(_one(r, False) for r in R[-2::-1][:11])
    return (f'<div class="cpv-wrap"><div class="cpv-grid"><section class="cpv-card"><header><span class="cpv-ic">🎭</span><div><b>가상 이사회</b>'
            f'<small>경쟁사·교육청 시각으로 본 비바샘 · 매월 2일 갱신 · 누적 {len(R)}회</small></div></header>{body}</section></div></div>')


if __name__ == "__main__":
    print(len(build()))
