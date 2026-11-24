#!/usr/bin/env python3
"""2027 교육부 예산안(사용자 요청 2026-11-24).

- 원천: 비공개 저장소 strategy_room/budget_2027.json (교육부 보도자료 수치 정리, 수동 갱신 — 국회 의결 후 확정치로 교체).
- cp(): CP 화면용 사실·숫자만 — 시장·정책 탭 '2027 교육부 예산 한눈에', B2G영업 탭 '교부금 전국 기준선'.
- build(sec): 관리 칸 '💰 2027 예산 해석' — 해석·실행 제안·추적 항목(내부 판단은 관리 탭에만).
"""
import json
from html import escape as h


def _load():
    try:
        from strategy_room import _private
        d = _private()
        f = d / "strategy_room" / "budget_2027.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def cp():
    D = _load()
    if not D:
        return None
    return {k: D.get(k) for k in ("as_of", "status", "title", "total", "sectors", "grant", "fund", "items")} | \
        {"source": (D.get("source") or {}).get("t", "")}


def _jo(v):  # 억 원 → 조 원 문자열
    return f"{v / 10000:.1f}조" if v >= 10000 else f"{v:,}억"


CSS = """<style>.bdv{font-size:13px}.bdv h4{margin:14px 0 6px}.bdv .c{border:1px solid var(--border,#e5e7eb);border-radius:10px;padding:10px 12px;margin:0 0 10px}
.bdv .c b.h{display:block;font-size:14px;margin-bottom:4px}.bdv .t{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:9px;background:#eef2ff;color:#4338ca;margin-right:6px}
.bdv .a{margin-top:6px;padding:6px 8px;border-radius:6px;background:var(--surface-2,#f4f6fa)}.bdv .n{color:var(--muted,#6b7280);font-size:12px}</style>"""


def build(sec=None):
    D = _load()
    if not D:
        return '<div class="bdv"><p class="n">데이터 준비 중</p></div>'
    T, G = D["total"], D["grant"]
    out = [CSS, '<div class="bdv">',
           f'<p class="n">{h(D["title"])} · {h(D["status"])} · 기준 {h(D["as_of"])} · 총지출 {_jo(T["y27"])}(+{T["pct"]}%) · 교부금 {G["y27"]}조</p>']
    for x in D.get("insight") or []:
        out.append(f'<div class="c"><b class="h"><span class="t">{h(x.get("tag", ""))}</span>{h(x["h"])}</b>{h(x["b"])}'
                   f'<div class="a">▶ {h(x.get("act", ""))}</div></div>')
    out.append('<h4>추적 항목</h4><ul>' + "".join(f"<li>{h(w)}</li>" for w in D.get("watch") or []) + "</ul>")
    out.append(f'<p class="n">원천: {h((D.get("source") or {}).get("t", ""))} — 정부안이라 국회 의결(12월) 뒤 확정치로 바꿔야 함. '
               '수치는 비공개 저장소 strategy_room/budget_2027.json. 해석은 가설 표시.</p></div>')
    return "".join(out)


if __name__ == "__main__":
    import re
    print(json.dumps(cp(), ensure_ascii=False)[:600]); print(re.sub("<[^>]+>", " ", build())[:800])
