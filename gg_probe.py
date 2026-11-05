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
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(locale="ko-KR")
        pg.goto("https://data.gg.go.kr/portal/data/dataset/searchDatasetPage.do", wait_until="domcontentloaded", timeout=60000)
        for w in WORDS:
            try:
                r = pg.request.get("https://data.gg.go.kr/portal/data/dataset/searchDataset.do?" + urllib.parse.urlencode(
                    {"category": "", "page": 1, "searchKeyword": w, "size": 10, "sort": "view"}), timeout=60000)
                items = ((r.json().get("result") or {}).get("contents")) or []
            except Exception as e:
                print(f"[{w}] 검색 실패: {str(e)[:100]}"); continue
            for it in items[:6]:
                nm = it.get("infNm") or ""
                seq = it.get("acolInfSeq")
                print(f"[{w}] {nm[:50]} · infId {it.get('infId')} · API seq {seq}", flush=True)
                if not seq:
                    continue
                try:
                    pg.goto(f"https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId={it['infId']}&infSeq={seq}",
                            wait_until="domcontentloaded", timeout=60000)
                    pg.wait_for_timeout(3000)
                    svcs = set(SVC_RE.findall(pg.content())) - {"sample"}
                    print(f"      -> 서비스명 {sorted(svcs)}", flush=True)
                    for s_ in svcs:
                        found.setdefault(s_, nm)
                except Exception as e:
                    print(f"      -> 상세 실패: {str(e)[:80]}", flush=True)
        br.close()
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
