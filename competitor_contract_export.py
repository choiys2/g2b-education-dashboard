#!/usr/bin/env python3
"""
조달청 나라장터 계약정보서비스(용역)로 경쟁사·자사의 '계약' 이력을 모은다.

왜: 낙찰정보서비스(competitor_g2b_export.py)는 경쟁입찰 낙찰만 잡혀서, 수의계약·협상계약으로 따낸
교원연수 위탁은 빠진다(실측: 비상교육 2년간 낙찰 0건). 계약정보는 계약방법과 무관하게 체결된 계약이
모두 올라오므로 실제 B2G 점유율에 가깝다.

- API: data.go.kr '조달청_나라장터 계약정보서비스'(공공데이터포털에서 활용신청 필요, 키는 G2B_SERVICE_KEY 공용)
- 업체명 필드 구조가 문서마다 달라(corpList 같은 '^'구분 문자열) 응답 항목 전체 문자열에서 별칭을 찾는다.
- history/competitor_contracts.jsonl 에 누적(git 추적). 매일 최근 60일만 겹쳐 조회, 처음엔 365일 백필.

  python competitor_contract_export.py [--days 60] [--out live/competitor_contract_export.json]
"""
import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from competitor_g2b_export import COMPETITOR_ALIASES, TARGET_COMPETITORS
from fetch_g2b_listings import call_api, date_chunks, guess_region, load_config

BASE = "https://apis.data.go.kr/1230000/ao/CntrctInfoService"
OPERATIONS = ["getCntrctInfoListServcPPSSrch", "getCntrctInfoListServc"]  # 검색조건 지원판 우선, 안 되면 전체 목록판
KEYWORDS = ["연수", "역량강화", "원격", "위탁교육", "직무교육"]
TITLE_RE = re.compile(r"연수|역량\s?강화|원격|위탁\s?교육|직무\s?교육|교원")
HISTORY_PATH = Path(__file__).parent / "history" / "competitor_contracts.jsonl"
NAMES = {c: [c] + COMPETITOR_ALIASES.get(c, []) for c in TARGET_COMPETITORS}


def _first(it, *keys):
    for k in keys:
        if it.get(k):
            return it[k]
    return ""


def match_company(item):
    blob = json.dumps(item, ensure_ascii=False)
    for comp, aliases in NAMES.items():
        if any(a in blob for a in aliases):
            return comp
    return None


def fetch(cfg, days):
    interval = cfg.get("request_interval_sec", 0.15)
    rows, op_ok, diag = {}, None, None
    for op in OPERATIONS:
        try:
            call_api(BASE, op, {"serviceKey": cfg["service_key"], "pageNo": 1, "numOfRows": 1, "inqryDiv": 1,
                                "inqryBgnDate": date.today().strftime("%Y%m01"), "inqryEndDate": date.today().strftime("%Y%m%d"),
                                "type": "json"})
            op_ok = op
            break
        except Exception as e:
            diag = str(e)[:300]
            print(f"  [경고] {op} 사용 불가: {diag}", file=sys.stderr)
    if not op_ok:
        return None, diag
    print(f"  계약정보 오퍼레이션: {op_ok}")
    kws = KEYWORDS if op_ok.endswith("PPSSrch") else [None]
    shown = False
    for kw in kws:
        for begin, end in date_chunks(days, 28):
            page, total = 1, None
            while total is None or (page - 1) * 999 < total:
                params = {"serviceKey": cfg["service_key"], "pageNo": page, "numOfRows": 999, "inqryDiv": 1,
                          "inqryBgnDate": begin.strftime("%Y%m%d"), "inqryEndDate": end.strftime("%Y%m%d"), "type": "json"}
                if kw:
                    params["cntrctNm"] = kw
                try:
                    items, total = call_api(BASE, op_ok, params, timeout=30)
                except Exception as e:
                    print(f"  [경고] 조회 실패(kw={kw}, {begin.date()}~{end.date()}, p{page}): {e}", file=sys.stderr)
                    break
                if items and not shown:
                    print(f"  응답 필드: {sorted(items[0].keys())}")
                    shown = True
                for it in items:
                    title = _first(it, "cntrctNm", "bizNm", "cntrctNmNm")
                    if not TITLE_RE.search(title or ""):
                        continue
                    comp = match_company(it)
                    if not comp:
                        continue
                    key = _first(it, "untyCntrctNo", "cntrctNo", "dcsnCntrctNo") or f"{title}|{_first(it, 'cntrctCnclsDate')}"
                    org = _first(it, "cntrctInsttNm", "dminsttNm", "insttNm")
                    dm = _first(it, "dminsttList")
                    if dm and "^" in dm:  # "[1^코드^기관명^...]" 형태면 수요기관명을 꺼낸다
                        parts = dm.strip("[]").split("^")
                        org = parts[2] if len(parts) > 2 else org
                    rows[key] = {"k": key, "competitor": comp, "course": title, "org": org,
                                 "region": guess_region(org), "method": _first(it, "cntrctMthdNm", "cntrctMthd"),
                                 "amount": int(float(_first(it, "totCntrctAmt", "thtmCntrctAmt", "cntrctAmt") or 0)),
                                 "date": str(_first(it, "cntrctCnclsDate", "cntrctDate"))[:10]}
                if not items or page >= 10:
                    break
                page += 1
                time.sleep(interval)
            time.sleep(interval)
    return list(rows.values()), None


def load_history():
    out = {}
    if HISTORY_PATH.exists():
        for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    out[r["k"]] = r
                except (json.JSONDecodeError, KeyError):
                    pass
    return out


def aggregate(records, status):
    by = defaultdict(lambda: {"n": 0, "amount": 0, "methods": Counter(), "regions": Counter()})
    for r in records:
        b = by[r["competitor"]]
        b["n"] += 1
        b["amount"] += r.get("amount") or 0
        b["methods"][("수의" if "수의" in (r.get("method") or "") else
                      "협상" if "협상" in (r.get("method") or "") else
                      "경쟁" if r.get("method") else "미상")] += 1
        b["regions"][r.get("region") or "전국"] += 1
    total_amt = sum(b["amount"] for b in by.values()) or 1
    comps = sorted(by, key=lambda c: -by[c]["amount"])
    return {
        "status": status, "generated": date.today().isoformat(),
        "competitors": [{"name": c, "n": by[c]["n"], "amount": by[c]["amount"],
                         "share": round(by[c]["amount"] / total_amt * 100, 1),
                         "methods": dict(by[c]["methods"]), "top_regions": [k for k, _ in by[c]["regions"].most_common(3)]}
                        for c in comps],
        "records": sorted(records, key=lambda r: r.get("date") or "", reverse=True)[:300],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--out", default="live/competitor_contract_export.json")
    args = ap.parse_args()
    hist = load_history()
    days = args.days if hist else max(args.days, 365)
    rows, err = fetch(load_config(), days)
    if rows is None:
        status = f"계약정보 API 사용 불가 - 공공데이터포털에서 '조달청_나라장터 계약정보서비스' 활용신청이 필요할 수 있음 ({err})"
        print(status, file=sys.stderr)
    else:
        added = sum(1 for r in rows if r["k"] not in hist)
        hist.update({r["k"]: r for r in rows})
        HISTORY_PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                        for r in sorted(hist.values(), key=lambda r: (r.get("date") or "", r["k"]))),
                                encoding="utf-8")
        status = "ok"
        print(f"계약정보: 최근 {days}일 매칭 {len(rows)}건, 신규 {added}건, 누적 {len(hist)}건")
    out = aggregate(list(hist.values()), status)
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
