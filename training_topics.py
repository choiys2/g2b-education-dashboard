#!/usr/bin/env python3
"""
나라장터 입찰공고(최근 12개월)에서 초·중·고 대상 연수 주제 수요를 뽑아 2027 연수 개발 과정을 추천한다.

왜 따로 수집하나: 일일 파이프라인(run_pipeline.py)은 AI·원격연수 위주 키워드로 연초부터만
조회해서(1월엔 사실상 0일치) '어떤 주제의 연수가 발주되는가'를 보기엔 편향되고 짧다.
그래서 연수 일반 키워드로 입찰공고를 넓게 받아 history/training_bids.jsonl 에 누적한다
(git 추적 - competitor_wins.jsonl 과 같은 방식). 매일은 최근 45일만 겹쳐 조회하고,
처음 한 번만 --days 365 로 백필한다.

  python training_topics.py fetch --days 45     # 수집·누적 (G2B_SERVICE_KEY 필요)
  training_topics.build(...)                    # combine_dashboard.py 가 호출(API 호출 없음)

분류(학교급·온오프라인·주제)는 공고명 키워드 규칙이다. 결정적이고 검증 가능하지만 사람이
태깅한 것만큼 정확하진 않으므로 대시보드에 '자동 분류'로 표시한다. 한 공고가 여러 주제에
걸리면 주제마다 1건씩 센다(주제별 합계 > 전체 공고 수).
"""
import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
HISTORY_PATH = HERE / "history" / "training_bids.jsonl"
KEEP_DAYS = 400      # 12개월 창 + 여유
RULES_VERSION = "2026-10-04b"  # 연수 판정 규칙을 바꾸면 올린다 -> 다음 수집 때 12개월 재백필('학업설계' 오분류 수정, 첨부파일 주소 수집 추가)
WINDOW_DAYS = 365

# 입찰공고 서버측 제목 검색어. '연수'가 대부분을 잡고, 연수라는 말을 안 쓰는 위탁 사업을 나머지로 보완.
FETCH_KEYWORDS = ["연수", "역량강화", "워크숍", "위탁교육", "직무교육", "교원 컨설팅"]
# 초·중·고 교육행정 기관 (대학교는 제외 - 'OO대학교'는 학교 규칙에서 따로 뺀다)
EDU_ORG_RE = re.compile(r"교육청|교육지원청|연수원|교육원|교육연구|교육정보|교육과학|과학원|초등학교|중학교|고등학교|학교")
UNIV_RE = re.compile(r"대학교|대학원|대학$")
# 연수·교육 용역이 아닌 공고(시설·물품·급식 등)
# 교원 연수 과정 개발과 무관한 여행·교류형 연수(학생·교원 해외/어학연수, 자매학교 방문 등)
TRIP_RE = re.compile(r"해외|국외|어학\s?연수|자매\s?학교|방한|해외\s?체험|글로벌\s?현장|콜센터|탐방|문화\s?교류|초청\s?연수")
# 교육 행정기관이 아닌 발주처(이름에 '연수원'·'학교'가 들어가도 제외)
NOT_EDU_ORG_RE = re.compile(r"소방|해양수산|경찰|국방|산림|농업기술|공무원|인재개발원|사법|법무|보훈|연금|기술교육원|고용노동")
NOT_TRAINING_RE = re.compile(r"공사|구매|임차|설치|급식|청소|경비|세탁|침구|사무\s?기기|전산\s?장비|시설|리모델링|건축|전기|소방|물품|차량|보험|"
                             r"인쇄|제작\s?설치|유지\s?보수|유지관리|숙박|식당|방역|승강기|냉난방|조경|감리|(?<!학업)(?<!수업)(?<!과정)(?<!교육)(?<!진로)설계")

# ---------------- 분류 규칙 ----------------
LEVELS = ["초", "중", "고"]
LEVEL_RULES = {
    "초": r"초등|초교|늘봄|돌봄|유초|초중",
    "중": r"중학|중등|초중|중고|자유학기",
    "고": r"고등학교|고교|고등|중고|학점제|진로진학|진학|대입|직업계|특성화고|마이스터",
}
_LEVEL_RE = {k: re.compile(v) for k, v in LEVEL_RULES.items()}

MODES = ["원격", "집합", "혼합"]
MODE_RULES = [
    ("혼합", r"블렌디드|혼합|온[·ㆍ\-]?오프|온오프"),
    ("원격", r"원격|온라인|이러닝|e-?러닝|비대면|실시간\s?쌍방향|콘텐츠\s?(개발|제작)|LMS|사이버"),
    ("집합", r"집합|대면|워크숍|캠프|현장|출장|찾아가는|컨설팅|합숙|체험|실습|아카데미|포럼|세미나"),
]
_MODE_RE = [(k, re.compile(v, re.I)) for k, v in MODE_RULES]

AUDIENCE_RULES = [
    ("교원", r"교원|교사|교직|직무|관리자|교장|교감|선도교|수석|신규|저경력|장학|교육\s?공무원|전문직|교육\s?전문가"),
    ("학부모", r"학부모"),
    ("학생", r"학생|캠프|체험|방과후|동아리|취업|진로\s?체험|중소기업\s?(의\s?)?이해|현장\s?실습|도제|기능\s?경기|인력\s?양성"),
]
_AUD_RE = [(k, re.compile(v)) for k, v in AUDIENCE_RULES]

# 주제 사전: (id, 이름, 정규식, 2027 정책 연계 가중치 1~3, 연계 근거, 학교급별 추천 과정)
# 정책 근거는 편집 기준(2026-09 시점 공개 정책 흐름)이며 수치 주장은 넣지 않는다.
TOPICS = [
    ("ai", "AI·디지털 수업", r"AI|인공지능|디지털|에듀테크|AIDT|코딩|SW|소프트웨어|데이터|메타버스|생성형|챗\s?GPT|정보교육|하이러닝",
     3, "AI 활용 수업·교원 AI 역량 연수체계 개편 기조가 2027년에도 이어진다(2026 AI 활용 선도교사 1만 명 연수).",
     {"초": ("초등 AI 도구로 여는 교과 수업 설계", "AI 도구 선택→수업 설계→윤리·저작권까지 초등 교과 사례 실습"),
      "중": ("중등 교과별 AI 활용 수업·평가 실습", "교과별 생성형 AI 활용 수업안과 AI 기반 피드백·평가 루브릭 제작"),
      "고": ("고교 AI 활용 탐구·프로젝트 수업", "선택과목 연계 AI·데이터 탐구 프로젝트 설계와 학생 산출물 평가")}),
    ("credit", "고교학점제·진로진학", r"고교\s?학점제|학점제|진로|진학|대입|학업\s?설계|과목\s?선택|최소\s?성취|책임교육",
     3, "고교학점제 전면 시행(2025) 3년차 — 학업설계 지도와 최소성취수준 보장이 현장 과제로 남아 있다.",
     {"중": ("중3 진로연계교육·고교 과목선택 지도", "고교학점제 이해, 진로 탐색과 과목 선택 상담 실습(중3 담임용)"),
      "고": ("고교학점제 학업설계 상담과 최소성취수준 보장 지도", "학업설계 상담 대화 모형, 미이수 예방 보충지도 설계, 사례 실습")}),
    ("rights", "교권·교육활동보호", r"교권|교육\s?활동\s?보호|교육\s?활동\s?침해|악성\s?민원|민원\s?대응|교원\s?보호",
     3, "교권보호 관련 법 개정(2023) 이후 학교 단위 교육활동보호 체계(책임관·보호센터) 운영이 확대되고 있다.",
     {"초": ("초등 교육활동 침해 예방과 학부모 민원 대응", "민원 유형별 대응 절차, 기록·보고, 학부모 소통 문장 실습"),
      "중": ("중등 교육활동 침해 사안 처리 실무", "침해 유형 판단, 단계별 대응·보고 절차, 보호 제도 활용 사례"),
      "고": ("중등 교육활동 침해 사안 처리 실무", "침해 유형 판단, 단계별 대응·보고 절차, 보호 제도 활용 사례")}),
    ("care", "생활지도·마음건강", r"생활\s?지도|생활\s?교육|학교\s?폭력|학폭|회복적|상담|마음\s?건강|정서|위기\s?학생|자살|사회\s?정서|SEL|인성",
     3, "학생 마음건강·학교폭력 대응 강화가 교육부·시도교육청 공통 우선과제로 이어진다.",
     {"초": ("초등 사회정서학습(SEL)과 학급 관계 회복", "감정 코칭, 학급 갈등 회복적 대화, 위기 징후 조기 발견"),
      "중": ("중학교 학교폭력 예방과 회복적 생활교육", "관계 회복 서클 운영, 사안 초기 대응, 또래 상담 연계"),
      "고": ("고교 학생 마음건강 위기 대응(게이트키퍼)", "위기 신호 인지, 1차 면담, 전문기관 연계 절차 실습")}),
    ("basic", "기초학력·문해력", r"기초\s?학력|문해력|문해|읽기|난독|학습\s?지원|학습\s?부진|한글|수해력|책임\s?교육",
     2, "기초학력 보장법 시행(2022) 이후 진단-보정 지원 체계가 학교 현장에 정착 중이다.",
     {"초": ("초등 한글·문해력 진단과 맞춤 지도", "학년별 문해 진단 도구 활용, 읽기 부진 유형별 지도 전략"),
      "중": ("중등 교과 문해력과 학습 부진 보정 지도", "교과서 읽기 전략, 어휘·배경지식 지도, 보정 수업 설계"),
      "고": ("고교 교과 문해력과 학습 부진 보정 지도", "교과서 읽기 전략, 어휘·배경지식 지도, 보정 수업 설계")}),
    ("lesson", "수업·평가 혁신", r"수업|평가|과정\s?중심|서\s?논술|논술|IB|교육\s?과정|프로젝트|토론|질문|배움|학습\s?공동체|전학공",
     2, "2022 개정 교육과정 전 학년 적용 완료 시점 — 과정중심 평가·학생 참여형 수업 내실화가 과제다.",
     {"초": ("초등 개념기반 탐구수업과 과정중심평가", "단원 재구성, 탐구 질문 설계, 관찰 평가 기록 실습"),
      "중": ("중등 서·논술형 평가 문항 개발과 채점", "성취기준 기반 문항 개발, 채점 기준표, 피드백 문장 작성"),
      "고": ("고교 서·논술형 평가와 학생부 기록 연계", "문항 개발·채점 기준, 과세특 기록으로 이어지는 평가 설계")}),
    ("neulbom", "늘봄·방과후", r"늘봄|방과\s?후|돌봄",
     2, "늘봄학교 운영 체계 정착 과정에서 프로그램 운영·강사 역량 수요가 이어진다.",
     {"초": ("늘봄 프로그램 기획·운영 실무", "학년별 맞춤 프로그램 설계, 안전·운영 관리, 강사 협업")}),
    ("inclusive", "다문화·특수·통합", r"다문화|이주\s?배경|한국어|특수|통합\s?교육|장애|느린\s?학습자|경계선",
     2, "이주배경 학생 증가와 통합교육 확대로 일반 교사 대상 수요가 늘고 있다.",
     {"초": ("통합학급 개별화 수업과 이주배경 학생 지원", "UDL 기반 수업 조정, 한국어 지원, 가정 소통 실습"),
      "중": ("중등 통합교육 수업 조정과 행동 지원", "수업 조정 전략, 긍정적 행동지원(PBS) 기초, 협력 교수"),
      "고": ("중등 통합교육 수업 조정과 행동 지원", "수업 조정 전략, 긍정적 행동지원(PBS) 기초, 협력 교수")}),
    ("safety", "안전·보건", r"안전|재난|응급|심폐|보건|감염|생존\s?수영|재해|약물|마약",
     1, "법정 안전교육 이수 의무로 수요가 꾸준하다(정책 신규성은 낮음).",
     {"초": ("초등 학교안전 7대 영역 수업 적용", "영역별 안전 수업안, 응급 상황 대응 실습"),
      "중": ("중등 약물·디지털 위험 예방 교육", "마약·약물 오남용과 디지털 위험 예방 수업 실습"),
      "고": ("중등 약물·디지털 위험 예방 교육", "마약·약물 오남용과 디지털 위험 예방 수업 실습")}),
    ("citizen", "민주시민·생태전환", r"민주\s?시민|인권|생태|환경|기후|탄소|노동\s?인권|양성\s?평등|성인지|디지털\s?시민|미디어\s?리터러시",
     1, "생태전환·민주시민 교육은 시도교육청별 편차가 크다(지역 맞춤 제안 필요).",
     {"초": ("초등 기후·생태전환 프로젝트 수업", "학교 텃밭·에너지 프로젝트, 교과 연계 탐구"),
      "중": ("중등 디지털 시민성과 미디어 리터러시", "허위정보 판별, 디지털 발자국, 온라인 관계 윤리 수업"),
      "고": ("중등 디지털 시민성과 미디어 리터러시", "허위정보 판별, 디지털 발자국, 온라인 관계 윤리 수업")}),
    ("leader", "학교 리더십·교원 성장", r"관리자|교장|교감|리더십|생애\s?단계|교직\s?생애|은퇴|신규\s?교사|신규\s?교원|저경력|수석\s?교사|멘토링|컨설팅|장학|자격\s?연수|승진",
     2, "저경력 교사 처우·성장 경로가 정책 쟁점으로 부각되고(OECD 교육지표 2026), 관리자 역량 요구도 커지고 있다.",
     {"초": ("초등 저경력 교사 학급경영 첫 3년", "학급 규칙·관계 형성, 학부모 상담, 업무 적응 사례"),
      "중": ("중등 저경력 교사 수업·생활지도 실무", "수업 운영, 생활지도 초기 대응, 담임 업무 사례"),
      "고": ("중등 저경력 교사 수업·생활지도 실무", "수업 운영, 생활지도 초기 대응, 담임 업무 사례")}),
    ("subject", "교과 전문성", r"수학|과학|영어|국어|사회과|역사|음악|미술|체육|정보과|교과\s?(연구|역량)|실험",
     1, "교과 전문성 연수는 상시 수요이나 AI·평가와 결합한 과정의 차별성이 높다.",
     {"초": ("초등 수학·과학 탐구 실험 수업", "교과서 실험의 탐구화, 안전한 실험 운영, 디지털 측정 도구"),
      "중": ("중등 교과별 AI·에듀테크 결합 수업", "교과 핵심 개념별 에듀테크 활용 수업안 제작"),
      "고": ("고교 선택과목 교과 심화 수업 설계", "진로·융합 선택과목 수업 설계와 평가")}),
    ("parent", "학부모·지역연계", r"학부모|마을\s?교육|지역\s?사회|지역\s?연계|교육\s?공동체",
     1, "학부모 소통 역량은 교권 이슈와 맞물려 교사 대상 수요로 전환되고 있다.",
     {"초": ("교사를 위한 학부모 소통·상담 실무", "상담 준비, 어려운 대화 대응, 안내문·문자 작성 실습"),
      "중": ("교사를 위한 학부모 소통·상담 실무", "상담 준비, 어려운 대화 대응, 안내문·문자 작성 실습"),
      "고": ("교사를 위한 학부모 소통·상담 실무", "상담 준비, 어려운 대화 대응, 안내문·문자 작성 실습")}),
]
_TOPIC_RE = [(t[0], re.compile(t[2])) for t in TOPICS]  # 대소문자 구분: "AI"가 영문 단어 속 "ai"에 걸리지 않게
TOPIC_META = {t[0]: t for t in TOPICS}
POLICY_POINTS = {3: 20, 2: 13, 1: 6}
GENERIC_CONTENT_RE = re.compile(r"콘텐츠|원격\s?(직무)?연수|사이버\s?연수|이러닝")


def classify_levels(title, org=""):
    lv = [k for k, rx in _LEVEL_RE.items() if rx.search(title)]
    if not lv and re.search(r"초등학교", org):
        lv = ["초"]
    elif not lv and re.search(r"중학교", org):
        lv = ["중"]
    elif not lv and re.search(r"고등학교", org):
        lv = ["고"]
    return lv  # 빈 목록 = 학교급 미표기(초·중·고 공통으로 본다)


def classify_mode(title):
    for k, rx in _MODE_RE:
        if rx.search(title):
            return k
    return "미표기"


def classify_audience(title):
    for k, rx in _AUD_RE:
        if rx.search(title):
            return k
    return "미표기"


def classify_topics(title):
    return [tid for tid, rx in _TOPIC_RE if rx.search(title)]


# ---------------- 수집(누적) ----------------
def _to_int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def is_training_bid(title, org):
    if not title or NOT_TRAINING_RE.search(title) or TRIP_RE.search(title):
        return False
    if UNIV_RE.search(org or "") or NOT_EDU_ORG_RE.search(org or ""):
        return False
    return bool(EDU_ORG_RE.search(org or ""))


def fetch(cfg, days_back):
    """입찰공고(용역)를 연수 키워드로 조회 -> 누적용 최소 행 목록."""
    from fetch_g2b_listings import call_api, date_chunks, guess_region, to_date
    svc = cfg["services"]["bid_public"]
    chunk_days = cfg.get("date_range_chunk_days", 28)
    interval = cfg.get("request_interval_sec", 0.15)
    rows = {}
    for kw in FETCH_KEYWORDS:
        for begin, end in date_chunks(days_back, chunk_days):
            page, total = 1, None
            while total is None or (page - 1) * 200 < total:
                params = {
                    "serviceKey": cfg["service_key"], "pageNo": page, "numOfRows": 200, "inqryDiv": 1,
                    "inqryBgnDt": begin.strftime("%Y%m%d%H%M"), "inqryEndDt": end.strftime("%Y%m%d%H%M"),
                    "type": "json", svc["keyword_param"]: kw,
                }
                try:
                    items, total = call_api(svc["base_url"], svc["operation"], params)
                except Exception as e:
                    print(f"  [경고] 조회 실패 (kw={kw}, {begin.date()}~{end.date()}, p{page}): {e}", file=sys.stderr)
                    break
                for it in items:
                    title = (it.get("bidNtceNm") or "").strip()
                    org = it.get("dminsttNm") or it.get("ntceInsttNm") or ""
                    if not is_training_bid(title, org):
                        continue
                    key = f'{it.get("bidNtceNo","")}-{it.get("bidNtceOrd","")}'
                    docs = [[it.get(f"ntceSpecFileNm{i}") or "", it.get(f"ntceSpecDocUrl{i}")]
                            for i in range(1, 11) if it.get(f"ntceSpecDocUrl{i}")]
                    rows[key] = {"k": key, "t": title, "o": org,
                                 "r": guess_region(org, it.get("ntceInsttNm", "")),
                                 "d": to_date(it.get("bidNtceDt")),
                                 "a": _to_int(it.get("asignBdgtAmt") or it.get("presmptPrce")),
                                 "u": it.get("bidNtceDtlUrl") or "",
                                 "f": docs[:6]}  # 첨부(제안요청서·과업지시서 등) - rfp_analysis.py 가 읽는다
                if not items or page >= 20:
                    break
                page += 1
                time.sleep(interval)
            time.sleep(interval)
    return list(rows.values())


def load_history(path=HISTORY_PATH):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    out[r["k"]] = r
                except (json.JSONDecodeError, KeyError):
                    continue
    return out


def save_history(rows, path=HISTORY_PATH, keep_days=KEEP_DAYS, today=None):
    cutoff = ((today or date.today()) - timedelta(days=keep_days)).isoformat()
    kept = sorted((r for r in rows.values() if (r.get("d") or "") >= cutoff), key=lambda r: (r["d"], r["k"]))
    path.parent.mkdir(exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    return len(kept)


# ---------------- 분석 ----------------
def _rows_from_sources(history, full_live=None, competitor_wins=None):
    """누적 이력 + 오늘 파이프라인 입찰공고/낙찰정보 + 경쟁사 낙찰 이력을 합친다(공고번호 기준 중복 제거)."""
    rows = dict(history)
    seen_titles = {(r["t"], r["o"]) for r in rows.values()}

    def add(key, title, org, region, d, amount):
        title = (title or "").replace("[사전규격]", "").strip()
        if not key or key in rows or (title, org) in seen_titles or not is_training_bid(title, org):
            return
        rows[key] = {"k": key, "t": title, "o": org, "r": region or "", "d": d or "", "a": _to_int(amount)}
        seen_titles.add((title, org))

    an = (full_live or {}).get("analytics", {})
    for it in an.get("입찰공고", []):
        add(it.get("_bid_key"), it.get("공고명"), it.get("발주기관"), it.get("지역"), it.get("공고일"), it.get("예산"))
    for it in an.get("낙찰정보", []):
        add(it.get("_bid_key"), it.get("공고명"), it.get("발주기관"), "", it.get("개찰일"), it.get("낙찰금액"))
    for it in competitor_wins or []:
        add(it.get("_key"), it.get("course"), it.get("org"), it.get("region"), it.get("date"), it.get("amount"))
    return list(rows.values())


def _chasi(credit):
    m = re.search(r"(\d+)\s*차시", credit or "")
    return int(m.group(1)) if m else None


def _catalog_coverage(courses_by_company, self_name):
    """주제별 자사·경쟁사 보유 강좌 수, 경쟁사 대표 강좌·가격(15차시 환산 중앙값).
    B2C(개인 수강) 시장의 공급 지표로도 쓴다 - 경쟁사가 많이 깔아둔 주제 = 개인 수요가 검증된 주제."""
    own, comp = Counter(), defaultdict(Counter)
    comp_courses, prices15 = defaultdict(list), defaultdict(list)
    comp_total = 0
    for name, courses in (courses_by_company or {}).items():
        for c in courses:
            title = c.get("title") or ""
            if name != self_name:
                comp_total += 1
            for tid in classify_topics(title):
                if name == self_name:
                    own[tid] += 1
                    continue
                comp[name][tid] += 1
                ch, price = _chasi(c.get("credit")), c.get("price")
                if ch and price:
                    prices15[tid].append(round(price / ch * 15))
                comp_courses[tid].append({"co": name, "t": title, "credit": c.get("credit") or "", "price": price, "url": c.get("url")})
    n_comp = max(len(comp), 1)
    out = {}
    for tid, *_ in TOPICS:
        ps = sorted(prices15[tid])
        comp_n = sum(comp[c][tid] for c in comp)
        out[tid] = {"own": own[tid], "comp_avg": round(comp_n / n_comp, 1), "comp_n": comp_n,
                    "comp_share": round(comp_n / comp_total * 100, 1) if comp_total else 0,
                    "price15_median": ps[len(ps) // 2] if ps else None,
                    "price15_range": [ps[len(ps) // 4], ps[(len(ps) * 3) // 4]] if len(ps) >= 4 else None,
                    # 대표 강좌: 회사별로 고르게(한 회사가 독식하지 않게) 최대 6개
                    "comp_examples": [x for i in range(3) for co in comp
                                      for x in [c for c in comp_courses[tid] if c["co"] == co][i:i + 1]][:6]}
    return out, bool(courses_by_company)


def _pick_mode(mode_counter):
    on, off, mix = mode_counter["원격"], mode_counter["집합"], mode_counter["혼합"]
    total = on + off + mix
    if not total:
        return "블렌디드(원격 15차시 + 실시간 실습 1회)", "공고에 운영 형태 표기가 적어 기본안을 제시"
    if on / total >= 0.5:
        return "원격 15차시(1학점)", f"공고의 {round(on / total * 100)}%가 원격·콘텐츠형"
    if off / total >= 0.5:
        return "집합·출강 연수 + 원격 사전학습(블렌디드)", f"공고의 {round(off / total * 100)}%가 집합·현장형"
    return "블렌디드(원격 + 집합 실습)", "원격·집합 공고가 고르게 섞임"


def build(history_rows=None, full_live=None, competitor_wins=None, courses_by_company=None,
          self_name="비바샘연수원", today=None, window_days=WINDOW_DAYS):
    today = today or date.today()
    start = (today - timedelta(days=window_days)).isoformat()
    # 누적 이력에도 현재 규칙을 다시 적용한다(규칙을 고치면 과거분까지 바로 반영되게)
    in_window = [r for r in _rows_from_sources(history_rows or {}, full_live, competitor_wins)
                 if start <= (r.get("d") or "") <= today.isoformat() and is_training_bid(r["t"], r.get("o", ""))]
    # 학생 대상 프로그램(취업캠프·현장실습 등)은 교원 연수 개발 대상이 아니라 분석에서 뺀다
    rows = [r for r in in_window if classify_audience(r["t"]) != "학생"]
    excluded_student = len(in_window) - len(rows)
    dates = sorted(r["d"] for r in rows)
    first = dates[0] if dates else ""
    # 증감: 실제 데이터 구간을 반으로 나눠 앞/뒤 건수 비교(데이터가 12개월이 안 차도 공정하게)
    mid = ""
    if first:
        d0 = date.fromisoformat(first)
        mid = (d0 + (today - d0) / 2).isoformat()

    coverage, has_catalog = _catalog_coverage(courses_by_company, self_name)
    agg = {tid: {"n": 0, "amount": 0, "recent": 0, "prior": 0, "levels": Counter(), "modes": Counter(),
                 "aud": Counter(), "regions": Counter(), "samples": []} for tid, *_ in TOPICS}
    level_totals, mode_totals, untagged, generic = Counter(), Counter(), 0, []
    for r in rows:
        title = r["t"]
        lv = classify_levels(title, r.get("o", ""))
        mode = classify_mode(title)
        aud = classify_audience(title)
        for l in (lv or ["공통"]):
            level_totals[l] += 1
        mode_totals[mode] += 1
        tids = classify_topics(title)
        if not tids:
            untagged += 1
            if GENERIC_CONTENT_RE.search(title):
                generic.append({"t": title, "o": r.get("o", ""), "d": r["d"], "a": r.get("a") or 0})
        for tid in tids:
            a = agg[tid]
            a["n"] += 1
            a["amount"] += r.get("a") or 0
            if mid and r["d"] >= mid:
                a["recent"] += 1
            else:
                a["prior"] += 1
            for l in (lv or ["공통"]):
                a["levels"][l] += 1
            a["modes"][mode] += 1
            a["aud"][aud] += 1
            if r.get("r"):
                a["regions"][r["r"]] += 1
            a["samples"].append({"t": title, "o": r.get("o", ""), "d": r["d"], "a": r.get("a") or 0,
                                 "lv": lv, "m": mode})

    total = len(rows)
    max_n = max([a["n"] for a in agg.values()] + [1])
    topics = []
    for tid, name, _pat, weight, policy_note, courses in TOPICS:
        a = agg[tid]
        n = a["n"]
        growth = round((a["recent"] - a["prior"]) / a["prior"] * 100) if a["prior"] else (100 if a["recent"] else 0)
        cov = coverage[tid]
        # 점수(100): 수요 40 + 성장 20 + 2027 정책 20 + 자사 공백 20. 규칙이 단순해야 설명 가능하다.
        demand_pts = round(40 * n / max_n)
        growth_pts = 0 if n < 3 else round(max(0, min(growth, 100)) / 100 * 20)
        policy_pts = POLICY_POINTS[weight]
        if has_catalog:
            deficit = cov["comp_avg"] - cov["own"]
            gap_pts = 20 if cov["own"] == 0 else round(max(0, min(deficit / max(cov["comp_avg"], 1), 1)) * 20)
        else:
            gap_pts = 10
        score = demand_pts + growth_pts + policy_pts + gap_pts
        mode_label, mode_reason = _pick_mode(a["modes"])
        lv_total = sum(a["levels"][l] for l in LEVELS) or 0
        samples, seen = [], set()
        for smp in sorted(a["samples"], key=lambda s: (s["d"], s["a"]), reverse=True):
            if (smp["t"], smp["o"]) not in seen:   # 같은 공고의 재공고·차수는 한 번만
                seen.add((smp["t"], smp["o"]))
                samples.append(smp)
            if len(samples) >= 5:
                break
        proposals = []
        for l in LEVELS:
            if l not in courses:
                continue
            title_c, content = courses[l]
            demand_lv = a["levels"][l] + a["levels"]["공통"]
            proposals.append({"level": l, "title": title_c, "content": content, "format": mode_label,
                              "demand": demand_lv, "explicit": a["levels"][l]})
        topics.append({
            "id": tid, "name": name, "n": n, "amount": a["amount"], "share": round(n / total * 100, 1) if total else 0,
            "recent": a["recent"], "prior": a["prior"], "growth": growth,
            "levels": {l: a["levels"][l] for l in LEVELS + ["공통"]},
            "modes": {m: a["modes"][m] for m in MODES + ["미표기"]},
            "audience": dict(a["aud"]), "top_regions": [k for k, _ in a["regions"].most_common(3)],
            "policy_weight": weight, "policy_note": policy_note,
            "coverage": cov, "score": score,
            "score_parts": {"수요": demand_pts, "성장": growth_pts, "정책": policy_pts, "공백": gap_pts},
            "format": mode_label, "format_reason": mode_reason, "level_explicit": lv_total,
            "proposals": proposals, "samples": samples,
        })
    # B2G(입찰) 수요 비중 vs B2C(경쟁사 개인 수강 카탈로그) 공급 비중 - 주제별 채널 전략 신호
    if has_catalog:
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0
        g_med = med([t["share"] for t in topics if t["n"]])
        c_med = med([t["coverage"]["comp_share"] for t in topics])
        for t in topics:
            g_hi, c_hi = t["share"] >= g_med and t["n"] > 0, t["coverage"]["comp_share"] >= c_med
            t["channel"] = ("양쪽 수요 확인 · B2G 제안 + 샘몰 상품" if g_hi and c_hi else
                            "B2G 선점 기회 · 경쟁사 개인과정 적음" if g_hi else
                            "B2C 검증 주제 · 샘몰 상품화 우선" if c_hi else "관망")
    topics.sort(key=lambda t: (-t["score"], -t["n"]))
    return {
        "generated": today.isoformat(),
        "window": {"from": first or start, "to": today.isoformat(), "target_days": window_days,
                   "covered_days": (today - date.fromisoformat(first)).days + 1 if first else 0, "mid": mid},
        "total": total, "untagged": untagged, "excluded_student": excluded_student,
        # 주제를 정하지 않은 원격연수 콘텐츠 개발·임대 공고 = 자사 콘텐츠를 그대로 제안할 수 있는 직접 기회
        "generic_content": {"n": len(generic), "amount": sum(g["a"] for g in generic),
                            "samples": sorted(generic, key=lambda g: g["d"], reverse=True)[:5]},
        "levels": {l: level_totals[l] for l in LEVELS + ["공통"]},
        "modes": {m: mode_totals[m] for m in MODES + ["미표기"]},
        "has_catalog": has_catalog, "self_name": self_name,
        "topics": topics,
    }


def build_from_files(courses_by_company=None, self_name="비바샘연수원", full_live=None):
    wins = []
    p = HERE / "history" / "competitor_wins.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    wins.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return build(load_history(), full_live, wins, courses_by_company, self_name)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="입찰공고 연수 키워드 수집 -> history/training_bids.jsonl 누적")
    f.add_argument("--days", type=int, default=45, help="최근 N일 조회(첫 백필은 365)")
    args = ap.parse_args()
    if args.cmd == "fetch":
        sys.path.insert(0, str(HERE))
        from fetch_g2b_listings import load_config
        cfg = load_config()
        hist = load_history()
        # 누적이 비어 있거나 수집 규칙이 바뀌었으면(예전 규칙이 걸러낸 공고 복구) 12개월 다시 백필
        ver_path = HERE / "history" / "training_bids.rules"
        rules_changed = not ver_path.exists() or ver_path.read_text().strip() != RULES_VERSION
        days = max(args.days, WINDOW_DAYS) if (not hist or rules_changed) else args.days
        new = fetch(cfg, days)
        added = sum(1 for r in new if r["k"] not in hist)
        hist.update({r["k"]: r for r in new})
        kept = save_history(hist)
        ver_path.write_text(RULES_VERSION + "\n")
        print(f"training bids: 최근 {days}일 조회 {len(new)}건, 신규 {added}건, 누적 {kept}건(최근 {KEEP_DAYS}일)")


if __name__ == "__main__":
    main()
