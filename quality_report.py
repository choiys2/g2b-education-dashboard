#!/usr/bin/env python3
"""
관리 탭 '🛡️ 품질 점검' 칸 — 월 1회 보안 감사·디자인 리뷰 결과(심각도 순 수정 목록).
- 데이터: 비공개 저장소 reports/quality/YYYY-MM.json (배포 때 _private/ 로 내려받음, 공개 저장소에는 두지 않음)
  로컬 시험은 QUALITY_DIR 환경변수 또는 _private/reports/quality.
- 결과 HTML 은 관리 탭 암호문 안에만 들어간다(ADMIN_PASSWORD). 외부 텍스트는 모두 escape.
"""
import json
import os
from html import escape as h
from pathlib import Path

HERE = Path(__file__).parent
SEV = {"치명": ("#dc2626", 0), "높음": ("#dc2626", 0), "중요": ("#f59e0b", 1), "중간": ("#f59e0b", 1), "검증 필요": ("#6366f1", 1),
       "낮음": ("#64748b", 2), "다듬기": ("#64748b", 3), "참고": ("#94a3b8", 4)}
STAT = {"수정 완료": "#10b981", "결정 필요": "#f59e0b", "권고": "#6366f1", "이상 없음": "#94a3b8"}


def _dirs():
    env = os.environ.get("QUALITY_DIR", "").strip()
    return ([Path(env)] if env else []) + [HERE / "_private" / "reports" / "quality"]


def load():
    for d in _dirs():
        fs = sorted(d.glob("????-??.json")) if d.exists() else []
        if fs:
            out = []
            for f in fs:
                try:
                    out.append(json.loads(f.read_text(encoding="utf-8")))
                except ValueError:
                    continue
            return out
    return []


def build(sec=None):
    R = load()
    if not R:
        return '<div class="cpv-wrap"><p class="cpv-note">데이터 준비 중 — 첫 점검 결과가 올라오면 여기에 표시됩니다.</p></div>'
    cur = R[-1]
    items = sorted(cur.get("items") or [], key=lambda x: (SEV.get(x.get("sev"), ("#94a3b8", 5))[1], x.get("area", "")))
    open_n = sum(1 for x in items if x.get("status") in ("결정 필요", "권고"))
    done_n = sum(1 for x in items if x.get("status") == "수정 완료")
    head = (f'<div class="qa-kpi"><span><b>{len(items)}</b>점검 항목</span><span><b style="color:#10b981">{done_n}</b>수정 완료</span>'
            f'<span><b style="color:#f59e0b">{open_n}</b>결정·권고 남음</span><span><b>{len(R)}</b>회 누적</span></div>')
    rows = []
    for x in items:
        c = SEV.get(x.get("sev"), ("#94a3b8", 5))[0]
        sc = STAT.get(x.get("status"), "#94a3b8")
        rows.append(f'<details class="qa-it"><summary><em style="background:{c}">{h(x.get("sev", ""))}</em><span class="qa-a">{h(x.get("area", ""))}</span>'
                    f'<b>{h(x.get("title", ""))}</b><i style="color:{sc}">● {h(x.get("status", ""))}</i></summary>'
                    f'<p>{h(x.get("detail", ""))}</p>'
                    + (f'<p><strong>수정</strong> {h(x["fix"])}</p>' if x.get("fix") else "")
                    + (f'<p><strong>확인 방법</strong> {h(x["check"])}</p>' if x.get("check") else "") + "</details>")
    hist = "".join(f'<li>{h(r.get("date", ""))} · {len(r.get("items") or [])}건 · 수정 {sum(1 for x in r.get("items") or [] if x.get("status") == "수정 완료")}건</li>' for r in R[::-1][:12])
    return (f'<div class="cpv-wrap"><div class="cpv-grid"><section class="cpv-card"><header><span class="cpv-ic">🛡️</span><div><b>월간 품질 점검 · {h(cur.get("date", ""))}</b>'
            f'<small>보안 감사 + 디자인 리뷰 · 심각도 순</small></div></header>{head}<div class="qa-list">{"".join(rows)}</div>'
            f'<p class="cpv-note"><strong>범위</strong> {h(cur.get("scope", ""))}</p><p class="cpv-note"><strong>확인 못 한 부분</strong> {h(cur.get("gaps", ""))}</p></section>'
            f'<section class="cpv-card"><header><span class="cpv-ic">🗂️</span><div><b>점검 이력</b><small>매월 1일 자동 점검</small></div></header><ul class="qa-h">{hist}</ul></section></div></div>')


if __name__ == "__main__":
    print(len(build()))
