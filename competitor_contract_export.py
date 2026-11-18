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
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from competitor_g2b_export import COMPETITOR_ALIASES, TARGET_COMPETITORS
from fetch_g2b_listings import call_api, date_chunks, guess_region, load_config
import org_watch

# 서비스 경로가 개편 전후로 다르다(ao/ 접두 유무). 둘 다 시도해 되는 쪽을 쓴다.
BASES = ["https://apis.data.go.kr/1230000/ao/CntrctInfoService", "https://apis.data.go.kr/1230000/ao/CntrctInfoService02",
         "https://apis.data.go.kr/1230000/CntrctInfoService"]  # 신규 서비스는 '02' 접미가 붙기도 한다(사용자정보 UsrInfoService02)
STATUS_PATH = Path(__file__).parent / "history" / "competitor_contracts_status.json"
OPERATIONS = ["getCntrctInfoListServcPPSSrch", "getCntrctInfoListServc"]  # 검색조건 지원판 우선, 안 되면 전체 목록판
KEYWORDS = ["연수", "역량강화", "원격", "위탁교육", "직무교육"]
TITLE_RE = re.compile(r"연수|역량\s?강화|원격|위탁\s?교육|직무\s?교육|교원")
HISTORY_PATH = Path(__file__).parent / "history" / "competitor_contracts.jsonl"
FIELDS = []  # 첫 응답 항목의 필드 목록(진단용)
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


# 날짜 변수 형식이 오퍼레이션마다 다르다(일자 YYYYMMDD / 일시 YYYYMMDDHHMM) — 2026-11-18 오류(07 입력범위값 초과·08 필수값 누락) 대응
DATE_STYLES = [
    ("일시", lambda b, e: {"inqryBgnDt": b.strftime("%Y%m%d") + "0000", "inqryEndDt": e.strftime("%Y%m%d") + "2359"}),
    ("일자", lambda b, e: {"inqryBgnDate": b.strftime("%Y%m%d"), "inqryEndDate": e.strftime("%Y%m%d")}),
]
INQRY_DIVS = [1, 2]
CHUNK_DAYS = 7  # 조회 기간이 길면 '입력범위값 초과'가 나므로 7일 단위로 나눠 받는다


def week_chunks(days_back, span=CHUNK_DAYS):
    """겹치지 않는 '양끝 포함 span일' 구간 — 서비스가 8일 이상(양끝 포함) 조회를 '입력범위값 초과'로 거절한다(2026-11-18 로그 확인)"""
    end = datetime.now()
    cur = end - timedelta(days=days_back)
    while cur.date() <= end.date():
        nxt = min(cur + timedelta(days=span - 1), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


def _safe(e):
    return re.sub(r"serviceKey=[^&\s]+", "serviceKey=***", str(e))[:300]  # 키는 기록하지 않는다


def fetch(cfg, days):
    interval = cfg.get("request_interval_sec", 0.15)
    rows, op_ok, diag, BASE, style, div = {}, None, [], None, None, None
    end0 = datetime.now()
    beg0 = end0 - timedelta(days=CHUNK_DAYS - 1)
    for base, op, (sname, sfn), dv in [(b, o, s, d) for b in BASES for o in OPERATIONS for s in DATE_STYLES for d in INQRY_DIVS]:
        try:
            call_api(base, op, {"serviceKey": cfg["service_key"], "pageNo": 1, "numOfRows": 1, "inqryDiv": dv, **sfn(beg0, end0), "type": "json"},
                     retries=0)
            op_ok, BASE, style, div = op, base, (sname, sfn), dv
            break
        except Exception as e:
            msg = _safe(e)
            diag.append(f"{base.rsplit('/', 2)[-2]}/{op}/{sname}/구분{dv}: {msg[:160]}")
            print(f"  [경고] {op}({sname}, 구분 {dv}) 사용 불가: {msg}", file=sys.stderr)
            time.sleep(interval)
    if not op_ok:
        return None, " | ".join(diag)
    print(f"  계약정보 조합: {op_ok} · 날짜 {style[0]} · 조회구분 {div}")
    print(f"  계약정보 오퍼레이션: {op_ok}")
    kws = KEYWORDS if op_ok.endswith("PPSSrch") else [None]
    shown, fields = False, FIELDS
    fields.clear()
    for kw in kws:
        for begin, end in week_chunks(days):
            page, total = 1, None
            while total is None or (page - 1) * 999 < total:
                params = {"serviceKey": cfg["service_key"], "pageNo": page, "numOfRows": 999, "inqryDiv": div, **style[1](begin, end), "type": "json"}
                if kw:
                    params["cntrctNm"] = kw
                try:
                    items, total = call_api(BASE, op_ok, params, timeout=30)
                except Exception as e:
                    print(f"  [경고] 조회 실패(kw={kw}, {begin.date()}~{end.date()}, p{page}): {_safe(e)}", file=sys.stderr)
                    break
                if items and not shown:
                    print(f"  응답 필드: {sorted(items[0].keys())}")
                    fields[:] = sorted(items[0].keys())
                    shown = True
                for it in items:
                    title = _first(it, "cntrctNm", "bizNm", "cntrctNmNm")
                    if not TITLE_RE.search(title or ""):
                        continue
                    ow = org_watch.match(_first(it, "corpList", "cntrctCorpNm", "corpNm") or json.dumps(it, ensure_ascii=False))
                    if ow:
                        o2 = _first(it, "cntrctInsttNm", "dminsttNm", "insttNm")
                        org_watch.collect({"k": _first(it, "untyCntrctNo", "cntrctNo", "dcsnCntrctNo") or f"{title}|{_first(it, 'cntrctCnclsDate')}",
                                           "org": ow, "kind": "contract", "t": title, "buyer": o2, "region": guess_region(o2),
                                           "amount": int(float(_first(it, "totCntrctAmt", "thtmCntrctAmt", "cntrctAmt") or 0)),
                                           "date": str(_first(it, "cntrctCnclsDate", "cntrctDate"))[:10]})
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
                                 "region": guess_region(org), "method": _first(it, "cntrctCnclsMthdNm", "cntrctMthdNm", "cntrctMthd"),
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
    # 처음이거나 계약방법이 비어 있는 기록이 있으면(필드명 교정 전 수집분) 1년치를 다시 받는다
    days = args.days if hist and all(r.get("method") for r in hist.values()) else max(args.days, 365)
    rows, err = fetch(load_config(), days)
    org_watch.save()
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
    # 진단 기록(git 추적): CI 로그를 못 볼 때도 API 상태·응답 필드를 확인할 수 있게
    STATUS_PATH.write_text(json.dumps({"date": date.today().isoformat(), "status": status, "days": days,
                                       "matched": None if rows is None else len(rows), "fields": FIELDS},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    out = aggregate(list(hist.values()), "ok" if status == "ok" else "error")
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
