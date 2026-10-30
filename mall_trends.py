#!/usr/bin/env python3
"""
교사몰 상품 동향 -> B2S·샘몰 기획 탭 패널 데이터(API 호출 없음, combine_dashboard.py 에서 호출).

  - 카테고리 구성(상품 수), 베스트 상위, 신상품(주간 신규 + NEW 메뉴), 세트 상품, 추천 검색어
  - 자사 과정 ↔ 인기 상품 짝짓기: 같은 연수 주제(training_topics.TOPICS)로 묶이는 상품과 과정을 찾아
    '연수+상품 SET' 후보를 점수순으로 낸다.
    점수 = 상품 인기(베스트 순위·카테고리 인기점수) + 추천 검색어 가중치(같은 주제면 +) - 경쟁 강도 없음(공개 데이터 한계)
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import training_topics

HERE = Path(__file__).parent
CATALOG = HERE / "history" / "competitor_mall_catalog.json"
NEW_LOG = HERE / "history" / "competitor_mall_new.jsonl"

# 상품명·카테고리명은 연수 제목과 어휘가 달라 주제 판정에 상품 어휘를 보탠다.
PRODUCT_RULES = [
    ("ai", r"코딩|VR|AR|드론|메이커|NFC|AI|인공지능|로봇|스마트|디지털|태블릿|크롬북|보관함"),
    ("care", r"인성|감정|마음|사회\s?정서|SEL|학교\s?폭력|회복|편견|고정관념|관계|상담|칭찬|멈춤|알아차림|마음챙김|다했니"),
    ("basic", r"한글|문해|읽기|독서|어휘|한자|글쓰기|받아쓰기|낱말|말싸미"),
    ("lesson", r"보드\s?게임|토론|평가|프로젝트|수업\s?도구|수업\s?꾸러미|교구|활동지|탐구\s?노트"),
    ("safety", r"안전|보건|성\s?교육|응급|임신|출산|약물"),
    ("inclusive", r"점자|장애|특수|다문화|배프|수어"),
    ("citizen", r"환경|생태|기후|인권|미디어|리터러시|업사이클|탄소|분리\s?배출"),
    ("subject", r"과학|수학|영어|국어|사회|역사|한국사|음악|미술|체육|실험|악기|피구|공\b"),
    ("leader", r"학급\s?(경영|운영|세트)|선생님\s?도장|환경\s?미화|단체\s?티|청소|학급\s?문고"),
    ("neulbom", r"늘봄|방과\s?후|만들기|DIY|키트|KIT|공예"),
]
_PR = [(t, re.compile(r)) for t, r in PRODUCT_RULES]
NEULBOM_STRICT = re.compile(r"늘봄|방과\s?후|초등\s?돌봄")
TOPIC_NAME = {t[0]: t[1] for t in training_topics.TOPICS}


def topics_of(text, product=False):
    ts = training_topics.classify_topics(text)
    if product:
        ts += [t for t, rx in _PR if rx.search(text) and t not in ts]
    return ts


def _load():
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _slim(r, cat=""):
    return {"no": r["no"], "n": r["name"], "p": r.get("price"), "o": r.get("orig"), "rk": r.get("rank"), "cat": cat}


def build(own_courses, own_name="비바샘연수원", weeks=8):
    cat = _load()
    if not cat:
        return {"available": False}
    tm = cat["malls"].get("teachermall", {})
    isc = cat["malls"].get("iscream", {})
    url = tm.get("url", "")

    cats = [{"code": c["code"], "name": c["name"], "count": c.get("count") or len(c.get("top", [])),
             "exact": c.get("count") is not None, "top": [_slim(r, c["name"]) for r in c.get("top", [])[:5]]}
            for c in tm.get("categories", [])]
    cats.sort(key=lambda c: -c["count"])
    cat_of = {r["no"]: c["name"] for c in tm.get("categories", []) for r in c.get("top", [])}

    best = [_slim(r, cat_of.get(r["no"], "")) for r in tm.get("best", [])]

    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    new = []
    if NEW_LOG.exists():
        for line in NEW_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("first_seen", "") >= cutoff:
                    new.append({"no": r["no"], "n": r["name"], "p": r.get("price"), "d": r["first_seen"]})
    new.sort(key=lambda r: (r["d"], int(r["no"])), reverse=True)
    weekly = {}
    for r in new:
        weekly[r["d"]] = weekly.get(r["d"], 0) + 1
    if not new:  # 첫 주: 몰 NEW 메뉴, 없으면 상품번호가 큰(최근 등록) 순
        src = tm.get("new_menu") or sorted({r["no"]: r for c in tm.get("categories", []) for r in c.get("top", [])}.values(),
                                           key=lambda r: -int(r["no"]))
        new = [{"no": r["no"], "n": r["name"], "p": r.get("price"), "d": ""} for r in src[:20]]

    sets = [_slim(r, cat_of.get(r["no"], "")) for r in tm.get("sets", [])]
    kws = [k for k in tm.get("keywords", []) if not k.isdigit()]
    kw_topics = {}
    for k in kws:
        for t in topics_of(k, product=True):
            kw_topics.setdefault(t, []).append(k)

    # 상품 인기 점수: 베스트 순위(1위=100) 우선, 없으면 카테고리 인기순 위치(상위 12 → 40~18)
    pop = {}
    for r in best:
        pop[r["no"]] = (max(10, 101 - (r["rk"] or 100)), r)
    for c in tm.get("categories", []):
        for i, r in enumerate(c.get("top", [])[:12]):
            if r["no"] not in pop:
                pop[r["no"]] = (40 - i * 2, _slim(r, c["name"]))

    by_topic = {}
    for no, (score, r) in pop.items():
        for t in topics_of(r["n"] + " " + (r.get("cat") or ""), product=True):
            by_topic.setdefault(t, []).append((score, r))
    own = [c for c in (own_courses or []) if c.get("title")]
    own_by_topic = {}
    for c in own:
        for t in topics_of(c["title"]):
            if t == "neulbom" and not NEULBOM_STRICT.search(c["title"]):
                continue  # '마음돌봄' 같은 교사 대상 과정이 늘봄으로 잡히지 않게
            own_by_topic.setdefault(t, []).append({"t": c["title"], "url": c.get("url", "")})

    pairs = []
    for t, prods in by_topic.items():
        prods.sort(key=lambda x: -x[0])
        demand = sum(s for s, _ in prods[:5])
        kw_bonus = 30 * len(kw_topics.get(t, []))
        oc = own_by_topic.get(t, [])
        pairs.append({"topic": t, "name": TOPIC_NAME.get(t, t), "score": round(demand + kw_bonus),
                      "demand": round(demand), "kw": kw_topics.get(t, []), "n_prod": len(prods),
                      "products": [dict(r, s=s) for s, r in prods[:4]],
                      "own_n": len(oc), "own": oc[:3],
                      "gap": not oc})
    pairs.sort(key=lambda x: -x["score"])

    return {"available": True, "captured_date": cat.get("captured_date"), "mall_url": url,
            "malls": [{"name": tm.get("name", "티처몰"), "operator": tm.get("operator", ""), "status": "수집 중" if tm.get("best") else tm.get("status", ""),
                       "n_best": len(best), "n_cat": len(cats)},
                      {"name": isc.get("name", "아이스크림몰"), "operator": isc.get("operator", ""),
                       "status": isc.get("status", "수집 불가"), "note": isc.get("note", "")}],
            "keywords": kws, "categories": cats, "best": best[:30], "new": new[:20], "new_weekly": weekly,
            "sets": sets[:20], "pairs": pairs[:10], "own_name": own_name}


if __name__ == "__main__":
    import sys
    cat = json.loads((HERE / "history" / "competitor_course_catalog.json").read_text(encoding="utf-8"))
    own = cat["companies"].get("비바샘연수원", {}).get("courses", [])
    out = build(own)
    print(json.dumps({k: out[k] for k in out if k not in ("best", "categories")}, ensure_ascii=False, indent=1)[:4000])
