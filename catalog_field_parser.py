#!/usr/bin/env python3
"""
경쟁사 연수과정 카탈로그(competitor_course_catalog_scrape.py)가 모은 title/context
원문 텍스트에서 실제 강좌명·가격·학점(차시)·카테고리를 정규식으로 뽑아낸다.

세 사이트가 카드 텍스트를 완전히 다른 형식으로 이어붙여놓기 때문에(2026-09-05
실측), 사이트별로 별도 정규식을 쓴다. 매칭에 실패하면 원본 title을 그대로 두고
나머지 필드는 None으로 둔다 - 사이트 레이아웃이 바뀌어도 조용히 깨지기만 하고
잘못된 값을 만들어내지는 않게 하기 위함.

- 아이스크림 context 예: "미리보기 상세보기 15차시(1학점) 교수학습 50,000원
  연수·상품SET 신규 2022 개정 교육과정에 딱 맞는 디지털 드로잉 수업 디자인"
  -> 카드의 <a>가 '상세보기' 버튼 자체라 title이 항상 '상세보기'로만 잡힌다.
- 아이스크림 2026-11 개편 후 context 예: "미리보기 상세보기 30차시 할인중 신규
  제이제이의 평생 가는 다이어트 공식 20% 68,000원 85,000원" -> 카테고리 표기가
  사라지고 배지(할인중·신규·교재 등) 뒤에 강좌명, 끝에 [할인율] 판매가 [정가] 순.
  이 형식을 못 읽어 11-09·11-12 수집분 604건이 전부 '상세보기'로 저장됐다.
- 비바샘연수원 title 예: "구글 제미나이를 활용한 실질적인 수업 및 업무 혁신 방법!
  직무/15차시(1학점) 미리보기 상세보기 신규 질문이 답이 되는 제미나이 수업
  솔루션 20% 60,000원 48,000원" -> 앞부분은 홍보 카피(teaser)이고 실제 강좌명은
  '미리보기 상세보기' 뒤, 가격 앞에 온다.
- 티처빌 title은 data-tv-label 속성이라 이미 깨끗하다 - context에서 가격/학점만
  보조로 뽑는다.
"""
import re

_ISCREAM_RE = re.compile(
    r"^(?:미리보기\s*)?(?:상세보기\s*)?"
    r"(?P<credit>\d+차시(?:\(\d+학점\))?)\s*"
    r"(?P<category>\S+)\s*"
    r"(?:(?P<price1>[\d,]+원)\s*(?:(?P<price2>[\d,]+원)\s*)?|(?P<free>무료)\s*)"
    r"(?:할인중\s*)?"
    r"(?:(?:연수.\S*SET|신규|베스트|교재|할인중)\s*)*"
    r"(?P<title>.+)$"
)

# 2026-11 개편 레이아웃(가격이 맨 끝, 카테고리 없음). 배지는 실측된 것만 벗긴다 -
# 모르는 배지가 새로 붙으면 제목 앞에 남을 뿐 제목이 사라지진 않는다.
_ISCREAM_BADGE = r"(?:연수·\S*SET|신규|베스트|교재|할인중|법정연수|Ai튜터|NEW|인기|히트|자격증)"
_ISCREAM_V2_RE = re.compile(
    r"^(?:미리보기\s*)?(?:상세보기\s*)?"
    r"(?P<credit>\d+차시(?:\(\d+학점\))?)\s*"
    r"(?:" + _ISCREAM_BADGE + r"\s*)*"
    r"(?P<title>.+?)\s*"
    r"(?:\d+%\s*)?"
    r"(?:(?P<price1>[\d,]+원)(?:\s*(?P<price2>[\d,]+원))?|(?P<free>무료))\s*$"
)

# 화면 버튼 문구 - 제목으로 저장되면 안 되는 값(수집기 방어 코드와 공용).
INVALID_TITLES = frozenset({"", "상세보기", "미리보기", "신청하기", "수강신청", "연수신청",
                            "강의체험", "더보기", "장바구니", "바로가기"})


def is_valid_title(title):
    t = (title or "").strip()
    return len(t) >= 2 and t not in INVALID_TITLES


def _with_credit_hours(credit):
    """'15차시' -> '15차시(1학점)'. 직무연수 1학점=15시간 기준, 15의 배수만 환산."""
    m = re.fullmatch(r"(\d+)차시", credit or "")
    if m and int(m.group(1)) >= 15 and int(m.group(1)) % 15 == 0:
        return f"{credit}({int(m.group(1)) // 15}학점)"
    return credit


_VIVASAM_RE = re.compile(
    r"^(?P<teaser>.*?)\s*직무/(?P<credit>\d+차시(?:\([^)]*\))?)\s*"
    r"미리보기\s*상세보기\s*"
    r"(?:(?:신규|베스트|샘크리에이티브연수|인기|MD추천|이벤트)\s*)*"
    r"(?P<title>.+?)\s*"
    r"(?:\d+%\s*)?"
    r"(?P<price1>[\d,]+원)(?:\s*(?P<price2>[\d,]+원))?\s*$"
)

_TEACHERVILLE_RE = re.compile(
    r"^\[(?P<format>[^\]]+)\]\s*(?P<category>\S+)\s*.+?"
    r"(?P<price>[\d,]+원)\s*(?:강의체험\s*)?연수신청\s*$"
)


# 가격 없이 소개 문구만 있는 카드(예: 추천 강좌 영역):
# "<소개> 15차시(1학점) 미리보기 상세보기 [신규 ]<강좌명>"
_VIVASAM_NOPRICE_RE = re.compile(r"^.*?(?P<credit>\d+차시\S*)\s+미리보기\s+상세보기\s+(?:신규\s+)?(?P<title>.+?)\s*$")

def _price_int(s):
    if not s:
        return None
    try:
        return int(s.replace(",", "").replace("원", ""))
    except ValueError:
        return None


def parse_fields(site, title, context):
    """반환: dict(title, category, credit, price, orig_price) - 매칭 실패 시
    title=원본, 나머지는 None."""
    out = {"title": title, "category": None, "credit": None, "price": None, "orig_price": None}

    if site == "아이스크림":
        m = _ISCREAM_RE.match(context or "")
        if m:
            out["title"] = m.group("title").strip()
            out["category"] = m.group("category")
            out["credit"] = m.group("credit")
            p1, p2 = _price_int(m.group("price1")), _price_int(m.group("price2"))
            # 교과서 연계 무료 연수는 가격 대신 '무료'로 표기된다(2026-09-27 실측 8건)
            out["price"] = 0 if m.group("free") else (p2 if p2 is not None else p1)
            out["orig_price"] = p1 if p2 is not None else None
            return out
        m = _ISCREAM_V2_RE.match((context or "").strip())
        if m:
            out["title"] = m.group("title").strip()
            out["credit"] = _with_credit_hours(m.group("credit"))
            ps = [x for x in (_price_int(m.group("price1")), _price_int(m.group("price2"))) if x is not None]
            # 개편 후 순서는 '판매가 정가'라 크기로 판정한다(작은 값=판매가).
            out["price"] = 0 if m.group("free") else (min(ps) if ps else None)
            out["orig_price"] = max(ps) if len(ps) == 2 and max(ps) != min(ps) else None
        return out

    if site == "비바샘연수원":
        # title이 아니라 context에서 파싱한다 - scrape_site가 title을 이미 정제된
        # 값으로 덮어쓴 뒤에도(예: 재처리) context는 원본 그대로 남아있어 안전하다.
        m = _VIVASAM_RE.match(context or title or "")
        if m:
            out["title"] = m.group("title").strip()
            out["credit"] = m.group("credit")
            p1, p2 = _price_int(m.group("price1")), _price_int(m.group("price2"))
            out["price"] = p2 if p2 is not None else p1
            out["orig_price"] = p1 if p2 is not None else None
        else:
            m = _VIVASAM_NOPRICE_RE.match(context or title or "")
            if m:
                out["title"] = m.group("title").strip()
                out["credit"] = m.group("credit")
        return out

    if site == "티처빌":
        m = _TEACHERVILLE_RE.match(context or "")
        if m:
            out["category"] = m.group("category")
            out["credit"] = m.group("format")
            out["price"] = _price_int(m.group("price"))
        return out

    return out
