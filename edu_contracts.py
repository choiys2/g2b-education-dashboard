#!/usr/bin/env python3
"""
교육청·학교 수의계약(K-에듀파인 자동연계 공개) -> 학교 단위 연수·역량강화 계약 누적.

S2B(학교장터)는 robots.txt가 자동 접근을 금지해 직접 수집하지 않는다. 대신 학교·교육청이 체결한
1백만원 이상 수의계약(S2B 거래 포함)은 K-에듀파인과 연계돼 교육청 홈페이지에 공개되므로 그 공개 목록을 읽는다.
교육청별 robots.txt를 매번 확인해 허용된 경로만 요청한다(2026-10-06 진단: history/edu_contract_probe*.json).

  - 전북: /open/edufine/eduCntrlist1.jbe (1인 수의), 계약명 검색(cntr_nm) 지원 -> 연수 키워드로 검색
  - 경남: /user/cntr/BD_cntrInfoSuiList.do (수의계약) - 최신 페이지를 읽어 걸러 냄(표 머리글 자동 인식)
  * 해외(GitHub 서버) 접속이 막힌 교육청·robots 금지 교육청(제주·대전)은 제외.

개인정보: 계약 상대자가 개인(강사 등)일 수 있어 상대자 이름은 저장하지 않는다. 경쟁사·자사로 식별되면 회사 표기,
법인 표지(주식회사·(주)·재단·협회 등)가 있으면 '기타 법인', 그 외는 '기타'로만 남긴다.
  python edu_contracts.py [out_json]
"""
import json
import re
import sys
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
HIST = HERE / "history" / "edu_contracts.jsonl"
STATUS = HERE / "history" / "edu_contracts_status.json"
UA = "Mozilla/5.0 (compatible; g2b-education-dashboard)"
KEYWORDS = ["연수", "역량강화", "직무", "원격"]
TRAIN_RE = re.compile(r"연수|역량\s?강화|직무|원격\s?(교육|강의)|컨설팅|워크숍|워크샵|교육\s?프로그램|강사")
NOT_RE = re.compile(r"공사|수선|구입|구매|임차|설치|급식|청소|경비|세탁|버스|차량|숙박|식비|식대|여행|관광|해외|국외|"
                    r"어학\s?연수|보험|인쇄|현수막|물품|기념품|간식|도시락|안전\s?점검|건설\s?재해|소독|방역|"
                    r"대관|작업|현장\s?실습|체험비|학생|동아리|간담회|진로\s?탐색")
VENDORS = {"아이스크림": r"아이스크림|시공미디어", "티처빌": r"테크빌|티처빌", "비바샘연수원": r"비상교육|비바샘",
           "한교원": r"한국교원연수원"}
CORP = re.compile(r"주식회사|\(주\)|㈜|\(유\)|유한회사|재단|협회|조합|연구소|연구원|대학교|산학협력단|센터|학회|㈔|\(사\)|사단법인")
TAG = re.compile(r"<[^>]+>")
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)


import http.cookiejar
from urllib.request import HTTPCookieProcessor, build_opener
_OPENER = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def get(url, timeout=25, data=None):
    req = Request(url, data=urlencode(data).encode() if data else None,
                  headers={"User-Agent": UA, "Accept-Language": "ko", "Content-Type": "application/x-www-form-urlencoded"})
    with _OPENER.open(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def robots(host):
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(get(f"https://{host}/robots.txt").splitlines())
    except HTTPError as e:
        if e.code in (401, 403):
            rp.disallow_all = True  # 표준: 접근 거부면 전체 금지로 본다
    return rp


def clean(s):
    return re.sub(r"\s+", " ", TAG.sub("", s or "").replace("&nbsp;", " ").replace("&amp;", "&")).strip()


def parse_table(html):
    """머리글로 열을 찾는 범용 표 파서 -> [{org,title,date,amount,vendor}]"""
    rows = [[clean(c) for c in CELL.findall(r)] for r in ROW.findall(html)]
    hi = next((i for i, r in enumerate(rows) if len(r) >= 4 and any(re.fullmatch(r"[^ ]*(계약명|사업명|건명)[^ ]*", c) for c in r)
               and any("금액" in c for c in r)), None)
    if hi is None:
        return [], []
    head = rows[hi]

    def col(rx):
        return next((i for i, h in enumerate(head) if re.search(rx, h)), None)
    ci = {"org": col(r"계약기관|기관명|발주기관|학교명|부서"), "title": col(r"계약명|사업명|건명"),
          "date": col(r"계약일|체결일"), "amount": col(r"계약금액|금액"), "vendor": col(r"상대자|업체|계약자|계약대상자"), "year": col(r"회계\s?년도|회계연도")}
    out = []
    for r in rows[hi + 1:]:
        if len(r) < len(head) - 1:
            continue
        g = lambda k: (r[ci[k]] if ci.get(k) is not None and ci[k] < len(r) else "")
        # 일부 게시판은 셀 앞에 머리글을 다시 붙여 둔다("사업명 2024학년도 ...")
        val = lambda k: re.sub(r"^" + re.escape(head[ci[k]]) + r"\s*", "", g(k)) if ci.get(k) is not None else ""
        d = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", val("date"))
        amt = re.sub(r"[^\d]", "", val("amount"))
        y = re.search(r"20\d{2}", r[ci["year"]]) if ci.get("year") is not None and ci["year"] < len(r) else None
        if not (val("title") and (d or (ci["date"] is None and y)) and amt):
            continue
        title = val("title")
        if val("org") and title.startswith(val("org")):  # 전북: 계약명 앞에 계약기관명이 붙어 나온다
            title = title[len(val("org")):].strip()
        out.append({"org": val("org"), "title": title, "date": f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else y.group(0),
                    "amount": int(amt), "vendor_raw": val("vendor")})
    return out, head


def vendor_label(v):
    for k, rx in VENDORS.items():
        if re.search(rx, v or ""):
            return k
    return "기타 법인" if CORP.search(v or "") else ("기타" if v else "")


def is_training(title):
    t = re.sub(r"연수원", "", title or "")  # '교육연수원 ○○ 작업' 같은 기관명 속 '연수'는 제외
    return bool(TRAIN_RE.search(t)) and not NOT_RE.search(t)


def jbe(status, years, max_pages=10):
    host, path = "www.jbe.go.kr", "/open/edufine/eduCntrlist1.jbe"
    rp = robots(host)
    base = f"https://{host}{path}"
    if not rp.can_fetch(UA, base):
        status["jbe"] = {"skipped": "robots"}
        return []
    rows, pages, heads, per = [], 0, None, {}
    # schoolIn=Y: 학교 계약 포함 여부 플래그로 보인다(기본 N). 두 방식 모두 읽고 중복은 누적 단계에서 제거.
    for variant in ({}, {"schoolIn": "Y"}):
        vk = "school" if variant else "base"
        per[vk] = 0
        for y in years:
            for kw in KEYWORDS:
                for page in range(1, max_pages + 1):
                    q = {"fscl_y": y, "cntr_mthd_div_nm": "1인수의", "cntr_mthd_div": "1", "cntr_nm": kw,
                         "menuCd": "DOM_000001003001009000", "contentsSid": "3099", "cpath": "/open", "pageIndex": page, **variant}
                    html = get(f"{base}?{urlencode(q)}")
                    pages += 1
                    got, heads = parse_table(html)
                    per[vk] += len(got)
                    rows += [{**r, "sido": "전북", "src": "jbe"} for r in got]
                    time.sleep(0.8)
                    if len(got) < 10:
                        break
    status["jbe"] = {"pages": pages, "rows": len(rows), "per_variant": per, "head": heads}
    return rows


def gne(status, pages=8):
    host, path = "www.gne.go.kr", "/user/cntr/BD_cntrInfoSuiList.do"
    rp = robots(host)
    base = f"https://{host}{path}"
    if not rp.can_fetch(UA, base):
        status["gne"] = {"skipped": "robots"}
        return []
    rows, heads, n, seen = [], None, 0, set()
    for page in range(1, pages + 1):
        html = get(f"{base}?{urlencode({'q_currPage': page, 'pageIndex': page, 'currPage': page})}")
        n += 1
        got, heads = parse_table(html)
        key = tuple((r["title"], r["date"]) for r in got[:3])
        if not got or key in seen:  # 페이지 이동 파라미터가 안 먹으면 같은 첫 페이지가 반복된다
            break
        seen.add(key)
        rows += [{**r, "sido": "경남", "src": "gne"} for r in got]
        time.sleep(0.8)
    status["gne"] = {"pages": n, "rows": len(rows), "head": heads}
    return rows


def sen(status, years, max_pages=30):
    """서울: 열린 서울교육 계약정보(학교 포함). 목록에는 계약일자·상대자가 없어 회계연도만 남는다."""
    host, path = "open.sen.go.kr", "/fus/MI000000000000000539/cntr/list0010v.do"
    rp = robots(host)
    base = f"https://{host}{path}"
    if not rp.can_fetch(UA, base):
        status["sen"] = {"skipped": "robots"}
        return []
    get(base)  # 세션 쿠키가 필요한 경우 대비(무해)
    rows, pages, heads = [], 0, None
    for y in years:
        for kw in ("연수", "역량"):
            for page in range(1, max_pages + 1):
                html = get(base, data={"pageIndex": page, "fscl_y": y, "cntr_mthd_div": "1", "cntr_purp_objt_div": "",
                                       "inst_clss_div": "", "cntr_nm": kw, "cntr_inst_nm": "", "cntr_amt": ""})
                pages += 1
                got, heads = parse_table(html)
                rows += [{**r, "sido": "서울", "src": "sen"} for r in got]
                time.sleep(0.8)
                if len(got) < 10:
                    break
    status["sen"] = {"pages": pages, "rows": len(rows), "head": heads}
    return rows


def pen(status, months):
    """부산: K-에듀파인 자동연계 수의계약(1백만원 이상). 1개월 단위 기간 조회 + 계약명 검색."""
    host, path = "www.pen.go.kr", "/main/ir/selectPrvcntrInfoList.do"
    rp = robots(host)
    base = f"https://{host}{path}"
    if not rp.can_fetch(UA, base + "?mi=31735"):
        status["pen"] = {"skipped": "robots"}
        return []
    from datetime import timedelta
    today = date.today()
    rows, pages, heads, mode, diag = [], 0, None, {}, {}
    get(base + "?mi=31735")  # 세션 쿠키
    for m in range(months):
        end = (today.replace(day=1) - timedelta(days=1)).replace(day=1) if m else today
        if m:
            first = today.replace(day=1)
            for _ in range(m):
                first = (first - timedelta(days=1)).replace(day=1)
            bdt, edt = first, (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        else:
            bdt, edt = today.replace(day=1), today
        for inst in ("2", "3", "4", "5"):
            for kw in ("연수", "역량"):
                for page in range(1, 6):
                    q = {"mi": "31735", "accnutYear": bdt.year, "instClCd": inst, "inpBdt": bdt.isoformat(), "inpEdt": edt.isoformat(),
                         "inpSrchCate": "srchCntrctNm", "inpSrchTxt": kw, "inpAmt": "1000000", "currPage": page, "pageIndex": page}
                    html = get(base, data=q) if mode.get("post") else get(f"{base}?{urlencode(q)}")
                    pages += 1
                    got, heads = parse_table(html)
                    if pages == 1 and not got and not mode.get("post"):  # GET이 안 먹으면 POST로 전환(폼은 POST 제출)
                        diag["get_text"] = re.sub(r"\s+", " ", TAG.sub(" ", html))[:300]
                        mode["post"] = True
                        html = get(base, data=q)
                        got, heads = parse_table(html)
                        diag["post_rows"] = len(got)
                        if not got:
                            diag["post_text"] = re.sub(r"\s+", " ", TAG.sub(" ", html))[-600:]
                    rows += [{**r, "sido": "부산", "src": "pen"} for r in got]
                    time.sleep(0.6)
                    if len(got) < 10:
                        break
    status["pen"] = {"pages": pages, "rows": len(rows), "months": months, "post": bool(mode.get("post")), "diag": diag, "head": heads}
    return rows


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "live/edu_contracts.json")
    today = date.today()
    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    status["date"] = today.isoformat()
    years = [today.year, today.year - 1]
    fetched = []
    have = {json.loads(l).get("src") for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()} if HIST.exists() else set()
    # 첫 회는 백필(전년도 포함·여러 쪽), 이후 매일은 올해 최신 몇 쪽만 읽는다(요청 수·시간 절약)
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    jobs = (("jbe", lambda: jbe(status, years if "jbe" not in have else years[:1], 10 if "jbe" not in have else 3)),
            ("gne", lambda: gne(status)),
            ("sen", lambda: sen(status, years if "sen" not in have else years[:1], 30 if "sen" not in have else 5)),
            ("pen", lambda: pen(status, 12 if "pen" not in have else 2)))
    for name, fn in jobs:
        if only and name not in only:
            continue
        try:
            fetched += fn()
        except Exception as e:
            status[name] = {"error": str(e)[:200]}
    old = [json.loads(l) for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()] if HIST.exists() else []
    old = [r for r in old if is_training(r["title"])]  # 필터 규칙이 바뀌면 누적분에도 다시 적용
    seen = {(r["sido"], r["org"], r["title"], r["date"], r["amount"]) for r in old}
    new = 0
    for r in fetched:
        if not is_training(r["title"]):
            continue
        k = (r["sido"], r["org"], r["title"], r["date"], r["amount"])
        if k in seen:
            continue
        seen.add(k)
        old.append({"sido": r["sido"], "org": r["org"][:40], "school": bool(re.search(r"학교$|유치원$", r["org"])),
                    "title": r["title"][:120], "date": r["date"], "amount": r["amount"],
                    "vendor": vendor_label(r.get("vendor_raw")), "src": r["src"]})
        new += 1
    old.sort(key=lambda r: r["date"] if len(r["date"]) > 4 else r["date"] + "-00", reverse=True)
    HIST.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old), encoding="utf-8")
    status.update({"fetched": len(fetched), "training": sum(1 for r in fetched if is_training(r["title"])), "new": new, "total": len(old)})
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(build(old), ensure_ascii=False), encoding="utf-8")
    print(f"교육청 수의계약: 수집 {len(fetched)}건, 연수 {status['training']}건, 신규 {new}건, 누적 {len(old)}건")


def build(rows=None):
    if rows is None:
        rows = [json.loads(l) for l in HIST.read_text(encoding="utf-8").splitlines() if l.strip()] if HIST.exists() else []
    if not rows:
        return {"available": False}
    for r in rows:
        r["school"] = bool(re.search(r"학교$|유치원$", r["org"]))
    from collections import defaultdict
    by_v, by_s, by_m = defaultdict(lambda: {"n": 0, "amt": 0}), defaultdict(lambda: {"n": 0, "amt": 0, "school": 0}), defaultdict(int)
    for r in rows:
        v = by_v[r["vendor"] or "미상"]
        v["n"] += 1
        v["amt"] += r["amount"]
        s = by_s[r["sido"]]
        s["n"] += 1
        s["amt"] += r["amount"]
        s["school"] += r["school"]
        if len(r["date"]) >= 7:
            by_m[r["date"][:7]] += 1
    st = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    return {"available": True, "rows": rows[:400], "total": len(rows), "amount": sum(r["amount"] for r in rows),
            "school": sum(1 for r in rows if r["school"]), "by_vendor": dict(by_v), "by_sido": dict(by_s),
            "months": dict(sorted(by_m.items())[-12:]), "span": [min(r["date"] for r in rows), max(r["date"] for r in rows)],
            "updated": st.get("date"), "sources": {k: v for k, v in (("전북", "전북교육청 1인 수의계약현황"), ("경남", "경남교육청 수의계약 정보"),
                                          ("서울", "열린 서울교육 계약정보"), ("부산", "부산교육청 K-에듀파인 수의계약")) if k in by_s}}


if __name__ == "__main__":
    main()
