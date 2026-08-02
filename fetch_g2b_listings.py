#!/usr/bin/env python3
"""
data.go.kr 조달청 나라장터 OpenAPI 실데이터 수집기
설정: g2b_config.json (엔드포인트/인증키/파라미터/기관 필터)
키워드 프로필: score_listings.py의 KEYWORDS_HIGH / KEYWORDS_MID를 그대로 재사용한다.

핵심 스코프: "연수" 키워드 = 교육청·연수원이 발주하는 사업.
검색 자체는 KEYWORDS_HIGH/MID로 폭넓게 걸어 재현율을 확보하고,
그 결과에서 발주기관/수요기관명이 g2b_config.json의 org_filter_keywords
(기본: 교육청, 연수원)를 포함하는 건만 남겨 정밀도를 맞춘다. 이렇게
두 단계로 걸러야 "인공지능" 같은 넓은 키워드가 교육과 무관한 기관
(상수도공사, 지자체 산업진흥원 등) 공고까지 끌고 오는 문제가 없다.

사용법:
  python fetch_g2b_listings.py digest --days 21 --out live/digest_live.json
    -> 사전규격/입찰공고/낙찰정보 3종을 한 파일에 담아 build_dashboard.py가
       바로 쓸 수 있는 형태로 저장 (run_pipeline.py가 내부적으로 이 경로를 씀)
  python fetch_g2b_listings.py listings --days 21 --out live/listings_live.json
    -> 입찰공고+사전규격만 병합한 구버전 호환 스코어링 입력 (score_listings.py용)
  python fetch_g2b_listings.py winintel --days 21 --out live/win_intel.json
    -> 낙찰정보만 단독 저장

실측으로 확인된 사항 (2026-07-22 기준):
  - 입찰공고정보서비스 getBidPblancListInfoServcPPSSrch: bidNtceNm 파라미터가
    서버단에서 실제로 필터링됨 (전체 14468건 -> "원격연수" 검색 시 3건).
  - 낙찰정보서비스 getScsbidListSttusServcPPSSrch: bidNtceNm 파라미터 정상 동작.
  - 사전규격정보서비스 getPublicPrcureThngInfoServc: prdctClsfcNoNm 파라미터를
    넘겨도 결과가 전혀 바뀌지 않음(무시됨) -> 이 서비스는 전체 목록을 받아
    클라이언트에서 제목 키워드로 걸러낸다.
  - 조회 기간(inqryBgnDt~inqryEndDt)이 약 30일을 넘으면 "입력범위값 초과 에러"
    발생 -> date_chunks()로 g2b_config.json의 date_range_chunk_days 단위로 분할 호출.
  - 발주계획현황서비스(2026-07-28 활성화): 오퍼레이션명은 getOrderPlanSttusListServc
    ("Info"를 끼워 넣은 이름들은 전부 API not found였음). orderBgnYm/orderEndYm은
    서버가 사실상 무시하는 롤링 스냅샷 서비스라, 매일 파이프라인을 돌려야 예정사업이
    누적된다. 자세한 내용은 g2b_config.json의 order_plan.비고 참고.
"""
import sys, os, json, time, argparse
from datetime import datetime, timedelta
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

from score_listings import KEYWORDS_HIGH, KEYWORDS_MID, score_listing

CONFIG_PATH = "g2b_config.json"
SEARCH_KEYWORDS = KEYWORDS_HIGH + KEYWORDS_MID


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    env_key = os.environ.get("G2B_SERVICE_KEY")
    if env_key:
        cfg["service_key"] = env_key
    return cfg


def call_api(base_url, operation, params, timeout=15, retries=2):
    url = f"{base_url}/{operation}?{urlencode(params)}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urlopen(url, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            break
        except (URLError, HTTPError) as e:
            last_err = e
            time.sleep(1)
    else:
        raise RuntimeError(f"네트워크 오류: {last_err} url={url}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON 파싱 실패(응답이 JSON이 아님): {raw[:200]} url={url}")

    if "response" not in data:
        raise RuntimeError(f"API 오류: {raw[:300]} url={url}")
    header = data["response"]["header"]
    if header.get("resultCode") != "00":
        raise RuntimeError(f"API 오류[{header.get('resultCode')}]: {header.get('resultMsg')} url={url}")
    body = data["response"]["body"]
    items = body.get("items") or []
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount", 0) or 0)


def date_chunks(days_back, chunk_days):
    end = datetime.now()
    start = end - timedelta(days=days_back)
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        yield cur, nxt
        cur = nxt


REGION_MAP = [
    ("서울특별시", "서울"), ("부산광역시", "부산"), ("대구광역시", "대구"),
    ("인천광역시", "인천"), ("광주광역시", "광주"), ("대전광역시", "대전"),
    ("울산광역시", "울산"), ("세종특별자치시", "세종"),
    ("경기도", "경기"), ("강원특별자치도", "강원"), ("강원도", "강원"),
    ("충청북도", "충북"), ("충청남도", "충남"),
    ("전북특별자치도", "전북"), ("전라북도", "전북"), ("전라남도", "전남"),
    ("경상북도", "경북"), ("경상남도", "경남"), ("제주특별자치도", "제주"),
    ("서울", "서울"), ("부산", "부산"), ("대구", "대구"), ("인천", "인천"),
    ("광주", "광주"), ("대전", "대전"), ("울산", "울산"), ("세종", "세종"),
    ("경기", "경기"), ("강원", "강원"), ("충북", "충북"), ("충남", "충남"),
    ("전북", "전북"), ("전남", "전남"), ("경북", "경북"), ("경남", "경남"),
    ("제주", "제주"),
]


def guess_region(*texts):
    """기관명에 지역명이 둘 이상 섞여 있을 수 있어(예: 통합사무소 명칭) REGION_MAP
    순서가 아니라 문자열에서 가장 먼저 등장하는 지역명을 우선한다."""
    blob = " ".join(t for t in texts if t)
    best_pos, best_short = None, None
    for pattern, short in REGION_MAP:
        pos = blob.find(pattern)
        if pos != -1 and (best_pos is None or pos < best_pos):
            best_pos, best_short = pos, short
    return best_short or "전국"


def is_target_org(cfg, *texts):
    blob = " ".join(t for t in texts if t)
    return any(kw in blob for kw in cfg.get("org_filter_keywords", ["교육청", "연수원"]))


def to_date(s):
    if not s:
        return ""
    return s.strip().split(" ")[0]


def to_int(*vals):
    for v in vals:
        try:
            n = int(str(v).strip())
            if n:
                return n
        except (TypeError, ValueError):
            continue
    return 0


def dedupe(rows, key_fn):
    seen = {}
    for r in rows:
        seen[key_fn(r)] = r
    return list(seen.values())


def extract_eligibility(it):
    """입찰공고정보서비스 원시 필드에서 참가자격 관련 플래그만 뽑는다. API는 Y/N
    플래그와 제한기준 '명칭'만 줄 뿐 구체적 제한 내용(예: 어떤 업종코드인지)은
    공고 첨부문서에만 있어, 여기서는 '이 공고는 자격조건을 직접 확인해야 한다'는
    주의 신호만 표시한다 - 자사가 자격을 충족하는지 자동 판정하지 않는다.
    실측(2026-07-30, 59건 샘플): indstrytyLmtYn(업종제한)은 93%에서 'Y'라 사실상
    모든 용역 공고에 붙는 구조적 필드일 뿐 변별력이 없어 플래그 계산에서 제외했다.
    반면 지역제한(rgnLmtBidLocplcJdgmBssNm)은 17%만 값이 있어 실제 신호가 된다."""
    region_limit = (it.get("rgnLmtBidLocplcJdgmBssNm") or "").strip()
    joint_region = (it.get("jntcontrctDutyRgnNm1") or "").strip()
    flags = {
        "지역제한": region_limit,
        "실적제한": it.get("arsltCmptYn") == "Y",
        "지정경쟁": it.get("dsgntCmptYn") == "Y",
        "공동계약의무지역": joint_region,
    }
    flags["제한있음"] = bool(region_limit or flags["실적제한"] or flags["지정경쟁"] or joint_region)
    return flags


def fetch_bid_announcements(cfg, keywords=SEARCH_KEYWORDS, days_back=21):
    svc = cfg["services"]["bid_public"]
    chunk_days = cfg.get("date_range_chunk_days", 28)
    interval = cfg.get("request_interval_sec", 0.15)
    rows = []
    skipped_org = 0
    for kw in keywords:
        for begin, end in date_chunks(days_back, chunk_days):
            params = {
                "serviceKey": cfg["service_key"],
                "pageNo": 1,
                "numOfRows": 200,
                "inqryDiv": 1,
                "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
                "inqryEndDt": end.strftime("%Y%m%d%H%M"),
                "type": "json",
                svc["keyword_param"]: kw,
            }
            try:
                items, _ = call_api(svc["base_url"], svc["operation"], params)
            except Exception as e:
                print(f"  [경고] 입찰공고 조회 실패 (kw={kw}, {begin.date()}~{end.date()}): {e}", file=sys.stderr)
                continue
            for it in items:
                dminstt = it.get("dminsttNm", "")
                ntceInstt = it.get("ntceInsttNm", "")
                if not is_target_org(cfg, dminstt, ntceInstt):
                    skipped_org += 1
                    continue
                deadline = to_date(it.get("bidClseDt")) or to_date(it.get("opengDt"))
                bid_key = f'{it.get("bidNtceNo","")}-{it.get("bidNtceOrd","")}'
                rows.append({
                    "공고명": it.get("bidNtceNm", ""),
                    "발주기관": dminstt or ntceInstt,
                    "지역": guess_region(dminstt, ntceInstt, it.get("rgnLmtBidLocplcJdgmBssNm", "")),
                    "예산": to_int(it.get("asignBdgtAmt"), it.get("presmptPrce")),
                    "마감일": deadline,
                    "공고일": to_date(it.get("bidNtceDt")),
                    "url": it.get("bidNtceDtlUrl") or it.get("bidNtceUrl") or "https://www.g2b.go.kr/",
                    "_출처": "입찰공고",
                    "_key": bid_key,
                    "_bid_key": bid_key,
                    "자격": extract_eligibility(it),
                })
            time.sleep(interval)
    result = dedupe(rows, lambda r: r["_key"])
    print(f"  입찰공고: 키워드 {len(keywords)}개 x 기간 {days_back}일 조회 -> {len(result)}건(교육청/연수원 외 {skipped_org}건 제외)")
    return result


def fetch_pre_specs(cfg, keywords=SEARCH_KEYWORDS, days_back=21):
    svc = cfg["services"]["pre_spec"]
    chunk_days = cfg.get("date_range_chunk_days", 28)
    interval = cfg.get("request_interval_sec", 0.15)
    all_items = []
    for begin, end in date_chunks(days_back, chunk_days):
        page = 1
        while True:
            params = {
                "serviceKey": cfg["service_key"],
                "pageNo": page,
                "numOfRows": 999,
                "inqryDiv": 1,
                "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
                "inqryEndDt": end.strftime("%Y%m%d%H%M"),
                "type": "json",
            }
            try:
                items, total = call_api(svc["base_url"], svc["operation"], params)
            except Exception as e:
                print(f"  [경고] 사전규격 조회 실패 ({begin.date()}~{end.date()}, page={page}): {e}", file=sys.stderr)
                break
            all_items.extend(items)
            time.sleep(interval)
            if page * 999 >= total or not items or page >= 20:
                break
            page += 1

    rows = []
    skipped_org = 0
    for it in all_items:
        title = it.get("prdctClsfcNoNm", "")
        if not any(kw in title for kw in keywords):
            continue
        rlDminstt = it.get("rlDminsttNm", "")
        orderInstt = it.get("orderInsttNm", "")
        if not is_target_org(cfg, rlDminstt, orderInstt):
            skipped_org += 1
            continue
        rows.append({
            "공고명": f'[사전규격] {title}',
            "발주기관": rlDminstt or orderInstt,
            "지역": guess_region(rlDminstt, orderInstt),
            "예산": to_int(it.get("asignBdgtAmt")),
            "마감일": to_date(it.get("opninRgstClseDt")),
            "공고일": to_date(it.get("rcptDt")),
            "url": it.get("specDocFileUrl1") or "https://www.g2b.go.kr/",
            "_출처": "사전규격",
            "_key": it.get("bfSpecRgstNo", ""),
        })
    result = dedupe(rows, lambda r: r["_key"])
    print(f"  사전규격: 전체 {len(all_items)}건 중 키워드+기관 매칭 -> {len(result)}건(교육청/연수원 외 {skipped_org}건 제외)")
    return result


def fetch_scsbid_intel(cfg, keywords=SEARCH_KEYWORDS, days_back=21):
    svc = cfg["services"]["scsbid"]
    chunk_days = cfg.get("date_range_chunk_days", 28)
    interval = cfg.get("request_interval_sec", 0.15)
    rows = []
    skipped_org = 0
    for kw in keywords:
        for begin, end in date_chunks(days_back, chunk_days):
            params = {
                "serviceKey": cfg["service_key"],
                "pageNo": 1,
                "numOfRows": 200,
                "inqryDiv": 1,
                "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
                "inqryEndDt": end.strftime("%Y%m%d%H%M"),
                "type": "json",
                svc["keyword_param"]: kw,
            }
            try:
                items, _ = call_api(svc["base_url"], svc["operation"], params)
            except Exception as e:
                print(f"  [경고] 낙찰정보 조회 실패 (kw={kw}, {begin.date()}~{end.date()}): {e}", file=sys.stderr)
                continue
            for it in items:
                dminstt = it.get("dminsttNm", "")
                if not is_target_org(cfg, dminstt):
                    skipped_org += 1
                    continue
                bid_key = f'{it.get("bidNtceNo","")}-{it.get("bidNtceOrd","")}'
                rows.append({
                    "공고명": it.get("bidNtceNm", ""),
                    "발주기관": dminstt,
                    "낙찰업체": it.get("bidwinnrNm", ""),
                    "낙찰금액": to_int(it.get("sucsfbidAmt")),
                    "낙찰율(%)": it.get("sucsfbidRate", ""),
                    "참여업체수": it.get("prtcptCnum", ""),
                    "개찰일": to_date(it.get("rlOpengDt")),
                    "url": f'https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={it.get("bidNtceNo","")}&bidPbancOrd={it.get("bidNtceOrd","000")}',
                    "_출처": "낙찰정보",
                    "_key": f'{bid_key}-{it.get("rbidNo","")}',
                    "_bid_key": bid_key,
                })
            time.sleep(interval)
    result = dedupe(rows, lambda r: r["_key"])
    result.sort(key=lambda r: r["개찰일"], reverse=True)
    print(f"  낙찰정보: 키워드 {len(keywords)}개 x 기간 {days_back}일 조회 -> {len(result)}건(교육청/연수원 외 {skipped_org}건 제외)")
    return result


def fetch_order_plan(cfg, **_):
    """발주계획현황서비스(용역, getOrderPlanSttusListServc) - 아직 정식 입찰공고로
    뜨기 전 단계의 '연간 발주계획'을 조회한다. 2026-07-28 실측 확인:
      - orderBgnYm/orderEndYm(YYYYMM) 파라미터는 서버가 실제로는 무시한다(값을
        바꿔도 결과 동일) -> 사전규격서비스와 같은 패턴. 대신 이 서비스는 '오늘
        기준으로 등록/갱신된 발주계획 전체'를 돌려주는 롤링 스냅샷이다(조회일마다
        nticeDt가 당일로 찍힌 건들만 잡힘). 즉 한 번 호출로 연간 전체를 못 받고,
        파이프라인을 매일 돌려야 시간이 지날수록 예정사업이 누적된다.
      - inqryDiv=1 은 필수(없으면 ERROR-08 필수값 누락).
    """
    svc = cfg["services"]["order_plan"]
    interval = cfg.get("request_interval_sec", 0.15)
    today = datetime.now()
    params_base = {
        "serviceKey": cfg["service_key"],
        "type": "json",
        "inqryDiv": 1,
        "orderBgnYm": today.strftime("%Y%m"),
        "orderEndYm": today.strftime("%Y%m"),
    }
    all_items = []
    page = 1
    while True:
        params = {**params_base, "pageNo": page, "numOfRows": 500}
        try:
            items, total = call_api(svc["base_url"], svc["operation"], params)
        except Exception as e:
            print(f"  [경고] 발주계획 조회 실패 (page={page}): {e}", file=sys.stderr)
            break
        all_items.extend(items)
        time.sleep(interval)
        if page * 500 >= total or not items or page >= 10:
            break
        page += 1

    rows = []
    skipped_org = 0
    for it in all_items:
        orderInstt = it.get("orderInsttNm", "")
        totlmng = it.get("totlmngInsttNm", "")
        if not is_target_org(cfg, orderInstt, totlmng):
            skipped_org += 1
            continue
        rows.append({
            "공고명": it.get("bizNm", ""),
            "발주기관": orderInstt or totlmng,
            "지역": guess_region(orderInstt, totlmng),
            "예산": to_int(it.get("sumOrderAmt")),
            "발주예정월": it.get("orderMnth", ""),
            "계약방법": it.get("cntrctMthdNm", ""),
            "등록일": to_date(it.get("nticeDt")),
            "url": "https://www.g2b.go.kr/",
            "_출처": "발주계획",
            "_key": it.get("orderPlanUntyNo") or f'{orderInstt}-{it.get("bizNm","")}',
        })
    result = dedupe(rows, lambda r: r["_key"])
    print(f"  발주계획: 오늘 스냅샷 {len(all_items)}건 중 교육청/연수원 매칭 -> {len(result)}건(그 외 {skipped_org}건 제외)")
    return result


def is_open(deadline_str, today=None):
    """마감일이 비어있거나(정보없음) 오늘 이후면 '진행중'으로 간주."""
    today = today or datetime.now().date()
    if not deadline_str:
        return True
    try:
        d = datetime.strptime(deadline_str, "%Y-%m-%d").date()
    except ValueError:
        return True
    return d >= today


def build_full_digest(cfg, analytics_days=200):
    """
    단일 광역 조회(analytics_days, 기본 연초~오늘)로 입찰공고/사전규격/낙찰정보를
    한 번에 받아, 여기서 '지금 진행중인 것'만 골라 action 셋으로 다시 쓴다.
    (같은 데이터를 두 번 API 호출하지 않기 위한 최적화)
    반환 구조:
      {"action": {"입찰공고":[...], "사전규격":[...]},
       "analytics": {"입찰공고":[...], "사전규격":[...], "낙찰정보":[...]}}
    """
    bid_rows = fetch_bid_announcements(cfg, days_back=analytics_days)
    spec_rows = fetch_pre_specs(cfg, days_back=analytics_days)
    win_rows = fetch_scsbid_intel(cfg, days_back=analytics_days)
    try:
        plan_rows = fetch_order_plan(cfg)
    except Exception as e:
        print(f"  [경고] 발주계획 조회 실패, 이번 실행에서는 제외: {e}", file=sys.stderr)
        plan_rows = []

    def scored(rows):
        out = []
        for r in rows:
            r = dict(r)
            r.pop("_key", None)
            out.append(score_listing(r))
        out.sort(key=lambda x: x["점수"], reverse=True)
        return out

    bid_scored = scored(bid_rows)
    spec_scored = scored(spec_rows)
    for r in win_rows:
        r.pop("_key", None)
    for r in plan_rows:
        r.pop("_key", None)

    action_bid = [x for x in bid_scored if is_open(x.get("마감일", ""))]
    action_spec = [x for x in spec_scored if is_open(x.get("마감일", ""))]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "analytics_days": analytics_days,
        "action": {"입찰공고": action_bid, "사전규격": action_spec},
        "analytics": {"입찰공고": bid_scored, "사전규격": spec_scored, "낙찰정보": win_rows},
        "발주계획_오늘스냅샷": plan_rows,
    }


def build_digest(cfg, days_back=21):
    """사전규격/입찰공고/낙찰정보 3종을 각각 수집·스코어링해 하나의 dict로 묶는다."""
    bid_rows = fetch_bid_announcements(cfg, days_back=days_back)
    spec_rows = fetch_pre_specs(cfg, days_back=days_back)
    scsbid_rows = fetch_scsbid_intel(cfg, days_back=days_back)

    def scored(rows):
        out = []
        for r in rows:
            r = dict(r)
            r.pop("_key", None)
            out.append(score_listing(r))
        out.sort(key=lambda x: x["점수"], reverse=True)
        return out

    for r in scsbid_rows:
        r.pop("_key", None)

    return {
        "생성일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "기준_범위": "연수(교원연수·원격연수 등) 키워드 + 교육청·연수원 발주 건",
        "조회기간_일": days_back,
        "입찰공고": scored(bid_rows),
        "사전규격": scored(spec_rows),
        "낙찰정보": scsbid_rows,
    }


def main():
    ap = argparse.ArgumentParser(description="나라장터 OpenAPI 실데이터 수집")
    ap.add_argument("mode", choices=["full", "digest", "listings", "winintel"],
                     help="full=전략 대시보드용(action+analytics), digest=3종 단순통합, listings=입찰공고+사전규격 병합, winintel=낙찰 인텔리전스만")
    ap.add_argument("--days", type=int, default=None, help="조회 기간(일). 기본값은 g2b_config.json의 default_lookback_days")
    ap.add_argument("--out", default=None, help="출력 파일 경로")
    ap.add_argument("--config", default=CONFIG_PATH)
    args = ap.parse_args()

    cfg = load_config(args.config)
    days = args.days or cfg.get("default_lookback_days", 21)

    if args.mode == "full":
        out = args.out or "live/full_live.json"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        print(f"[나라장터 실데이터 수집 - 전략 대시보드용] 최근 {days}일, 키워드 {len(SEARCH_KEYWORDS)}개")
        full = build_full_digest(cfg, analytics_days=days)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        a, s, w = full["analytics"]["입찰공고"], full["analytics"]["사전규격"], full["analytics"]["낙찰정보"]
        print(f"저장 완료: {out} (analytics: 입찰공고 {len(a)} / 사전규격 {len(s)} / 낙찰정보 {len(w)}, action: 입찰공고 {len(full['action']['입찰공고'])} / 사전규격 {len(full['action']['사전규격'])})")
    elif args.mode == "digest":
        out = args.out or "live/digest_live.json"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        print(f"[나라장터 실데이터 수집 - 통합] 최근 {days}일, 키워드 {len(SEARCH_KEYWORDS)}개")
        digest = build_digest(cfg, days_back=days)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)
        print(f"저장 완료: {out} (입찰공고 {len(digest['입찰공고'])} / 사전규격 {len(digest['사전규격'])} / 낙찰정보 {len(digest['낙찰정보'])})")
    elif args.mode == "listings":
        out = args.out or "live/listings_live.json"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        print(f"[나라장터 실데이터 수집] 최근 {days}일, 키워드 {len(SEARCH_KEYWORDS)}개")
        bid_rows = fetch_bid_announcements(cfg, days_back=days)
        spec_rows = fetch_pre_specs(cfg, days_back=days)
        merged = bid_rows + spec_rows
        for r in merged:
            r.pop("_key", None)
        merged.sort(key=lambda r: r.get("공고일", ""), reverse=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"저장 완료: {out} (총 {len(merged)}건 = 입찰공고 {len(bid_rows)} + 사전규격 {len(spec_rows)})")
    else:
        out = args.out or "live/win_intel.json"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        print(f"[낙찰 인텔리전스 수집] 최근 {days}일, 키워드 {len(SEARCH_KEYWORDS)}개")
        rows = fetch_scsbid_intel(cfg, days_back=days)
        for r in rows:
            r.pop("_key", None)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"저장 완료: {out} (총 {len(rows)}건)")


if __name__ == "__main__":
    main()
