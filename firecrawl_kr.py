#!/usr/bin/env python3
"""
Firecrawl(한국 경유) 공통 수집 도구 - 해외 서버(GitHub 러너) 접속을 끊거나 시간 초과가 나는 국내 공개 페이지용.

  - 키: FIRECRAWL_API_KEY (GitHub Secrets). 없으면 enabled()=False → 각 수집기는 기존 방식만 쓴다.
  - 접속 위치: 한국(location.country=KR). 로그인 없이 보이는 공개 페이지만.
  - robots.txt: 호스트마다 먼저 읽어(Firecrawl 경유) 금지 경로는 요청하지 않는다. Crawl-delay 를 지킨다.
    학교장터(s2b.kr)처럼 전체 금지(Disallow: /)인 곳은 이 도구로도 열지 않는다.
  - 비용: 호출 1건 = 크레딧 1(대략). 실행 1회당 상한 FIRECRAWL_MAX_CALLS(기본 30).
  - 로그에는 키를 남기지 않는다(safe()).
  - 받은 내용은 데이터로만 쓴다(페이지 안의 문구를 지시로 해석하지 않음).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse

API = "https://api.firecrawl.dev/v2/scrape"
KEY = os.environ.get("FIRECRAWL_API_KEY", "").strip()
MAX_CALLS = int(os.environ.get("FIRECRAWL_MAX_CALLS", "30") or 30)
_calls = 0
_robots = {}      # host -> (RobotFileParser|None, delay)
_last = {}        # host -> 마지막 요청 시각
UA_TOKEN = "*"


def enabled():
    return bool(KEY)


def calls():
    return _calls


def safe(s):
    s = str(s)
    if KEY:
        s = s.replace(KEY, "***")
    return re.sub(r"fc-[A-Za-z0-9]{8,}", "fc-***", s)


def _post(body, timeout=90):
    global _calls
    if _calls >= MAX_CALLS:
        raise RuntimeError(f"Firecrawl 호출 상한({MAX_CALLS}) 도달")
    _calls += 1
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {safe(e.read()[:200])}") from None


def _raw(url, formats, main_only=False, wait=0):
    body = {"url": url, "formats": list(formats), "onlyMainContent": main_only,
            "location": {"country": "KR", "languages": ["ko"]}, "maxAge": 0, "timeout": 60000}
    if wait:
        body["waitFor"] = wait
    d = _post(body)
    if not d.get("success"):
        raise RuntimeError(safe(d.get("error") or "실패")[:200])
    return d.get("data") or {}


def robots_ok(url):
    """(허용 여부, crawl-delay초). robots.txt 를 못 읽으면 허용(일반 관례) - 단 4xx/5xx 가 아닌 네트워크 실패만."""
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in _robots:
        rp, delay = None, 0
        try:
            d = _raw(host + "/robots.txt", ["rawHtml"])
            code = (d.get("metadata") or {}).get("statusCode") or 200
            if code < 400:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse((d.get("rawHtml") or "").splitlines())
                delay = rp.crawl_delay(UA_TOKEN) or 0
        except Exception as e:  # noqa: BLE001
            print("  [firecrawl] robots.txt 확인 실패:", safe(e)[:120])
        _robots[host] = (rp, float(delay))
    rp, delay = _robots[host]
    return (rp.can_fetch(UA_TOKEN, url) if rp else True), delay


def scrape(url, formats=("markdown", "links"), main_only=False, wait=2500):
    """공개 페이지 1건. robots 금지면 None. 실패는 예외."""
    ok, delay = robots_ok(url)
    if not ok:
        print(f"  [firecrawl] robots.txt 금지 - 건너뜀: {url}")
        return None
    host = urlparse(url).netloc
    if delay and host in _last:
        gap = delay - (time.time() - _last[host])
        if gap > 0:
            time.sleep(min(gap, 60))
    _last[host] = time.time()
    return _raw(url, formats, main_only, wait)


MD_LINK = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\((https?://[^)\s]+)[^)]*\)")


def _clean(t):
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)          # 이미지
    t = re.sub(r"\\+\n|\\\\", " ", t)
    t = re.sub(r"[*_#`>]|\\", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def grab(url, main_only=False, wait=2500):
    """Playwright grab() 과 같은 모양 {title,url,nav,heads,links,body}. robots 금지면 None."""
    d = scrape(url, ("markdown", "links"), main_only, wait)
    if d is None:
        return None
    return from_doc(d, url)


def from_doc(d, url=""):
    """Firecrawl 응답(data) -> grab 모양"""
    md, meta = d.get("markdown") or "", d.get("metadata") or {}
    links = [{"t": _clean(m.group(1))[:40], "h": m.group(2)} for m in MD_LINK.finditer(md)]
    links = [x for x in links if x["t"]]
    heads = [_clean(MD_LINK.sub(lambda m: m.group(1), x)) for x in re.findall(r"^#{1,4}\s+(.*)$", md, re.M)]
    heads += [_clean(x) for x in re.findall(r"\*\*([^*]{2,60})\*\*", md)]
    heads += [x["t"] for x in links if 4 <= len(x["t"]) <= 60]
    nav = [x["t"] for x in links[:120] if len(x["t"]) <= 20]
    body = _clean(MD_LINK.sub(lambda m: m.group(1), md))
    uniq = lambda xs: list(dict.fromkeys(x for x in xs if x))
    return {"title": meta.get("title") or "", "url": meta.get("url") or url, "nav": uniq(nav)[:80],
            "heads": uniq(heads)[:120], "links": links[:400], "body": body[:60000], "md": md}


if __name__ == "__main__":
    import sys
    print("키:", "설정됨" if enabled() else "미설정")
    if enabled() and len(sys.argv) > 1:
        g = grab(sys.argv[1])
        print(json.dumps({k: (v[:10] if isinstance(v, list) else str(v)[:200]) for k, v in (g or {}).items() if k != "md"}, ensure_ascii=False, indent=1))
