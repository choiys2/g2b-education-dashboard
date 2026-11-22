#!/usr/bin/env python3
"""교사단체 분석(사용자 요청 2026-11-22).

- cp(): CP 탭 '교사단체 분석' 데이터 — 기관별 주간 활동량·이슈 유형·리더십/성명 동향(실명 가림, 원문 링크).
- build(sec): 관리 칸 '🏛️ 교사단체 해석' — 활동 급증·리더십 교체 = 접촉 타이밍, MOU 단체 최근 움직임, 경쟁 연수원 동향, 제안.
  결과 HTML 은 관리 탭 암호문 안에만. 외부 텍스트는 모두 escape, 링크는 https 만.
"""
import json
import re
from html import escape as h
from pathlib import Path

HERE = Path(__file__).parent


def _load(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def _url(u):
    return u if isinstance(u, str) and u.startswith("https://") else ""


def cp():
    D = _load("history/teacher_org_watch.json")
    if not D:
        return None
    orgs = []
    for o in D["orgs"]:
        orgs.append({k: o[k] for k in ("name", "cat", "n", "weekly", "tags", "r4", "p4avg", "last")} |
                    {"items": [{"t": x["t"], "d": x["d"], "src": x["src"], "u": _url(x["u"]), "tg": x["tg"]} for x in o["all"][:6]]})
    clean = lambda L: [{"t": x["t"], "d": x["d"], "src": x["src"], "u": _url(x["u"]), "org": x["org"], "cat": x["cat"], "tg": x["tg"]} for x in L]
    return {"generated": D["generated"], "weeks": D["weeks"], "cats": D["cats"], "tags": D["tags"], "orgs": orgs,
            "leadership": clean(D["leadership"][:12]), "stance": clean(D["stance"][:10])}


CSS = """<style>.tov{font-size:13px}.tov h4{margin:14px 0 8px}.tov table{border-collapse:collapse;width:100%;font-size:12.5px}
.tov td,.tov th{border-bottom:1px solid var(--border,#e5e7eb);padding:5px 6px;text-align:left;vertical-align:top}.tov .n{color:var(--muted,#6b7280);font-size:12px}
.tov .up{color:#059669;font-weight:700}.tov .dn{color:#dc2626;font-weight:700}.tov ul.s{background:var(--surface-2,#f4f6fa);border-radius:10px;padding:10px 14px 10px 28px}
.tov .g{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr));gap:14px}.tov .c{border:1px solid var(--border,#e5e7eb);border-radius:10px;padding:10px 12px;overflow-x:auto}</style>"""


def _a(u, t):
    u = _url(u)
    return f'<a href="{h(u)}" target="_blank" rel="noopener noreferrer">{h(t)}</a>' if u else h(t)


def build(sec=None):
    D = cp()
    if not D:
        return '<div class="tov"><p class="n">데이터 준비 중</p></div>'
    G = _load("static_data/teacher_groups.json", {}) or {}
    mou = {}
    for g in (G.get("national") or []) + (G.get("regional") or []):
        if g.get("mou"):
            mou[re.sub(r"\s*\(.*\)", "", g.get("name", ""))] = g.get("mou_note") or "MOU"
    O = D["orgs"]
    hot = sorted([o for o in O if o["r4"] >= 3 and o["r4"] > o["p4avg"] * 1.5], key=lambda o: -o["r4"])
    quiet = [o for o in O if o["cat"] != "pub" and o["n"] == 0]
    lead_orgs = sorted({x["org"] for x in D["leadership"]})
    pub = sorted([o for o in O if o["cat"] == "pub" and o["name"] != "비바샘 연수원"], key=lambda o: -o["r4"])
    pubtxt = ", ".join("%s(%d)" % (o["name"], o["r4"]) for o in pub[:3]) or "없음"
    s = [
        f"최근 4주 활동 급증: <b>{h(', '.join(o['name'] for o in hot) or '없음')}</b> — 이슈 발언이 많은 시기는 공동 연수·자문 제안보다 '입장 정리용 자료' 제공이 먹힌다.",
        f"리더십·인선 관련 소식이 잡힌 곳: <b>{h(', '.join(lead_orgs) or '없음')}</b> — 집행부 교체·선거 시기는 새 사업 협의의 창이 열리는 때(취임 100일 안에 인사·제안).",
        f"경쟁 출판사·연수원 중 최근 4주 노출 상위: <b>{h(pubtxt)}</b>.",
        f"소식이 잡히지 않는 단체 {len(quiet)}곳 — 공개 활동이 적은 단체는 뉴스 대신 회원 커뮤니티·교육청 연수 이력으로 따로 확인.",
    ]
    out = [CSS, '<div class="tov">', f'<p class="n">기준 {h(D["generated"])} · 최근 180일 · 기관 {len(O)}곳</p>',
           '<ul class="s">' + "".join(f"<li>{x}</li>" for x in s) + "</ul>"]
    rows = []
    for o in sorted(O, key=lambda o: -o["r4"]):
        m = next((v for k, v in mou.items() if k and (k in o["name"] or o["name"] in k)), "")
        trend = o["r4"] - o["p4avg"]
        lead = "●" if o["name"] in lead_orgs else ""
        act = ("리더십 변화 → 인사·제안 타이밍" if lead else "") or ("활동 급증 → 이슈 자료 제공" if o in hot else "") or \
              ("MOU 후속: 공동 연수·콘텐츠 일정 확인" if m else "") or ("관망" if o["n"] else "공개 활동 적음 — 커뮤니티 확인")
        rows.append(f"<tr><td>{h(o['name'])}<div class='n'>{h(D['cats'].get(o['cat'], ''))}</div></td><td>{o['n']}</td><td>{o['r4']}</td>"
                    f"<td class='{'up' if trend > 0 else 'dn' if trend < 0 else ''}'>{trend:+.1f}</td><td>{lead}</td><td>{h(m)}</td><td>{h(act)}</td></tr>")
    out.append('<div class="c"><h4>기관별 판단표</h4><table><tr><th>기관</th><th>180일</th><th>최근 4주</th><th>직전 대비</th><th>리더십</th><th>MOU</th><th>다음 행동</th></tr>' + "".join(rows) + "</table></div>")
    L = "".join(f"<tr><td>{h(x['d'])}</td><td>{h(x['org'])}</td><td>{_a(x['u'], x['t'])}</td></tr>" for x in D["leadership"][:10])
    S = "".join(f"<tr><td>{h(x['d'])}</td><td>{h(x['org'])}</td><td>{_a(x['u'], x['t'])}</td></tr>" for x in D["stance"][:10])
    out.append(f'<div class="g"><div class="c"><h4>리더십·인선 소식</h4><table>{L or "<tr><td>없음</td></tr>"}</table></div>'
               f'<div class="c"><h4>성명·입장(정책 온도)</h4><table>{S or "<tr><td>없음</td></tr>"}</table></div></div>')
    out.append('<p class="n">실명은 저장하지 않고 ○○○로 가렸습니다 — 인물 확인은 원문 링크로. MOU 표시는 교사단체 조사표 기준. '
               '원천: 뉴스 검색(무료)·레이더·교사단체 소식 주 1회 누적(history/teacher_org_watch.json).</p></div>')
    return "".join(out)


if __name__ == "__main__":
    import re as _r
    print(_r.sub("<[^>]+>", " ", build())[:1500])
