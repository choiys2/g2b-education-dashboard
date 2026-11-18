#!/usr/bin/env python3
"""관리 탭 '마케팅 보드' 위쪽: 3사 마케팅 현황 시각화 + 트렌드 코리아 2027 × 교원연수 아이디어 제안.

- 현황: 공개 수집된 경쟁사 이벤트·과정 목록(history/)만 쓴다. 개인정보 없음.
- 제안: 비공개 저장소 strategy_room/mkt_trends.json(채팅으로 갱신)에서만 읽는다(내부 판단 → 관리 탭 암호문 안에만).
"""
import html
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import adm_viz as V

HERE = Path(__file__).parent
E = html.escape
COS = ["비바샘연수원", "아이스크림", "티처빌"]
SHORT = {"비바샘연수원": "비바샘", "아이스크림": "아이스크림", "티처빌": "티처빌"}
MECH = [("단체·세트", r"단체|SET|세트|3인|패키지|결합"), ("사은품·경품", r"사은품|선물|증정|당첨|다이어리|젤리|상품권|시상|네이버페이|N페이"),
        ("가격 혜택", r"할인|특가|1\+1|PASS|패스|무료|쿠폰"), ("자료 제공", r"자료|웹앱|미리캔버스|수업"),
        ("참여·커뮤니티", r"서포터즈|쌤포터즈|후기|모집|이야기|공모전|티클"), ("제휴", r"스픽|듀오링고|교보|GPT|gemini|zep|제휴")]
MCOL = dict(zip([m for m, _ in MECH] + ["기타"], V.PAL))


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _jsonl(p):
    f = HERE / p
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []


def mech(title):
    for m, rx in MECH:
        if re.search(rx, title or "", re.I):
            return m
    return "기타"


def fmt_of(credit, title):
    c, t = credit or "", title or ""
    if re.search(r"연수\s*\+|\+\s*(교구|도서|자료|키트)", t):
        return "연수+실물 묶음"
    if "모듈" in c or "미만" in c:
        return "모듈(짧은 과정)"
    m = re.search(r"(\d+)\s*차시", c)
    if m:
        n = int(m.group(1))
        return "모듈(짧은 과정)" if n < 15 else "1학점" if n < 30 else "2학점 이상"
    m = re.search(r"(\d)\s*학점", c)
    if m:
        return "1학점" if m.group(1) == "1" else "2학점 이상"
    if "자율" in c:
        return "자율"
    return "기타"


FCOL = {"모듈(짧은 과정)": V.PAL[3], "1학점": V.PAL[0], "2학점 이상": V.PAL[6], "연수+실물 묶음": V.PAL[1], "자율": V.PAL[2], "기타": V.PAL[7]}


def _private_trends():
    try:
        from strategy_room import _private
        d = _private()
        f = d / "strategy_room" / "mkt_trends.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None
    except Exception:
        return None


def market_html(sec):
    snap = _j("history/competitor_content_snapshot.json", {}) or {}
    cat = _j("history/competitor_course_catalog.json", {}) or {}
    ev = _jsonl("history/competitor_events.jsonl")
    nc = _jsonl("history/competitor_new_courses.jsonl")
    if not (snap.get("companies") or cat.get("companies")):
        return sec("3사 마케팅 현황", "", '<p style="color:var(--muted);font-size:13px;">데이터 준비 중</p>')
    # 진행 중 이벤트의 유형
    live = {co: [e.get("title", "") for e in (snap.get("companies", {}).get(co) or {}).get("events", [])] for co in COS}
    mrows = [(SHORT[co], Counter(mech(t) for t in live[co])) for co in COS]
    mseries = [(m, MCOL[m]) for m in [x for x, _ in MECH] + ["기타"] if any(d.get(m) for _, d in mrows)]
    # 과정 형태·가격
    frows, prices, cats = [], {}, {}
    for co in COS:
        cs = ((cat.get("companies") or {}).get(co) or {}).get("courses") or []
        frows.append((SHORT[co], Counter(fmt_of(c.get("credit"), c.get("title")) for c in cs)))
        p1 = sorted(c["price"] for c in cs if isinstance(c.get("price"), (int, float)) and c["price"] > 0 and fmt_of(c.get("credit"), c.get("title")) == "1학점")
        prices[co] = p1[len(p1) // 2] if p1 else 0
        cats[co] = Counter((c.get("category") or "기타") for c in cs)
    fseries = [(f, FCOL[f]) for f in FCOL if any(d.get(f) for _, d in frows)]
    # 최근 8주 신규 이벤트 감지 수
    today = date.today()
    wk = defaultdict(int)
    for e in ev:
        try:
            d = date.fromisoformat(e["first_seen"])
        except Exception:
            continue
        if not e.get("seed") and (today - d).days < 56:
            wk[(today - d).days // 7] += 1
    weeks = [(f"{(today - timedelta(days=7 * i)).strftime('%m/%d')}주", wk.get(i, 0)) for i in range(7, -1, -1)]
    new60 = Counter(n["company"] for n in nc if n.get("first_seen", "") >= (today - timedelta(days=60)).isoformat())
    tl = [(f"{len(live[co])}건", f"{SHORT[co]} 진행 중 이벤트") for co in COS] + [(f"{prices['비바샘연수원'] // 1000 if prices.get('비바샘연수원') else '-'}천원", "비바샘 1학점 가격 중앙값")]
    bundle = {SHORT[co]: d.get("연수+실물 묶음", 0) for co, (_, d) in zip(COS, frows)}
    insight = (f"진행 중 이벤트는 아이스크림 {len(live['아이스크림'])}건·티처빌 {len(live['티처빌'])}건·비바샘 {len(live['비바샘연수원'])}건. "
               + " · ".join(f"{lab} 주력 유형 ‘{d.most_common(1)[0][0]}’" for lab, d in mrows if d) + ". "
               f"‘연수+실물 묶음’ 과정은 " + " · ".join(f"{k} {v}개" for k, v in bundle.items()) + "(폼팩터 시프트 신호). "
               "이벤트 대부분이 신규 획득형이라 유지(리텐션) 설계가 3사 공통 빈칸입니다.")
    body = (V.CSS + V.tiles(tl)
            + f'<p style="font-size:13px;margin:0 0 12px;">💡 {E(insight)}</p>'
            + V.grid(("진행 중 이벤트 유형", V.stacked(mrows, mseries)),
                     ("과정 형태 구성(비중)", V.stacked(frows, fseries, pct=True)),
                     ("1학점 과정 가격 중앙값", V.hbars([(SHORT[co], prices[co], V.CO[co]) for co in COS], fmt=lambda v: f"{v:,.0f}", unit="원")),
                     ("최근 60일 신규 과정 감지", V.hbars([(SHORT[co], new60.get(co, 0), V.CO[co]) for co in COS], unit="개")),
                     ("경쟁사 신규 이벤트 감지(주별)", V.cols(weeks, color=V.PAL[1])),
                     ("과정 분야 Top 6(3사 합계)", V.hbars([kv for kv in sum((cats[c] for c in COS), Counter()).most_common(8) if kv[0] not in ("기타", "-", "")][:6], color=V.PAL[6], unit="개"))))
    rows = "".join(f"<tr><td>{E(SHORT[co])}</td><td><span style='display:inline-block;width:8px;height:8px;border-radius:2px;background:{MCOL[mech(t)]};margin-right:5px;'></span>{E(mech(t))}</td><td>{E(t)}</td></tr>"
                   for co in COS for t in live[co][:6])
    body += ("<details style='margin-top:12px;'><summary style='cursor:pointer;font-weight:700;font-size:13px;'>진행 중 이벤트 목록 보기</summary>"
             f"<div class='tbl-wrap'><table><thead><tr><th>회사</th><th>유형</th><th>이벤트</th></tr></thead><tbody>{rows}</tbody></table></div></details>")
    return sec("3사 마케팅 현황판", f"비바샘·아이스크림·티처빌 공개 이벤트와 과정 목록 기준 · 과정 기준일 {E(str(cat.get('captured_date') or '-'))} · 매일 갱신", body), live


def trends_html(sec, live):
    T = _private_trends()
    if not T:
        return sec("트렌드 코리아 2027 × 교원연수 제안", "", '<p style="color:var(--muted);font-size:13px;">데이터 준비 중</p>')
    allev = [(SHORT[co], t) for co in COS for t in live.get(co, [])]
    tr = T.get("trends") or []
    # 우선순위 매트릭스(효과 높고 품 적은 것 먼저)
    ranked = sorted(tr, key=lambda t: (-(t.get("impact", 0) * 2 - t.get("effort", 0)), t.get("no", 0)))
    top = ranked[:5]
    cells = defaultdict(list)
    for t in tr:
        cells[("high" if t.get("impact", 0) >= 4 else "low", "easy" if t.get("effort", 0) <= 2 else "hard")].append(t)
    q = lambda k, title, bg: (f'<div style="border:1px solid var(--border);border-radius:10px;padding:10px;background:{bg};"><b style="font-size:12.5px;">{title}</b>'
                              + "".join(f'<div style="font-size:12.5px;margin-top:4px;">#{t["no"]} {E(t["name"])}</div>' for t in cells[k]) + "</div>")
    matrix = ('<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;max-width:620px;">'
              + q(("high", "easy"), "⚡ 바로 실행 (효과↑·품↓)", "color-mix(in srgb,#1baf7a 14%,transparent)")
              + q(("high", "hard"), "🏗️ 전략 과제 (효과↑·품↑)", "color-mix(in srgb,#2a78d6 12%,transparent)")
              + q(("low", "easy"), "🧪 작은 실험 (효과↓·품↓)", "color-mix(in srgb,#eda100 12%,transparent)")
              + q(("low", "hard"), "⏸️ 보류 (효과↓·품↑)", "color-mix(in srgb,#8a8a85 12%,transparent)") + "</div>")
    toprows = "".join(f"<tr><td><b>{i}</b></td><td><b>{E(t['name'])}</b></td><td>{E(t['idea'])}</td><td>{E(t['test'])}</td><td>{E(t['kpi'])}</td></tr>" for i, t in enumerate(top, 1))
    cards = []
    for t in tr:
        hits = [f"{c}: {x}" for c, x in allev if t.get("signal") and re.search(t["signal"], x, re.I)][:3]
        sig = ("".join(f"<li>{E(h)}</li>" for h in hits) if hits else "<li style='color:var(--muted);'>진행 중 경쟁사 이벤트에서 아직 신호 없음 → 선점 기회</li>")
        bar = lambda v, c: f'<span style="display:inline-block;width:{v * 12}px;height:6px;border-radius:3px;background:{c};vertical-align:middle;"></span>'
        cards.append(f'<div style="border:1px solid var(--border);border-radius:12px;padding:12px;">'
                     f'<div style="display:flex;justify-content:space-between;gap:6px;"><b>{t["no"]:02d} {E(t["name"])}</b>'
                     f'<span style="font-size:11px;color:var(--muted);white-space:nowrap;">효과 {bar(t.get("impact", 0), "#2a78d6")} 품 {bar(t.get("effort", 0), "#eb6834")}</span></div>'
                     f'<p style="margin:4px 0 6px;font-size:12px;color:var(--muted);">{E(t["line"])}</p>'
                     f'<p style="margin:0 0 6px;font-size:12.5px;"><b>교사 시장</b> {E(t["teacher"])}</p>'
                     f'<p style="margin:0 0 4px;font-size:12.5px;"><b>경쟁사 신호</b></p><ul style="margin:0 0 6px;padding-left:18px;font-size:12px;">{sig}</ul>'
                     f'<p style="margin:0 0 6px;font-size:12.5px;"><b>💡 제안</b> {E(t["idea"])}</p>'
                     f'<p style="margin:0;font-size:12px;color:var(--muted);">30일 실험: {E(t["test"])} · KPI: {E(t["kpi"])}</p></div>')
    iss = "".join(f'<div style="border-left:3px solid #6250d6;padding:4px 10px;"><b style="font-size:12.5px;">{E(i["m"])}</b><div style="font-size:12.5px;">{E(i["t"])}</div>'
                  f'<div style="font-size:12px;color:var(--muted);">→ {E(i["hook"])}</div></div>' for i in T.get("issues") or [])
    return (sec("💡 이번 달 실행 제안 Top 5", f"트렌드 코리아 2027 10대 트렌드 × 3사 현황에서 뽑은 제안(AI 초안, {E(T.get('as_of', ''))}) · 채팅으로 고치면 바로 반영",
                f"<div class='tbl-wrap'><table><thead><tr><th>#</th><th>트렌드</th><th>아이디어</th><th>30일 실험</th><th>KPI</th></tr></thead><tbody>{toprows}</tbody></table></div>"
                f"<p class='vz-h' style='margin-top:14px;font-weight:700;font-size:13px;'>효과 × 품 매트릭스</p>{matrix}")
            + sec("트렌드 코리아 2027 × 교원연수 아이디어 10", "트렌드별: 교사 시장에서의 뜻 → 지금 경쟁사 신호(진행 중 이벤트 자동 대조) → 제안 → 30일 실험·KPI",
                  f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(330px,100%),1fr));gap:12px;">{"".join(cards)}</div>')
            + sec("2027 교육 이슈 × 마케팅 훅", "학사 일정·정책 이슈에 맞춰 위 아이디어를 언제 꺼낼지",
                  f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;">{iss}</div>'))


def build(sec):
    r = market_html(sec)
    if isinstance(r, tuple):
        mk, live = r
    else:
        mk, live = r, {}
    return mk + trends_html(sec, live)


def comp_charts(sec):
    """'경쟁사 변화' 칸 위: 최근 8주 3사 활동량(신규 이벤트·신규 과정·몰 신상품) 추이"""
    today = date.today()
    wkey = lambda s: (today - date.fromisoformat(s)).days // 7
    def weekly(rows, keyf):
        d = defaultdict(Counter)
        for r in rows:
            try:
                w = wkey(r["first_seen"])
            except Exception:
                continue
            if 0 <= w < 8 and not r.get("seed"):
                d[w][keyf(r)] += 1
        return d
    ev = weekly(_jsonl("history/competitor_events.jsonl"), lambda r: r.get("company"))
    nc = weekly(_jsonl("history/competitor_new_courses.jsonl"), lambda r: r.get("company"))
    ml = weekly(_jsonl("history/competitor_mall_new.jsonl"), lambda r: r.get("mall"))
    lab = lambda i: (today - timedelta(days=7 * i)).strftime("%m/%d") + "주"
    series = [(SHORT[c], V.CO[c]) for c in COS]
    rowsf = lambda d: [(lab(i), {SHORT.get(k, k): v for k, v in d.get(i, Counter()).items()}) for i in range(7, -1, -1)]
    malls = sorted({m for c in ml.values() for m in c})
    mser = [(m, V.PAL[(i + 3) % 7]) for i, m in enumerate(malls)]
    tot = lambda d: sum(sum(c.values()) for c in d.values())
    body = (V.CSS + V.tiles([(f"{tot(ev)}건", "최근 8주 새 이벤트"), (f"{tot(nc)}개", "최근 8주 새 과정"), (f"{tot(ml)}개", "최근 8주 몰 새 상품")])
            + V.grid(("새 이벤트(주별·회사별)", V.stacked(rowsf(ev), series)),
                     ("새 과정(주별·회사별)", V.stacked(rowsf(nc), series)),
                     ("몰 새 상품(주별)", V.stacked([(l, d) for l, d in rowsf(ml)], mser) if mser else "")))
    return sec("경쟁사 활동 추이 (최근 8주)", "주별로 새로 감지된 이벤트·과정·몰 상품 수 — 막대가 길어지는 주는 경쟁사가 판촉을 몰아치는 시기입니다", body)
