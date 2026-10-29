#!/usr/bin/env python3
"""
통합교육연수시스템 이수현황 -> '교원연수 이수 현황' 탭 데이터(combine_dashboard.py 에서 호출, API 호출 없음).

  - 연도·유형별 추이, 이수율, 상시(원격) 비중
  - 2026 연간 추정: 상반기 이수 ÷ 상반기 비중(2021·2022 상반기/연간 평균, 유형별) - 추정치로 표시
  - 기관·시도별 규모·성장(2022→2025 연평균)
  - 자사 B2G 연결: 시도별 상시 원격 이수 규모 × 최근 12개월 나라장터 연수 계약(자사·경쟁사, history/competitor_contracts.jsonl)
"""
import json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "static_data" / "neti_completion.json"
CONTRACTS = HERE / "history" / "competitor_contracts.jsonl"
OWN = "비바샘연수원"
TYPES = ["집합", "혼합", "정기", "상시"]


def _cagr(a, b, n):
    return round(((b / a) ** (1 / n) - 1) * 100, 1) if a and b and n else None


def _rate(v):
    return round(v[1] / v[0] * 100, 1) if v and v[0] else None


def build():
    try:
        d = json.loads(SRC.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    tot, insts = d["totals"], d["institutions"]
    years = sorted(k for k in tot if k.isdigit())
    last = years[-1]

    # 상반기 비중(유형별): 2021·2022 상반기 기관 합 / 같은 해 연간 기관 합
    def isum(key, t):
        return sum(i["years"].get(key, {}).get(t, [0, 0])[1] for i in insts)
    h1_ratio = {}
    for t in TYPES + ["전체"]:
        rs = [isum(f"{y}H1", t) / isum(y, t) for y in ("2021", "2022") if isum(y, t) and isum(f"{y}H1", t)]
        h1_ratio[t] = round(sum(rs) / len(rs), 3) if rs else None
    h1 = tot.get(f"{int(last) + 1}H1")
    est = None
    if h1:
        est_types = {t: round(h1[t][1] / h1_ratio[t]) if h1_ratio.get(t) else None for t in TYPES}
        est_all = round(h1["전체"][1] / h1_ratio["전체"]) if h1_ratio.get("전체") else None
        est = {"year": str(int(last) + 1), "h1": h1["전체"][1], "h1_types": {t: h1[t][1] for t in TYPES},
               "all": est_all, "types": est_types, "ratio": h1_ratio["전체"],
               "yoy": round((est_all / tot[last]["전체"][1] - 1) * 100, 1) if est_all else None}

    series = [{"y": y, "done": {t: tot[y][t][1] for t in TYPES}, "appr": {t: tot[y][t][0] for t in TYPES},
               "all": tot[y]["전체"][1], "rate": _rate(tot[y]["전체"])} for y in years]
    rates = {t: [_rate(tot[y][t]) for y in years] for t in TYPES}
    kpi = {"last": last, "done": tot[last]["전체"][1], "appr": tot[last]["전체"][0], "rate": _rate(tot[last]["전체"]),
           "cagr5": _cagr(tot[str(int(last) - 5)]["전체"][1], tot[last]["전체"][1], 5) if str(int(last) - 5) in tot else None,
           "sangsi_share": round(tot[last]["상시"][1] / tot[last]["전체"][1] * 100, 1),
           "est": est}

    base = str(int(last) - 3)
    rows = []
    for i in insts:
        y = i["years"]
        cur = y.get(last, {}).get("전체", [0, 0])[1]
        if not cur and not y.get(f"{int(last) + 1}H1"):
            continue
        h1v = y.get(f"{int(last) + 1}H1", {}).get("전체", [0, 0])[1]
        # 기관 자체 상반기 비중(2021·2022, 0.3~0.7 범위만) 우선, 없으면 시스템 평균
        own_r = [y[f"{k}H1"]["전체"][1] / y[k]["전체"][1] for k in ("2021", "2022")
                 if y.get(k, {}).get("전체", [0, 0])[1] and f"{k}H1" in y and 0.3 <= y[f"{k}H1"]["전체"][1] / y[k]["전체"][1] <= 0.7]
        ratio = sum(own_r) / len(own_r) if own_r else h1_ratio.get("전체")
        e = round(h1v / ratio) if h1v and ratio else None
        rows.append({"name": i["name"], "region": i["region"], "done": cur, "rate": _rate(y.get(last, {}).get("전체")),
                     "sangsi": y.get(last, {}).get("상시", [0, 0])[1], "jiphap": y.get(last, {}).get("집합", [0, 0])[1],
                     "cagr3": _cagr(y.get(base, {}).get("전체", [0, 0])[1], cur, 3),
                     "trend": [y.get(k, {}).get("전체", [0, 0])[1] for k in years],
                     "h1": h1v, "est": e, "own_ratio": bool(own_r), "yoy": round((e / cur - 1) * 100, 1) if e and cur else None})
    rows.sort(key=lambda r: -r["done"])

    # 시도 묶음 + 최근 12개월 나라장터 연수 계약(자사·경쟁사)
    cut = (date.today() - timedelta(days=365)).isoformat()
    con = {}
    try:
        for line in CONTRACTS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            c = json.loads(line)
            if (c.get("date") or "") < cut:
                continue
            g = con.setdefault(c.get("region") or "", {"own": [0, 0], "comp": [0, 0], "who": {}})
            k = "own" if c.get("competitor") == OWN else "comp"
            g[k][0] += 1
            g[k][1] += c.get("amount") or 0
            if k == "comp":
                g["who"][c["competitor"]] = g["who"].get(c["competitor"], 0) + (c.get("amount") or 0)
    except FileNotFoundError:
        pass
    reg = {}
    for r in rows:
        g = reg.setdefault(r["region"], {"region": r["region"], "done": 0, "sangsi": 0, "est": 0, "n": 0})
        g["done"] += r["done"]
        g["sangsi"] += r["sangsi"]
        g["est"] += r["est"] or 0
        g["n"] += 1
    regions = []
    for g in reg.values():
        c = con.get(g["region"], {"own": [0, 0], "comp": [0, 0], "who": {}})
        own, comp = c["own"], c["comp"]
        if g["region"] == "국립·전국":
            label = "-"
        elif own[0] and own[1] >= comp[1]:
            label = "방어"
        elif own[0]:
            label = "확대"
        elif comp[0]:
            label = "공략"
        else:
            label = "탐색"
        regions.append({**g, "own_n": own[0], "own_amt": own[1], "comp_n": comp[0], "comp_amt": comp[1],
                        "leader": max(c["who"], key=c["who"].get) if c["who"] else "", "label": label})
    regions.sort(key=lambda g: -g["sangsi"])
    return {"available": True, "source": d.get("source"), "as_of": d.get("as_of"), "note": d.get("note"),
            "types": TYPES, "series": series, "rates": rates, "kpi": kpi, "h1_ratio": h1_ratio,
            "institutions": rows, "regions": regions, "contract_since": cut, "base": base}


if __name__ == "__main__":
    o = build()
    print(json.dumps({k: o[k] for k in ("kpi", "h1_ratio")}, ensure_ascii=False, indent=1))
    for g in o["regions"]:
        print(g["region"], g["sangsi"], g["own_n"], g["own_amt"], g["comp_n"], g["comp_amt"], g["leader"], g["label"])
