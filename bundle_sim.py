#!/usr/bin/env python3
"""
D. 샘몰 묶음 상품 가격 시뮬레이터 데이터 - 연수 단품 가격(회사·차시별) + 경쟁사 결합상품(연수+도서·교구·이용권·자료집) 가격·프리미엄
   공개 강좌 목록(history/competitor_course_catalog.json) 재조합, API 호출 없음.

  build(strength=None) -> dict  (combine_dashboard.py 가 호출, strength = strength_view.build 결과로 라인업 초안)
"""
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
CHASI_RE = re.compile(r"(\d+)\s*차시")
SELF = "비바샘연수원"
# 구성요소 묶음(경쟁사 표기 → 시뮬레이터 선택지)
COMP = {"도서": "교재·도서", "교재": "교재·도서", "교구": "교구", "이용권": "이용권", "마이클 이용권": "이용권",
        "수업 도안 자료집": "수업자료집", "실전 자료집": "수업자료집", "자료": "수업자료집"}


def _q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f))


def build(strength=None):
    try:
        cat = json.loads((HERE / "history" / "competitor_course_catalog.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    from catalog_field_parser import parse_fields
    import training_topics as tt
    singles = defaultdict(lambda: defaultdict(list))
    for co, v in (cat.get("companies") or {}).items():
        for c in v.get("courses", []):
            f = parse_fields(co, c.get("title") or "", c.get("context") or "")
            m = CHASI_RE.search(f.get("credit") or c.get("credit") or "")
            p = f.get("price") if f.get("price") is not None else c.get("price")
            if m and p:
                singles[co][int(m.group(1))].append(p)
    single = {co: {str(ch): {"n": len(x), "p25": _q(x, .25), "med": _q(x, .5), "p75": _q(x, .75)}
                   for ch, x in sorted(d.items()) if len(x) >= 3} for co, d in singles.items()}
    b = __import__("bundle_products").build()
    bundles = []
    for r in b.get("items", []):
        comps = sorted({COMP.get(x, x) for x in r.get("comps", [])})
        bundles.append({"co": r["co"], "t": r["t"], "comps": comps, "chasi": r.get("chasi"), "price": r.get("price"),
                        "premium": r.get("premium"), "topics": tt.classify_topics(r["t"]), "url": r.get("url", "") if str(r.get("url", "")).startswith("https://") else ""})
    prem = defaultdict(list)
    for r in bundles:
        if r["premium"] is not None and len(r["comps"]) == 1:
            prem[r["comps"][0]].append(r["premium"])
    premium = {k: {"n": len(v), "med": _q(v, .5), "p25": _q(v, .25), "p75": _q(v, .75)} for k, v in prem.items() if len(v) >= 2}
    # 라인업 초안: 강점 분야 × 15차시 + 판단에 맞는 구성
    lineup = []
    base15 = (single.get(SELF, {}).get("15") or single.get("티처빌", {}).get("15") or {}).get("med")
    for s in (strength or {}).get("rows", []):
        comp = ["교재·도서"] if s.get("verdict") != "샘몰 대표 상품 전면 배치" else ["교재·도서", "수업자료집"]
        pm = sum((premium.get(c) or {}).get("med") or 0 for c in comp)
        # 같은 구성(15차시) 실제 판매가가 3개 이상이면 그 중앙값, 아니면 단품 × 프리미엄 합(추정)
        same = [r["price"] for r in bundles if r["chasi"] == 15 and r["price"] and sorted(r["comps"]) == sorted(comp)]
        if len(same) >= 3:
            price, basis = round(_q(same, .5) / 1000) * 1000, f"같은 구성 실제 판매가 {len(same)}개 중앙값"
            pm = round((price / base15 - 1) * 100) if base15 else pm
        else:
            price, basis = (round(base15 * (1 + pm / 100) / 1000) * 1000 if base15 else None), "단품 × 구성 프리미엄 추정"
        comp_n = sum(1 for r in bundles if s["id"] in r["topics"])
        lineup.append({"id": s["id"], "name": s["name"], "verdict": s.get("verdict"), "chasi": 15, "comps": comp,
                       "price": price, "base": base15, "premium": pm, "basis": basis, "competitors": comp_n,
                       "title": f"{s['name']} 연수 15차시 + 비상 {'·'.join(comp)}"})
    return {"available": True, "captured": cat.get("captured_date"), "self": SELF, "single": single,
            "premium": premium, "bundles": bundles, "lineup": lineup, "comps": ["교재·도서", "교구", "이용권", "수업자료집"]}


if __name__ == "__main__":
    import strength_view
    d = build(strength_view.build())
    print(json.dumps({k: d[k] for k in ("single", "premium", "lineup")}, ensure_ascii=False, indent=1)[:3000])
