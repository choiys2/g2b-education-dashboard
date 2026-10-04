#!/usr/bin/env python3
"""
주간 경영 보고(최근 7일) - live/weekly.html (사이트 full/weekly.html) + live/weekly_mail.txt(메일 본문용 평문)

매일 배포 때 다시 만들어지는 '최근 7일' 스냅샷이다. 월요일 아침 열면 지난 한 주 요약이 된다.
입력: combine_dashboard.py 가 남기는 live/_weekly_inputs.json, briefings/*.json
  python weekly_digest.py [out_html] [out_txt]
"""
import html
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

OUT_HTML = Path(sys.argv[1] if len(sys.argv) > 1 else "live/weekly.html")
OUT_TXT = Path(sys.argv[2] if len(sys.argv) > 2 else "live/weekly_mail.txt")
TRAINING = re.compile(r"연수|역량\s?강화|원격|위탁\s?교육|직무|교원|AI|인공지능|디지털")


def won(n):
    n = n or 0
    return f"{n / 1e8:.1f}억원" if n >= 1e8 else (f"{round(n / 1e4):,}만원" if n >= 1e4 else f"{n:,}원")


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or ""))


def main():
    today = date.today()
    wk = (today - timedelta(days=7)).isoformat()
    try:
        inp = json.loads(Path("live/_weekly_inputs.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        inp = {}
    bids = inp.get("bids", [])
    new_bids = sorted([b for b in bids if (b.get("공고일") or "") >= wk and TRAINING.search(b.get("공고명") or "")],
                      key=lambda b: -(b.get("예산") or 0))
    due = sorted([b for b in bids if today.isoformat() <= (b.get("마감일") or "") <= (today + timedelta(days=7)).isoformat()
                  and TRAINING.search(b.get("공고명") or "")], key=lambda b: b.get("마감일"))
    early = (inp.get("early") or {}).get("items", [])
    new_courses = [r for r in inp.get("new_courses", []) if (r.get("first_seen") or "") >= wk]
    briefs = []
    for f in sorted(Path("briefings").glob("????-??-??.json"))[-7:]:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("date", "") >= wk:
            briefs.append((d["date"], strip(d.get("lead", {}).get("headline"))))
    topics = inp.get("topics", [])[:3]
    contracts = inp.get("contracts", [])

    secs = []  # (제목, [(본문, 링크)])
    secs.append((f"신규 연수·AI 입찰공고 {len(new_bids)}건 (최근 7일, 예산 큰 순)",
                 [(f"{b.get('지역','')} · {b.get('발주기관','')} · {b.get('공고명','')} · {won(b.get('예산'))} · 마감 {b.get('마감일','-')}", b.get("url")) for b in new_bids[:10]]))
    secs.append((f"마감 임박 {len(due)}건 (7일 이내)",
                 [(f"{b.get('마감일')} · {b.get('발주기관','')} · {b.get('공고명','')} · {won(b.get('예산'))}", b.get("url")) for b in due[:10]]))
    secs.append((f"발주 조기 경보 {len(early)}건 (사전규격·발주계획)",
                 [(f"[{e['stage']}] {e['o']} · {e['t']} · {won(e['a'])} · {e['due'] or '-'} · {e['ready']}", e.get("url")) for e in early[:10]]))
    secs.append((f"경쟁사 신규 과정 {len(new_courses)}건 (최근 7일)",
                 [(f"{r.get('company','')} · {r.get('title','')}", r.get("url")) for r in new_courses[:10]]))
    secs.append(("2027 연수 개발 추천 상위 3",
                 [(f"{t['name']} — 점수 {t['score']} · 공고 {t['n']}건 · " + " / ".join(p['title'] for p in t.get('proposals', [])[:2]), None) for t in topics]))
    if contracts:
        secs.append(("계약 기준 B2G 점유(수의계약 포함, 누적)",
                     [(f"{c['name']} · {c['n']}건 · {won(c['amount'])} ({c['share']}%)", None) for c in contracts[:5]]))
    secs.append((f"조간 브리핑 헤드라인 {len(briefs)}호", [(f"{d} · {h}", f"../news/{d}.html") for d, h in briefs]))

    # 평문(메일 본문)
    lines = [f"[비바샘연수원 B2G 주간 보고] {wk} ~ {today.isoformat()}", ""]
    for title, items in secs:
        lines.append(f"■ {title}")
        lines += [f"  - {t}" for t, _ in items] or ["  - 해당 없음"]
        lines.append("")
    lines.append("대시보드: https://choiys2.github.io/g2b-education-dashboard/full/")
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    e = html.escape

    def li(t, u):
        inner = f'<a href="{e(u)}" target="_blank" rel="noopener">{e(t)}</a>' if u else e(t)
        return f"<li>{inner}</li>"

    body = "".join(
        f"<section><h2>{e(title)}</h2>"
        + ("<ul>" + "".join(li(t, u) for t, u in items) + "</ul>" if items else "<p class='none'>해당 없음</p>")
        + "</section>" for title, items in secs)
    OUT_HTML.write_text(f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>B2G 주간 보고</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#14202e;--muted:#5f6b7a;--accent:#0f766e;--line:#e3e7ec}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1420;--card:#182234;--ink:#eef2fa;--muted:#9aa6bb;--accent:#3fc1ad;--line:#2a3448}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:Pretendard,-apple-system,"Malgun Gothic",sans-serif;line-height:1.6}}
.wrap{{max-width:880px;margin:0 auto;padding:28px 16px 60px}} h1{{font-size:24px;margin:0 0 4px}}
.sub{{color:var(--muted);font-size:14px;margin:0 0 20px}} section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}}
h2{{font-size:15.5px;margin:0 0 8px;color:var(--accent)}} ul{{margin:0;padding-left:18px;font-size:13.5px}} li{{margin:3px 0;overflow-wrap:anywhere}}
a{{color:inherit}} .none{{color:var(--muted);font-size:13px;margin:0}} .bar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}}
.bar a,.bar button{{font:inherit;font-size:13px;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;cursor:pointer}}
@media print{{.bar{{display:none}}}}
</style></head><body><div class="wrap">
<h1>B2G 주간 보고</h1><p class="sub">{wk} ~ {today.isoformat()} · 매일 자동 갱신(최근 7일) · 나라장터·경쟁사 카탈로그·조간 브리핑 기준</p>
<div class="bar"><a href="./">대시보드로</a><a href="weekly_mail.txt" download>메일 본문(텍스트)</a><button onclick="print()">인쇄·PDF 저장</button></div>
{body}</div></body></html>""", encoding="utf-8")
    print(f"weekly: 신규 {len(new_bids)} · 마감임박 {len(due)} · 조기경보 {len(early)} · 신규과정 {len(new_courses)} · 브리핑 {len(briefs)}")


if __name__ == "__main__":
    main()
