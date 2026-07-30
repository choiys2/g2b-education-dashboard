#!/usr/bin/env python3
"""
S2B(학교장터, The-K 한국교직원공제회 위탁운영) 견적요청/소액수의공고 공개 조회 파일럿.

⚠️ 자동/정기 실행 금지: https://s2b.kr/robots.txt 가 "User-agent: * / Disallow: /"로
전체 사이트에 대한 자동화 접근을 명시적으로 금지하고 있다(2026-07-30 확인). 로그인 없이
열리는 페이지라도 운영자가 로봇 배제 표준으로 명시적으로 거부 의사를 밝힌 이상 존중해야
한다고 판단해, 이 스크립트는 GitHub Actions 등 예약/자동 실행 파이프라인에 절대 연결하지
않는다(deploy.yml에 없음). 기술 검증·수동 1회성 조회 용도로만 로컬에서 실행할 것.
공식 데이터 제공(API 협조 요청 등)이 성사되기 전에는 이 상태를 유지한다.

https://s2b.kr/S2BNCustomer/tcmo001.do 는 로그인 없이 조회 가능한 공개 페이지다
(나라장터에는 안 뜨는 학교 단위 소액 수의계약이 여기 올라온다). 서버가 세션 쿠키를
요구하므로 반드시 GET으로 세션을 먼저 연 뒤 같은 쿠키로 POST해야 한다.

실측으로 확인된 사항(2026-07-30):
  - urllib.parse.urlencode()에 encoding="euc-kr"를 명시하지 않으면 한글 파라미터
    (areaKind 등)가 UTF-8로 퍼센트인코딩되어 서버에 전달되고, 서버는 이를 EUC-KR로
    해석해 조건에 안 맞아 결과 0건을 반환한다(에러 없이 빈 목록만 옴 - 조용한 실패라
    발견이 어려웠다). 응답 자체는 항상 EUC-KR.
  - "3개월 이상은 조회 하실 수 없습니다" 라는 클라이언트 제약이 있어 날짜 범위는
    최대 90일. 매일 도는 파이프라인이므로 기본값은 21일(최근 발생분만)로 좁혀서
    매번 전체 백로그를 다시 긁지 않는다.
  - 응답은 JSON이 아니라 서버렌더링 HTML(구형 JSP). 결과 행은 2개 <tr>이 한 쌍으로
    구성되며(홀수행: NO/계약구분/도서산간/공고번호/공고명/상태, 짝수행: 거래구분/
    기관명/공고일/마감일), 두 행의 배경색 클래스가 white/sky로 번갈아 바뀐다.
    파싱은 "NO" 셀(1~3자리 숫자, rowspan=2) 위치를 앵커로 청크를 나눠 처리한다
    (공고번호는 15자리라 NO와 자릿수로 구분됨).
  - 아직 파일럿 단계라 지역은 2곳(경기/서울, 학교 수·기존 나라장터 실적 상위권)만
    수집한다. 페이지당 10건, 최대 max_pages까지만 따라간다(무제한 백필 방지).
"""
import http.cookiejar
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE_URL = "https://s2b.kr/S2BNCustomer/tcmo001.do"
PILOT_REGIONS = ["경기", "서울"]

AI_KEYWORDS = ["AI", "인공지능", "AIDT", "디지털교과서", "에듀테크", "메타버스", "VR", "코딩",
               "스마트교육", "디지털 튜터", "생성형", "챗봇", "빅데이터", "이러닝", "e러닝"]

_NO_CELL_RE = re.compile(r'<td rowspan="2" class="td_list_(?:white|sky)_c_01">(\d{1,3})</td>')
_ROWSPAN_CELL_RE = re.compile(r'<td rowspan="2" class="td_list_(?:white|sky)_c_01">([^<]+)</td>')
_NOTICE_NO_RE = re.compile(r'<td rowspan="2" class="td_list_(?:white|sky)_c_01">(\d{15})</td>')
_DETAIL_LINK_RE = re.compile(r"f_detail\('(\d+)','(\d+)'\);\">([^<]*)</a>")
_BIZ_RE = re.compile(r'<td class="td_list_(?:white|sky)_c_01">(물품|공사|용역)</td>')
_ORG_RE = re.compile(r'<td class="td_list_(?:white|sky)_l_01">&nbsp;([^<]+)</td>')
_DATE_RE = re.compile(r'<td class="td_list_(?:white|sky)_c_01">(\d{4}-\d{2}-\d{2}[^<]*)</td>')


def _new_session():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    opener.open(BASE_URL, timeout=20).read()  # 세션 쿠키 확보용 최초 GET
    return opener


def _search_page(opener, region, date_start, date_end, page_no):
    data = {
        "forwardName": "list01", "pageNo": str(page_no), "estimateCode": "", "tender_step_code": "",
        "page_flag": "", "process_yn": "Y", "search_yn": "Y",
        "tender_sep1": "1", "tender_name": "", "company_name_s": "",
        "tender_sep2": "2", "tender_date_start": date_start, "tender_date_end": date_end,
        "tender_item": "", "estimate_kind": "", "areaKind": region,
    }
    body = urllib.parse.urlencode(data, encoding="euc-kr").encode("ascii")
    req = urllib.request.Request(BASE_URL, data=body,
                                  headers={"Content-Type": "application/x-www-form-urlencoded; charset=euc-kr"})
    return opener.open(req, timeout=20).read().decode("euc-kr", errors="replace")


def _parse_rows(html, region):
    starts = [m.start() for m in _NO_CELL_RE.finditer(html)]
    rows = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else s + 3000
        chunk = html[s:e]
        m = _DETAIL_LINK_RE.search(chunk)
        if not m:
            continue
        code, kind, title = m.groups()
        rowspan_cells = _ROWSPAN_CELL_RE.findall(chunk)  # [NO, 계약구분, 공고번호]
        contract = rowspan_cells[1] if len(rowspan_cells) > 1 else ""
        notice_no_m = _NOTICE_NO_RE.search(chunk)
        biz_m = _BIZ_RE.search(chunk)
        org_m = _ORG_RE.search(chunk)
        dates = _DATE_RE.findall(chunk)
        rows.append({
            "학교장터공고번호": notice_no_m.group(1) if notice_no_m else "",
            "계약구분": contract,
            "공고명": title.strip(),
            "거래구분": biz_m.group(1) if biz_m else "",
            "기관명": (org_m.group(1) if org_m else "").strip(),
            "지역": region,
            "공고일": dates[0] if len(dates) > 0 else "",
            "마감일": dates[1] if len(dates) > 1 else "",
            "url": f"https://s2b.kr/S2BNCustomer/tcmo001.do?forwardName=view01_{kind}&estimateCode={code}",
        })
    return rows


def matches_ai(title):
    upper = title.upper()
    return [k for k in AI_KEYWORDS if k.upper() in upper]


def fetch_region(region, days_back=21, max_pages=5, interval=0.3):
    today = datetime.now()
    date_start = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    date_end = today.strftime("%Y%m%d")
    opener = _new_session()
    all_rows = []
    for page in range(1, max_pages + 1):
        html = _search_page(opener, region, date_start, date_end, page)
        rows = _parse_rows(html, region)
        if not rows:
            break
        all_rows.extend(rows)
        time.sleep(interval)
    return all_rows


def fetch_pilot(regions=PILOT_REGIONS, days_back=21, max_pages=5):
    all_rows = []
    for region in regions:
        try:
            rows = fetch_region(region, days_back=days_back, max_pages=max_pages)
        except Exception as e:
            print(f"  [경고] S2B 조회 실패 (지역={region}): {e}", file=sys.stderr)
            continue
        ai_rows = [r for r in rows if matches_ai(r["공고명"])]
        print(f"  {region}: 전체 {len(rows)}건 중 AI 관련 {len(ai_rows)}건")
        all_rows.extend(rows)
    ai_only = [{**r, "키워드": matches_ai(r["공고명"])} for r in all_rows if matches_ai(r["공고명"])]
    return {"all_count": len(all_rows), "ai_rows": ai_only, "regions": regions, "days_back": days_back}


def main():
    import json
    out_path = sys.argv[1] if len(sys.argv) > 1 else "live/s2b_export.json"
    print("[파일럿] S2B(학교장터) 공개 공고 조회 - 지역:", ", ".join(PILOT_REGIONS))
    result = fetch_pilot()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"saved {out_path}: 전체 {result['all_count']}건 중 AI 관련 {len(result['ai_rows'])}건")


if __name__ == "__main__":
    main()
