#!/usr/bin/env python3
"""
B2S 학교 잠재 수요 - 학교알리미 전국 학교별 교원 수(history/schoolinfo_market.json, schoolinfo_export.py 가 주 1회 수집)로
시도·시군구·학교별 교원연수 잠재 시장을 계산한다.

  잠재 매출 = 교원 수 × 유료 연수 참여율 × 1인 연간 객단가   (참여율·객단가는 화면에서 바꾸는 가정값)
  - AI 중점·선도학교(static_data/ai_schools_2026.json) 표시 → 정책 수요가 확실한 학교 우선
  - 학교 규모: 대(교원 60명+) 학교 단위 단체연수 / 중(30~59) / 소(30 미만) 교육지원청 단위 묶음 제안
  - 시도별 자사·경쟁사 계약(최근 1년, 계약정보 API) 건수를 붙여 '경쟁 공백'을 본다
출력: build() -> dict (대시보드), write_csv() -> 전체 학교 CSV(내려받기)
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
MARKET = HERE / "history" / "schoolinfo_market.json"
CONTRACTS = HERE / "history" / "competitor_contracts.jsonl"
SELF = "비바샘연수원"
TOP_PER_SIDO = 60


def tier(t):
    return "대" if t >= 60 else "중" if t >= 30 else "소"


def _ai_names():
    try:
        rows = json.loads((HERE / "static_data" / "ai_schools_2026.json").read_text(encoding="utf-8"))["schools"]
    except FileNotFoundError:
        return {}
    return {(r["소속지역"], r["학교명"]): r.get("유형") or "AI" for r in rows}


def _contracts():
    own, comp = Counter(), Counter()
    if CONTRACTS.exists():
        for line in CONTRACTS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            (own if r.get("competitor") == SELF else comp)[r.get("region") or "미상"] += 1
    return own, comp


def load():
    if not MARKET.exists():
        return None
    return json.loads(MARKET.read_text(encoding="utf-8"))


def build():
    m = load()
    if not m or not m.get("schools"):
        return {"available": False}
    ai = _ai_names()
    own, comp = _contracts()
    schools = [{**s, "ai": ai.get((s["s"], s["n"]), "")} for s in m["schools"]]
    sido = defaultdict(lambda: {"schools": 0, "teachers": 0, "kind": Counter(), "tier": Counter(), "tier_t": Counter(), "ai": 0})
    sgg = defaultdict(lambda: {"schools": 0, "teachers": 0, "large": 0, "ai": 0})
    for s in schools:
        d = sido[s["s"]]
        d["schools"] += 1
        d["teachers"] += s["t"]
        d["kind"][s["k"]] += s["t"]
        d["tier"][tier(s["t"])] += 1
        d["tier_t"][tier(s["t"])] += s["t"]
        d["ai"] += bool(s["ai"])
        g = sgg[(s["s"], s["g"])]
        g["schools"] += 1
        g["teachers"] += s["t"]
        g["large"] += s["t"] >= 60
        g["ai"] += bool(s["ai"])
    sido_rows = sorted([{"s": k, "schools": v["schools"], "teachers": v["teachers"], "kind": dict(v["kind"]),
                         "tier": dict(v["tier"]), "tier_t": dict(v["tier_t"]), "ai": v["ai"],
                         "own_c": own.get(k, 0), "comp_c": comp.get(k, 0)} for k, v in sido.items()],
                       key=lambda r: -r["teachers"])
    sgg_rows = sorted([{"s": k[0], "g": k[1], **v} for k, v in sgg.items()], key=lambda r: -r["teachers"])
    top = []
    for k in sido:
        rows = sorted([s for s in schools if s["s"] == k], key=lambda s: (-(bool(s["ai"])), -s["t"]))
        top += [{"n": s["n"], "s": s["s"], "g": s["g"], "k": s["k"], "t": s["t"], "ai": s["ai"]} for s in rows[:TOP_PER_SIDO]]
    tot_t = sum(r["teachers"] for r in sido_rows)
    return {"available": True, "year": m.get("year"), "collected": m.get("date"), "n_schools": len(schools),
            "n_teachers": tot_t, "sido": sido_rows, "sgg": sgg_rows, "top": top,
            "contracts_note": "자사·경쟁사 계약 = 계약정보 API 최근 1년(교원연수 관련 매칭분)"}


def write_csv(path):
    m = load()
    if not m:
        return 0
    ai = _ai_names()
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["시도", "시군구", "학교급", "학교명", "교원수", "규모", "AI중점·선도"])
        for s in sorted(m["schools"], key=lambda s: (s["s"], s["g"], s["k"], -s["t"])):
            w.writerow([s["s"], s["g"], s["k"], s["n"], s["t"], tier(s["t"]), ai.get((s["s"], s["n"]), "")])
    return len(m["schools"])


if __name__ == "__main__":
    d = build()
    print({k: d[k] for k in ("available", "n_schools", "n_teachers")} if d.get("available") else d)
