#!/usr/bin/env python3
"""경기데이터드림 데이터셋 탐색(1회성 점검) - 검색어로 데이터셋을 찾아 Open API 서비스명과 응답 항목 이름만 로그에 남긴다.
키(GG_DATA_KEY)와 개별 행 값은 출력하지 않는다(항목 이름·건수·시군 분포만)."""
import json, os, re, sys, urllib.parse, urllib.request
from playwright.sync_api import sync_playwright

KEY = os.environ.get("GG_DATA_KEY", "")
WORDS = sys.argv[1:] or ["학교 현황", "학원 교습소"]
SVC_RE = re.compile(r"openapi\.gg\.go\.kr/([A-Za-z][A-Za-z0-9_]{2,40})")


def api(svc, **p):
    url = f"https://openapi.gg.go.kr/{svc}?" + urllib.parse.urlencode({"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 5, **p})
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_err": str(e)[:120]}


def main():
    print("키 설정:", "있음" if KEY else "없음")
    found = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(locale="ko-KR")
        for w in WORDS:
            js = []
            pg.on("response", lambda r: js.append(r) if ("json" in (r.headers.get("content-type") or "") or r.request.resource_type in ("xhr", "fetch")) else None)
            url = "https://data.gg.go.kr/portal/data/dataset/searchDatasetPage.do?searchWord=" + urllib.parse.quote(w)
            try:
                pg.goto(url, wait_until="networkidle", timeout=60000)
                pg.wait_for_timeout(2500)
            except Exception as e:
                print(f"[{w}] 검색 실패: {str(e)[:100]}"); continue
            print(f"[{w}] 최종 주소 {pg.url} · XHR {len(js)}개")
            for r in js[:12]:
                try:
                    body = r.text()[:3000]
                except Exception:
                    body = ""
                print("   xhr", r.request.method, r.url[:140], "|", re.sub(r"\s+", " ", body)[:300])
                for s_ in SVC_RE.findall(body):
                    found.setdefault(s_, w)
            text = re.sub(r"\s+", " ", pg.evaluate("() => document.body.innerText"))
            i = text.find(w.split()[0])
            print("   본문:", text[max(0, i - 200): i + 1200])
            links = pg.evaluate("""() => [...document.querySelectorAll('a,[onclick]')].map(a => ({t:(a.innerText||'').trim().replace(/\\s+/g,' ').slice(0,70), h:a.getAttribute('href')||'', on:a.getAttribute('onclick')||''}))
                                   .filter(x => /infId|infSeq|dataset\\/view|selectDataset|goDetail|fn_/i.test(x.h + ' ' + x.on))""")
            print(f"   상세 링크 {len(links)}개:", [(l['t'], (l['h'] + ' ' + l['on'])[:90]) for l in links[:15]])
            for l in [l for l in links if w.split()[0] in l["t"]][:4]:
                try:
                    if l["h"].startswith(("http", "/")) and "javascript" not in l["h"]:
                        pg.goto(urllib.parse.urljoin(pg.url, l["h"]), wait_until="networkidle", timeout=45000)
                    else:
                        pg.goto(url, wait_until="networkidle", timeout=45000)
                        pg.locator("a,[onclick]").filter(has_text=l["t"][:20]).first.click(timeout=10000)
                        pg.wait_for_load_state("networkidle", timeout=30000)
                    for tab in ("Open API", "OpenAPI", "오픈API"):
                        loc = pg.get_by_text(tab, exact=False)
                        if loc.count():
                            try:
                                loc.first.click(timeout=4000); pg.wait_for_timeout(2000); break
                            except Exception:
                                pass
                    svcs = sorted(set(SVC_RE.findall(pg.content())) - {"sample"})
                    print(f"   - {l['t']} ({pg.url[:120]}) -> 서비스명 {svcs}")
                    for s_ in svcs:
                        found.setdefault(s_, l["t"])
                except Exception as e:
                    print(f"   - {l['t']} 열기 실패: {str(e)[:100]}")
        b.close()
    for s, title in found.items():
        d = api(s)
        if "_err" in d:
            print(f"## {s} ({title}) 호출 실패: {d['_err']}"); continue
        body = d.get(s)
        if not body:
            print(f"## {s} ({title}) 응답: {json.dumps(d, ensure_ascii=False)[:200]}"); continue
        head = body[0]["head"]; rows = body[1]["row"] if len(body) > 1 else []
        total = next((h["list_total_count"] for h in head if "list_total_count" in h), None)
        code = next((h.get("RESULT", {}).get("CODE") for h in head if "RESULT" in h), None)
        print(f"## {s} ({title}) 결과 {code} · 전체 {total}건 · 항목 {list(rows[0].keys()) if rows else []}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
