#!/usr/bin/env python3
"""교사 커뮤니티 동향 화면(사용자 요청 2026-11-24).

- cp(): CP '교사 트렌드 2027' 탭 최상단 — 오늘의 핵심 메시지(AI 초안/규칙 문장)·주제 흐름·단체별 한 줄·기사·영상 원문 링크.
  단체명은 보이고(사용자 결정), 개인 실명은 ○○○, 출처 서비스 이름·수집 방법은 쓰지 않는다. 블로그·카페 글 링크는 CP 에 내지 않는다(건수만).
- build(sec): 관리 칸 '📡 커뮤니티 동향' — 단체×종류 건수, 주제 7일 vs 직전 평균, 전체 글 목록(블로그·카페 링크 포함), 다음 행동.
"""
import json
import re
from html import escape as h
from pathlib import Path

HERE = Path(__file__).parent
KIND = {"news": "기사", "blog": "글", "cafe": "커뮤니티", "video": "영상"}


def _load():
    try:
        return json.loads((HERE / "history" / "teacher_pulse.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _u(u):
    return u if isinstance(u, str) and u.startswith("https://") else ""


def cp():
    D = _load()
    if not D or not D.get("msg"):
        return None
    cur = (D.get("days") or {}).get(D["generated"]) or {}
    name = {t["k"]: t["name"] for t in D["targets"]}
    orgs = []
    for k, v in (cur.get("by") or {}).items():
        mine = [i for i in D["items"] if i["tg"] == k]
        tp = sorted((v.get("tp") or {}).items(), key=lambda x: -x[1])[:3]
        links = [{"t": i["t"], "d": i["d"], "k": KIND[i["kind"]], "u": _u(i["u"])} for i in mine if i["kind"] in ("news", "video") and _u(i["u"])][:3]
        orgs.append({"name": name.get(k, k), "n": v["n"], "kind": {KIND[a]: b for a, b in (v.get("kind") or {}).items()}, "tp": tp,
                     "one": (D["msg"].get("by_org") or {}).get(name.get(k, k), ""), "links": links})
    orgs.sort(key=lambda o: -o["n"])
    tr = D.get("trend") or {}
    return {"date": D["generated"], "msg": {k: D["msg"].get(k) for k in ("head", "lines", "by")}, "n": cur.get("n", 0),
            "tp": tr.get("tp") or [], "w": [w["k"] for w in (tr.get("w") or [])[:10]], "base": tr.get("base_days", 0), "orgs": orgs}


CSS = """<style>.tpv{font-size:13px}.tpv h4{margin:14px 0 6px}.tpv table{border-collapse:collapse;width:100%;font-size:12.5px}
.tpv td,.tpv th{border-bottom:1px solid var(--border,#e5e7eb);padding:5px 6px;text-align:left;vertical-align:top}.tpv .n{color:var(--muted,#6b7280);font-size:12px}
.tpv ul.s{background:var(--surface-2,#f4f6fa);border-radius:10px;padding:10px 14px 10px 28px}.tpv .w{overflow-x:auto}.tpv .up{color:#059669;font-weight:700}</style>"""


def build(sec=None):
    D = _load()
    if not D:
        return '<div class="tpv"><p class="n">데이터 준비 중 — 첫 수집은 매일 05:20(KST) 실행 뒤 반영됩니다.</p></div>'
    cur = (D.get("days") or {}).get(D["generated"]) or {}
    name = {t["k"]: t["name"] for t in D["targets"]}
    tr = D.get("trend") or {}
    M = D.get("msg") or {}
    by = cur.get("by") or {}
    hot = sorted(by.items(), key=lambda x: -x[1]["n"])
    s = [f"<b>{h(M.get('head', ''))}</b> ({'AI 초안' if M.get('by') == 'ai' else '규칙 문장'})"] + [h(x) for x in M.get("lines") or []]
    out = [CSS, '<div class="tpv">', f'<p class="n">기준 {h(D["generated"])} · 최근 7일 {cur.get("n", 0)}건 · 비교 기준 {tr.get("base_days", 0)}일치 누적(28일 쌓이면 급상승 판정이 정확해짐)</p>',
           '<ul class="s">' + "".join(f"<li>{x}</li>" for x in s) + "</ul>"]
    rows = []
    for k, v in hot:
        kd = v.get("kind") or {}
        tp = ", ".join(f"{h(a)} {b}" for a, b in sorted((v.get("tp") or {}).items(), key=lambda x: -x[1])[:3])
        act = ("활발 → 공동 연수·콘텐츠 협업 제안 타이밍" if v["n"] >= 5 else "관망" if v["n"] else "이번 주 공개 활동 적음")
        rows.append(f"<tr><td><b>{h(name.get(k, k))}</b></td><td>{v['n']}</td><td>{kd.get('news', 0)}</td><td>{kd.get('blog', 0)}</td><td>{kd.get('cafe', 0)}</td><td>{kd.get('video', 0)}</td><td>{tp}</td><td>{h(act)}</td></tr>")
    out.append('<h4>단체별 7일 활동</h4><div class="w"><table><tr><th>단체</th><th>합계</th><th>기사</th><th>블로그</th><th>카페</th><th>영상</th><th>주요 주제</th><th>다음 행동</th></tr>' + "".join(rows) + "</table></div>")
    T = "".join(f"<tr><td>{h(t['k'])}</td><td>{t['n']}</td><td>{t['base']}</td><td class='up'>{'NEW' if t.get('new') else ('+%.1f' % (t['n'] - t['base']))}</td></tr>" for t in tr.get("tp") or [])
    out.append('<h4>주제 흐름(7일 vs 직전 3주 평균)</h4><div class="w"><table><tr><th>주제</th><th>7일</th><th>평소</th><th>차이</th></tr>' + (T or "<tr><td>없음</td></tr>") + "</table></div>")
    out.append('<p class="n">자주 보인 말: ' + h(" · ".join(w["k"] for w in (tr.get("w") or [])[:15])) + "</p>")
    li = "".join(f"<tr><td>{h(i['d'] or '')}</td><td>{h(name.get(i['tg'], i['tg']))}</td><td>{h(KIND[i['kind']])}</td><td>"
                 + (f'<a href="{h(_u(i["u"]))}" target="_blank" rel="noopener noreferrer">{h(i["t"])}</a>' if _u(i["u"]) else h(i["t"]))
                 + f"</td><td>{h(', '.join(i.get('tp') or []))}</td></tr>" for i in (D.get("items") or [])[:120])
    out.append('<h4>최근 7일 글·영상 전체</h4><div class="w"><table><tr><th>날짜</th><th>단체</th><th>종류</th><th>제목(실명 가림)</th><th>주제</th></tr>' + li + "</table></div>")
    ch = ", ".join(f"{h(name.get(k, k))}: {h(v.get('title', ''))}" for k, v in (D.get("channels") or {}).items())
    out.append(f'<p class="n">출처: 네이버 검색 API(뉴스·블로그·카페, 무료 한도 — 막히면 구글 뉴스 RSS·다음 블로그/카페 검색으로 대체) · YouTube Data API(무료 한도{", 확인된 채널 " + ch if ch else ""}) · 핵심 문장 Gemini 무료 등급 1회/일. '
               '인스타그램·페이스북은 쿠키 수집을 하지 않기로 결정(2026-11-24) — 공식 경로가 생기면 추가. 본문·작성자 이름은 저장하지 않음. 원천 history/teacher_pulse.json.</p></div>')
    return "".join(out)


if __name__ == "__main__":
    print(json.dumps(cp(), ensure_ascii=False)[:800])
    print(re.sub("<[^>]+>", " ", build())[:600])
