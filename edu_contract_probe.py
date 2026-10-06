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


if __name__ == "__main__":
    main()
