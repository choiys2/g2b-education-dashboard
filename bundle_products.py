#!/usr/bin/env python3
"""
경쟁사(아이스크림·티처빌) 결합상품 목록 - 연수에 도서·교구·이용권·상품을 묶어 파는 강좌.

카탈로그(history/competitor_course_catalog.json, 주 1회 크롤링)의 강좌 카드 원문으로 판정한다.
  - 티처빌: 강좌명 끝 괄호 "(연수+도서+교구)" 형태 -> + 로 나눈 구성품
  - 아이스크림: 카드 배지 "연수·도서SET", "연수·상품SET", "교재"
같은 차시 단독 강좌의 가격 중앙값과 비교해 '결합 프리미엄'도 계산한다(샘몰 결합상품 가격 책정 참고).
"""
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

CATALOG = Path(__file__).parent / "history" / "competitor_course_catalog.json"
TV_RE = re.compile(r"\((연수(?:\s*\+\s*[^()+]+)+)\)\s*$")
IS_TAGS = [("연수·도서SET", "도서"), ("연수·상품SET", "상품"), ("교재", "교재")]  # 교재는 단독이면 제외(아래)
CHASI_RE = re.compile(r"(\d+)\s*차시")


def components(company, title, context):
    if company == "티처빌":
        m = TV_RE.search(title or "")
        if m:
            return [p.strip() for p in m.group(1).split("+")[1:] if p.strip()]
        return []
    if company == "아이스크림":
        return [name for tag, name in IS_TAGS if tag in (context or "")]
    return []


def build(companies=("아이스크림", "티처빌")):
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"items": [], "summary": []}
    from catalog_field_parser import parse_fields
    items, singles = [], defaultdict(list)
    for co in companies:
        seen = set()
        for c in cat.get("companies", {}).get(co, {}).get("courses", []):
            url = c.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            f = parse_fields(co, c.get("title") or "", c.get("context") or "")
            title = (f.get("title") or c.get("title") or "").strip()
            if title in ("", "상세보기", "미리보기"):
                continue
            comps = components(co, c.get("title") or title, c.get("context"))
            if not [x for x in comps if x != "교재"]:
                comps = []  # '교재' 배지만 있는 강좌는 온라인 교재 제공이라 결합상품으로 보지 않는다
            m = CHASI_RE.search(f.get("credit") or c.get("credit") or "")
            chasi = int(m.group(1)) if m else None
            price = f.get("price") if f.get("price") is not None else c.get("price")
            row = {"co": co, "t": title, "comps": comps, "credit": f.get("credit") or c.get("credit") or "",
                   "chasi": chasi, "price": price, "cat": f.get("category") or c.get("category") or "", "url": url}
            if comps:
                items.append(row)
            elif chasi and price:
                singles[(co, chasi)].append(price)
    med = {k: statistics.median(v) for k, v in singles.items() if len(v) >= 3}
    for r in items:
        base = med.get((r["co"], r["chasi"]))
        r["premium"] = round((r["price"] / base - 1) * 100) if base and r["price"] else None
    summary = []
    for co in companies:
        rows = [r for r in items if r["co"] == co]
        total = len(cat.get("companies", {}).get(co, {}).get("courses", []))
        prem = [r["premium"] for r in rows if r["premium"] is not None]
        summary.append({"co": co, "n": len(rows), "total": total,
                        "share": round(len(rows) / total * 100, 1) if total else 0,
                        "comps": Counter(x for r in rows for x in r["comps"]).most_common(),
                        "cats": Counter(r["cat"] for r in rows if r["cat"]).most_common(4),
                        "premium_median": statistics.median(prem) if prem else None})
    items.sort(key=lambda r: (r["co"], r["cat"], r["t"]))
    return {"captured": cat.get("captured_date"), "items": items, "summary": summary}


if __name__ == "__main__":
    b = build()
    for s in b["summary"]:
        print(s)
    print(len(b["items"]))
