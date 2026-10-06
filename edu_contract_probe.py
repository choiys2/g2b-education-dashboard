#!/usr/bin/env python3
"""
17개 시도교육청 '수의계약 공개(K-에듀파인 자동연계)' 게시판 수집 가능성 진단 (1회성, 수집 아님).

배경: S2B(학교장터)는 robots.txt로 자동 접근을 금지해 쓰지 않는다. 대신 학교·교육청이 체결한 1백만원 이상
수의계약(S2B 거래 포함)은 K-에듀파인과 연계돼 각 교육청 홈페이지 '수의계약공개'에 공개된다.
이 스크립트는 교육청마다
  1) robots.txt 내용과 해당 게시판 경로 허용 여부
  2) 홈페이지에서 '수의계약' 메뉴 링크 탐색(1~2단계)
  3) 찾은 목록 페이지의 응답 코드·표 행 수·머리글
만 기록한다(history/edu_contract_probe.json). 공개 계약정보라 개인정보는 없지만, 본문 행 값은 저장하지 않는다.
요청 간 1초 간격, 교육청당 최대 8회 요청.
"""
import json
import re
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
OUT = HERE / "history" / "edu_contract_probe.json"
UA = "Mozilla/5.0 (compatible; g2b-education-dashboard probe)"
OFFICES = [("서울", "https://www.sen.go.kr/"), ("부산", "https://www.pen.go.kr/"), ("대구", "https://www.dge.go.kr/"),
           ("인천", "https://www.ice.go.kr/"), ("광주", "https://www.gen.go.kr/"), ("대전", "https://www.dje.go.kr/"),
           ("울산", "https://use.go.kr/"), ("세종", "https://www.sje.go.kr/"), ("경기", "https://www.goe.go.kr/"),
           ("강원", "https://www.gwe.go.kr/"), ("충북", "https://www.cbe.go.kr/"), ("충남", "https://www.cne.go.kr/"),
           ("전북", "https://www.jbe.go.kr/"), ("전남", "https://www.jne.go.kr/"), ("경북", "https://www.gbe.kr/"),
           ("경남", "https://www.gne.go.kr/"), ("제주", "https://www.jje.go.kr/")]
# 검색으로 확인한 목록 주소(있으면 탐색 대신 바로 점검)
KNOWN = {"인천": ["https://www.ice.go.kr/contract/ir/selectCntrInfoList.do?mi=11307"],
         "부산": ["https://www.pen.go.kr/main/na/ntt/selectNttList.do?mi=31736&bbsId=2261"],
         "강원": ["https://www.gwe.go.kr/open/bbs/list.do?key=m2305310768003"],
         "광주": ["https://www.gen.go.kr/opengen/kedu/index.php?mode=jaai001f_list"],
         "울산": ["https://use.go.kr/user/edufine/BD_selectJaai001fList.do?q_ifIsSidoCd=H10"]}
LINK_RX = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.S | re.I)
TAG = re.compile(r"<[^>]+>")


def get(url, timeout=20):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw, code, final = r.read(), r.status, r.geturl()
    except HTTPError as e:
        return e.code, "", url
    for enc in ("utf-8", "euc-kr"):
        try:
            return code, raw.decode(enc), final
        except UnicodeDecodeError:
            pass
    return code, raw.decode("utf-8", "replace"), final


def links(html, base, rx):
    out = []
    for href, text in LINK_RX.findall(html):
        t = re.sub(r"\s+", " ", TAG.sub("", text)).strip()
        if rx.search(t) and not href.lower().startswith("javascript"):
            out.append((t[:30], urljoin(base, href)))
    return list(dict.fromkeys(out))


def table_info(html):
    rows = re.findall(r"<tr\b", html, re.I)
    ths = [re.sub(r"\s+", " ", TAG.sub("", h)).strip()[:12] for h in re.findall(r"<th\b[^>]*>(.*?)</th>", html, re.S | re.I)][:14]
    return {"tr": len(rows), "th": ths, "has_amount": bool(re.search(r"계약금액|금액", html)),
            "has_vendor": bool(re.search(r"업체|상대자|계약상대", html)), "school": bool(re.search(r"학교", html))}


def probe(region, home):
    res = {"home": home, "requests": 0}
    host = urlparse(home).netloc
    rp = urllib.robotparser.RobotFileParser()
    code, txt, _ = get(f"https://{host}/robots.txt")
    res["requests"] += 1
    res["robots_code"] = code
    res["robots"] = txt[:600] if code == 200 else ""
    rp.parse(txt.splitlines() if code == 200 else [])
    allowed = lambda u: rp.can_fetch(UA, u) if code == 200 else True  # robots 없으면(404) 표준상 허용
    cands = [("검색 확인", u) for u in KNOWN.get(region, [])]
    if not cands:
        time.sleep(1)
        c, html, final = get(home)
        res["requests"] += 1
        res["home_code"] = c
        cands = links(html, final, re.compile(r"수의계약"))
        if not cands:  # 2단계: 정보공개·계약정보 메뉴 안으로
            for t, u in links(html, final, re.compile(r"계약정보|재정공개|정보공개"))[:3]:
                if not allowed(u):
                    continue
                time.sleep(1)
                c2, h2, f2 = get(u)
                res["requests"] += 1
                cands += links(h2, f2, re.compile(r"수의계약"))
                if cands:
                    break
    res["candidates"] = []
    for t, u in cands[:3]:
        item = {"text": t, "url": u, "robots_allowed": allowed(u)}
        if item["robots_allowed"] and res["requests"] < 8:
            time.sleep(1)
            c, html, final = get(u)
            res["requests"] += 1
            item.update({"code": c, "final": final, **table_info(html)})
        res["candidates"].append(item)
    ok = [c for c in res["candidates"] if c.get("robots_allowed") and c.get("code") == 200 and c.get("tr", 0) >= 5]
    res["verdict"] = ("수집 가능" if ok else "robots 금지" if res["candidates"] and not any(c["robots_allowed"] for c in res["candidates"])
                      else "목록 미확인")
    return res


def main():
    out = {"date": date.today().isoformat(), "offices": {}}
    for region, home in OFFICES:
        try:
            out["offices"][region] = probe(region, home)
        except Exception as e:
            out["offices"][region] = {"home": home, "error": str(e)[:200], "verdict": "접속 실패"}
        print(region, out["offices"][region].get("verdict"))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__" and "--deep" not in __import__("sys").argv:
    main()


# ---------------------------------------------------------------- 2차 진단(--deep)
# 1) 수집 가능 교육청(부산·전북): 표 머리글·첫 3행(셀 40자)·페이지 이동 방식 표본 -> 파서 설계용
# 2) 목록 미확인 교육청: 사이트맵 페이지를 따라가 '수의계약' 링크 탐색, 목록 페이지의 iframe·스크립트 속 계약 주소 수집
# 3) 공공데이터포털 수의계약 파일데이터 카탈로그(이름·기관·파일 주소)
DEEP_OUT = HERE / "history" / "edu_contract_probe_deep.json"
DEEP_KNOWN = {"부산": KNOWN["부산"], "전북": ["https://www.jbe.go.kr/index.jbe?menuCd=DOM_000001003001009000"],
              "경남": ["https://www.gne.go.kr/www/buseo17/contractinfo/contractinfo09.jsp"]}
DATASETS = ["15150722", "15149551", "15139139", "15154073", "15145393", "15137244", "15159509", "15142662",
            "15149295", "15154993", "15153637", "15146957", "15155026", "15153760", "15153862", "15147897", "15144993"]
CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)


def sample(html, final):
    rows = []
    for r in ROW.findall(html)[:5]:
        rows.append([re.sub(r"\s+", " ", TAG.sub("", c)).strip()[:40] for c in CELL.findall(r)][:12])
    pag = list(dict.fromkeys(re.findall(r'href=["\']([^"\']*(?:page|Page|pageIndex|pageNo|currPage)[^"\']*)["\']', html)))[:4]
    js = list(dict.fromkeys(re.findall(r"(?:fn_|go|move)[A-Za-z_]*[Pp]age\w*\([^)]*\)", html)))[:3]
    forms = [(a[:120], re.findall(r'name=["\'](\w+)["\']', b)[:15]) for a, b in
             re.findall(r'<form\b[^>]*action=["\']([^"\']*)["\'][^>]*>(.*?)</form>', html, re.S | re.I)][:3]
    frames = re.findall(r'<iframe\b[^>]*src=["\']([^"\']+)["\']', html, re.I)[:3]
    ajax = list(dict.fromkeys(re.findall(r'["\']([^"\'\s]*(?:jaai|Jaai|cntr|Cntr|contract|Contract|sugye|edufine)[^"\'\s]*)["\']', html)))[:8]
    total = re.search(r"(?:총|전체)\s*(?:게시물|건수)?\s*[:：]?\s*([\d,]+)\s*건", TAG.sub(" ", html))
    return {"final": final, "rows": rows, "paging_links": pag, "paging_js": js, "forms": forms, "iframes": frames,
            "contract_urls": ajax, "total": total.group(1) if total else None, "len": len(html)}


def deep():
    out = {"date": date.today().isoformat(), "samples": {}, "discover": {}, "datasets": {}}
    first = json.loads(OUT.read_text(encoding="utf-8")).get("offices", {}) if OUT.exists() else {}
    for region, home in OFFICES:
        host = urlparse(home).netloc
        rp = urllib.robotparser.RobotFileParser()
        try:
            code, txt, _ = get(f"https://{host}/robots.txt")
            rp.parse(txt.splitlines() if code == 200 else [])
            allowed = lambda u, rp=rp, code=code: rp.can_fetch(UA, u) if code == 200 else True
            if region in DEEP_KNOWN:
                for u in DEEP_KNOWN[region]:
                    if allowed(u):
                        time.sleep(1)
                        c, html, final = get(u)
                        out["samples"][region] = {"code": c, **sample(html, final)}
                continue
            if first.get(region, {}).get("verdict") != "목록 미확인":
                continue
            time.sleep(1)
            c, html, final = get(home)
            found, visited = links(html, final, re.compile(r"수의계약")), []
            for t, u in links(html, final, re.compile(r"사이트\s?맵|sitemap", re.I))[:2]:
                if found or not allowed(u):
                    break
                time.sleep(1)
                c2, h2, f2 = get(u)
                visited.append((u, c2))
                found += links(h2, f2, re.compile(r"수의계약"))
            res = {"home_code": c, "sitemap": visited, "found": found[:5], "checked": []}
            for t, u in found[:2]:
                if not allowed(u):
                    res["checked"].append({"url": u, "robots_allowed": False})
                    continue
                time.sleep(1)
                c3, h3, f3 = get(u)
                res["checked"].append({"url": u, "robots_allowed": True, "code": c3, **sample(h3, f3)})
            out["discover"][region] = res
        except Exception as e:
            out["discover"][region] = {"error": str(e)[:200]}
        print(region, "ok")
    for ds in DATASETS:
        try:
            c, txt, _ = get(f"https://www.data.go.kr/catalog/{ds}/fileData.json")
            d = json.loads(txt) if c == 200 else {}
            dist = d.get("distribution") or []
            out["datasets"][ds] = {"code": c, "name": d.get("name"), "publisher": (d.get("publisher") or {}).get("name") if isinstance(d.get("publisher"), dict) else d.get("publisher"),
                                   "modified": d.get("dateModified"), "keywords": d.get("keywords"),
                                   "files": [{k: x.get(k) for k in ("name", "encodingFormat", "contentUrl", "url")} for x in dist[:3]] if isinstance(dist, list) else dist}
        except Exception as e:
            out["datasets"][ds] = {"error": str(e)[:160]}
        time.sleep(0.5)
    DEEP_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__" and "--deep" in __import__("sys").argv:
    deep()
