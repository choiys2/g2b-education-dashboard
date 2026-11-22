#!/usr/bin/env python3
"""관리 칸 '📱 SNS 핵심 계정'(사용자 요청 2026-11-23) — 단체 공식·회장/임원·교사 인플루언서·경쟁 연수원의 인스타그램·페이스북.

- 계정 목록: static_data/sns_watch.enc.json (공개키 암호화, STRATEGY_KEY 로만 복호화). 개인 이름·계정은 평문으로 두지 않는다.
- 주간 지표: history/sns_metrics.enc.json (sns_collect.py — Meta 공식 API, 토큰이 있을 때만). 없으면 목록·검색 시점 값만 표시.
- 결과 HTML 은 관리 탭 암호문 안에만. 링크는 https + instagram.com / facebook.com 만, 모든 글자 escape.
"""
import json
import os
import re
from html import escape as h
from pathlib import Path

HERE = Path(__file__).parent
LIST = HERE / "static_data" / "sns_watch.enc.json"
METRICS = HERE / "history" / "sns_metrics.enc.json"
CATS = [("org", "🏛️ 단체 공식"), ("leader", "👔 회장·임원"), ("influencer", "⭐ 교사 인플루언서"), ("comp", "🏢 경쟁 출판사·연수원")]
HANDLE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
FB = re.compile(r"^https://(www\.)?facebook\.com/[^\s\"'<>]+$")


def _dec(path):
    plain = os.environ.get("SNS_WATCH_PLAIN")  # 로컬 점검용(평문 경로) — 배포에서는 쓰지 않음
    if plain and path == LIST and Path(plain).exists():
        return json.loads(Path(plain).read_text(encoding="utf-8"))
    key = os.environ.get("STRATEGY_KEY", "")
    if not key or not path.exists():
        return None
    try:
        import strategy_crypto
        return strategy_crypto.decrypt(json.loads(path.read_text(encoding="utf-8")), key)
    except Exception:  # noqa: BLE001
        return None


def accounts():
    d = _dec(LIST) or {}
    return d, [a for a in d.get("accounts") or [] if isinstance(a, dict)]


def _ig(u):
    return f'<a href="https://www.instagram.com/{h(u)}/" target="_blank" rel="noopener noreferrer">@{h(u)}</a>' if u and HANDLE.match(u) else ""


def _fb(u):
    return f'<a href="{h(u)}" target="_blank" rel="noopener noreferrer">페이스북</a>' if u and FB.match(u) else ""


def _n(v):
    return f"{v:,}" if isinstance(v, (int, float)) and v else "-"


CSS = """<style>.snw{font-size:13px}.snw h4{margin:16px 0 6px}.snw table{border-collapse:collapse;width:100%;font-size:12.5px}
.snw td,.snw th{border-bottom:1px solid var(--border,#e5e7eb);padding:5px 6px;text-align:left;vertical-align:top}.snw .n{color:var(--muted,#6b7280);font-size:12px}
.snw ul.s{background:var(--surface-2,#f4f6fa);border-radius:10px;padding:10px 14px 10px 28px}.snw .p{font-weight:700}.snw .p.상{color:#dc2626}.snw .p.중{color:#d97706}
.snw .w{overflow-x:auto}.snw .bar{display:inline-block;height:8px;border-radius:4px;background:#e1306c;vertical-align:middle;margin-right:4px}</style>"""


def build(sec=None):
    D, A = accounts()
    if not A:
        return '<div class="snw"><p class="n">데이터 준비 중 (계정 목록 복호화 키가 필요합니다)</p></div>'
    M = (_dec(METRICS) or {}).get("accounts") or {}
    gen = (_dec(METRICS) or {}).get("generated")
    for a in A:
        m = M.get(a.get("ig") or "") or {}
        a["F"] = m.get("followers") or a.get("f")
        a["P"] = m.get("media") or a.get("posts")
        a["eng"], a["r30"], a["tags"], a["dF"] = m.get("eng"), m.get("posts30"), m.get("tags") or {}, m.get("dF")
    have_ig = sum(1 for a in A if a.get("ig"))
    slots = [a for a in A if a.get("cat") == "leader" and not (a.get("ig") or a.get("fb"))]
    infl = [a for a in A if a.get("cat") == "influencer" and not a.get("ig")]
    top = sorted([a for a in A if a.get("F")], key=lambda a: -(a["F"] or 0))[:3]
    s = [
        f"계정 {len(A)}개 중 인스타그램 확인 {have_ig}개. 팔로워 상위: {h(', '.join('%s %s' % (a.get('org'), _n(a['F'])) for a in top))}.",
        f"회장·임원 개인 계정 슬롯 {len(slots)}개가 비어 있습니다 — 이름·계정을 알려 주시면 암호화해 채웁니다.",
        f"교사 인플루언서 {len(infl)}명은 유튜브 규모로 골랐고 인스타그램 계정 확인이 필요합니다.",
        ("주간 지표: " + h(gen) + " 수집") if gen else "주간 자동 지표(팔로워 증감·게시 빈도·반응)는 공식 API 토큰을 넣으면 시작됩니다.",
    ]
    out = [CSS, '<div class="snw">', f'<p class="n">목록 기준 {h(D.get("as_of", ""))} · {h(D.get("note", ""))}</p>',
           '<ul class="s">' + "".join(f"<li>{x}</li>" for x in s) + "</ul>"]
    mx = max([a["F"] or 0 for a in A] + [1])
    for k, title in CATS:
        rows = [a for a in A if a.get("cat") == k]
        if not rows:
            continue
        tr = []
        for a in sorted(rows, key=lambda a: ({"상": 0, "중": 1}.get(a.get("pri"), 2), -(a.get("F") or a.get("f_yt") or 0))):
            who = h(a.get("org", "")) + (f" · {h(a.get('role'))}" if a.get("role") and a.get("role") != "공식" else "")
            nm = h(a.get("name") or "")
            f = a.get("F")
            fcell = (f'<span class="bar" style="width:{max(2, (f or 0) / mx * 70):.0f}px"></span>{_n(f)}' if f else
                     (f"유튜브 {_n(a.get('f_yt'))}" if a.get("f_yt") else "-"))
            d = a.get("dF")
            dcell = f"{d:+,}" if isinstance(d, int) else ""
            tg = ", ".join(f"{h(t)} {n}" for t, n in sorted(a["tags"].items(), key=lambda x: -x[1])[:3])
            tr.append(f"<tr><td>{who}<div class='n'>{nm}</div></td><td>{_ig(a.get('ig')) or '<span class=n>확인 필요</span>'} {_fb(a.get('fb'))}</td>"
                      f"<td>{fcell}</td><td>{dcell}</td><td>{_n(a.get('P'))}</td><td>{_n(a.get('r30'))}</td><td>{h(tg)}</td>"
                      f"<td class='p {h(a.get('pri', ''))}'>{h(a.get('pri', ''))}</td><td>{h(a.get('memo', ''))}</td></tr>")
        out.append(f'<h4>{title}</h4><div class="w"><table><tr><th>대상</th><th>계정</th><th>팔로워</th><th>주간 증감</th><th>게시물</th><th>30일 게시</th><th>최근 주제</th><th>우선</th><th>메모</th></tr>{"".join(tr)}</table></div>')
    out.append('<p class="n">인스타그램·페이스북은 자동 수집(크롤)을 하지 않습니다. 지표는 Meta 공식 API(비즈니스·크리에이터 계정만 조회 가능)로만 가져오며, '
               '게시물 본문은 저장하지 않고 주제 유형 수만 셉니다. 개인 계정은 공개 활동 계정만, 목적은 협력·섭외 타이밍 판단.</p></div>')
    return "".join(out)


if __name__ == "__main__":
    print(re.sub("<[^>]+>", " ", build())[:1500])
