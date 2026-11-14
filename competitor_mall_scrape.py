#!/usr/bin/env python3
"""
교사 대상 쇼핑몰(티처몰·아이스크림몰) 상품 동향 수집 - 주 1회(mall_catalog.yml).

수집 항목(로그인 없이 보이는 공개 목록만)
  - 베스트100 순위(/goods/best)
  - 1단계 카테고리별 상품 수와 인기순 상위 상품(/goods/catalog?code=...)
  - 신상품: 지난주 스냅샷에 없던 상품 번호(history/competitor_mall_new.jsonl 누적) + 몰의 NEW 메뉴
  - 세트 상품: 학급세트 카테고리와 상품명의 세트·꾸러미·키트 표기
  - 인기 검색어: 몰 상단 추천 검색어(교사 관심 트렌드 신호)

robots.txt: shop.teacherville.co.kr 은 기본 Disallow / 에 /goods·/promotion·/main 만 허용한다.
허용 경로만 열고, 메뉴의 /click/hyperlink 추적 링크는 따라가지 않고 move= 목적지로 바로 간다.
아이스크림몰(i-screammall.co.kr)은 해외(GitHub 러너) 접속을 끊는다. FIRECRAWL_API_KEY 가 있으면 한국 경유(firecrawl_kr.py)로
첫 화면(쌤PICK·체험단·추천 상품·공지)을 읽는다 - robots.txt Allow, Crawl-delay 30초. 키가 없으면 상태만 기록.
"""
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from playwright.sync_api import sync_playwright

OUT_PATH = Path("history/competitor_mall_catalog.json")
NEW_PATH = Path("history/competitor_mall_new.jsonl")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
TM = "https://shop.teacherville.co.kr"
IS = "https://i-screammall.co.kr/"
SET_RE = re.compile(r"세트|SET|꾸러미|패키지|키트|KIT|묶음")
PRICE_RE = re.compile(r"([\d,]+)\s*원")
COUNT_RE = re.compile(r"(?:총|전체)\s*([\d,]+)\s*(?:개|건)|([\d,]+)\s*개의\s*상품")


def robots_rules(base):
    """(allow, disallow) 경로 목록. 'Disallow : /' 처럼 콜론 앞 공백도 읽는다."""
    try:
        req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  [경고] robots.txt 조회 실패: {e}", file=sys.stderr)
        return None
    allow, disallow, star = [], [], False
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$", line.split("#")[0])
        if not m:
            continue
        k, v = m.group(1).lower(), m.group(2)
        if k == "user-agent":
            star = v == "*"
        elif star and v and k in ("allow", "disallow"):
            (allow if k == "allow" else disallow).append(v.rstrip("$"))
    return allow, disallow


def allowed(rules, url):
    """가장 긴 규칙이 이긴다(Google 방식). robots 조회 실패 시 허용 경로만 쓰는 이 스크립트 특성상 진행."""
    if rules is None:
        return True
    path = urlparse(url).path or "/"
    a = max((len(p) for p in rules[0] if path.startswith(p)), default=-1)
    d = max((len(p) for p in rules[1] if path.startswith(p)), default=-1)
    return a >= d


def target(href):
    """추적 링크(/click/hyperlink?...&move=/goods/...)의 실제 목적지."""
    if "/click/hyperlink" in href:
        mv = parse_qs(urlparse(href).query).get("move", [""])[0]
        return urljoin(TM, unquote(mv)) if mv else ""
    return href


def won(s):
    m = PRICE_RE.search(s or "")
    return int(m.group(1).replace(",", "")) if m else None


def goto(page, url, rules):
    if not allowed(rules, url):
        print(f"  [건너뜀] robots 비허용: {url}")
        return False
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(1500)
        return True
    except Exception as e:
        print(f"  [열기 실패] {url}: {str(e).splitlines()[0][:160]}")
        return False


JS_CARDS = """() => {
  const out = [];
  const num = s => { const m = (s || '').match(/no=(\\d+)/); return m ? m[1] : null; };
  document.querySelectorAll('li.li_goods_best, div.product-card, li.li_goods_only').forEach(el => {
    const a = el.querySelector('a[href*="goods/view"]');
    const no = a && num(a.getAttribute('href'));
    if (!no) return;
    const nameEl = el.querySelector('.wrap_best_name a, .product-name, .wrap_only_name a');
    const sale = el.querySelector('.price, .product-sale-price');
    const cons = el.querySelector('.consumer_price, .product-consumer-price:not(.hide)');
    const rank = el.querySelector('.ranking');
    const badges = [...el.querySelectorAll('.badge-area img, .wrap_item_badge img')].map(i => (i.getAttribute('src') || '').split('/').pop().replace(/\\.\\w+$/, ''));
    out.push({no, name: (nameEl ? nameEl.innerText : a.innerText).trim().replace(/\\s+/g, ' '),
      price: sale ? sale.innerText : '', orig: cons ? cons.innerText : '', rank: rank ? rank.innerText.trim() : '',
      score: el.getAttribute('data-score'), badges});
  });
  return out;
}"""


def cards(page):
    rows, seen = [], set()
    for c in page.evaluate(JS_CARDS):
        if c["no"] in seen or not c["name"]:
            continue
        seen.add(c["no"])
        rows.append({"no": c["no"], "name": c["name"][:120], "price": won(c["price"]), "orig": won(c["orig"]),
                     "rank": int(c["rank"]) if c["rank"].isdigit() else None,
                     "score": float(c["score"]) if c["score"] else None, "badges": c["badges"][:4]})
    return rows


def scrape_teachermall(page):
    rules = robots_rules(TM)
    res = {"name": "티처몰", "operator": "테크빌교육", "url": TM, "status": "ok",
           "best": [], "categories": [], "new_menu": [], "sets": [], "keywords": []}
    if not goto(page, TM + "/", rules):
        res["status"] = "접속 실패"
        return res
    links = page.eval_on_selector_all("a[href]", "els => els.map(a => [a.innerText.trim().replace(/\\s+/g,' '), a.href])")
    # 상단 추천 검색어(학교폭력·독서활동 등): 앞쪽 짧은 링크 중 검색·기획전으로 가는 것
    for t, hr in links[:80]:
        if 1 < len(t) <= 12 and not t.isdigit() and ("search_text=" in hr or "event_view" in hr) and t not in res["keywords"]:
            res["keywords"].append(t)
    cats = {}
    for t, hr in links:
        m = re.search(r"catalog\?code=(\d+)", unquote(hr))
        if m and t and t != "전체보기" and len(m.group(1)) == 8:
            cats.setdefault(m.group(1), t)
    new_url = next((target(hr) for t, hr in links if t.strip().upper() == "NEW"), "")
    print(f"  카테고리 {len(cats)}개 · 추천 검색어 {res['keywords']} · NEW 메뉴 {new_url or '-'}")

    if goto(page, TM + "/goods/best", rules):
        res["best"] = [r for r in cards(page) if r["rank"]][:100] or cards(page)[:100]
        for i, r in enumerate(res["best"]):
            r["rank"] = r["rank"] or i + 1
    print(f"  베스트 {len(res['best'])}개")

    for code, name in sorted(cats.items()):
        url = f"{TM}/goods/catalog?code={code}"
        if not goto(page, url, rules):
            continue
        body = page.inner_text("body")
        m = COUNT_RE.search(body)
        rows = cards(page)
        total = int((m.group(1) or m.group(2)).replace(",", "")) if m else None
        res["categories"].append({"code": code, "name": name, "count": total, "top": rows[:12]})
        print(f"  카테고리 {code} {name}: 총 {total if total is not None else '?'} · 상위 {len(rows)}")
        if re.search(r"세트", name):
            res["sets"] += rows[:24]

    if new_url and goto(page, new_url, rules):
        res["new_menu"] = cards(page)[:40]
        print(f"  NEW 메뉴 {len(res['new_menu'])}개")

    pool = {r["no"]: r for c in res["categories"] for r in c["top"]}
    pool.update({r["no"]: r for r in res["best"] + res["new_menu"]})
    res["sets"] = list({r["no"]: r for r in res["sets"] + [r for r in pool.values() if SET_RE.search(r["name"])]}.values())[:60]
    res["providers"] = providers(page, rules)
    return res


REGION_RE = re.compile(r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청북|충북|충청남|충남|전북|전라북|전남|전라남|경상북|경북|경상남|경남|제주)")


def providers(page, rules):
    """입점사 현황(/service/provider): 회사명·시도만(상세 주소는 저장하지 않음)."""
    if not goto(page, TM + "/service/provider", rules):
        return []
    # 표(tr/td)가 아니어도 되게: 소재지(시도로 시작) 요소와 바로 앞 형제(회사명)를 짝짓는다
    rows = page.evaluate("""() => {
      const RE = /^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|충북|충남|전라|전북|전남|경상|경북|경남|제주)/;
      const out = [];
      document.querySelectorAll('td, li, div, span, p, dd').forEach(el => {
        if (el.children.length) return;
        const t = (el.innerText || '').trim();
        if (!RE.test(t) || t.length > 80) return;
        let prev = el.previousElementSibling;
        if (!prev && el.parentElement) prev = el.parentElement.previousElementSibling;
        const name = prev ? (prev.innerText || '').trim() : '';
        if (name && name.length <= 60 && !RE.test(name) && name !== '입점사 명') out.push([name, t]);
      });
      return out;
    }""")
    out, seen = [], set()
    for c in rows:
        if c[0] in seen:
            continue
        seen.add(c[0])
        m = REGION_RE.match(c[1])
        if m:
            r = m.group(1)
            r = {"충청북": "충북", "충청남": "충남", "전라북": "전북", "전라남": "전남", "경상북": "경북", "경상남": "경남"}.get(r, r)
            out.append({"name": c[0][:60], "region": r})
    print(f"  입점사 {len(out)}곳")
    return out


SELLER_RE = re.compile(r"판매자\s+(.+?)\s+미니샵")
MAKER_RE = re.compile(r"수입자를 함께 표기\s+(.+?)\s+AS\s?책임자")


def sellers(page, rules, nos, cache, limit=260):
    """상품 상세의 판매자·제조자(공개 표기). 한 번 본 상품은 캐시를 쓴다."""
    n = 0
    for no in nos:
        if no in cache or n >= limit:
            continue
        n += 1
        if not goto(page, f"{TM}/goods/view?no={no}", rules):
            continue
        t = re.sub(r"\s+", " ", page.inner_text("body"))
        s, m = SELLER_RE.search(t), MAKER_RE.search(t)
        cache[no] = {"seller": s.group(1)[:40] if s else "", "maker": m.group(1)[:40] if m else ""}
    print(f"  판매자 조회 {n}건(캐시 {len(cache)})")
    return cache


def probe_iscream(page):
    try:
        page.goto(IS, wait_until="domcontentloaded", timeout=20000)
        return {"name": "아이스크림몰", "operator": "아이스크림미디어", "url": IS, "status": "접속 가능(수집기 미구현)"}
    except Exception as e:
        return {"name": "아이스크림몰", "operator": "아이스크림미디어", "url": IS, "status": "수집 불가",
                "note": "해외 서버 접속 차단(" + str(e).splitlines()[0].split("net::")[-1][:40] + ")"}


ISC_GOODS = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\((https://i-screammall\.co\.kr/goods/detail/(\d+))[^)]*\)")
ISC_EVENT = re.compile(r"\[\\?\[체험단\\?\]\s*([^\\\]]+?)\\*\n(?:.|\n)*?모집기간\s*([\d-]+\s*~\s*[\d-]+)(?:.|\n)*?체험단인원\s*(\d+)명\]\((https://i-screammall\.co\.kr/event/\d+)\)")
ISC_NOTICE = re.compile(r"- \[(.+?)\]\((https://i-screammall\.co\.kr/customer/notice/\d+)\)", re.S)


def _isc_lines(t):
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    return [x.strip(" \\*") for x in re.split(r"(?:\\+)?\n", t) if x.strip(" \\*")]


def parse_iscream(md):
    """아이스크림몰 첫 화면(한국 경유 수집본) -> 쌤PICK·체험단 상품·카테고리·공지. 공개 목록만, 회원 정보 없음."""
    goods = {}
    for m in ISC_GOODS.finditer(md):
        lines = _isc_lines(m.group(1))
        if not lines:
            continue
        prices = [int(x.replace(",", "").replace("원", "")) for x in lines if re.fullmatch(r"[\d,]+원", x)]
        disc = next((int(x[:-1]) for x in lines if re.fullmatch(r"\d{1,2}%", x)), None)
        names = [x for x in lines if not re.fullmatch(r"[\d,]+원|\d{1,2}%|상품 바로가기", x)]
        name = max(names, key=len) if names else ""
        if not name:
            continue
        seller = names[0] if len(names) > 1 and names[0] != name and len(names[0]) <= 20 else ""
        no = m.group(3)
        cur = goods.get(no, {})
        if len(name) >= len(cur.get("name", "")):
            goods[no] = {"no": no, "name": name[:80], "price": prices[0] if prices else cur.get("price"),
                         "orig": prices[1] if len(prices) > 1 else cur.get("orig"), "disc": disc if disc is not None else cur.get("disc"),
                         "seller": seller or cur.get("seller", "")}
    trials = [{"title": re.sub(r"\s+", " ", m.group(1)).strip()[:60], "period": m.group(2), "n": int(m.group(3)), "url": m.group(4)}
              for m in ISC_EVENT.finditer(md)]
    notices = []
    for m in ISC_NOTICE.finditer(md):
        ls = _isc_lines(m.group(1).replace("\\[", "[").replace("\\]", "]"))
        if len(ls) >= 2 and re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", ls[-1]):
            notices.append({"title": ls[0][:60], "date": ls[-1].replace(".", "-")})
    head = md.split("## 30초")[0]
    cats = [x.strip() for x in head.split("\n") if x.strip() and not x.startswith(("#", "[", "!")) and len(x.strip()) <= 20 and x.strip() != "전체"]
    pick = next(iter(goods.values()), None) if "30초 쌤 PICK" in md else None
    return {"goods": list(goods.values())[:40], "pick": pick, "trials": trials[:10], "notices": notices[:8], "categories": cats[:20]}


def scrape_iscream(prev_isc):
    """FIRECRAWL_API_KEY 가 있으면 한국 경유로 첫 화면을 읽는다(robots.txt Allow·Crawl-delay 30초 준수, 요청 1~2건).
    키가 없거나 실패하면 지난 수집분을 유지하고 상태만 바꾼다."""
    base = {"name": "아이스크림몰", "operator": "아이스크림미디어", "url": IS}
    try:
        import firecrawl_kr as fc
    except Exception:  # noqa: BLE001
        fc = None
    if not (fc and fc.enabled()):
        print("아이스크림몰 한국 경유: FIRECRAWL_API_KEY 미설정 - 지난 수집분 유지", flush=True)
        keep = {k: v for k, v in (prev_isc or {}).items() if k in ("goods", "pick", "trials", "notices", "categories", "services", "captured", "via")}
        return dict(base, status="수집 중" if keep.get("goods") else "수집 불가",
                    note=("지난 수집분 " + keep.get("captured", "") + " · 키 미설정") if keep.get("goods") else "해외 서버 접속 차단 · 키 미설정", **keep) if keep.get("goods") else None
    print(f"아이스크림몰 한국 경유: 키 설정됨 · 이번 달 사용 {fc.month_used()}/{fc.MONTH_CAP}", flush=True)
    try:
        d = fc.scrape(IS, ("markdown",), main_only=True, wait=3000)
        if d is None:
            return dict(base, status="수집 불가", note="robots.txt 금지")
        r = parse_iscream(d.get("markdown") or "")
        if not (r["goods"] or r["trials"]):
            raise RuntimeError("상품 0건(화면 구조 변경 의심)")
        return dict(base, status="수집 중", via="firecrawl(한국 경유)", services=(prev_isc or {}).get("services", []), **r)
    except Exception as e:  # noqa: BLE001
        msg = fc.safe(e)[:80]
        keep = {k: v for k, v in (prev_isc or {}).items() if k in ("goods", "pick", "trials", "notices", "categories", "services", "captured")}
        return dict(base, status="수집 불가", note="한국 경유 수집 실패: " + msg, **keep)


def main():
    today = date.today().isoformat()
    prev = {}
    if OUT_PATH.exists():
        prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    seen = prev.get("seen", {})
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(user_agent=UA, locale="ko-KR").new_page()
        tm = scrape_teachermall(page)
        if tm.get("status") == "ok":
            nos = [r["no"] for r in tm["best"]] + [r["no"] for r in tm["sets"]] + [r["no"] for c in tm["categories"] for r in c["top"]]
            tm["sellers"] = sellers(page, robots_rules(TM), list(dict.fromkeys(nos)),
                                    ((prev.get("malls") or {}).get("teachermall") or {}).get("sellers", {}))
        page2 = b.new_context(user_agent=UA, locale="ko-KR").new_page()
        isc = probe_iscream(page2)
        b.close()
    fc_isc = scrape_iscream((prev.get("malls") or {}).get("iscream"))
    if fc_isc:
        isc = fc_isc
        if isc.get("status") == "수집 중":
            isc["captured"] = today
            first_isc = not any(k.startswith("isc:") for k in seen)
            for g in isc.get("goods", []):
                key = "isc:" + g["no"]
                if key not in seen:
                    seen[key] = today
                    if not first_isc:
                        with NEW_PATH.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"first_seen": today, "mall": "아이스크림몰", "no": g["no"], "name": g["name"], "price": g.get("price")}, ensure_ascii=False) + "\n")
    if tm["status"] != "ok" or not (tm["best"] or tm["categories"]):
        print("티처몰 수집 결과가 비어 기존 파일을 유지합니다.", file=sys.stderr)
        if prev:
            prev.setdefault("malls", {})["iscream"] = isc
            OUT_PATH.write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    pool = {r["no"]: r for c in tm["categories"] for r in c["top"]}
    pool.update({r["no"]: r for r in tm["best"] + tm["new_menu"] + tm["sets"]})
    first_run = not seen
    new_rows = []
    for no, r in pool.items():
        if no not in seen:
            seen[no] = today
            if not first_run:
                new_rows.append({"first_seen": today, "mall": "티처몰", **{k: r[k] for k in ("no", "name", "price")}})
    if new_rows:
        with NEW_PATH.open("a", encoding="utf-8") as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out = {"captured_date": today, "malls": {"teachermall": tm, "iscream": isc}, "seen": seen}
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: 베스트 {len(tm['best'])} · 카테고리 {len(tm['categories'])} · 세트 {len(tm['sets'])} · 신규 {len(new_rows)}"
          f"{' (첫 수집 - 기준선만 저장)' if first_run else ''} · 아이스크림몰 {isc['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
