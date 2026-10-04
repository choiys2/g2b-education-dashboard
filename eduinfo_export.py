#!/usr/bin/env python3
"""
지방교육재정알리미(eduinfo.go.kr) Open API - 시도교육청 교원 연수 관련 세출(예산·결산).

호출 형식: http://openapi.eduinfo.go.kr/openApi.do?requestType=<서비스명>&key=<키>&type=json&pIndex=1&pSize=1000
키는 GitHub Secret EDUINFO_KEY.

서비스명(requestType) 목록은 공개 문서에 정리된 곳이 없어, 1단계로 Open API 안내 페이지를 읽어
서비스명·이름을 수집하고(history/eduinfo_status.json 에 기록), 교원 연수 관련 서비스가 확인되면
SERVICES 에 넣어 2단계 데이터 수집을 한다. 수집 결과에서는 사업명·세부사업명에 '연수'가 들어간 행만 남긴다.
"""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
BASE = "http://openapi.eduinfo.go.kr/openApi.do"
DOC_PAGES = ["https://www.eduinfo.go.kr/portal/open/openData/openApiPage.do",
             "https://www.eduinfo.go.kr/portal/open/openData/openApiInfo.do",
             "https://openapi.eduinfo.go.kr/portal/open/openData/openApiPage.do"]
SERVICES = []  # 1단계 진단 후 채운다. 예: [("서비스명", "설명")]
TRAIN_RE = re.compile(r"연수|역량\s?강화|직무")
STATUS = HERE / "history" / "eduinfo_status.json"


def get(url, timeout=25):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 g2b-education-dashboard"})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def discover():
    """안내 페이지에서 requestType 후보와 주변 이름을 긁는다."""
    found, errors = {}, []
    for u in DOC_PAGES:
        try:
            html = get(u)
        except Exception as e:
            errors.append(f"{u}: {str(e)[:120]}")
            continue
        text = re.sub(r"\s+", " ", html)
        for m in re.finditer(r"requestType=([A-Za-z0-9_]+)", text):
            found.setdefault(m.group(1), text[max(0, m.start() - 120):m.start()][-120:])
        # 표/목록에 영문 서비스명이 따로 적힌 경우: 한글명 옆 영문 식별자
        for m in re.finditer(r">\s*([가-힣][^<>]{2,40})\s*<[^>]*>\s*(?:<[^>]*>\s*)*([a-z][A-Za-z0-9_]{4,40})\s*<", html):
            found.setdefault(m.group(2), m.group(1).strip())
    return found, errors


def fetch(key, service):
    rows, page = [], 1
    while page <= 30:
        q = {"requestType": service, "key": key, "type": "json", "pIndex": page, "pSize": 1000}
        data = json.loads(get(f"{BASE}?{urlencode(q)}", timeout=40))
        # 응답 구조가 문서화돼 있지 않아 리스트를 깊이 우선으로 찾는다
        def lists(o):
            if isinstance(o, list) and o and isinstance(o[0], dict):
                yield o
            elif isinstance(o, dict):
                for v in o.values():
                    yield from lists(v)
        batch = max(lists(data), key=len, default=[])
        rows += batch
        if len(batch) < 1000:
            break
        page += 1
        time.sleep(0.2)
    return rows


def main():
    key = os.environ.get("EDUINFO_KEY")
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/eduinfo_export.json")
    found, errors = discover()
    status = {"date": date.today().isoformat(), "doc_errors": errors,
              "services_found": dict(sorted(found.items())[:300]), "fetched": {}}
    result = {"rows": [], "services": []}
    if key:
        for svc, label in SERVICES:
            try:
                rows = fetch(key, svc)
                keep = [r for r in rows if TRAIN_RE.search(json.dumps(r, ensure_ascii=False))]
                status["fetched"][svc] = {"rows": len(rows), "training_rows": len(keep),
                                          "sample": rows[0] if rows else None}
                result["rows"] += [{**r, "_svc": svc} for r in keep]
                result["services"].append({"svc": svc, "label": label})
            except Exception as e:
                status["fetched"][svc] = {"error": str(e)[:200]}
    else:
        status["note"] = "EDUINFO_KEY 없음 - 서비스 목록 진단만 수행"
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"eduinfo: 서비스 후보 {len(found)}개, 문서 오류 {len(errors)}건, 수집 {len(result['rows'])}행")


if __name__ == "__main__":
    main()
