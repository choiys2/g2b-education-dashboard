#!/usr/bin/env python3
"""
B2S 학교 타깃 레이더 + 샘몰 상품 기획 보드 (통합 대시보드 'B2S·샘몰 기획' 탭).

API를 새로 호출하지 않는다. 이미 저장소·파이프라인에 있는 데이터만 조합한다.
  - static_data/school_contract_national_2025.json : EDSS 학교회계 2025 계약(시도 합계, 시군구 상위, 시도별 상위 30개교)
  - history/training_bids.jsonl (+ 오늘 파이프라인)   : 교원 연수 입찰공고 12개월 (training_topics.py 규칙 재사용)
  - history/competitor_wins.jsonl                     : 경쟁사 나라장터 낙찰
  - 경쟁사·자사 강좌 카탈로그(combine_dashboard.build_new_courses) : 주제별 보유 강좌·가격·차시
  - training_topics.build() 결과                       : 주제별 학교급 수요·정책 가중치·과정안

점수는 화면에서 가중치를 바꿀 수 있게 요인별 0~1 값만 만들어 넘긴다(합산은 브라우저).
학교 데이터에는 학교명이 없다(소재지·학교급·설립유형만 있음). 그래서 '학교'는 소재지로 식별하는
익명 리드로 보여 주고, 시도 상위 30개교에 들지 않는 학교는 레이더에 나오지 않는다.
"""
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import training_topics as tt

HERE = Path(__file__).parent
SCHOOL_PATH = HERE / "static_data" / "school_contract_national_2025.json"
WINS_PATH = HERE / "history" / "competitor_wins.jsonl"

FULL2SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}
GRADE_SHORT = {"초등학교": "초", "중학교": "중", "고등학교": "고"}
CHASI_RE = re.compile(r"(\d+)\s*차시")


def _read_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _norm(values):
    """min-max -> 0~1 (전부 같으면 0.5)."""
    lo, hi = min(values), max(values)
    return [0.5 if hi == lo else (v - lo) / (hi - lo) for v in values]


def _pct_rank(values):
    """백분위 순위 0~1. 금액처럼 꼬리가 긴 분포에서 최상위 몇 곳이 나머지를 0으로 누르지 않게 쓴다."""
    order = sorted(values)
    n = len(order)
    if n <= 1:
        return [0.5] * n
    return [sum(1 for x in order if x < v) / (n - 1) for v in values]


# ---------------- 연수 공고(12개월, 교원 대상) ----------------
def teacher_training_rows(full_live=None, wins=None, today=None, window_days=tt.WINDOW_DAYS):
    today = today or date.today()
    start = (today - timedelta(days=window_days)).isoformat()
    rows = tt._rows_from_sources(tt.load_history(), full_live, wins)
    return [r for r in rows
            if start <= (r.get("d") or "") <= today.isoformat()
            and tt.is_training_bid(r["t"], r.get("o", "")) and tt.classify_audience(r["t"]) != "학생"]


# ---------------- ① B2S 타깃 레이더 ----------------
def build_radar(school, bids, wins, self_name):
    bids_by_region = Counter(r.get("r") for r in bids if r.get("r"))
    topics_by_region = defaultdict(Counter)
    for r in bids:
        for tid in tt.classify_topics(r["t"]):
            if r.get("r"):
                topics_by_region[r["r"]][tid] += 1
    comp_wins = Counter(w.get("region") for w in wins if w.get("competitor") != self_name and w.get("region"))

    regions = []
    for s in school["by_sido"]:
        short = FULL2SHORT.get(s["sido"], s["sido"])
        n = s.get("n") or 0
        regions.append({
            "region": short, "sido": s["sido"], "schools": n,
            "amt": s.get("amt", 0), "svc_amt": s.get("svc_amt", 0),
            "svc_per_school": round((s.get("svc_amt") or 0) / n) if n else 0,
            "bids": bids_by_region.get(short, 0), "comp_wins": comp_wins.get(short, 0),
            "top_topics": [[tid, c] for tid, c in topics_by_region[short].most_common(3)],
        })
    if regions:
        buy = _norm([r["svc_per_school"] for r in regions])
        hist = _norm([r["bids"] for r in regions])
        scale = _norm([r["schools"] for r in regions])
        max_w = max([r["comp_wins"] for r in regions] + [1])
        for r, b, h, s in zip(regions, buy, hist, scale):
            r["f"] = {"buy": round(b, 3), "history": round(h, 3), "scale": round(s, 3),
                      "gap": round(1 - r["comp_wins"] / max_w, 3)}
    reg_f = {r["region"]: r["f"] for r in regions}

    # 시도별 상위 30개교 + 전국 상위 120개교(겹치면 한 번만). 학교명이 없어 소재지·학교급·설립유형으로 구분한다.
    seen, raw = set(), []
    for rec in list(school.get("top_national", [])) + [x for v in school.get("top_by_sido", {}).values() for x in v]:
        key = (rec["sido"], rec.get("sigungu"), rec.get("dong"), rec.get("grade"), rec.get("type"), rec.get("amt"))
        if key in seen:
            continue
        seen.add(key)
        raw.append(rec)
    buy = _pct_rank([r.get("svc_amt") or 0 for r in raw])
    scale = _pct_rank([r.get("amt") or 0 for r in raw])
    leads = []
    for rec, b, s in zip(raw, buy, scale):
        short = FULL2SHORT.get(rec["sido"], rec["sido"])
        rf = reg_f.get(short, {"history": 0, "gap": 1})
        leads.append({
            "region": short, "sigungu": rec.get("sigungu") or "", "dong": rec.get("dong") or "",
            "grade": GRADE_SHORT.get(rec.get("grade"), rec.get("grade") or ""), "type": rec.get("type") or "",
            "amt": rec.get("amt") or 0, "svc_amt": rec.get("svc_amt") or 0, "cnt": rec.get("cnt") or 0,
            "f": {"buy": round(b, 3), "history": rf["history"], "scale": round(s, 3), "gap": rf["gap"]},
        })

    sigungu = [{"label": x["label"], "region": FULL2SHORT.get(x["sido"], x["sido"]), "amt": x["amt"], "n": x["n"],
                "per_school": round(x["amt"] / x["n"]) if x.get("n") else 0}
               for x in school.get("sigungu", [])]
    return regions, leads, sigungu


# ---------------- ② 샘몰 상품 기획 보드 ----------------
def _chasi(credit):
    m = CHASI_RE.search(credit or "")
    return int(m.group(1)) if m else None


def _price_stats(prices):
    if not prices:
        return None
    q = sorted(prices)
    pick = lambda p: q[min(len(q) - 1, int(round(p * (len(q) - 1))))]
    return {"n": len(q), "p25": pick(0.25), "median": int(statistics.median(q)), "p75": pick(0.75)}


def build_products(courses_by_company, new_rows, topic_data, self_name):
    comp_names = [n for n in (courses_by_company or {}) if n != self_name]
    by_topic = defaultdict(lambda: {"own": [], "comp": defaultdict(list)})
    for name, courses in (courses_by_company or {}).items():
        for c in courses:
            for tid in tt.classify_topics(c.get("title") or ""):
                if name == self_name:
                    by_topic[tid]["own"].append(c)
                else:
                    by_topic[tid]["comp"][name].append(c)
    new_by_topic = Counter()
    for r in new_rows or []:
        if r.get("company") != self_name:
            for tid in tt.classify_topics(r.get("title") or ""):
                new_by_topic[tid] += 1

    # 15차시(1학점) 기준 가격. 경쟁사 과정이 3개 미만인 주제는 경쟁사 전체 15차시 가격으로 대신한다.
    def p15(courses):
        return [c["price"] for c in courses if c.get("price") and _chasi(c.get("credit")) == 15]
    all_comp15 = [p for n in comp_names for p in p15(courses_by_company[n])]
    overall = {"comp": _price_stats(all_comp15), "own": _price_stats(p15(courses_by_company.get(self_name, [])))}

    topics = {t["id"]: t for t in (topic_data or {}).get("topics", [])}
    n_comp = max(len(comp_names), 1)
    cands = []
    for tid, name, _pat, weight, policy_note, courses in tt.TOPICS:
        t = topics.get(tid, {"levels": {}, "format": "", "n": 0})
        bt = by_topic[tid]
        comp_all = [c for n in comp_names for c in bt["comp"].get(n, [])]
        comp_avg = round(len(comp_all) / n_comp, 1)
        own = len(bt["own"])
        prices = p15(comp_all)
        price = _price_stats(prices) if len(prices) >= 3 else None
        chasi = Counter(_chasi(c.get("credit")) for c in comp_all if _chasi(c.get("credit")))
        own_prices = p15(bt["own"])
        if own == 0:
            position = "신규 진입"
        elif own < comp_avg:
            position = "라인업 보강"
        else:
            position = "보유 강화·리뉴얼"
        for lv, (title_c, content) in courses.items():
            demand = (t["levels"].get(lv, 0) or 0) + (t["levels"].get("공통", 0) or 0)
            cands.append({
                "tid": tid, "topic": name, "level": lv, "title": title_c, "content": content,
                "demand": demand, "policy_weight": weight, "policy_note": policy_note,
                "comp_courses": len(comp_all), "comp_avg": comp_avg, "own": own,
                "comp_new": new_by_topic.get(tid, 0), "position": position,
                "price": price, "price_basis": "주제" if price else "전체",
                "own_price_median": int(statistics.median(own_prices)) if own_prices else None,
                "chasi_mode": chasi.most_common(1)[0][0] if chasi else None,
                "chasi_mix": [[k, v] for k, v in chasi.most_common(3)],
                "format": t.get("format") or "",
                "own_samples": [c.get("title") for c in bt["own"][:3]],
                "comp_samples": [{"co": n, "t": c.get("title"), "p": c.get("price"), "cr": c.get("credit")}
                                 for n in comp_names for c in bt["comp"].get(n, [])[:2]],
            })

    # 점수 100 = 공공 수요 25 + 시장 규모 20 + 경쟁사 신규 모멘텀 15 + 정책 15 + 자사 공백 25
    if cands:
        max_d = max(c["demand"] for c in cands) or 1
        max_m = max(c["comp_courses"] for c in cands) or 1
        max_n = max(c["comp_new"] for c in cands) or 1
        for c in cands:
            if c["own"] == 0:
                gap = 25
            else:
                gap = round(max(0.0, min((c["comp_avg"] - c["own"]) / max(c["comp_avg"], 1), 1.0)) * 25)
            parts = {"수요": round(25 * c["demand"] / max_d), "시장": round(20 * c["comp_courses"] / max_m),
                     "모멘텀": round(15 * c["comp_new"] / max_n), "정책": {3: 15, 2: 10, 1: 5}[c["policy_weight"]],
                     "공백": gap}
            c["parts"], c["score"] = parts, sum(parts.values())
        cands.sort(key=lambda c: (-c["score"], -c["demand"]))
    return cands, overall


def build(full_live=None, courses_by_company=None, new_rows=None, topic_data=None,
          self_name="비바샘연수원", today=None):
    today = today or date.today()
    school = json.loads(SCHOOL_PATH.read_text(encoding="utf-8"))
    wins = _read_jsonl(WINS_PATH)
    bids = teacher_training_rows(full_live, wins, today)
    regions, leads, sigungu = build_radar(school, bids, wins, self_name)
    products, price_overall = build_products(courses_by_company, new_rows, topic_data, self_name)
    return {
        "generated": today.isoformat(), "self_name": self_name,
        "school_year": school.get("year"), "school_total": school.get("total_schools"),
        "bids_total": len(bids), "comp_wins_total": sum(r["comp_wins"] for r in regions),
        "topic_names": {t[0]: t[1] for t in tt.TOPICS},
        "regions": regions, "leads": leads, "sigungu": sigungu,
        "products": products, "price_overall": price_overall,
        "catalog_counts": {n: len(v) for n, v in (courses_by_company or {}).items()},
    }


if __name__ == "__main__":
    import combine_dashboard as cd
    nc = cd.build_new_courses()
    td = tt.build_from_files(nc["courses"], "비바샘연수원")
    out = build(None, nc["courses"], nc["rows"], td)
    print(json.dumps({k: (v if not isinstance(v, list) else f"{len(v)} rows") for k, v in out.items()
                      if k not in ("topic_names",)}, ensure_ascii=False, indent=1))
    print(json.dumps(out["products"][:3], ensure_ascii=False, indent=1)[:2500])
    print(json.dumps(sorted(out["regions"], key=lambda r: -sum(r["f"].values()))[:3], ensure_ascii=False))
