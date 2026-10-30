#!/usr/bin/env python3
"""
샘몰 협력사 우선 협의 리스트 - 티처몰 입점사(공개 '입점사 현황') × 인기 상품의 판매자·제조자 표기.

  협력사 = 상품의 판매자. 판매자가 테크빌교육(티처몰 직매입)이면 제조자를 협력사로 본다(제조자도 테크빌/티처몰이면 자체상품).
  우선순위 점수(0~100) = 판매 인기 35 + 자사 과정 연결성 25 + 상품 폭 20 + 교사 관심 트렌드 20
    - 판매 인기: 베스트100 순위(1위=100) + 카테고리 인기순 위치 점수 합
    - 자사 과정 연결성: 협력사 상품 주제 중 자사 과정이 있는 주제 비율
    - 상품 폭: 조사된 인기 상품 수
    - 교사 관심 트렌드: 상품 주제의 교사 관심 신호(네이버 데이터랩 상승·유튜브 주제 비중)
  [티처몰ONLY]·'x티처몰' 표기 상품은 '티처몰 전용 제휴'로 구분(협의 난이도 높음).
"""
import json
import re
from pathlib import Path

from mall_trends import TOPIC_NAME, topics_of

HERE = Path(__file__).parent
CATALOG = HERE / "history" / "competitor_mall_catalog.json"
SELF_RE = re.compile(r"테크빌|티처몰|teacherville", re.I)
EXCL_RE = re.compile(r"티처몰\s?ONLY|x\s?티처몰|티처몰\s?x", re.I)
CORP_RE = re.compile(r"\(주\)|㈜|주식회사|\(유\)|유한회사|농업회사법인|\s+")


def _norm(n):
    return CORP_RE.sub("", n or "")


def build(own_courses, trends=None):
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    tm = cat.get("malls", {}).get("teachermall", {})
    sellers, provs = tm.get("sellers", {}), tm.get("providers", [])
    if not sellers:
        return {"available": False, "n_providers": len(provs)}
    prov_region = {_norm(p["name"]): p["region"] for p in provs}

    # 상품 풀: 베스트 순위 점수 + 카테고리 인기순 점수
    items = {}
    for r in tm.get("best", []):
        items[r["no"]] = {**r, "pop": max(10, 101 - (r.get("rank") or 100)), "best": r.get("rank")}
    for c in tm.get("categories", []):
        for i, r in enumerate(c.get("top", [])[:12]):
            it = items.setdefault(r["no"], {**r, "pop": 0, "best": None})
            it["pop"] += 40 - i * 2
            it.setdefault("cat", c["name"])
    for r in tm.get("sets", []):
        items.setdefault(r["no"], {**r, "pop": 15, "best": None})

    own_topics = {}
    for c in own_courses or []:
        for t in topics_of(c.get("title", "")):
            own_topics[t] = own_topics.get(t, 0) + 1
    # 교사 관심: 데이터랩 상승(+) 과 유튜브 주제 비중을 0~1 로
    trend = {}
    tr = trends or {}
    name_to_id = {v: k for k, v in TOPIC_NAME.items()}
    for r in (tr.get("interest") or {}).get("rows", []):
        tid = name_to_id.get(r["topic"])
        if tid:
            trend[tid] = trend.get(tid, 0) + (0.6 if "상승" in r.get("signal", []) else 0) + min(0.4, (r.get("idx") or 0) / 250)
    for r in tr.get("heat", []):
        tid = name_to_id.get(r["topic"])
        if tid:
            trend[tid] = trend.get(tid, 0) + min(0.4, r["heat"] / 100)

    part = {}
    for no, it in items.items():
        s = sellers.get(no) or {}
        seller, maker = s.get("seller", ""), s.get("maker", "")
        name, via = seller, "입점 판매"
        if not seller or SELF_RE.search(seller):
            if maker and not SELF_RE.search(maker):
                name, via = maker, "티처몰 직매입(제조사)"
            else:
                name, via = "", ""
        if not name:
            continue
        p = part.setdefault(_norm(name), {"name": name, "via": set(), "items": [], "excl": 0, "topics": {}})
        p["via"].add(via)
        excl = bool(EXCL_RE.search(it.get("name", "")))
        p["excl"] += excl
        ts = topics_of(it.get("name", "") + " " + (it.get("cat") or ""), product=True)
        for t in ts:
            p["topics"][t] = p["topics"].get(t, 0) + 1
        p["items"].append({"no": no, "n": it.get("name", ""), "p": it.get("price"), "best": it.get("best"), "pop": it["pop"], "excl": excl})

    rows = []
    for k, p in part.items():
        pop = sum(i["pop"] for i in p["items"])
        tops = list(p["topics"])
        link = sum(1 for t in tops if own_topics.get(t)) / len(tops) if tops else 0
        tr_score = max((trend.get(t, 0) for t in tops), default=0)
        rows.append({"name": p["name"], "key": k, "region": prov_region.get(k, ""), "listed": k in prov_region,
                     "via": " · ".join(sorted(p["via"])), "n": len(p["items"]), "best_n": sum(1 for i in p["items"] if i["best"]),
                     "best_top": min((i["best"] for i in p["items"] if i["best"]), default=None),
                     "excl_share": round(p["excl"] / len(p["items"]), 2), "pop": pop, "link": round(link, 2), "trend": round(tr_score, 2),
                     "topics": [TOPIC_NAME.get(t, t) for t in sorted(p["topics"], key=lambda t: -p["topics"][t])[:3]],
                     "own_courses": sum(own_topics.get(t, 0) for t in tops),
                     "items": sorted(p["items"], key=lambda i: -i["pop"])[:3]})
    if not rows:
        return {"available": False, "n_providers": len(provs)}
    mx_pop, mx_n, mx_tr = max(r["pop"] for r in rows) or 1, max(r["n"] for r in rows) or 1, max(r["trend"] for r in rows) or 1
    for r in rows:
        r["score"] = round(35 * r["pop"] / mx_pop + 25 * r["link"] + 20 * r["n"] / mx_n + 20 * r["trend"] / mx_tr)
        r["kind"] = "티처몰 전용 제휴" if r["excl_share"] >= 0.5 else "일반 입점"
        t = r["topics"][0] if r["topics"] else ""
        if r["kind"] == "티처몰 전용 제휴":
            r["point"] = "티처몰 전용 상품 비중이 높음 — 전용이 아닌 다른 상품군이나 공동 기획 신상품으로 접근"
        elif r["own_courses"] and t:
            r["point"] = f"자사 '{t}' 과정과 SET(연수+실습 상품) 공동 구성 제안"
        elif t:
            r["point"] = f"'{t}' 주제 자사 과정이 없음 — 상품 먼저 입점 후 과정 개발 연계 검토"
        else:
            r["point"] = "샘몰 초기 구색용 일반 입점 제안"
    rows.sort(key=lambda r: (r["kind"] != "일반 입점", -r["score"]))
    reg = {}
    for p in provs:
        reg[p["region"]] = reg.get(p["region"], 0) + 1
    return {"available": True, "captured_date": cat.get("captured_date"), "n_providers": len(provs),
            "regions": sorted(reg.items(), key=lambda x: -x[1]), "n_partners": len(rows), "n_items": len(items),
            "n_sellers_checked": len(sellers), "rows": rows[:40],
            "self_listed": [p["name"] for p in provs if re.search(r"비상교육|미래엔|천재|아이스크림|동아출판|지학사|YBM|와이비엠", p["name"])],
            "mall_url": tm.get("url", "")}
