#!/usr/bin/env python3
"""
B2G 연수 배너(수의계약 포함) 자사·타사 시장 분석 - 구글시트 '26타사DT'(gid 400854416).

시트의 테마별(gid 1889843024)·지역별(gid 116759966) 피벗은 모양이 바뀌면 깨지기 쉬워 원본 DT를 읽어
같은 집계(테마×업체, 지역×업체, 월별 추이, 자사 점유)를 직접 계산한다. 피벗 탭은 행 수만 진단에 남긴다.
공개 배포 대시보드이므로 이름·연락처 열은 읽지 않는다(PRIVATE). 연수명·기관명·업체·테마·지역·일자만 쓴다.
  python banner_market.py [out_json]
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
DT_GID = os.environ.get("BANNER_DT_GID", "400854416")
PIVOT_GIDS = {"theme": "1889843024", "region": "116759966"}
STATUS_PATH = HERE / "history" / "banner_market_status.json"
SELF = "비바샘"
PRIVATE = re.compile(r"연락|전화|휴대|메일|성명|이름|주무관|장학사|담당자|담당\s?공무원")
ROLES = [
    ("date", re.compile(r"일자|날짜|일시|게시|등록일|공고일|시작일|date", re.I)),
    ("company", re.compile(r"연수원|업체|운영\s?기관|회사|사업자|자사|타사|경쟁사|브랜드")),
    ("region", re.compile(r"시도|지역|권역")),
    ("org", re.compile(r"교육청|지원청|발주|기관|학교")),
    ("theme", re.compile(r"테마|주제|분야|영역|카테고리")),
    ("title", re.compile(r"연수명|과정명|제목|배너|연수")),
    ("kind", re.compile(r"수의|계약|유형|방식|구분")),
    ("amount", re.compile(r"금액|예산|단가|매출")),
    ("people", re.compile(r"인원|명수|수강")),
]
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
COMPANY_ALIAS = [("비바샘", r"비바샘|비상"), ("티처빌", r"티처빌|테크빌"), ("아이스크림", r"아이스크림|i-?scream"),
                 ("한국교원연수원", r"한국교원|한교원"), ("에듀니티", r"에듀니티|해피스쿨"), ("지식샘터", r"지식샘터"),
                 ("중앙교육연수원", r"중앙교육연수원|중앙교원"), ("방송대", r"방송대|방송통신"), ("EBS", r"EBS|이비에스")]


def detect(header):
    roles = {}
    for i, h in enumerate(header):
        h = (h or "").strip()
        if not h or PRIVATE.search(h):
            continue
        for role, rx in ROLES:
            if role not in roles and rx.search(h):
                roles[role] = i
                break
    return roles


def company(s):
    s = (s or "").strip()
    for name, rx in COMPANY_ALIAS:
        if re.search(rx, s, re.I):
            return name
    return s[:12] or "미상"


def region(*ts):
    blob = " ".join(t or "" for t in ts)
    for r in REGIONS:
        if r in blob:
            return r
    for full, r in (("충청북", "충북"), ("충청남", "충남"), ("전라북", "전북"), ("전북특별", "전북"), ("전라남", "전남"),
                    ("경상북", "경북"), ("경상남", "경남"), ("강원특별", "강원"), ("제주특별", "제주")):
        if full in blob:
            return r
    return "미상"


def pdate(s):
    s = (s or "").strip()
    m = re.search(r"(20\d{2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", s)
    try:
        if m:
            return date(*map(int, m.groups()))
        m = re.search(r"(?<!\d)(\d{1,2})\s?[./월-]\s?(\d{1,2})", s)
        return date(2026, *map(int, m.groups())) if m else None
    except ValueError:
        return None


def num(s):
    try:
        return int(re.sub(r"[^\d]", "", str(s)) or 0)
    except ValueError:
        return 0


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/banner_market.json")
    status = {"date": date.today().isoformat(), "gid": DT_GID}
    try:
        import own_pipeline_export as ope
        if not ope.SA_JSON:
            raise RuntimeError("GOOGLE_SHEETS_SA_JSON 없음")
        m = ope.fetch_via_service_account(DT_GID)
        status["tab"] = ope.STATUS.get("sheet_tab")
        for k, g in PIVOT_GIDS.items():
            try:
                status[f"pivot_{k}_rows"] = len(ope.fetch_via_service_account(g))
            except Exception as e:
                status[f"pivot_{k}_error"] = str(e)[:120]
    except Exception as e:
        status["error"] = str(e)[:300]
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        out.write_text(json.dumps({"available": False, "error": status["error"]}, ensure_ascii=False), encoding="utf-8")
        print(f"[경고] 배너 DT 조회 실패: {e}", file=sys.stderr)
        return
    hrow = max(range(min(10, len(m))), key=lambda i: len(detect(m[i])))
    header, roles = m[hrow], detect(m[hrow])
    status.update({"header_row": hrow + 1, "roles": {k: (header[i] or "").strip() for k, i in roles.items()}})
    rows = []
    for r in m[hrow + 1:]:
        g = lambda k: (r[roles[k]] if k in roles and roles[k] < len(r) else "") or ""
        if not (g("title").strip() or g("company").strip()):
            continue
        rows.append({"d": pdate(g("date")), "co": company(g("company") or g("title")), "rg": region(g("region"), g("org")),
                     "org": g("org").strip()[:30], "t": g("title").strip()[:80], "th": (g("theme").strip() or "미분류")[:16],
                     "k": g("kind").strip()[:10], "a": num(g("amount")), "p": num(g("people"))})
    status["rows"] = len(rows)
    cos = [c for c, _ in Counter(r["co"] for r in rows).most_common(6)]
    if SELF in {r["co"] for r in rows} and SELF not in cos:
        cos = cos[:5] + [SELF]
    top = lambda c: c if c in cos else "기타"
    theme = defaultdict(Counter)
    reg = defaultdict(Counter)
    mon = defaultdict(Counter)
    amt = Counter()
    for r in rows:
        theme[r["th"]][top(r["co"])] += 1
        reg[r["rg"]][top(r["co"])] += 1
        amt[top(r["co"])] += r["a"]
        if r["d"]:
            mon[r["d"].strftime("%Y-%m")][top(r["co"])] += 1
    kinds = Counter(r["k"] for r in rows if r["k"])
    series = cos + (["기타"] if any(r["co"] not in cos for r in rows) else [])
    today = date.today()
    recent = sorted([r for r in rows if r["d"]], key=lambda r: r["d"], reverse=True)[:40]
    data = {
        "available": True, "tab": status["tab"], "rows": len(rows), "self": SELF, "companies": series,
        "fetched": (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
        "totals": {c: sum(theme[t][c] for t in theme) for c in series}, "amount": dict(amt),
        "theme": {t: dict(v) for t, v in sorted(theme.items(), key=lambda x: -sum(x[1].values()))[:20]},
        "region": {k: dict(reg[k]) for k in REGIONS + ["미상"] if k in reg},
        "months": {k: dict(mon[k]) for k in sorted(mon)[-12:]},
        "kinds": dict(kinds.most_common(6)),
        "last30": Counter(top(r["co"]) for r in rows if r["d"] and (today - r["d"]).days <= 30),
        "recent": [{"d": r["d"].isoformat(), "co": r["co"], "rg": r["rg"], "org": r["org"], "t": r["t"], "th": r["th"]} for r in recent],
    }
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"배너 시장: {len(rows)}건, 업체 {series}, 테마 {len(theme)}개")


if __name__ == "__main__":
    main()
