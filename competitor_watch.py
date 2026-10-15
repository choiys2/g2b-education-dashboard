#!/usr/bin/env python3
"""
경쟁사 변화 감지(대표 전용 화면용). 새로 수집하지 않고 이미 쌓이는 공개 데이터를 엮는다.

- 홈페이지 이벤트: competitor_content_scrape.py 결과(live/competitor_content_export.json, 없으면
  history 스냅샷)에서 처음 본 이벤트를 history/competitor_events.jsonl 에 누적한다(첫 실행분은 기준선).
- 신규 과정: history/competitor_new_courses.jsonl (카탈로그 크롤링이 누적)
- B2G 계약·낙찰: history/competitor_contracts.jsonl · competitor_wins.jsonl (나라장터 공개 정보)

  python competitor_watch.py            # 이벤트 로그 갱신(배포 워크플로에서 매일 1회)
  build() -> dict                       # combine_dashboard.py 가 대표 전용 암호문에 싣는다
"""
import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

OWN = "비바샘연수원"
EVENTS_LOG = Path("history/competitor_events.jsonl")
LIVE = Path("live/competitor_content_export.json")
SNAP = Path("history/competitor_content_snapshot.json")

# 이벤트·과정 제목 분류(첫 일치)
KINDS = [
    ("무상·무료", r"무료|무상|0원|공짜"),
    ("AI", r"AI|인공지능|생성형|챗GPT|GPT|제미나이|코딩|디지털"),
    ("단체·학교", r"단체|학교로|방문|찾아가는|구독|연수원 단체"),
    ("할인·사은품", r"할인|선물|증정|쿠폰|페이|커피|젤리|받아가|이벤트|PASS|결산|축제"),
]


def _jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def kind(title):
    for k, rx in KINDS:
        if re.search(rx, title or "", re.I):
            return k
    return "기타"


def _today_events():
    src = LIVE if LIVE.exists() else SNAP
    if not src.exists():
        return None, {}
    d = json.loads(src.read_text(encoding="utf-8"))
    comps = d.get("companies") or {}
    if isinstance(comps, list):
        comps = {c.get("name") or c.get("company"): c for c in comps}
    return d.get("captured_date") or date.today().isoformat(), {k: (v or {}).get("events") or [] for k, v in comps.items()}


def update_log():
    """오늘 처음 본 경쟁사 이벤트를 누적. 로그가 비어 있으면 현재 목록을 기준선(seed)으로 기록한다."""
    day, comps = _today_events()
    if not comps:
        print("경쟁사 이벤트 데이터 없음 - 건너뜀")
        return 0
    log = _jsonl(EVENTS_LOG)
    seen = {(r["company"], r["title"]) for r in log}
    seed = not log
    new = []
    for co, evs in comps.items():
        if co == OWN:
            continue
        for e in evs:
            t = (e.get("title") or "").strip()
            if t and (co, t) not in seen:
                seen.add((co, t))
                new.append({"first_seen": day, "company": co, "title": t[:120], "period": e.get("period", ""), "seed": seed})
    if new:
        EVENTS_LOG.parent.mkdir(exist_ok=True)
        with EVENTS_LOG.open("a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"경쟁사 이벤트 {'기준선' if seed else '신규'} {len(new)}건 기록")
    return len(new)


def build(today=None, days=30):
    today = today or date.today()
    since = (today - timedelta(days=days)).isoformat()
    wk = (today - timedelta(days=7)).isoformat()
    items = []
    for r in _jsonl(EVENTS_LOG):
        if not r.get("seed") and r.get("first_seen", "") >= since:
            items.append({"d": r["first_seen"], "co": r["company"], "type": "이벤트", "kind": kind(r["title"]), "title": r["title"], "note": r.get("period", "")})
    for r in _jsonl("history/competitor_new_courses.jsonl"):
        if r.get("company") != OWN and r.get("first_seen", "") >= since:
            note = " · ".join(x for x in [r.get("category"), r.get("credit"), f"{r['price']:,}원" if r.get("price") else ""] if x)
            items.append({"d": r["first_seen"], "co": r["company"], "type": "신규 과정", "kind": kind(r.get("title")), "title": r.get("title", ""), "note": note})
    seen_k = set()
    for r in _jsonl("history/competitor_contracts.jsonl") + _jsonl("history/competitor_wins.jsonl"):
        co, d = r.get("competitor"), (r.get("date") or "")[:10]
        k = r.get("k") or r.get("_key")
        if co == OWN or not co or d < since or k in seen_k:
            continue
        seen_k.add(k)
        try:
            amt = int(float(r.get("amount") or 0))
        except ValueError:
            amt = 0
        items.append({"d": d, "co": co, "type": "B2G 계약", "kind": kind(r.get("course")), "title": r.get("course", ""),
                      "note": " · ".join(x for x in [r.get("region"), r.get("org"), r.get("method"), f"{amt / 1e4:,.0f}만원" if amt else ""] if x),
                      "region": r.get("region", ""), "amount": amt})
    items.sort(key=lambda x: x["d"], reverse=True)
    week = [x for x in items if x["d"] >= wk]
    by_co = Counter(x["co"] for x in items)
    by_type = Counter(x["type"] for x in items)
    regions = Counter(x["region"] for x in items if x["type"] == "B2G 계약" and x.get("region") and x["region"] != "전국")
    signals = []
    free = [x for x in items if x["kind"] == "무상·무료"]
    if free:
        signals.append({"lv": "high", "t": f"무상·무료 공세 {len(free)}건", "do": "가격 맞대응보다 '이수 학점·학교 단위 성과 보고'로 차별화하고, 해당 경쟁사 고객 학교에 우리 체험 과정을 먼저 제안"})
    ai = [x for x in items if x["kind"] == "AI"]
    if len(ai) >= 3:
        signals.append({"lv": "mid", "t": f"AI 관련 신규 {len(ai)}건", "do": "AI 과정 라인업 공백 점검: 경쟁사 신규 주제 중 우리에게 없는 주제를 콘텐츠 Cell 개발 후보로 이관"})
    if regions:
        top = ", ".join(f"{k} {v}건" for k, v in regions.most_common(3))
        signals.append({"lv": "mid", "t": f"경쟁사 B2G 계약 집중 지역: {top}", "do": "해당 시도의 재발주 시점을 17개 시도 카드에서 확인하고, 연말 집행형 제안을 먼저 넣을 것"})
    grp = [x for x in items if x["kind"] == "단체·학교"]
    if grp:
        signals.append({"lv": "mid", "t": f"단체·학교 대상 판촉 {len(grp)}건", "do": "B2S 단체 할인 조건을 경쟁사와 비교하고, 학교 담당 교사용 1장짜리 비교표를 준비"})
    if not items:
        signals.append({"lv": "low", "t": "최근 30일 감지된 변화 없음", "do": "수집이 정상인지 관리 탭 '데이터 출처 상태'에서 확인"})
    return {"date": today.isoformat(), "days": days, "total": len(items), "week": len(week),
            "by_co": dict(by_co.most_common()), "by_type": dict(by_type), "signals": signals, "items": items[:60]}


if __name__ == "__main__":
    update_log()
    b = build()
    print(f"최근 {b['days']}일 변화 {b['total']}건(7일 {b['week']}건) · {b['by_type']}")
