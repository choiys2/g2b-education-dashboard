#!/usr/bin/env python3
"""경기데이터드림 데이터셋 점검(1회성) - 검색 JSON(searchDataset.do)으로 데이터셋을 찾고, API 서비스 페이지에서
Open API 서비스명을 뽑아 시험 호출한다. 키와 개별 행 값은 출력하지 않는다(서비스명·건수·항목 이름만)."""
import json, os, re, sys, urllib.parse, urllib.request

KEY = os.environ.get("GG_DATA_KEY", "")
WORDS = sys.argv[1:] or ["학교 현황", "학원 교습소"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "X-Requested-With": "XMLHttpRequest", "Referer": "https://data.gg.go.kr/portal/data/dataset/searchDatasetPage.do"}
SVC_RE = re.compile(r"openapi\.gg\.go\.kr/([A-Za-z][A-Za-z0-9_]{2,40})")


def get(url, js=True):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode("utf-8", "replace")
    return json.loads(t) if js else t


def api(svc):
    url = f"https://openapi.gg.go.kr/{svc}?" + urllib.parse.urlencode({"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 3})
    try:
        return get(url)
    except Exception as e:
        return {"_err": str(e)[:120]}


def main():
    print("키 설정:", "있음" if KEY else "없음")
    found = {}
    for w in WORDS:
        try:
            d = get("https://data.gg.go.kr/portal/data/dataset/searchDataset.do?" + urllib.parse.urlencode({"category": "", "page": 1, "searchKeyword": w, "size": 20, "sort": "view"}))
        except Exception as e:
            print(f"[{w}] 검색 실패: {e}"); continue
        items = (d.get("result") or {}).get("contents") or []
        if items:
            print(f"[{w}] 키 목록:", sorted(items[0].keys()))
        for it in items[:12]:
            nm = it.get("infNm") or it.get("title") or it.get("infNmKor") or ""
            print(f"[{w}] {nm[:50]} · 기관 {it.get('orgNm')} · infId {it.get('infId')} · API seq {it.get('acolInfSeq')}")
            if not it.get("acolInfSeq"):
                continue
            try:
                html = get(f"https://data.gg.go.kr/portal/data/service/selectAPIServicePage.do?infId={it['infId']}&infSeq={it['acolInfSeq']}", js=False)
                svcs = set(SVC_RE.findall(html))
                if not svcs:
                    html = get(f"https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId={it['infId']}&infSeq={it['acolInfSeq']}", js=False)
                    svcs = set(SVC_RE.findall(html))
                svcs -= {"sample"}
                print(f"      -> 서비스명 {sorted(svcs)}")
                for s in svcs:
                    found.setdefault(s, nm)
            except Exception as e:
                print(f"      -> 상세 실패: {str(e)[:80]}")
    for s, title in found.items():
        d = api(s)
        if "_err" in d:
            print(f"## {s} ({title[:30]}) 호출 실패: {d['_err']}"); continue
        body = d.get(s)
        if not body:
            print(f"## {s} ({title[:30]}) 응답: {json.dumps(d, ensure_ascii=False)[:160]}"); continue
        head = body[0]["head"]; rows = body[1]["row"] if len(body) > 1 else []
        total = next((h["list_total_count"] for h in head if "list_total_count" in h), None)
        code = next((h.get("RESULT", {}).get("CODE") for h in head if "RESULT" in h), None)
        print(f"## {s} ({title[:30]}) {code} · 전체 {total}건 · 항목 {list(rows[0].keys()) if rows else []}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
